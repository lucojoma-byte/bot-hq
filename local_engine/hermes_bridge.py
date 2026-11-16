#!/usr/bin/env python3
"""JOE HQ → Hermes, one JSON request on stdin and one JSON response on stdout.

Commands: diagnose; run. Required run fields: home, workspace, message, bot_id,
callback_token. Optional: model, history, session_id, callback_url. No API-key
provider or raw OS/MCP tool is exposed. Launch with the existing Hermes venv
Python and -B. OAuth credentials are read-only and remain in process memory.
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
TOOL_NAMES = frozenset({'memory', 'save_file', 'list_files', 'task_create', 'drive_list', 'request_action'})


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


def configuration(home, model):
    """Write only our own allowlisted configuration; never merge global config."""
    import yaml
    cfg = {
        'model': {'default': model, 'provider': 'openai-codex', 'base_url': CODEX_URL, 'api_mode': 'codex_responses'},
        'fallback_providers': [], 'fallback_model': {},
        'providers': {'openai-codex': {'request_timeout_seconds': 20, 'stale_timeout_seconds': 25}},
        'toolsets': ['memory', 'joe_hq'],
        'platform_toolsets': {'cli': ['memory', 'joe_hq']},
        'agent': {'max_turns': 8, 'environment_probe': False, 'coding_context': False,
                  'bot_mode_protocol': False, 'verify_on_stop': False,
                  'api_max_retries': 1, 'disabled_toolsets': ['terminal', 'file', 'browser', 'computer_use',
                  'code_execution', 'delegation', 'cronjob', 'skills', 'connections', 'web', 'tts', 'stt']},
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
        schema('drive_list', 'Lee la carpeta Drive autorizada para este bot. No acepta carpetas de otros negocios.',
               {'folder_id': text}, []),
        schema('request_action', 'Prepara una acción externa para aprobación de Joe. No la ejecuta. Envíos, eventos, publicaciones y borrados requieren el botón de aprobación.',
               {'action': {'type': 'string', 'enum': ['gmail_send', 'calendar_create', 'instagram_publish', 'file_delete']},
                'details': {'type': 'object'}}, ['action', 'details']),
    ]


def register_callbacks(request):
    url = request.get('callback_url') or 'http://127.0.0.1:8787/api/engine/tool'
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port != 8787
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or not parsed.path.startswith('/api/')):
        raise BridgeError('Callback inválido; solo se permite el servidor local JOE HQ en 127.0.0.1:8787.')
    token = bounded_string(request.get('callback_token'), 'callback_token', 512)
    bot_id = bounded_string(request.get('bot_id'), 'bot_id', 64)
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', bot_id):
        raise BridgeError('Identidad del bot inválida.')
    from tools.registry import registry
    from toolsets import create_custom_toolset
    create_custom_toolset('joe_hq', 'Herramientas aisladas de JOE HQ',
                          tools=[definition['name'] for definition in tool_definitions()])
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def callback(name, arguments):
        if not isinstance(arguments, dict):
            return {'ok': False, 'error': 'Argumentos inválidos.'}
        encoded = json.dumps({'bot_id': bot_id, 'tool': name, 'arguments': arguments}, ensure_ascii=False).encode()
        if len(encoded) > 1_000_000:
            return {'ok': False, 'error': 'La solicitud excede el límite permitido.'}
        req = urllib.request.Request(url, data=encoded, headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}, method='POST')
        try:
            with opener.open(req, timeout=45) as response:
                body = response.read(1_000_001)
                if len(body) > 1_000_000:
                    return {'ok': False, 'error': 'La respuesta excede el límite permitido.'}
                return json.loads(body)
        except Exception:
            return {'ok': False, 'error': 'El servidor local no pudo completar esta herramienta.'}

    for definition in tool_definitions():
        name = definition['name']
        registry.register(name=name, toolset='joe_hq', schema=definition,
                          handler=lambda args, _name=name, **kw: callback(_name, args),
                          check_fn=lambda: True, override=True)


def install_dispatch_gate():
    """Deny hallucinated tool calls too, before Hermes executes any handler."""
    import agent.tool_executor as executor
    original = executor._dispatch_authorized_once

    def guarded(agent, state, ref, **kwargs):
        if ref.name not in TOOL_NAMES:
            kwargs['scope_block'] = 'Herramienta bloqueada por el aislamiento de JOE HQ.'
        return original(agent, state, ref, **kwargs)
    executor._dispatch_authorized_once = guarded


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
        raise BridgeError('Este proceso no puede resolver chatgpt.com. La red del entorno bloquea la conexión a Hermes Codex.')
    configuration(home, model)
    oauth_token = read_credentials()
    register_callbacks(request)
    install_dispatch_gate()
    from run_agent import AIAgent
    agent = AIAgent(
        provider='openai-codex', requested_provider='openai-codex', model=model,
        api_mode='codex_responses', base_url=CODEX_URL, api_key=oauth_token,
        max_iterations=8, max_tokens=2500, enabled_toolsets=['memory', 'joe_hq'],
        fallback_model={}, load_soul_identity=True, skip_background_review=True,
        skip_context_files=True, quiet_mode=True, save_trajectories=False,
        verbose_logging=False, session_id=session_id, cwd=str(workspace),
        run_budget_seconds=120,
    )
    agent._bot_mode_protocol = False
    agent.tools = [tool for tool in agent.tools if tool.get('function', {}).get('name') in TOOL_NAMES]
    agent.valid_tool_names = set(TOOL_NAMES)
    instruction = ('Eres el bot persistente de JOE HQ. Responde siempre en español, breve y claro. '
                   'Usa solo tu memoria y biblioteca. Nunca pidas ni leas datos de otro negocio. '
                   'No envíes correos, crees eventos, publiques ni borres archivos directamente: '
                   'request_action solamente prepara una aprobación de Joe. No afirmes que una acción ocurrió sin confirmación de herramienta.')
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
