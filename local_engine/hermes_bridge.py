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

if __package__:
    from .computer_payload import PayloadError, freeze_payload, approved_arguments
else:
    from computer_payload import PayloadError, freeze_payload, approved_arguments

VOLUME = Path('/Volumes/JOE_HQ')
SOURCE = Path('/Users/m4/.hermes/hermes-agent')
GLOBAL_HOME = Path('/Users/m4/.hermes')
CODEX_URL = 'https://chatgpt.com/backend-api/codex'
DEFAULT_MODEL = 'gpt-5.6-terra'
MAX_INPUT = 2_000_000
BASE_TOOLS = frozenset({'memory', 'save_file', 'list_files', 'task_create', 'task_complete', 'assign_task',
                        'drive_list', 'drive_read', 'sheets_read',
                        'gmail_search', 'gmail_read', 'calendar_list', 'instagram_read', 'github_read',
                        'request_action', 'message_agent'})
# Políticas de turno que fija el SERVIDOR (el modelo no las puede cambiar):
#   clean       mensaje entre Guardián y Casa Kiraz: sin memoria, sin historial, sin archivos ni apps.
#   no_persist  Holding atendiendo a un negocio hijo: no escribe memoria ni archivos.
POLICY_TOOLS = {'clean': frozenset({'task_create', 'task_complete'}),
                'no_persist': BASE_TOOLS - {'memory', 'save_file'}}
SEEN = {'elements': {}, 'app': '', 'window': ''}   # lo último que computer_use capturó en pantalla
TOOL_NAMES = set(BASE_TOOLS)
ALLOWED_PORTS = (8787, 8788)  # producción y ensayo, ambos solo en 127.0.0.1
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


def configuration(home, model, computer=False, memory=True):
    """Write only our own allowlisted configuration; never merge global config."""
    import yaml
    toolsets = (['memory'] if memory else []) + ['joe_hq'] + (['computer_use'] if computer else [])
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
        'memory': {'memory_enabled': bool(memory), 'user_profile_enabled': bool(memory)},
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
        schema('task_complete', 'Marca como completa una tarea de TU lista (usa el task_id que recibiste).', {'task_id': text}, ['task_id']),
        schema('assign_task', 'Asigna una tarea a OTRO bot: aparece en su lista de tareas y se le avisa para que la trabaje. '
               'Su respuesta te llega después como mensaje nuevo. Guardián y Casa Kiraz están bloqueados como destinos mutuos para mensajes y tareas, sin excepción ni aprobación.',
               {'target': text, 'title': text, 'details': text}, ['target', 'title']),
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
    props['target'] = {'type': 'string', 'description': "Handle de UN bot del roster de tus instrucciones (ej. 'holding')."}
    return {'name': native['name'],
            'description': ('Send a message to ANOTHER agent on your roster. FIRE-AND-FORGET: it validates the target '
                            'against the roster, delivers into that agent\'s chat with your attribution prefixed, and returns a '
                            'dispatch ack at once (status queued + delivery_id). It never returns the reply: finish your turn; '
                            'their reply wakes you later as a new message. COMPOSE the message yourself (lead with the point and '
                            'the concrete ask). To another business send ONLY what the request needs: never paste memory, files or '
                            'client data. Guardián and Casa Kiraz must never message or assign tasks to each other. The server rejects '
                            'that route before creating an approval, message, or task. Holding may communicate with either one, but '
                            'must not forward content between them within a conversation chain.'),
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
                          tools=[definition['name'] for definition in definitions] + ['open_app'])
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


def track_captures():
    """Guarda qué elementos vio el bot en su última captura, para describir cada paso a Joe."""
    from tools.computer_use.cua_backend import CuaDriverBackend
    if getattr(CuaDriverBackend, '_joe_hq_tracked', False):
        return
    original = CuaDriverBackend.capture

    def capture(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        try:
            SEEN['elements'] = {int(e.index): {'role': str(e.role or '')[:40], 'label': ' '.join(str(e.label or '').split())[:120]}
                                for e in (result.elements or [])}
            SEEN['app'] = str(result.app or '')[:80]
            SEEN['window'] = str(result.window_title or '')[:120]
        except Exception:
            SEEN['elements'] = {}
        return result
    CuaDriverBackend.capture = capture
    CuaDriverBackend._joe_hq_tracked = True


def describe_step(action, args):
    """Resumen del paso y carga ÍNTEGRA desligada del original, ligada a su huella."""
    payload, digest = freeze_payload('computer_use', args)
    args = payload['arguments']
    if str(args.get('action') or '').strip().lower() != action:
        raise PayloadError('La acción no coincide con los argumentos del paso.')
    def element(value):
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        info = SEEN['elements'].get(index) or {}
        return {'index': index, 'role': info.get('role', ''), 'label': info.get('label', ''), 'known': bool(info)}

    def point(value):
        try:
            return [int(value[0]), int(value[1])] if value and value[0] is not None else None
        except (TypeError, ValueError, IndexError):
            return None
    step = {'action': action, 'app': str(args.get('app') or SEEN['app'])[:80], 'window': SEEN['window'],
            'element': element(args.get('element')) if args.get('element') is not None else None,
            'coordinate': point(args.get('coordinate')),
            'modifiers': [str(m)[:12] for m in (args.get('modifiers') or [])][:6],
            'foreground': args.get('delivery_mode') == 'foreground' or bool(args.get('bring_to_front')) or bool(args.get('raise_window'))}
    if action == 'type':
        step['text'] = str(args.get('text') or '')
    if action == 'key':
        step['keys'] = str(args.get('keys') or '')
    if action == 'set_value':
        step['value'] = str(args.get('value') or '')
    if action == 'drag':
        step['from'] = element(args.get('from_element')) if args.get('from_element') is not None else point(args.get('from_coordinate'))
        step['to'] = element(args.get('to_element')) if args.get('to_element') is not None else point(args.get('to_coordinate'))
    if action == 'scroll':
        step['direction'] = str(args.get('direction') or '')[:8]
    if action == 'click' and str(args.get('button') or 'left') != 'left':
        step['button'] = str(args.get('button'))[:8]
    step['payload'] = payload
    step['digest'] = digest
    return step


def guarded_computer_handler(native, callback):
    """Crea un handler comprobable sin cargar ni accionar la computadora real."""
    def guarded(args, **kw):
        action = str(args.get('action') or '').strip().lower() if isinstance(args, dict) else ''
        try:
            step = describe_step(action, args)
            verdict = callback('computer_gate', step, timeout=200)
            gate_result = verdict.get('result') if isinstance(verdict, dict) else None
            if (not isinstance(verdict, dict) or verdict.get('ok') is not True
                    or not isinstance(gate_result, dict) or gate_result.get('allow') is not True):
                reason = ((gate_result or {}).get('reason') if isinstance(gate_result, dict) else None)
                if not reason and isinstance(verdict, dict):
                    reason = verdict.get('error')
                return json.dumps({'ok': False, 'action': action, 'code': 'joe_hq_denied',
                                   'error': reason if isinstance(reason, str) else 'Joe no autorizó esta acción.'}, ensure_ascii=False)
            exact_args = approved_arguments(step['payload'], step['digest'], verdict)
        except PayloadError as exc:
            return json.dumps({'ok': False, 'action': action, 'code': 'joe_hq_denied',
                               'error': str(exc)}, ensure_ascii=False)
        except Exception:
            return json.dumps({'ok': False, 'action': action, 'code': 'joe_hq_denied',
                               'error': 'No se pudo verificar la autorización exacta del paso.'}, ensure_ascii=False)
        try:
            # Solo se ejecuta la copia cuyos bytes JSON vio y aprobó el servidor.
            result = native(exact_args, **kw)
        except Exception:
            result = json.dumps({'ok': False, 'error': 'El controlador no completó el paso autorizado.'}, ensure_ascii=False)
        failed = False
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                failed = isinstance(parsed, dict) and (bool(parsed.get('error')) or parsed.get('ok') is False)
            except (ValueError, TypeError):
                pass
        elif isinstance(result, dict):
            failed = bool(result.get('error')) or result.get('ok') is False
        # El registro no decide ni repite la acción, aunque falle el callback.
        with contextlib.suppress(Exception):
            callback('computer_event', {**step, 'ok': not failed}, timeout=10)
        return result
    return guarded


def enable_computer(callback):
    """Hermes native computer_use behind the JOE HQ gate (Joe's grant, view/step modes, take-over)."""
    import tools.computer_use_tool  # noqa: F401  (registra la herramienta nativa)
    from tools.computer_use import tool as cu
    from tools.computer_use.schema import COMPUTER_USE_SCHEMA
    from tools.registry import registry
    native = cu.handle_computer_use
    track_captures()
    # La aprobación la decide el servidor JOE HQ (permiso de Joe); la capa interna de Hermes queda delegada.
    cu._request_approval = lambda action, args: None

    guarded = guarded_computer_handler(native, callback)

    registry.register(name='computer_use', toolset='computer_use', schema=COMPUTER_USE_SCHEMA,
                      handler=guarded, check_fn=cu.check_computer_use_requirements, override=True)
    TOOL_NAMES.add('computer_use')

    # cua-driver no lanza apps cerradas (y Spotlight no recibe teclas en segundo plano):
    # abrir una app instalada es una acción aparte, con la misma compuerta de Joe.
    open_app = schema('open_app', 'Abre (o trae al frente) una app instalada en esta Mac por su nombre, p. ej. "Calculator", '
                      '"TextEdit", "Google Chrome". Úsala antes de computer_use cuando la app no está abierta.',
                      {'name': {'type': 'string'}}, ['name'])
    registry.register(name='open_app', toolset='joe_hq', schema=open_app, check_fn=lambda: True, override=True,
                      handler=lambda args, **kw: json.dumps(callback('open_app', args or {}, timeout=200), ensure_ascii=False))
    TOOL_NAMES.add('open_app')


def install_dispatch_gate():
    """Deny hallucinated tool calls too, before Hermes executes any handler."""
    import agent.tool_executor as executor
    original = executor._dispatch_authorized_once

    def guarded(agent, state, ref, **kwargs):
        if ref.name not in TOOL_NAMES:
            kwargs['scope_block'] = 'Herramienta bloqueada por el aislamiento de JOE HQ.'
        return original(agent, state, ref, **kwargs)
    executor._dispatch_authorized_once = guarded


def build_instruction(context, computer, policy=None):
    context = context if isinstance(context, dict) else {}
    lines = ['Eres un bot persistente de JOE HQ. Responde siempre en español, breve y claro.',
             'Usa solo tu memoria, tu biblioteca y las apps de TU negocio. Nunca pidas ni leas datos de otro negocio.',
             'Jamás envíes correos, crees eventos, publiques ni borres nada directamente: request_action solo PREPARA '
             'la acción y Joe la aprueba con un botón. No afirmes que algo ocurrió sin confirmación de herramienta.']
    now = context.get('now')
    if isinstance(now, str) and len(now) < 80:
        lines.append('Fecha y hora local: ' + now + '.')
    peer = context.get('peer') if isinstance(context.get('peer'), dict) else {}
    if policy == 'clean':
        lines.append('TURNO EN SALA LIMPIA: este mensaje viene de un bot de OTRO negocio hermano. En este turno no tienes '
                     'memoria, historial, archivos ni apps, y está prohibido revelar cualquier dato de tu negocio. Solo puedes: '
                     'leer el mensaje, crear una tarea para ti (task_create), cerrar una tarea (task_complete) y contestar. '
                     'Si te piden información de tu negocio, responde que eso lo decide Joe. Tu respuesta final se entrega sola.')
        return ' '.join(lines)
    apps = [a for a in context.get('apps', []) if isinstance(a, str)][:12]
    lines.append('Apps disponibles para tu negocio: ' + (', '.join(apps) if apps else 'solo Drive de tu negocio') + '.')
    team = [t for t in context.get('team', []) if isinstance(t, dict)][:6]
    if team:
        kinds = {'same': 'tu negocio', 'parent': 'otro negocio', 'sibling': 'negocio hermano: Joe aprueba cada mensaje'}
        roster = '; '.join(f"@{t.get('handle')} ({t.get('name')}, {kinds.get(t.get('relation'), 'otro negocio')})" for t in team)
        lines.append('Roster de message_agent y assign_task: ' + roster + '. Úsalos cuando otro bot deba hacer o saber algo; su '
                     'respuesta te llega después como mensaje nuevo. A un bot de otro negocio dile solo lo necesario para la '
                     'petición: jamás pegues tu memoria, tus archivos ni datos de clientes.')
    else:
        lines.append('No hay otros bots todavía; message_agent no tiene destinatarios.')
    if peer.get('mode') == 'incoming':
        lines.append('ESTE TURNO es un mensaje de otro bot, no de Joe. Responde directo a lo que pide: tu respuesta '
                     'final se le entrega automáticamente. No uses message_agent para contestarle.')
        if peer.get('task_id'):
            lines.append('Trae una tarea asignada (task_id ' + str(peer['task_id'])[:20] + '): cuando la termines llama task_complete.')
    if peer.get('mode') == 'reply':
        lines.append('ESTE TURNO es la respuesta de otro bot a un mensaje tuyo. Continúa la tarea original y resume '
                     'el resultado para Joe.')
    if policy == 'no_persist':
        lines.append('Este turno trae información de un negocio hijo: no puedes guardarla en memoria ni en archivos, y no '
                     'puedes reenviarla al otro negocio.')
    if computer:
        mode = context.get('computer_mode')
        if mode == 'view':
            lines.append('Joe te prestó la computadora en modo SOLO VER: puedes mirar (capture), desplazarte (scroll con element=), '
                         'cambiar a una app abierta (focus_app, open_app). NO puedes hacer clic, teclear ni escribir: el sistema lo '
                         'bloquea. Si la tarea necesita un clic o texto, describe a Joe el paso exacto y pídele el modo paso a paso.')
        else:
            lines.append('Joe te prestó la computadora en modo PASO A PASO: cada clic, tecla o texto lo aprueba Joe uno por uno '
                         'viendo exactamente qué elemento tocarás. Usa capture(app=...) y actúa por índice de elemento (element=), '
                         'no por coordenadas. Si la app no está abierta usa open_app. Si Joe niega un paso, no insistas: explica qué necesitas.')
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
    policy = request.get('policy') if request.get('policy') in POLICY_TOOLS else None
    clean = policy == 'clean'
    computer = bool(request.get('computer')) and not policy   # nunca hay computadora en turnos entre negocios
    configuration(home, model, computer, memory=not clean)
    oauth_token = read_credentials()
    callback = register_callbacks(request)
    if computer:
        enable_computer(callback)
    if policy:
        TOOL_NAMES.intersection_update(POLICY_TOOLS[policy])
    install_dispatch_gate()
    from run_agent import AIAgent
    toolsets = ([] if clean else ['memory']) + ['joe_hq'] + (['computer_use'] if computer else [])
    if clean:
        history = []   # sala limpia: el otro negocio no puede preguntar por conversaciones anteriores
    agent = AIAgent(
        provider='openai-codex', requested_provider='openai-codex', model=model,
        api_mode='codex_responses', base_url=CODEX_URL, api_key=oauth_token,
        max_iterations=40 if computer else 14, max_tokens=4000, enabled_toolsets=toolsets,
        fallback_model={}, load_soul_identity=True, skip_background_review=True, skip_memory=clean,
        skip_context_files=True, quiet_mode=True, save_trajectories=False,
        verbose_logging=False, session_id=session_id, cwd=str(workspace),
        run_budget_seconds=840 if computer else 270,
    )
    agent._bot_mode_protocol = False
    agent.tools = [tool for tool in agent.tools if tool.get('function', {}).get('name') in TOOL_NAMES]
    agent.valid_tool_names = set(TOOL_NAMES)
    instruction = build_instruction(request.get('context'), computer, policy)
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
    # El canal de protocolo es el stdout ORIGINAL. Todo lo demás (Hermes, cua-driver y otros
    # procesos hijos) escribe a /dev/null con descriptores reales: los hijos necesitan fileno()
    # y nada de lo que impriman debe mezclarse con la respuesta JSON ni llegar a logs.
    protocol = os.fdopen(os.dup(1), 'w', encoding='utf-8')
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 1)
    os.dup2(null, 2)
    sys.stdout = os.fdopen(1, 'w', encoding='utf-8', closefd=False)
    sys.stderr = os.fdopen(2, 'w', encoding='utf-8', closefd=False)
    request = {}
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise BridgeError('Solicitud demasiado grande.')
        request = json.loads(raw)
        if not isinstance(request, dict):
            raise BridgeError('La solicitud debe ser un objeto JSON.')
        result = run(request)
    except BridgeError as exc:
        result = {'ok': False, 'response': '', 'history': [], 'error': str(exc)}
    except Exception as exc:
        result = {'ok': False, 'response': '', 'history': [],
                  'error': f'No se pudo iniciar el motor Hermes ({type(exc).__name__}).'}
    protocol.write(json.dumps(result, ensure_ascii=False) + '\n')
    protocol.flush()
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
