#!/usr/bin/env python3
"""JOE HQ → Hermes, one JSON request on stdin and one JSON response on stdout.

Commands: diagnose; run. Required run fields: home, workspace, message, bot_id,
callback_token. Optional: model, history, session_id, callback_url, context
(roster/apps for the prompt), computer (bool: Joe lent the screen to this bot).
No API-key provider or raw OS/MCP tool is exposed. Launch with the existing
Hermes venv Python and -B. OAuth credentials are read-only and stay in memory.

Tools the model can call (everything else is blocked before dispatch):
  memory                     Hermes native memory.
  joe_hq toolset             files, tasks, scoped connectors, request_action,
                             and message_agent (Hermes Bot Mode tool contract).
  computer_use               Hermes native desktop control (cua-driver), only
                             while Joe has granted the computer to this bot;
                             every input action passes the JOE HQ gate first.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

VOLUME = Path('/Volumes/JOE_HQ')
SOURCE = Path('/Users/m4/.hermes/hermes-agent')
GLOBAL_HOME = Path('/Users/m4/.hermes')
CODEX_URL = 'https://chatgpt.com/backend-api/codex'
DEFAULT_MODEL = 'gpt-5.6-terra'
MAX_INPUT = 2_000_000
BASE_TOOLS = frozenset({'memory', 'save_file', 'list_files', 'task_create', 'drive_list', 'drive_read', 'sheets_read',
                        'gmail_search', 'gmail_read', 'calendar_list', 'instagram_read', 'github_read',
                        'request_action', 'message_agent'})
TOOL_NAMES = set(BASE_TOOLS)
ALLOWED_PORTS = (8787, 8788)  # producción y ensayo, ambos solo en 127.0.0.1
COMPUTER_FREE_ACTIONS = frozenset({'capture', 'list_apps', 'list_windows', 'wait'})
ACTIONS_HELP = ('gmail_send/gmail_draft {para, asunto, cuerpo, cc?, bcc?}; '
                'calendar_create {titulo, inicio, fin (AAAA-MM-DDTHH:MM), zona?, descripcion?, lugar?, invitados?}; '
                'instagram_publish {imagen_url (https pública), texto}; drive_delete {file_id}; '
                'sheets_append {spreadsheet_id, rango, filas}; github_issue {owner, repo, titulo, cuerpo?}')


class BridgeError(Exception):
    pass


def bounded_string(value, name, maximum=20_000, *, optional=False):
    if optional and value in (None, ''):
        return ''
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise BridgeError(f'Campo {name} inválido.')
    return value


def local_path(value, name, parent=None):
    raw = bounded_string(value, name, 1024)
    p = Path(raw)
    if not p.is_absolute():
        raise BridgeError(f'{name} debe ser una ruta absoluta.')
    p = p.resolve()
    root = (parent or VOLUME).resolve()
    if p == root or root not in p.parents:
        raise BridgeError(f'{name} debe estar dentro de {root}.')
    return p


def prepare(request):
    if not VOLUME.is_mount():
        raise BridgeError('El volumen /Volumes/JOE_HQ no está montado. Conéctalo y vuelve a iniciar.')
    home = local_path(request.get('home'), 'home')
    workspace = local_path(request.get('workspace'), 'workspace')
    if home == GLOBAL_HOME or GLOBAL_HOME in home.parents:
        raise BridgeError('No se permite usar el Hermes global como memoria.')
    for p in (home, workspace, home / 'memories', home / 'cache', home / 'logs'):
        p.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.environ['HERMES_HOME'] = str(home)
    os.environ['HERMES_DISABLE_LAZY_INSTALLS'] = '1'
    os.environ['HERMES_YOLO_MODE'] = '0'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['TMPDIR'] = str(home / 'cache')
    os.environ['TMP'] = str(home / 'cache')
    os.environ['TEMP'] = str(home / 'cache')
    os.environ['XDG_CACHE_HOME'] = str(home / 'cache')
    sys.dont_write_bytecode = True
    # Never inherit a paid provider or ambient forced Hermes configuration.
    for key in list(os.environ):
        if key.endswith('_API_KEY') or key in ('HERMES_CONFIG', 'HERMES_ENV', 'HERMES_PROFILE'):
            os.environ.pop(key, None)
    sys.path.insert(0, str(SOURCE))
    return home, workspace


def configuration(home, model, computer=False):
    """Write only our own allowlisted configuration; never merge global config."""
    import yaml
    toolsets = ['memory', 'joe_hq'] + (['computer_use'] if computer else [])
    disabled = ['terminal', 'file', 'browser', 'code_execution', 'delegation', 'cronjob', 'skills',
                'connections', 'web', 'tts', 'stt'] + ([] if computer else ['computer_use'])
    cfg = {
        'model': {'default': model, 'provider': 'openai-codex', 'base_url': CODEX_URL, 'api_mode': 'codex_responses'},
        'fallback_providers': [], 'fallback_model': {},
        'providers': {'openai-codex': {'request_timeout_seconds': 60, 'stale_timeout_seconds': 90}},
        'toolsets': toolsets,
        'platform_toolsets': {'cli': toolsets},
        'agent': {'max_turns': 40 if computer else 14, 'environment_probe': False, 'coding_context': False,
                  'bot_mode_protocol': False, 'verify_on_stop': False,
                  'api_max_retries': 1, 'disabled_toolsets': disabled},
        'memory': {'memory_enabled': True, 'user_profile_enabled': True},
        'plugins': {'enabled': []}, 'mcp_servers': {},
        'tools': {'tool_search': {'enabled': False}},
        'skills': {'external_dirs': [], 'inline_shell': False},
        'security': {'allow_lazy_installs': False},
    }
    path = home / 'config.yaml'
    # This home is owned by JOE HQ; model changes preserve SOUL and memory files.
    temp = home / 'config.joe-hq.tmp'
    temp.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def read_credentials():
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.auth_codex import resolve_codex_runtime_credentials
    scope = set_hermes_home_override(GLOBAL_HOME)
    try:
        result = resolve_codex_runtime_credentials(read_only=True)
        token = result.get('api_key')
        if not isinstance(token, str) or not token:
            raise BridgeError('Hermes no tiene una sesión Codex disponible.')
        return token
    except BridgeError:
        raise
    except Exception:
        raise BridgeError('No fue posible leer la sesión Codex existente sin modificar Hermes.') from None
    finally:
        reset_hermes_home_override(scope)


def schema(name, description, properties, required):
    return {'name': name, 'description': description,
            'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}


def tool_definitions():
    text = {'type': 'string'}
    return [
        schema('save_file', 'Guarda texto en la biblioteca de este bot. Solo rutas relativas; nunca elimina archivos.',
               {'path': text, 'content': text}, ['path', 'content']),
        schema('list_files', 'Lista únicamente la biblioteca aislada de este bot.', {}, []),
        schema('task_create', 'Crea una tarea local para este bot.', {'title': text, 'description': text}, ['title']),
        schema('drive_list', 'Lista archivos de la carpeta Drive de TU negocio (sin folder_id: carpetas raíz). No acepta carpetas de otros negocios.',
               {'folder_id': text}, []),
        schema('drive_read', 'Lee como texto un Google Doc, hoja (CSV) o archivo de texto dentro de la carpeta Drive de tu negocio.',
               {'file_id': text}, ['file_id']),
        schema('sheets_read', 'Lee una hoja de cálculo de tu negocio. Sin rango devuelve los nombres de pestañas; con rango (ej. "Hoja 1!A1:F40") devuelve valores.',
               {'spreadsheet_id': text, 'range': text}, ['spreadsheet_id']),
        schema('gmail_search', 'Busca correos en la cuenta Gmail asignada a tu negocio (sintaxis de búsqueda de Gmail). Solo lectura.',
               {'query': text, 'max_results': {'type': 'integer'}}, []),
        schema('gmail_read', 'Lee un correo por su id (obtenido con gmail_search). Solo lectura.', {'message_id': text}, ['message_id']),
        schema('calendar_list', 'Lista eventos del calendario asignado a tu negocio. Fechas RFC3339 (ej. 2026-11-16T09:00:00-06:00).',
               {'time_min': text, 'time_max': text, 'query': text}, []),
        schema('instagram_read', 'Lee el perfil o las últimas publicaciones de la cuenta de Instagram asignada a tu negocio.',
               {'what': {'type': 'string', 'enum': ['perfil', 'publicaciones']}}, []),
        schema('github_read', 'Lista repositorios o issues abiertos de la cuenta GitHub asignada a tu negocio.',
               {'what': {'type': 'string', 'enum': ['repos', 'issues']}, 'owner': text, 'repo': text}, []),
        schema('request_action', 'Prepara una acción externa para que Joe la apruebe con un botón. NO la ejecuta. '
               'Es la ÚNICA vía para enviar correos, crear eventos, publicar, borrar o escribir fuera. Detalles por acción: ' + ACTIONS_HELP,
               {'action': {'type': 'string', 'enum': ['gmail_send', 'gmail_draft', 'calendar_create', 'instagram_publish',
                                                     'drive_delete', 'sheets_append', 'github_issue']},
                'details': {'type': 'object'}}, ['action', 'details']),
    ]


def message_agent_definition():
    """Contrato nativo de Hermes Bot Mode (tools/bot_mode_dm.py), limitado al roster del negocio."""
    from tools.bot_mode_dm import message_agent_tool_schema
    native = message_agent_tool_schema()['function']
    props = {k: v for k, v in native['parameters']['properties'].items()
             if k in ('target', 'message', 'constraints', 'expecting', 'expects_reply')}
    props['target'] = {'type': 'string', 'description': "Handle de UN compañero de tu mismo negocio (ej. 'cotizaciones'). Ver roster en tus instrucciones."}
    return {'name': native['name'],
            'description': ('Send a message to ANOTHER agent (teammate) of YOUR business. FIRE-AND-FORGET: it validates the target '
                            'against the roster, delivers into that agent\'s chat with your attribution prefixed, and returns a '
                            'dispatch ack at once (status queued + delivery_id). It never returns the reply: finish your turn; '
                            'their reply wakes you later as a new message. COMPOSE the message yourself (lead with the point and '
                            'the concrete ask). Agents of other businesses do not exist for you.'),
            'parameters': {'type': 'object', 'properties': props, 'required': ['target', 'message']}}


def register_callbacks(request):
    url = request.get('callback_url') or 'http://127.0.0.1:8787/api/engine/tool'
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port not in ALLOWED_PORTS
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.startswith('/api/')):
        raise BridgeError('Callback inválido; solo se permite el servidor local JOE HQ en 127.0.0.1.')
    token = bounded_string(request.get('callback_token'), 'callback_token', 512)
    bot_id = bounded_string(request.get('bot_id'), 'bot_id', 64)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', bot_id):
        raise BridgeError('Identidad del bot inválida.')
    from tools.registry import registry
    from toolsets import create_custom_toolset
    definitions = tool_definitions() + [message_agent_definition()]
    create_custom_toolset('joe_hq', 'Herramientas aisladas de JOE HQ',
                          tools=[definition['name'] for definition in definitions])
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def callback(name, arguments, timeout=150):
        if not isinstance(arguments, dict):
            return {'ok': False, 'error': 'Argumentos inválidos.'}
        encoded = json.dumps({'bot_id': bot_id, 'tool': name, 'arguments': arguments}, ensure_ascii=False).encode()
        if len(encoded) > 1_000_000:
            return {'ok': False, 'error': 'La solicitud excede el límite permitido.'}
        req = urllib.request.Request(url, data=encoded, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method='POST')
        try:
            with opener.open(req, timeout=timeout) as response:
                body = response.read(1_000_001)
                if len(body) > 1_000_000:
                    return {'ok': False, 'error': 'La respuesta excede el límite permitido.'}
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            try:
                return {'ok': False, 'error': json.loads(exc.read(20000)).get('error', 'Herramienta rechazada.')}
            except Exception:
                return {'ok': False, 'error': 'El servidor local rechazó esta herramienta.'}
        except Exception:
            return {'ok': False, 'error': 'El servidor local no pudo completar esta herramienta.'}

    def message_agent(arguments):
        # Sobre nativo de Hermes: mensaje + Constraints + Reply needed.
        from tools.bot_mode_dm import _envelope, _wants_reply, MESSAGE_MAX_CHARS
        body = _envelope(arguments.get('message'), arguments.get('constraints'), arguments.get('expecting'))
        if not body.strip():
            return {'ok': False, 'error': 'message is required — compose what you want to say to that agent.'}
        if len(body) > MESSAGE_MAX_CHARS:
            return {'ok': False, 'error': f'message too long ({len(body)} chars > {MESSAGE_MAX_CHARS}).'}
        return callback('message_agent', {'target': str(arguments.get('target') or ''), 'body': body,
                                          'expects_reply': _wants_reply(arguments.get('expects_reply', True))})

    def as_text(result):
        # Contrato de Hermes: el resultado de una herramienta es SIEMPRE texto (JSON).
        return json.dumps(result, ensure_ascii=False, default=str)

    # Hermes despacha message_agent por su vía nativa en línea (agent/inline_tool_executors.py →
    # tools.bot_mode_dm.message_agent_tool), no por el registro. El transporte nativo usa perfiles
    # globales de ~/.hermes y un solo roster para todos; aquí se sustituye SOLO el transporte por la
    # entrega de JOE HQ, que valida el roster del negocio en el servidor. Contrato y sobre: los de Hermes.
    import tools.bot_mode_dm as native_dm

    def native_message_agent(target='', message='', task_id=None, agent=None, expects_reply=True,
                             cancel='', constraints='', expecting=''):
        if str(cancel or '').strip():
            return as_text({'ok': False, 'error': 'cancel is not supported here; tell Joe instead.'})
        return as_text(message_agent({'target': target, 'message': message, 'constraints': constraints,
                                      'expecting': expecting, 'expects_reply': expects_reply}))
    native_dm.message_agent_tool = native_message_agent

    for definition in definitions:
        name = definition['name']
        handler = ((lambda args, **kw: as_text(message_agent(args))) if name == 'message_agent'
                   else (lambda args, _name=name, **kw: as_text(callback(_name, args))))
        registry.register(name=name, toolset='joe_hq', schema=definition, handler=handler,
                          check_fn=lambda: True, override=True)
    return callback


def enable_computer(callback):
    """Hermes native computer_use behind the JOE HQ gate (Joe's grant, step approvals, take-over)."""
    import tools.computer_use_tool  # noqa: F401  (registra la herramienta nativa)
    from tools.computer_use import tool as cu
    from tools.computer_use.schema import COMPUTER_USE_SCHEMA
    from tools.registry import registry
    native = cu.handle_computer_use
    # La aprobación la decide el servidor JOE HQ (permiso de Joe); la capa interna de Hermes queda delegada.
    cu._request_approval = lambda action, args: None

    def summarize(action, args):
        try:
            return str(cu._summarize_action(action, args))[:300]
        except Exception:
            return action

    def guarded(args, **kw):
        action = str((args or {}).get('action') or '').strip().lower()
        summary = summarize(action, args or {})
        verdict = callback('computer_gate', {'action': action, 'summary': summary,
                                             'free': action in COMPUTER_FREE_ACTIONS}, timeout=200)
        allowed = isinstance(verdict, dict) and verdict.get('ok') and (verdict.get('result') or {}).get('allow')
        if not allowed:
            reason = ((verdict.get('result') or {}).get('reason') if isinstance(verdict, dict) and verdict.get('ok')
                      else (verdict or {}).get('error')) or 'Joe no autorizó esta acción.'
            return json.dumps({'ok': False, 'action': action, 'code': 'joe_hq_denied', 'error': reason}, ensure_ascii=False)
        result = native(args, **kw)
        failed = isinstance(result, str) and result.lstrip().startswith('{"error"')
        callback('computer_event', {'action': action, 'summary': summary, 'ok': not failed}, timeout=10)
        return result

    registry.register(name='computer_use', toolset='computer_use', schema=COMPUTER_USE_SCHEMA,
                      handler=guarded, check_fn=cu.check_computer_use_requirements, override=True)
    TOOL_NAMES.add('computer_use')


def install_dispatch_gate():
    """Deny hallucinated tool calls too, before Hermes executes any handler."""
    import agent.tool_executor as executor
    original = executor._dispatch_authorized_once

    def guarded(agent, state, ref, **kwargs):
        if ref.name not in TOOL_NAMES:
            kwargs['scope_block'] = 'Herramienta bloqueada por el aislamiento de JOE HQ.'
        return original(agent, state, ref, **kwargs)
    executor._dispatch_authorized_once = guarded


def build_instruction(context, computer):
    context = context if isinstance(context, dict) else {}
    lines = ['Eres un bot persistente de JOE HQ. Responde siempre en español, breve y claro.',
             'Usa solo tu memoria, tu biblioteca y las apps de TU negocio. Nunca pidas ni leas datos de otro negocio.',
             'Jamás envíes correos, crees eventos, publiques ni borres nada directamente: request_action solo PREPARA '
             'la acción y Joe la aprueba con un botón. No afirmes que algo ocurrió sin confirmación de herramienta.']
    now = context.get('now')
    if isinstance(now, str) and len(now) < 80:
        lines.append('Fecha y hora local: ' + now + '.')
    apps = [a for a in context.get('apps', []) if isinstance(a, str)][:12]
    lines.append('Apps disponibles para tu negocio: ' + (', '.join(apps) if apps else 'solo Drive de tu negocio') + '.')
    team = [t for t in context.get('team', []) if isinstance(t, dict)][:6]
    if team:
        roster = '; '.join(f"@{t.get('handle')} ({t.get('name')})" for t in team)
        lines.append('Compañeros de tu negocio (roster de message_agent): ' + roster + '. Úsalo cuando otro bot deba hacer '
                     'o saber algo; su respuesta te llegará después como mensaje nuevo.')
    else:
        lines.append('No tienes compañeros en tu negocio todavía; message_agent no tiene destinatarios.')
    peer = context.get('peer')
    if isinstance(peer, dict) and peer.get('mode') == 'incoming':
        lines.append('ESTE TURNO es un mensaje de un compañero bot, no de Joe. Responde directo a lo que pide: tu respuesta '
                     'final se le entrega automáticamente. No uses message_agent para contestarle.')
    if isinstance(peer, dict) and peer.get('mode') == 'reply':
        lines.append('ESTE TURNO es la respuesta de un compañero a un mensaje tuyo. Continúa la tarea original y resume '
                     'el resultado para Joe.')
    if computer:
        lines.append('Joe te prestó la computadora (computer_use). Empieza con capture para ver la pantalla. Trabaja solo en '
                     'la tarea pedida. PROHIBIDO con la computadora: pulsar Enviar/Publicar/Eliminar/Pagar/Comprar, aceptar '
                     'diálogos de esas acciones, abrir datos de otro negocio o escribir contraseñas. Si la tarea requiere uno '
                     'de esos pasos, déjalo listo y pide a Joe que lo haga o usa request_action. Si una acción es denegada, '
                     'no insistas: explica qué necesitas.')
    return ' '.join(lines)


def clean_history(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 200:
        raise BridgeError('Historial inválido o demasiado largo.')
    history = []
    for row in value:
        if not isinstance(row, dict) or row.get('role') not in ('user', 'assistant'):
            continue
        content = row.get('content')
        if isinstance(content, str) and content and len(content) <= 100_000:
            history.append({'role': row['role'], 'content': content})
    return history


def codex_dns_available():
    try:
        socket.getaddrinfo('chatgpt.com', 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False


def run(request):
    home, workspace = prepare(request)
    command = request.get('command', 'run')
    model = request.get('model') or DEFAULT_MODEL
    if not isinstance(model, str) or not re.fullmatch(r'gpt-[a-zA-Z0-9.\-]{1,64}', model):
        raise BridgeError('Solo se permiten modelos GPT mediante Hermes openai-codex.')
    if not SOURCE.is_dir():
        raise BridgeError('No se encontró el código de Hermes instalado.')
    if command == 'diagnose':
        diagnosis = {'source_present': True, 'home': str(home), 'workspace': str(workspace),
                     'provider': 'openai-codex', 'model': model, 'paid_api': False,
                     'native_memory': str(home / 'memories'),
                     'codex_dns_available': codex_dns_available(),
                     'dependencies': {name: bool(importlib.util.find_spec(name)) for name in ('yaml', 'openai', 'mcp')},
                     'tools': sorted(TOOL_NAMES)}
        try:
            read_credentials()
            diagnosis['codex_credentials_readable'] = True
        except BridgeError:
            diagnosis['codex_credentials_readable'] = False
        return {'ok': bool(diagnosis['codex_credentials_readable']) and all(diagnosis['dependencies'].values()),
                'response': '', 'history': [], 'error': None, 'diagnosis': diagnosis}
    if command != 'run':
        raise BridgeError('Comando de Hermes desconocido.')
    message = bounded_string(request.get('message'), 'message')
    history = clean_history(request.get('history'))
    session_id = request.get('session_id')
    if session_id is not None and (not isinstance(session_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', session_id)):
        raise BridgeError('Sesión inválida.')
    if not codex_dns_available():
        raise BridgeError('Esta Mac no puede resolver chatgpt.com. Revisa la conexión a internet.')
    computer = bool(request.get('computer'))
    configuration(home, model, computer)
    oauth_token = read_credentials()
    callback = register_callbacks(request)
    if computer:
        enable_computer(callback)
    install_dispatch_gate()
    from run_agent import AIAgent
    toolsets = ['memory', 'joe_hq'] + (['computer_use'] if computer else [])
    agent = AIAgent(
        provider='openai-codex', requested_provider='openai-codex', model=model,
        api_mode='codex_responses', base_url=CODEX_URL, api_key=oauth_token,
        max_iterations=40 if computer else 14, max_tokens=4000, enabled_toolsets=toolsets,
        fallback_model={}, load_soul_identity=True, skip_background_review=True,
        skip_context_files=True, quiet_mode=True, save_trajectories=False,
        verbose_logging=False, session_id=session_id, cwd=str(workspace),
        run_budget_seconds=840 if computer else 270,
    )
    agent._bot_mode_protocol = False
    agent.tools = [tool for tool in agent.tools if tool.get('function', {}).get('name') in TOOL_NAMES]
    agent.valid_tool_names = set(TOOL_NAMES)
    instruction = build_instruction(request.get('context'), computer)
    try:
        result = agent.run_conversation(message, system_message=instruction, conversation_history=history)
        if result.get('error') or result.get('failed') or result.get('completed') is False:
            return {'ok': False, 'response': '', 'history': history,
                    'error': 'Hermes no completó la conversación. Verifica conexión y disponibilidad de la sesión ChatGPT Pro.'}
        answer = result.get('final_response')
        if not isinstance(answer, str) or not answer.strip():
            return {'ok': False, 'response': '', 'history': history, 'error': 'Hermes devolvió una respuesta vacía.'}
        return {'ok': True, 'response': answer, 'history': clean_history((result.get('messages') or [])[-200:]), 'error': None}
    finally:
        with contextlib.suppress(Exception):
            agent.close()


def main():
    logging.disable(logging.CRITICAL)
    request = {}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise BridgeError('Solicitud demasiado grande.')
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise BridgeError('La solicitud debe ser un objeto JSON.')
        # Hermes has console output intended for its CLI. Keep the protocol clean,
        # suppressing library errors so OAuth data never reaches process logs.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = run(request)
    except BridgeError as exc:
        result = {'ok': False, 'response': '', 'history': [], 'error': str(exc)}
    except Exception as exc:
        result = {'ok': False, 'response': '', 'history': [],
                  'error': f'No se pudo iniciar el motor Hermes ({type(exc).__name__}).'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
