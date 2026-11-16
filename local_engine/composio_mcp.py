"""Conectores Composio para JOE HQ (Drive, Docs, Sheets, Gmail, Calendar, Instagram, GitHub).

Transporte: MCP HTTP de Composio Connect. Credencial, en este orden:
  1. COMPOSIO_API_KEY (llave de consumidor ``ck_…``) guardada SOLO en app/.env.
  2. OAuth que Hermes ya tiene para ``composio-lucojoma`` (lectura; nunca se modifica).

Reglas que este módulo hace cumplir en el servidor, no en el modelo:
  * Ningún bot recibe ``COMPOSIO_MULTI_EXECUTE_TOOL`` ni HTTP libre: solo funciones cerradas.
  * Drive/Docs/Sheets: cada negocio queda cercado a sus carpetas raíz.
  * Gmail, Calendar, Instagram y GitHub: la cuenta se asigna a UN negocio; otro negocio no la ve.
  * Toda escritura (enviar, crear evento, publicar, borrar…) solo corre desde una aprobación de Joe.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
import urllib.request
import urllib.error
from .core import Problem, SCOPES, EXCLUSIVE_TOOLKITS, APPROVAL_ACTIONS

log = logging.getLogger('joe_hq.composio')

TOKEN_FILE = Path('/Users/m4/.hermes/mcp-tokens/composio-lucojoma.json')
ENV_FILE = Path('/Volumes/JOE_HQ/app/.env')
ENDPOINT = 'https://connect.composio.dev/mcp'
PROTOCOL = '2025-03-26'
TOOLKITS = {
    'googledrive': 'Drive', 'googlesheets': 'Sheets', 'gmail': 'Gmail',
    'googlecalendar': 'Calendar', 'instagram': 'Instagram', 'github': 'GitHub',
}
# Lista blanca cerrada: herramienta Composio -> app. Nada fuera de aquí se ejecuta.
READ_SLUGS = {
    'GOOGLEDRIVE_FIND_FILE': 'googledrive', 'GOOGLEDRIVE_GET_FILE_METADATA': 'googledrive',
    'GOOGLEDRIVE_DOWNLOAD_FILE': 'googledrive',
    'GOOGLESHEETS_BATCH_GET': 'googlesheets', 'GOOGLESHEETS_GET_SHEET_NAMES': 'googlesheets',
    'GMAIL_FETCH_EMAILS': 'gmail', 'GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID': 'gmail',
    'GOOGLECALENDAR_EVENTS_LIST': 'googlecalendar',
    'INSTAGRAM_GET_USER_INFO': 'instagram', 'INSTAGRAM_GET_IG_USER_MEDIA': 'instagram',
    'GITHUB_LIST_REPOSITORIES_FOR_THE_AUTHENTICATED_USER': 'github', 'GITHUB_LIST_REPOSITORY_ISSUES': 'github',
}
WRITE_SLUGS = {
    'GMAIL_SEND_EMAIL': 'gmail', 'GMAIL_CREATE_EMAIL_DRAFT': 'gmail',
    'GOOGLECALENDAR_CREATE_EVENT': 'googlecalendar',
    'INSTAGRAM_POST_IG_USER_MEDIA': 'instagram', 'INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH': 'instagram',
    'GOOGLEDRIVE_TRASH_FILE': 'googledrive',
    'GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND': 'googlesheets',
    'GITHUB_CREATE_AN_ISSUE': 'github',
}
DISCOVERY = [
    {'use_case': 'list files in a google drive folder'},
    {'use_case': 'fetch emails from gmail inbox'},
    {'use_case': 'list google calendar events'},
    {'use_case': 'read values from a google sheets spreadsheet'},
    {'use_case': 'read instagram business profile and media'},
    {'use_case': 'list github repositories and issues'},
]
EMAIL_RE = re.compile(r'^[^@\s,;<>]{1,64}@[A-Za-z0-9.-]{1,180}\.[A-Za-z]{2,24}$')


def unpack(result):
    if isinstance(result, dict) and 'content' in result:
        for part in result['content']:
            if part.get('type') == 'text':
                try:
                    return json.loads(part['text'])
                except (ValueError, TypeError):
                    continue
    return result


def read_env_key(path=None):
    """Lee COMPOSIO_API_KEY de app/.env (única llave permitida). No usa variables de la terminal."""
    try:
        for line in Path(path or ENV_FILE).read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line.startswith('COMPOSIO_API_KEY='):
                value = line.split('=', 1)[1].strip().strip('"').strip("'")
                if re.fullmatch(r'[A-Za-z0-9_\-]{12,200}', value):
                    return value
    except OSError:
        pass
    return None


def save_env_key(value, path=None):
    """Guarda la llave SOLO en app/.env (0600, fuera de Git). Devuelve el tipo de llave."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_\-]{12,200}', value.strip()):
        raise Problem('La llave no tiene un formato válido.')
    value = value.strip()
    target = Path(path or ENV_FILE)
    lines = []
    try:
        lines = [l for l in target.read_text(encoding='utf-8').splitlines() if not l.strip().startswith('COMPOSIO_API_KEY=')]
    except OSError:
        pass
    lines.append('COMPOSIO_API_KEY=' + value)
    temp = target.with_name(target.name + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    os.replace(temp, target)
    os.chmod(target, 0o600)
    return 'consumidor (ck_)' if value.startswith('ck_') else 'otro formato'


def compact(value, limit=20000):
    text = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if len(text) <= limit:
        return value
    return {'truncado': True, 'vista': text[:limit]}


def clean_text(value, name, limit, required=True):
    if value in (None, '') and not required:
        return ''
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
        raise Problem(f'Campo «{name}» inválido o demasiado largo.')
    return value.strip()


def clean_emails(value, name, required=False):
    if value in (None, '', []):
        if required:
            raise Problem(f'Falta «{name}».')
        return []
    items = value if isinstance(value, list) else [value]
    if len(items) > 20 or not all(isinstance(x, str) and EMAIL_RE.match(x.strip()) for x in items):
        raise Problem(f'«{name}» debe contener correos válidos (máximo 20).')
    return [x.strip() for x in items]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class ComposioMCP:
    def __init__(self, store, config, endpoint=None, env_file=None):
        self.store = store
        # Producción: Composio real y app/.env. El ensayo usa su propio .env (nunca el real) y,
        # solo para pruebas de interfaz, puede apuntar a un Composio simulado en 127.0.0.1.
        self.endpoint = endpoint or ENDPOINT
        self.env_file = env_file
        self.simulated = bool(endpoint)
        try:
            self.roots = json.loads(Path(config).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.roots = {}
        self.lock = threading.RLock()
        self.session_id = None
        self.tool_names = {}
        self.request_id = 0
        self.workflow = None
        self.cache = None
        self.cache_time = 0.0
        self.last_ok = None
        self.last_error = None
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    # ------------------------------------------------------------------ credencial
    def key(self):
        return read_env_key(self.env_file)

    def save_key(self, value):
        self.check_key(value)  # se valida contra Composio ANTES de escribir el archivo
        kind = save_env_key(value, self.env_file)
        self.session_id, self.tool_names, self.cache = None, {}, None
        return kind

    def credential(self):
        key = self.key()
        if key:
            return 'llave', {'x-consumer-api-key': key}
        try:
            data = json.loads(TOKEN_FILE.read_text(encoding='utf-8'))
            token = data.get('access_token')
            if not isinstance(token, str) or not token:
                raise ValueError()
            if self.simulated:
                raise ValueError()  # jamás se envía el OAuth real de Hermes a un servidor simulado
        except (OSError, ValueError):
            raise Problem('Composio sin credencial: guarda tu llave en Apps o inicia sesión de Composio en Hermes.', 503)
        if float(data.get('expires_at') or 0) and float(data['expires_at']) < time.time():
            raise Problem('La sesión OAuth de Composio venció (Hermes la renueva al abrirse). '
                          'Para no depender de eso, guarda tu llave de Composio en la pestaña Apps.', 503)
        return 'oauth-hermes', {'Authorization': 'Bearer ' + token}

    def check_key(self, value):
        """Prueba una llave contra Composio ANTES de guardarla. Si no sirve, no se escribe nada en .env."""
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_\-]{12,200}', value.strip()):
            raise Problem('La llave no tiene un formato válido. Copia la llave completa, sin espacios.')
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                           'params': {'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'joe-hq', 'version': '0.2.0'}}}).encode()
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': PROTOCOL, 'x-consumer-api-key': value.strip()}
        try:
            with self.opener.open(urllib.request.Request(self.endpoint, data=body, headers=headers, method='POST'), timeout=30) as response:
                response.read(100000)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise Problem('Composio no aceptó esa llave, así que NO se guardó. Debe ser la llave de consumidor de '
                              'Composio Connect (empieza con ck_), no la llave de proyecto (ak_).', 400)
            raise Problem(f'Composio respondió HTTP {exc.code} al probar la llave; no se guardó.', 502)
        except (OSError, ValueError):
            raise Problem('No se pudo contactar a Composio para probar la llave; no se guardó. Revisa internet.', 503)

    def auth_mode(self):
        if self.key():
            return 'Llave propia en .env'
        if TOKEN_FILE.is_file():
            return 'OAuth de Hermes (solo lectura, se renueva cuando Hermes está abierto)'
        return 'Sin credencial'

    # ------------------------------------------------------------------ transporte MCP
    def rpc(self, method, params, notification=False, timeout=60):
        _, auth = self.credential()
        self.request_id += 1
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if not notification:
            payload['id'] = self.request_id
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': PROTOCOL, **auth}
        if self.session_id:
            headers['Mcp-Session-Id'] = self.session_id
        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers=headers, method='POST')
        parsed = None
        try:
            with self.opener.open(req, timeout=timeout) as response:
                self.session_id = response.headers.get('Mcp-Session-Id') or self.session_id
                if notification:
                    return {}
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:
                    raise Problem('Respuesta MCP demasiado grande.', 502)
                if 'text/event-stream' in response.headers.get('Content-Type', ''):
                    for line in raw.splitlines():
                        if line.startswith(b'data:'):
                            try:
                                candidate = json.loads(line[5:])
                            except ValueError:
                                continue
                            if candidate.get('id') == payload['id']:
                                parsed = candidate
                                break
                    if parsed is None:
                        raise Problem('MCP no devolvió resultado.', 502)
                else:
                    parsed = json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise Problem('Composio rechazó la credencial (401). Revisa la llave en Apps o renueva la sesión en Hermes.', 503)
            if exc.code in (400, 404) and self.session_id:
                self.session_id = None
                self.tool_names = {}
                raise Problem('La sesión MCP expiró; vuelve a intentar.', 503)
            raise Problem('MCP no disponible (HTTP ' + str(exc.code) + ').', 503)
        except Problem:
            raise
        except (OSError, ValueError, TimeoutError) as exc:
            log.warning('MCP sin conexión: %s', type(exc).__name__)
            raise Problem('No fue posible conectar con Composio. Revisa la conexión a internet de esta Mac.', 503)
        if 'error' in parsed:
            log.warning('MCP error: %s', str(parsed['error'])[:300])
            raise Problem('MCP rechazó la solicitud; no se ejecutó otra herramienta.', 502)
        return parsed.get('result', {})

    def initialize(self):
        if self.tool_names and self.session_id:
            return
        self.session_id = None
        self.rpc('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'joe-hq', 'version': '0.2.0'}})
        self.rpc('notifications/initialized', {}, True)
        result = self.rpc('tools/list', {})
        names = {}
        for tool in result.get('tools', []):
            for key in ('COMPOSIO_SEARCH_TOOLS', 'COMPOSIO_MULTI_EXECUTE_TOOL'):
                if tool['name'].upper().endswith(key):
                    names[key] = tool['name']
        if len(names) != 2:
            raise Problem('El MCP no expone las herramientas Composio esperadas.', 503)
        self.tool_names = names

    def call(self, key, arguments, timeout=90):
        for attempt in (1, 2):
            try:
                self.initialize()
                result = self.rpc('tools/call', {'name': self.tool_names[key], 'arguments': arguments}, timeout=timeout)
                return unpack(result), bool(result.get('isError'))
            except Problem as exc:
                # Se reintenta UNA vez solo cuando Composio rechazó antes de ejecutar (sesión MCP caída o
                # credencial 401): en ambos casos la herramienta no corrió, así que no hay doble escritura.
                # El 401 típico es el OAuth de Hermes recién renovado: se vuelve a leer del disco.
                if attempt == 1 and ('sesión MCP expiró' in str(exc) or '(401)' in str(exc) or 'OAuth de Composio venció' in str(exc)):
                    self.session_id, self.tool_names = None, {}
                    time.sleep(3)
                    continue
                raise

    # ------------------------------------------------------------------ estado de conexiones
    def discover(self, force=False):
        with self.lock:
            if self.cache and not force and time.time() - self.cache_time < 300:
                return self.cache
            try:
                found, bad = self.call('COMPOSIO_SEARCH_TOOLS', {'queries': DISCOVERY, 'session': {'generate_id': True}})
                if bad:
                    raise Problem('Composio no devolvió el estado de las conexiones.', 502)
            except Problem as exc:
                self.last_error = str(exc)
                raise
            data = found.get('data', found) if isinstance(found, dict) else {}
            statuses = {}
            for row in data.get('toolkit_connection_statuses', []):
                name = row.get('toolkit')
                if name not in TOOLKITS:
                    continue
                accounts = []
                for account in row.get('accounts', []):
                    if account.get('status') != 'ACTIVE' or not isinstance(account.get('id'), str):
                        continue
                    accounts.append({'id': account['id'], 'label': self.label(account.get('user_info'))})
                statuses[name] = {'active': bool(row.get('has_active_connection')), 'accounts': accounts}
            self.workflow = (data.get('session') or {}).get('id')
            self.cache, self.cache_time = statuses, time.time()
            self.last_ok, self.last_error = time.time(), None
            return statuses

    @staticmethod
    def label(info):
        """Etiqueta corta de la cuenta para que Joe la reconozca (correo o usuario)."""
        if isinstance(info, str):
            return info[:80]
        if isinstance(info, dict):
            for key in ('email', 'emailAddress', 'username', 'login', 'name', 'display_name'):
                if isinstance(info.get(key), str) and info[key]:
                    return info[key][:80]
            for value in info.values():
                if isinstance(value, dict):
                    nested = ComposioMCP.label(value)
                    if nested:
                        return nested
        return ''

    def status(self, force=False):
        """Estado para la UI: por app, cuentas y a qué negocio está asignada."""
        assigned = self.store.account_map()
        try:
            statuses = self.discover(force)
            error = None
        except Problem as exc:
            statuses, error = {}, str(exc)
        apps = []
        for key, name in TOOLKITS.items():
            row = statuses.get(key, {'active': False, 'accounts': []})
            item = {'toolkit': key, 'name': name, 'active': row['active'], 'accounts': row['accounts'],
                    'exclusive': key in EXCLUSIVE_TOOLKITS}
            if key in EXCLUSIVE_TOOLKITS:
                item['assigned_scope'] = assigned.get(key, {}).get('scope')
                item['assigned_account'] = assigned.get(key, {}).get('account_id')
            apps.append(item)
        return {'apps': apps, 'auth': self.auth_mode(), 'error': error, 'checked': self.last_ok,
                'has_key': bool(self.key()), 'simulated': self.simulated}

    # ------------------------------------------------------------------ cuenta permitida por bot
    def account_for(self, bot_id, toolkit):
        bot = self.store.bot(bot_id)
        statuses = self.discover()
        row = statuses.get(toolkit)
        if not row or not row['active'] or not row['accounts']:
            raise Problem(f'{TOOLKITS[toolkit]} no está conectado en Composio.', 503)
        if toolkit in EXCLUSIVE_TOOLKITS:
            entry = self.store.account_map().get(toolkit)
            if not entry or entry['scope'] != bot['scope']:
                raise Problem(f'{TOOLKITS[toolkit]} no está asignado a este negocio. Joe decide a qué negocio '
                              'pertenece cada cuenta en la pestaña Apps; no se comparte entre negocios.', 403)
            if entry['account_id'] not in {a['id'] for a in row['accounts']}:
                raise Problem(f'La cuenta asignada de {TOOLKITS[toolkit]} ya no está activa en Composio.', 503)
            return entry['account_id']
        if len(row['accounts']) != 1:
            raise Problem(f'Hay varias cuentas de {TOOLKITS[toolkit]}; falta elegir una.', 503)
        return row['accounts'][0]['id']

    def execute(self, bot_id, slug, args, write=False):
        table = WRITE_SLUGS if write else READ_SLUGS
        if slug not in table:
            raise Problem('Herramienta fuera de la lista permitida.', 403)
        with self.lock:
            account = self.account_for(bot_id, table[slug])
            call = {'tools': [{'tool_slug': slug, 'arguments': args, 'account': account}],
                    'sync_response_to_workbench': False,
                    'current_step': 'JOE_HQ_WRITE' if write else 'JOE_HQ_READ'}
            if self.workflow:
                call['session_id'] = self.workflow
            result, bad = self.call('COMPOSIO_MULTI_EXECUTE_TOOL', call, timeout=120)
        outer = result.get('data', result) if isinstance(result, dict) else {}
        results = outer.get('results', []) if isinstance(outer, dict) else []
        if not results:
            log.warning('Composio sin resultados para %s', slug)
            raise Problem('Composio no devolvió datos.', 502)
        response = results[0].get('response', {})
        if not response.get('successful'):
            detail = str(response.get('error') or results[0].get('error') or '')[:300]
            log.warning('Composio rechazó %s: %s', slug, detail)
            raise Problem('Composio rechazó la operación' + (': ' + detail if detail else '.'), 502)
        self.last_ok = time.time()
        return response.get('data', {})

    # ------------------------------------------------------------------ Drive / Docs / Sheets (cercado por carpeta)
    def permitted_roots(self, bot_id):
        scope = self.store.bot(bot_id)['scope']
        return {self.roots[name] for name in SCOPES[scope] if name in self.roots}

    def validate_id(self, value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,150}', value):
            raise Problem('ID de Drive inválido.', 403)
        return value

    def authorize(self, bot_id, file_id):
        """Sube por la cadena de carpetas hasta una raíz del negocio. Si no llega, bloquea."""
        self.validate_id(file_id)
        roots = self.permitted_roots(bot_id)
        if file_id in set(self.roots.values()) - roots:
            raise Problem('Carpeta de otra unidad de negocio bloqueada.', 403)
        current, seen, first = file_id, set(), None
        for _ in range(32):
            if current in seen:
                break
            seen.add(current)
            meta = self.execute(bot_id, 'GOOGLEDRIVE_GET_FILE_METADATA',
                                {'fileId': current, 'fields': 'id,name,mimeType,parents,trashed', 'supportsAllDrives': True})
            first = first or meta
            if meta.get('trashed') or meta.get('mimeType') == 'application/vnd.google-apps.shortcut':
                break
            if current in roots:
                return first
            parents = meta.get('parents', [])
            if len(parents) != 1:
                break
            current = parents[0]
        raise Problem('Archivo fuera de las carpetas autorizadas de este negocio.', 403)

    def list(self, bot_id, folder_id=None, page_token=None):
        roots = self.permitted_roots(bot_id)
        if not roots:
            raise Problem('Raíces Drive sin configurar (drive-folders.json).', 503)
        chosen = [self.validate_id(folder_id)] if folder_id else sorted(roots)
        if folder_id:
            self.authorize(bot_id, folder_id)
        files, continuations = [], {}
        for folder in chosen:
            query = {'folder_id': folder, 'q': 'trashed = false', 'pageSize': 100,
                     'fields': 'nextPageToken,files(id,name,mimeType,parents,size)', 'orderBy': 'name'}
            if page_token:
                query['pageToken'] = page_token
            result = self.execute(bot_id, 'GOOGLEDRIVE_FIND_FILE', query)
            for f in result.get('files', []):
                if folder not in f.get('parents', []) or f.get('mimeType') == 'application/vnd.google-apps.shortcut':
                    continue
                files.append({k: f[k] for k in ('id', 'name', 'mimeType', 'size') if k in f})
            if result.get('nextPageToken'):
                continuations[folder] = result['nextPageToken']
        return {'files': files, 'next_pages': continuations, 'truncated': bool(continuations), 'transport': 'composio-mcp'}

    def read_text(self, bot_id, file_id):
        meta = self.authorize(bot_id, file_id)
        kind = meta.get('mimeType')
        if kind not in {'application/vnd.google-apps.document', 'application/vnd.google-apps.spreadsheet',
                        'text/plain', 'text/markdown', 'text/csv'}:
            raise Problem('Por ahora solo se admite lectura de documentos de texto y hojas.')
        args = {'fileId': file_id}
        if kind == 'application/vnd.google-apps.document':
            args['mime_type'] = 'text/plain'
        if kind == 'application/vnd.google-apps.spreadsheet':
            args['mime_type'] = 'text/csv'
        result = self.execute(bot_id, 'GOOGLEDRIVE_DOWNLOAD_FILE', args)
        content = result.get('downloaded_file_content')
        if isinstance(content, dict):
            content = self.fetch_download(content)
        if not isinstance(content, str):
            raise Problem('El conector devolvió un archivo que este visor no admite.', 502)
        return {'id': file_id, 'name': meta.get('name'), 'content': content[:100000], 'truncated': len(content) > 100000}

    def fetch_download(self, info):
        """Composio puede devolver el archivo como URL temporal firmada (s3url). Se descarga solo de su dominio."""
        url = info.get('s3url') or info.get('url')
        if not isinstance(url, str) or not re.match(r'^https://[A-Za-z0-9.-]+\.(composio\.dev|r2\.cloudflarestorage\.com|amazonaws\.com)/', url):
            return None
        try:
            with self.opener.open(urllib.request.Request(url, method='GET'), timeout=60) as response:
                raw = response.read(2_000_001)
        except (OSError, ValueError):
            return None
        if len(raw) > 2_000_000:
            raw = raw[:2_000_000]
        try:
            return raw.decode('utf-8')
        except UnicodeError:
            return None

    def sheets_read(self, bot_id, spreadsheet_id, cell_range=None):
        meta = self.authorize(bot_id, spreadsheet_id)
        if meta.get('mimeType') != 'application/vnd.google-apps.spreadsheet':
            raise Problem('Ese archivo no es una hoja de cálculo.')
        if cell_range:
            cell_range = clean_text(cell_range, 'rango', 200)
            data = self.execute(bot_id, 'GOOGLESHEETS_BATCH_GET', {'spreadsheet_id': spreadsheet_id, 'ranges': [cell_range]})
        else:
            data = self.execute(bot_id, 'GOOGLESHEETS_GET_SHEET_NAMES', {'spreadsheet_id': spreadsheet_id})
        return {'name': meta.get('name'), 'data': compact(data)}

    # ------------------------------------------------------------------ lecturas de cuenta asignada
    def gmail_search(self, bot_id, query='', max_results=8):
        query = clean_text(query, 'búsqueda', 300, required=False)
        limit = max(1, min(int(max_results or 8), 15))
        data = self.execute(bot_id, 'GMAIL_FETCH_EMAILS', {'query': query, 'max_results': limit,
                                                           'include_payload': False, 'verbose': False})
        rows = []
        for m in (data.get('messages') or [])[:limit]:
            rows.append({'id': m.get('messageId') or m.get('id'), 'thread': m.get('threadId'),
                         'de': m.get('sender') or m.get('from'), 'asunto': m.get('subject'),
                         'fecha': m.get('messageTimestamp') or m.get('date'),
                         'vista': (m.get('preview', {}).get('body') if isinstance(m.get('preview'), dict) else m.get('snippet') or '')[:300]})
        return {'correos': rows, 'total': len(rows)}

    def gmail_read(self, bot_id, message_id):
        if not isinstance(message_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,64}', message_id):
            raise Problem('ID de correo inválido.')
        data = self.execute(bot_id, 'GMAIL_FETCH_MESSAGE_BY_MESSAGE_ID', {'message_id': message_id, 'format': 'full'})
        body = data.get('messageText') or data.get('preview', {}).get('body') if isinstance(data, dict) else ''
        return {'id': message_id, 'de': data.get('sender'), 'para': data.get('to'), 'asunto': data.get('subject'),
                'fecha': data.get('messageTimestamp'), 'texto': str(body or '')[:20000]}

    def calendar_list(self, bot_id, time_min=None, time_max=None, query=None):
        args = {'calendarId': 'primary', 'singleEvents': True, 'orderBy': 'startTime', 'maxResults': 25}
        for key, value in (('timeMin', time_min), ('timeMax', time_max)):
            if value:
                if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})', value):
                    raise Problem('Las fechas deben ir en formato RFC3339, por ejemplo 2026-11-16T09:00:00-06:00.')
                args[key] = value
        if 'timeMin' not in args:
            args['timeMin'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        if query:
            args['query'] = clean_text(query, 'búsqueda', 200)
        data = self.execute(bot_id, 'GOOGLECALENDAR_EVENTS_LIST', args)
        events = []
        for e in (data.get('items') or [])[:25]:
            events.append({'id': e.get('id'), 'titulo': e.get('summary'), 'inicio': (e.get('start') or {}).get('dateTime') or (e.get('start') or {}).get('date'),
                           'fin': (e.get('end') or {}).get('dateTime') or (e.get('end') or {}).get('date'), 'lugar': e.get('location'),
                           'invitados': len(e.get('attendees') or [])})
        return {'eventos': events, 'total': len(events)}

    def instagram_user(self, bot_id):
        data = self.execute(bot_id, 'INSTAGRAM_GET_USER_INFO', {})
        ident = data.get('id') or (data.get('data') or {}).get('id')
        if not ident:
            raise Problem('Instagram no devolvió el identificador de la cuenta.', 502)
        return str(ident), data

    def instagram_read(self, bot_id, what='perfil'):
        ident, info = self.instagram_user(bot_id)
        if what != 'publicaciones':
            return {'perfil': compact(info, 4000)}
        data = self.execute(bot_id, 'INSTAGRAM_GET_IG_USER_MEDIA', {'ig_user_id': ident, 'limit': 10,
                            'fields': 'id,caption,media_type,permalink,timestamp,like_count,comments_count'})
        return {'publicaciones': compact(data.get('data', data), 12000)}

    def github_read(self, bot_id, what='repos', owner=None, repo=None):
        if what == 'issues':
            for value in (owner, repo):
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value):
                    raise Problem('Indica owner y repo válidos.')
            data = self.execute(bot_id, 'GITHUB_LIST_REPOSITORY_ISSUES', {'owner': owner, 'repo': repo, 'state': 'open', 'per_page': 20})
            items = data.get('details') or data.get('issues') or data if isinstance(data, (dict, list)) else []
            if isinstance(items, dict):
                items = items.get('items') or []
            return {'issues': [{'n': i.get('number'), 'titulo': i.get('title'), 'estado': i.get('state'), 'url': i.get('html_url')}
                               for i in items[:20] if isinstance(i, dict)]}
        data = self.execute(bot_id, 'GITHUB_LIST_REPOSITORIES_FOR_THE_AUTHENTICATED_USER', {'per_page': 30, 'sort': 'updated'})
        items = data.get('details') or data.get('repositories') or data if isinstance(data, (dict, list)) else []
        if isinstance(items, dict):
            items = items.get('items') or []
        return {'repos': [{'nombre': r.get('full_name'), 'privado': r.get('private'), 'actualizado': r.get('updated_at')}
                          for r in items[:30] if isinstance(r, dict)]}

    # ------------------------------------------------------------------ escrituras: validar al proponer, ejecutar al aprobar
    def validate_action(self, bot_id, action, payload):
        """Normaliza la carga EXACTA que Joe verá y aprobará. No ejecuta nada externo de escritura."""
        if action not in APPROVAL_ACTIONS:
            raise Problem('Acción no permitida.', 403)
        if not isinstance(payload, dict):
            raise Problem('Faltan los detalles de la acción.')
        p = payload
        if action in ('gmail_send', 'gmail_draft'):
            self.account_for(bot_id, 'gmail')
            return {'para': clean_emails(p.get('para') or p.get('to') or p.get('recipient_email'), 'para', required=True),
                    'cc': clean_emails(p.get('cc'), 'cc'), 'bcc': clean_emails(p.get('bcc'), 'bcc'),
                    'asunto': clean_text(p.get('asunto') or p.get('subject'), 'asunto', 300),
                    'cuerpo': clean_text(p.get('cuerpo') or p.get('body'), 'cuerpo', 12000)}
        if action == 'calendar_create':
            self.account_for(bot_id, 'googlecalendar')
            start = clean_text(p.get('inicio') or p.get('start_datetime'), 'inicio', 40)
            end = clean_text(p.get('fin') or p.get('end_datetime'), 'fin', 40)
            for value in (start, end):
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?', value):
                    raise Problem('Inicio y fin van como AAAA-MM-DDTHH:MM (hora local de la zona indicada).')
            return {'titulo': clean_text(p.get('titulo') or p.get('summary'), 'título', 300), 'inicio': start, 'fin': end,
                    'zona': clean_text(p.get('zona') or p.get('timezone') or 'America/Mexico_City', 'zona', 60),
                    'descripcion': clean_text(p.get('descripcion') or p.get('description'), 'descripción', 4000, required=False),
                    'lugar': clean_text(p.get('lugar') or p.get('location'), 'lugar', 300, required=False),
                    'invitados': clean_emails(p.get('invitados') or p.get('attendees'), 'invitados')}
        if action == 'instagram_publish':
            self.account_for(bot_id, 'instagram')
            url = clean_text(p.get('imagen_url') or p.get('image_url'), 'imagen_url', 1000)
            if not re.match(r'^https://[^\s]+$', url):
                raise Problem('La imagen debe ser una URL https pública.')
            return {'imagen_url': url, 'texto': clean_text(p.get('texto') or p.get('caption'), 'texto', 2200, required=False)}
        if action == 'drive_delete':
            file_id = self.validate_id(p.get('file_id') or p.get('archivo_id'))
            meta = self.authorize(bot_id, file_id)
            if file_id in set(self.roots.values()):
                raise Problem('No se puede borrar una carpeta raíz del negocio.', 403)
            return {'file_id': file_id, 'nombre': meta.get('name'), 'tipo': meta.get('mimeType'), 'destino': 'papelera de Drive (recuperable 30 días)'}
        if action == 'sheets_append':
            sheet = self.validate_id(p.get('spreadsheet_id') or p.get('hoja_id'))
            meta = self.authorize(bot_id, sheet)
            values = p.get('filas') or p.get('values')
            if (not isinstance(values, list) or not values or len(values) > 200
                    or not all(isinstance(r, list) and len(r) <= 50 and all(isinstance(c, (str, int, float)) for c in r) for r in values)):
                raise Problem('«filas» debe ser una lista de filas (máximo 200 filas, 50 columnas).')
            return {'spreadsheet_id': sheet, 'nombre': meta.get('name'), 'rango': clean_text(p.get('rango') or p.get('range'), 'rango', 200), 'filas': values}
        if action == 'github_issue':
            self.account_for(bot_id, 'github')
            owner, repo = p.get('owner'), p.get('repo')
            for value in (owner, repo):
                if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', value):
                    raise Problem('Indica owner y repo válidos.')
            return {'owner': owner, 'repo': repo, 'titulo': clean_text(p.get('titulo') or p.get('title'), 'título', 250),
                    'cuerpo': clean_text(p.get('cuerpo') or p.get('body'), 'cuerpo', 8000, required=False)}
        raise Problem('Acción no permitida.', 403)

    def execute_action(self, bot_id, action, payload):
        """Solo se llama desde Store.decide tras el clic de Joe. Una vez; jamás se reintenta."""
        p = self.validate_action(bot_id, action, payload)  # revalida negocio, cuenta y carpeta al momento de ejecutar
        if action in ('gmail_send', 'gmail_draft'):
            args = {'recipient_email': p['para'][0], 'extra_recipients': p['para'][1:], 'cc': p['cc'], 'bcc': p['bcc'],
                    'subject': p['asunto'], 'body': p['cuerpo'], 'is_html': False}
            data = self.execute(bot_id, 'GMAIL_SEND_EMAIL' if action == 'gmail_send' else 'GMAIL_CREATE_EMAIL_DRAFT', args, write=True)
            return {'hecho': 'Correo enviado' if action == 'gmail_send' else 'Borrador creado', 'id': data.get('id') or (data.get('response_data') or {}).get('id')}
        if action == 'calendar_create':
            args = {'calendar_id': 'primary', 'summary': p['titulo'], 'start_datetime': p['inicio'], 'end_datetime': p['fin'],
                    'timezone': p['zona'], 'attendees': p['invitados'], 'send_updates': 'all' if p['invitados'] else 'none'}
            if p['descripcion']:
                args['description'] = p['descripcion']
            if p['lugar']:
                args['location'] = p['lugar']
            data = self.execute(bot_id, 'GOOGLECALENDAR_CREATE_EVENT', args, write=True)
            event = data.get('response_data') or data
            return {'hecho': 'Evento creado', 'id': event.get('id'), 'enlace': event.get('htmlLink')}
        if action == 'instagram_publish':
            ident, _ = self.instagram_user(bot_id)
            created = self.execute(bot_id, 'INSTAGRAM_POST_IG_USER_MEDIA', {'ig_user_id': ident, 'image_url': p['imagen_url'], 'caption': p['texto']}, write=True)
            creation = created.get('id') or (created.get('data') or {}).get('id')
            if not creation:
                raise Problem('Instagram no creó el contenedor de la publicación; no se publicó nada.', 502)
            done = self.execute(bot_id, 'INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH', {'ig_user_id': ident, 'creation_id': str(creation)}, write=True)
            return {'hecho': 'Publicado en Instagram', 'id': done.get('id') or (done.get('data') or {}).get('id')}
        if action == 'drive_delete':
            self.execute(bot_id, 'GOOGLEDRIVE_TRASH_FILE', {'file_id': p['file_id'], 'supportsAllDrives': True}, write=True)
            return {'hecho': 'Archivo enviado a la papelera de Drive', 'nombre': p['nombre']}
        if action == 'sheets_append':
            data = self.execute(bot_id, 'GOOGLESHEETS_SPREADSHEETS_VALUES_APPEND', {'spreadsheetId': p['spreadsheet_id'], 'range': p['rango'],
                                'valueInputOption': 'USER_ENTERED', 'values': p['filas']}, write=True)
            return {'hecho': 'Filas agregadas', 'detalle': compact((data.get('updates') or data), 600)}
        if action == 'github_issue':
            data = self.execute(bot_id, 'GITHUB_CREATE_AN_ISSUE', {'owner': p['owner'], 'repo': p['repo'], 'title': p['titulo'], 'body': p['cuerpo']}, write=True)
            return {'hecho': 'Issue creado', 'url': data.get('html_url') or (data.get('details') or {}).get('html_url')}
        raise Problem('Acción no permitida.', 403)
