#!/usr/bin/env python3
"""JOE HQ local. Servidor stdlib en 127.0.0.1; sin proveedores de API de pago.

Motor de todos los bots: Hermes Agent (openai-codex, la suscripción ChatGPT de Joe).
Este servidor es el único punto que toca disco, Composio, la pantalla y la voz; los
bots solo piden cosas por herramientas cerradas y el servidor decide.

Módulos:
  local_engine/core.py           datos, aislamiento por negocio, aprobaciones
  local_engine/hermes_bridge.py  un turno de Hermes por proceso
  local_engine/composio_mcp.py   Drive, Sheets, Gmail, Calendar, Instagram, GitHub
  local_engine/voice.py          dictado (faster-whisper)
  local_engine/tts_worker.py     voz de salida (VibeVoice)
"""
from __future__ import annotations
import argparse
import base64
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, unquote, parse_qs
from local_engine.core import (Store, Problem, ROOT, STAGING_ROOT, PROFILES, SCOPES, MODEL_ALLOWLIST, APPROVAL_ACTIONS,
                               EXCLUSIVE_TOOLKITS, preflight, cache_environment, safe_path, short_text, atomic_write)
from local_engine.composio_mcp import ComposioMCP, TOKEN_FILE, TOOLKITS, save_env_key

APP = Path(__file__).resolve().parent
HERMES_PYTHON = Path('/Users/m4/.hermes/installs/038c51e759d66ce1/environments/e5a1728f585a44cdb63518d0e4d705e5/venv/bin/python')
VOICE_PYTHON = APP / '.venv-voz/bin/python'
VERSION = '0.2.0'
TURN_SECONDS, COMPUTER_TURN_SECONDS = 330, 900
GRANT_SECONDS = 15 * 60
MAX_CHAIN_MESSAGES = 8
log = logging.getLogger('joe_hq')


def process_env(root, home=None):
    # No heredar credenciales ni proveedores presentes en la terminal.
    result = {k: os.environ[k] for k in ['PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'SYSTEMROOT'] if k in os.environ}
    result.update(cache_environment(root))
    if home:
        result['HERMES_HOME'] = str(home)
    return result


class Voice:
    """Voz de salida: un proceso VibeVoice residente que se apaga solo tras 10 min sin uso."""
    IDLE = 600

    def __init__(self, store):
        self.store = store
        self.lock = threading.Lock()
        self.process = None
        self.ready = None
        self.last_used = 0.0
        self.last_error = None
        self.verified = None
        self.tokens = {}
        self.folder = ROOT / 'cache' / 'tts'
        self.voices_dir = ROOT / 'data' / 'voces'
        threading.Thread(target=self.reaper, daemon=True).start()

    def available(self):
        return VOICE_PYTHON.is_file()

    def voices(self):
        if not self.voices_dir.is_dir():
            return []
        return sorted(p.stem for p in self.voices_dir.glob('*.wav') if p.is_file() and not p.is_symlink() and re.fullmatch(r'[A-Za-z0-9_-]{1,40}', p.stem))

    def voice(self):
        chosen, names = self.store.setting('voice'), self.voices()
        return chosen if chosen in names else (names[0] if names else None)

    def start(self):
        if self.process and self.process.poll() is None:
            return
        if not self.available():
            raise Problem('Falta el entorno de voz (.venv-voz). Ejecuta: bash instalar_voz.sh', 503)
        env = process_env(ROOT)
        env['NUMBA_CACHE_DIR'] = str(ROOT / 'cache/tmp/numba')
        errors = open(ROOT / 'logs' / 'voz.log', 'ab')
        self.process = subprocess.Popen([str(VOICE_PYTHON), '-B', str(APP / 'local_engine/tts_worker.py')],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
                                        cwd=str(APP), env=env, start_new_session=True)
        line = self.process.stdout.readline()
        try:
            self.ready = json.loads(line)
        except ValueError:
            self.ready = {'ready': False, 'error': 'El motor de voz no arrancó.'}
        if not self.ready.get('ready'):
            self.stop()
            raise Problem(self.ready.get('error') or 'VibeVoice no pudo cargar.', 503)
        log.info('voz: VibeVoice listo en %ss (%s %s)', self.ready.get('load_seconds'), self.ready.get('device'), self.ready.get('dtype'))

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.process = None

    def reaper(self):
        while True:
            time.sleep(30)
            if self.process and self.process.poll() is None and time.time() - self.last_used > self.IDLE and self.lock.acquire(blocking=False):
                try:
                    log.info('voz: motor apagado por inactividad')
                    self.stop()
                finally:
                    self.lock.release()

    def speak(self, text):
        text = short_text(text, 6000)
        name = self.voice()
        if not name:
            raise Problem('No hay voces en data/voces. Agrega un WAV de referencia.', 503)
        with self.lock:
            try:
                self.start()
                self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
                for old in self.folder.glob('*.wav'):  # caché propia: solo audios de más de una hora
                    if time.time() - old.stat().st_mtime > 3600:
                        old.unlink()
                token = secrets.token_urlsafe(18)
                out = self.folder / (token + '.wav')
                self.process.stdin.write(json.dumps({'id': token, 'text': text, 'voice': str(self.voices_dir / (name + '.wav')), 'out': str(out)}, ensure_ascii=False) + '\n')
                self.process.stdin.flush()
                result = json.loads(self.process.stdout.readline() or '{}')
            except Problem as exc:
                self.last_error = str(exc)
                raise
            except (OSError, ValueError):
                self.stop()
                self.last_error = 'El motor de voz se detuvo.'
                raise Problem('El motor de voz se detuvo. Vuelve a intentar.', 503)
            finally:
                self.last_used = time.time()
        if not result.get('ok'):
            self.last_error = result.get('error')
            raise Problem(result.get('error') or 'VibeVoice no generó audio.', 503)
        self.tokens[token] = out
        self.verified, self.last_error = time.time(), None
        log.info('voz: %ss de audio en %ss', result.get('audio_seconds'), result.get('compute_seconds'))
        return {'url': '/api/audio/' + token, 'mime': 'audio/wav', 'voice': name,
                'audio_seconds': result.get('audio_seconds'), 'compute_seconds': result.get('compute_seconds'), 'provider': 'VibeVoice-1.5B local'}

    def audio(self, token):
        path = self.tokens.get(token)
        if not path or not path.is_file():
            raise Problem('Audio no encontrado.', 404)
        return path.read_bytes()


class Application:
    def __init__(self, store, port=8787, staging=False):
        self.store = store
        self.port = port
        self.staging = staging
        self.mcp = ComposioMCP(store, APP / 'drive-folders.json')
        self.voice_out = Voice(store)
        self.login_attempts = []
        self.login_lock = threading.Lock()
        self.jobs = []                 # entregas pendientes entre bots
        self.turn_context = {}         # bot_id -> {'chain', 'depth'} del turno activo
        self.hermes_ok = None
        self.hermes_error = None
        self.stt_ok = None
        self.frame = {'time': 0.0, 'data': b''}
        self.frame_lock = threading.Lock()
        self.gate = threading.Condition()
        threading.Thread(target=self.dispatcher, daemon=True).start()

    # ------------------------------------------------------------------ estado
    def capabilities(self):
        c = self.store.computer
        return {
            'hermes': {'installed': HERMES_PYTHON.is_file(), 'provider': 'openai-codex', 'verified_at': self.hermes_ok, 'error': self.hermes_error},
            'composio': {'auth': self.mcp.auth_mode(), 'verified_at': self.mcp.last_ok, 'error': self.mcp.last_error},
            'voice': {'stt': 'faster-whisper local', 'stt_verified_at': self.stt_ok, 'tts': 'VibeVoice-1.5B local',
                      'tts_available': self.voice_out.available(), 'tts_verified_at': self.voice_out.verified,
                      'tts_error': self.voice_out.last_error, 'voices': self.voice_out.voices(), 'voice': self.voice_out.voice(),
                      'loaded': bool(self.voice_out.process and self.voice_out.process.poll() is None)},
            'computer': {'engine': 'Hermes computer_use (cua-driver)', 'granted': c['owner'] == 'agent' and c['expires'] > time.time()},
            'native_interbot': 'message_agent de Hermes; entrega JOE HQ dentro del mismo negocio',
            'imessage': 'fase 2',
        }

    def computer_state(self):
        with self.store.lock:
            c = self.store.computer
            if c['owner'] == 'agent' and c['expires'] <= time.time():
                self.revoke('El permiso venció.')
            return {'owner': c['owner'], 'bot_id': c['bot_id'], 'mode': c['mode'],
                    'seconds_left': max(0, int(c['expires'] - time.time())) if c['owner'] == 'agent' else 0,
                    'events': c['events'][-12:], 'pending': c['pending'] and {k: c['pending'][k] for k in ('id', 'action', 'summary', 'created')}}

    def state(self):
        return {'bots': self.store.bots(), 'profiles': PROFILES, 'capabilities': self.capabilities(),
                'approvals': self.store.approvals(), 'computer': self.computer_state(),
                'actions': APPROVAL_ACTIONS, 'staging': self.staging,
                'version': VERSION + (' · ENSAYO' if self.staging else '')}

    def run_json(self, script, payload, timeout=180):
        if not HERMES_PYTHON.is_file():
            raise Problem('No se encontró el Python existente de Hermes.', 503)
        try:
            result = subprocess.run([str(HERMES_PYTHON), '-B', str(APP / 'local_engine' / script)],
                                    input=json.dumps(payload, ensure_ascii=False), text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, cwd=str(APP), env=process_env(self.store.root), timeout=timeout)
            parsed = json.loads(result.stdout)
            if not parsed.get('ok'):
                raise Problem(parsed.get('error', 'El componente local no completó la operación.'), 503)
            return parsed
        except subprocess.TimeoutExpired:
            raise Problem('El componente local excedió el tiempo de espera.', 504)
        except (ValueError, OSError):
            raise Problem('No se pudo ejecutar el componente local. No se usó ningún proveedor alternativo.', 503)

    # ------------------------------------------------------------------ turnos Hermes
    def computer_granted(self, bot_id):
        c = self.store.computer
        return c['owner'] == 'agent' and c['bot_id'] == bot_id and c['expires'] > time.time()

    def send(self, bot_id, text):
        """Mensaje de Joe a un bot."""
        return self.start_turn(bot_id, short_text(text, 12000), role='user')

    def start_turn(self, bot_id, text, role='user', peer=None, chain=None, depth=0, dm_id=None):
        bot = self.store.bot(bot_id)
        if bot['model'] not in MODEL_ALLOWLIST:
            raise Problem('Modelo no permitido.', 403)
        with self.store.lock:
            if self.store.bot(bot_id)['status'] == 'pensando':
                raise Problem('Este bot sigue trabajando. Espera su respuesta.', 409)
            self.store.add_message(bot_id, role, text)
            self.store.db.execute("UPDATE bots SET status='pensando' WHERE id=?", (bot_id,))
            self.store.db.commit()
            ident = self.store.add_message(bot_id, 'assistant', '', status='pensando')
            self.turn_context[bot_id] = {'chain': chain, 'depth': depth, 'sent': 0}
        threading.Thread(target=self.turn, args=(bot_id, text, ident, peer, dm_id), daemon=True).start()
        return {'queued': True, 'message_id': ident}

    def prompt_context(self, bot_id, peer):
        bot = self.store.bot(bot_id)
        apps = ['Drive, Docs y Sheets (carpetas de ' + bot['scope'] + ')']
        for toolkit, entry in self.store.account_map().items():
            if entry['scope'] == bot['scope']:
                apps.append(TOOLKITS.get(toolkit, toolkit))
        return {'now': time.strftime('%A %d/%m/%Y %H:%M %Z'), 'apps': apps, 'peer': peer,
                'team': [{'handle': t['handle'], 'name': t['name']} for t in self.store.teammates(bot_id)]}

    def turn(self, bot_id, text, ident, peer=None, dm_id=None):
        ticket = secrets.token_urlsafe(40)
        bot = self.store.bot(bot_id)
        home = self.store.home(bot_id)
        history_path = safe_path(home, 'sessions/' + bot['generation'] + '.json')
        process = None
        computer = self.computer_granted(bot_id)
        budget = COMPUTER_TURN_SECONDS if computer else TURN_SECONDS
        started = time.time()
        try:
            if not HERMES_PYTHON.is_file():
                raise Problem('No se encontró el runtime de Hermes.', 503)
            history = json.loads(history_path.read_text()) if history_path.exists() else []
            with self.store.lock:
                self.store.engine_tickets[ticket] = {'bot_id': bot_id, 'expires': time.time() + budget + 60}
            payload = {'command': 'run', 'home': str(home), 'workspace': str(self.store.workspace(bot_id)),
                       'message': text, 'model': bot['model'], 'history': history, 'session_id': bot['generation'],
                       'bot_id': bot_id, 'callback_token': ticket, 'computer': computer,
                       'context': self.prompt_context(bot_id, peer),
                       'callback_url': f'http://127.0.0.1:{self.port}/api/engine/tool'}
            process = subprocess.Popen([str(HERMES_PYTHON), '-B', str(APP / 'local_engine/hermes_bridge.py')],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                       cwd=str(APP), env=process_env(self.store.root, home), start_new_session=True)
            with self.store.lock:
                self.store.active_processes[bot_id] = process
            output, _ = process.communicate(json.dumps(payload, ensure_ascii=False), timeout=budget)
            if len(output) > 5000000:
                raise Problem('Respuesta de Hermes demasiado grande.', 502)
            if process.returncode and process.returncode < 0:
                raise Problem('Turno detenido: Joe tomó el control.', 409)
            result = json.loads(output)
            if not result.get('ok'):
                raise Problem(result.get('error', 'Hermes no completó la conversación.'), 503)
            response = short_text(result.get('response', ''), 100000)
            if isinstance(result.get('history'), list):
                atomic_write(history_path, json.dumps(result['history'], ensure_ascii=False))
            status = 'completo'
            self.hermes_ok, self.hermes_error = time.time(), None
            log.info('turno %s: completo en %.1fs (computadora=%s)', bot_id, time.time() - started, computer)
        except subprocess.TimeoutExpired:
            response = f'Hermes no respondió en {budget} segundos. No se usó otro proveedor.'
            status = 'error'
            self.hermes_error = 'timeout'
        except Exception as exc:
            response = str(exc) if isinstance(exc, Problem) else 'No se pudo completar la conversación Hermes. Revisa logs/joe-hq.log.'
            status = 'error'
            self.hermes_error = response[:200]
            log.warning('turno %s: %s', bot_id, type(exc).__name__ if not isinstance(exc, Problem) else response[:200])
        finally:
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            with self.store.lock:
                self.store.engine_tickets.pop(ticket, None)
                self.store.active_processes.pop(bot_id, None)
                self.turn_context.pop(bot_id, None)
                self.store.db.execute('UPDATE messages SET text=?,status=? WHERE id=?', (response, status, ident))
                self.store.db.execute("UPDATE bots SET status='listo' WHERE id=?", (bot_id,))
                self.store.db.commit()
            self.after_turn(dm_id, peer, response, status)

    # ------------------------------------------------------------------ mensajes entre bots (mismo negocio)
    def after_turn(self, dm_id, peer, response, status):
        """Si el turno era un mensaje entrante de un compañero, su respuesta final vuelve al emisor."""
        if not dm_id or not peer or peer.get('mode') != 'incoming':
            return
        ok = status == 'completo'
        self.store.dm_update(dm_id, 'respondido' if ok else 'fallido', response)
        dm = self.store.dm(dm_id)
        if dm and dm['expects_reply']:
            with self.store.lock:
                self.jobs.append({'kind': 'reply', 'dm': dm_id})

    def message_agent(self, bot_id, args):
        target = self.store.resolve_teammate(bot_id, args.get('target'))
        with self.store.lock:
            ctx = self.turn_context.get(bot_id) or {'chain': None, 'depth': 0, 'sent': 0}
            if ctx['chain'] and self.store.db.execute('SELECT COUNT(*) FROM dms WHERE chain=?', (ctx['chain'],)).fetchone()[0] >= MAX_CHAIN_MESSAGES:
                raise Problem('Esta conversación entre bots llegó a su límite. Resume el resultado para Joe.', 409)
            ident = self.store.dm_create(bot_id, target['id'], args.get('body'), bool(args.get('expects_reply', True)),
                                         chain=ctx['chain'], depth=ctx['depth'] + 1)
            ctx['sent'] = ctx.get('sent', 0) + 1
            self.jobs.append({'kind': 'deliver', 'dm': ident})
        self.store.add_message(bot_id, 'system', f"Mensaje enviado a {target['name']} (@{target['handle']}). Su respuesta llegará aquí.")
        log.info('dm %s: %s -> %s en cola', ident, bot_id, target['id'])
        return {'status': 'queued', 'delivery_id': ident, 'target': target['handle'],
                'note': 'Hand-off, not a receipt. Finish your turn; the reply wakes you as a new message.'}

    def dispatcher(self):
        """Entrega mensajes entre bots cuando el destinatario está libre. Nunca cruza negocios."""
        while True:
            time.sleep(0.6)
            try:
                with self.store.lock:
                    pending = list(self.jobs)
                for job in pending:
                    dm = self.store.dm(job['dm'])
                    if not dm:
                        with self.store.lock:
                            self.jobs.remove(job)
                        continue
                    sender, receiver = self.store.bot(dm['from_bot']), self.store.bot(dm['to_bot'])
                    if sender['scope'] != receiver['scope']:  # defensa en profundidad
                        self.store.dm_update(dm['id'], 'bloqueado')
                        with self.store.lock:
                            self.jobs.remove(job)
                        continue
                    target = receiver if job['kind'] == 'deliver' else sender
                    if self.store.bot(target['id'])['status'] == 'pensando':
                        continue
                    with self.store.lock:
                        self.jobs.remove(job)
                    try:
                        if job['kind'] == 'deliver':
                            self.store.dm_update(dm['id'], 'entregando')
                            text = f"Message from 🤖 {sender['name']} (@{sender['handle']}): {dm['body']}"
                            self.start_turn(receiver['id'], text, role='peer', peer={'mode': 'incoming', 'from': sender['handle']},
                                            chain=dm['chain'], depth=dm['depth'], dm_id=dm['id'])
                        else:
                            outcome = 'answered' if dm['status'] == 'respondido' else 'could not answer'
                            text = (f"Reply from 🤖 {receiver['name']} (@{receiver['handle']}) to your message [{dm['id']}] "
                                    f"(outcome: {outcome}): {dm['reply'] or ''}")
                            self.start_turn(sender['id'], text[:12000], role='peer', peer={'mode': 'reply', 'from': receiver['handle']},
                                            chain=dm['chain'], depth=dm['depth'])
                    except Problem as exc:
                        if exc.status == 409:  # se ocupó en el intervalo: reintentar entrega (aún no se envió nada)
                            with self.store.lock:
                                self.jobs.append(job)
                        else:
                            self.store.dm_update(dm['id'], 'fallido', str(exc))
            except Exception:
                log.exception('dispatcher')

    def relay(self, bot_id, target_id, text):
        """Joe pide desde la UI que un bot le escriba a un compañero (mismo flujo que message_agent)."""
        target = self.store.bot(target_id)
        return self.message_agent(bot_id, {'target': target['handle'], 'body': short_text(text, 4000), 'expects_reply': True})

    # ------------------------------------------------------------------ herramientas que piden los bots
    def engine_tool(self, token, data):
        with self.store.lock:
            info = self.store.engine_tickets.get(token)
            if not info or info['expires'] < time.time() or info['bot_id'] != data.get('bot_id'):
                raise Problem('Credencial de herramienta inválida.', 403)
            bot_id = info['bot_id']
        args = data.get('arguments', {})
        if not isinstance(args, dict):
            raise Problem('Argumentos inválidos.')
        name = data.get('tool')
        if name == 'computer_gate':
            return self.computer_gate(bot_id, args)
        if name == 'computer_event':
            return self.computer_event(bot_id, args)
        if name == 'save_file':
            return self.store.save_file(bot_id, args.get('path'), args.get('content'))
        if name == 'list_files':
            return {'files': self.store.detail(bot_id)['files']}
        if name == 'task_create':
            return self.store.task(bot_id, args.get('title'))
        if name == 'message_agent':
            return self.message_agent(bot_id, args)
        if name == 'drive_list':
            return self.mcp.list(bot_id, args.get('folder_id') or None)
        if name == 'drive_read':
            return self.mcp.read_text(bot_id, args.get('file_id'))
        if name == 'sheets_read':
            return self.mcp.sheets_read(bot_id, args.get('spreadsheet_id'), args.get('range') or None)
        if name == 'gmail_search':
            return self.mcp.gmail_search(bot_id, args.get('query') or '', args.get('max_results') or 8)
        if name == 'gmail_read':
            return self.mcp.gmail_read(bot_id, args.get('message_id'))
        if name == 'calendar_list':
            return self.mcp.calendar_list(bot_id, args.get('time_min'), args.get('time_max'), args.get('query'))
        if name == 'instagram_read':
            return self.mcp.instagram_read(bot_id, args.get('what') or 'perfil')
        if name == 'github_read':
            return self.mcp.github_read(bot_id, args.get('what') or 'repos', args.get('owner'), args.get('repo'))
        if name == 'request_action':
            return self.propose(bot_id, args.get('action'), args.get('details'))
        raise Problem('Herramienta no permitida.', 403)

    def propose(self, bot_id, action, payload):
        """Deja la acción lista para el botón de Joe. Nada se envía, publica ni borra aquí."""
        if action == 'file_delete':
            action = 'drive_delete'
        normalized = self.mcp.validate_action(bot_id, action, payload)
        result = self.store.approval(bot_id, action, normalized)
        log.info('aprobación %s: %s propuesta por %s', result['id'], action, bot_id)
        return {'approval_id': result['id'], 'status': 'pendiente',
                'message': 'Acción preparada. NO se ha ejecutado: Joe debe aprobarla con el botón en la pestaña Aprobar.'}

    # ------------------------------------------------------------------ computadora del agente
    def revoke(self, reason):
        c = self.store.computer
        if c['pending']:
            c['pending']['decision'] = 'deny'
        c.update({'owner': 'user', 'bot_id': None, 'expires': 0, 'pending': None})
        with self.gate:
            self.gate.notify_all()

    def control(self, bot_id, owner, mode='step'):
        self.store.bot(bot_id)
        if owner not in {'user', 'agent'}:
            raise Problem('Control inválido.')
        with self.store.lock:
            c = self.store.computer
            if owner == 'agent':
                if mode not in ('step', 'session'):
                    raise Problem('Modo inválido.')
                if c['owner'] == 'agent' and c['bot_id'] not in (None, bot_id) and c['expires'] > time.time():
                    raise Problem('Otro bot tiene la computadora. Toma el control primero.', 409)
                c.update({'owner': 'agent', 'bot_id': bot_id, 'mode': mode, 'expires': time.time() + GRANT_SECONDS, 'events': [], 'pending': None})
                log.info('computadora: prestada a %s (modo %s)', bot_id, mode)
            else:
                holder = c['bot_id']
                self.revoke('Joe tomó el control.')
                # Detiene de inmediato el turno del bot que tenía la pantalla.
                process = self.store.active_processes.get(holder) if holder else None
                if process and process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                log.info('computadora: Joe tomó el control')
        return self.computer_state()

    def computer_gate(self, bot_id, args):
        """Cada acción de computer_use pasa por aquí ANTES de ejecutarse."""
        action = str(args.get('action') or '')[:40]
        summary = str(args.get('summary') or action)[:300]
        with self.store.lock:
            c = self.store.computer
            if not self.computer_granted(bot_id):
                return {'allow': False, 'reason': 'Joe no te ha prestado la computadora (o tomó el control). Pídele que la active.'}
            if args.get('free') or c['mode'] == 'session':
                return {'allow': True}
            pending = {'id': secrets.token_hex(6), 'bot_id': bot_id, 'action': action, 'summary': summary, 'created': time.time(), 'decision': None}
            c['pending'] = pending
        deadline = time.time() + 150
        with self.gate:
            while pending['decision'] is None and time.time() < deadline:
                self.gate.wait(timeout=1.0)
        with self.store.lock:
            if self.store.computer['pending'] is pending:
                self.store.computer['pending'] = None
        if pending['decision'] == 'allow' and self.computer_granted(bot_id):
            return {'allow': True}
        return {'allow': False, 'reason': 'Joe rechazó este paso.' if pending['decision'] == 'deny' else 'Joe no respondió a tiempo; paso cancelado.'}

    def computer_decide(self, ident, decision):
        if decision not in ('allow', 'deny'):
            raise Problem('Decisión inválida.')
        with self.store.lock:
            pending = self.store.computer['pending']
            if not pending or pending['id'] != ident:
                raise Problem('Ese paso ya no está pendiente.', 409)
            pending['decision'] = decision
        with self.gate:
            self.gate.notify_all()
        return self.computer_state()

    def computer_event(self, bot_id, args):
        with self.store.lock:
            events = self.store.computer['events']
            events.append({'time': time.time(), 'action': str(args.get('action'))[:40], 'summary': str(args.get('summary'))[:200], 'ok': bool(args.get('ok'))})
            del events[:-40]
        return {'logged': True}

    def screen(self):
        """Vista en vivo de la pantalla real, solo mientras un bot tiene la computadora."""
        with self.store.lock:
            c = self.store.computer
            if not (c['owner'] == 'agent' and c['expires'] > time.time()):
                raise Problem('La vista en vivo solo existe mientras un bot tiene la computadora.', 404)
        with self.frame_lock:
            if time.time() - self.frame['time'] < 1.0 and self.frame['data']:
                return self.frame['data']
            path = ROOT / 'cache' / 'tmp' / ('pantalla-%d.jpg' % self.port)
            try:
                subprocess.run(['/usr/sbin/screencapture', '-x', '-t', 'jpg', str(path)], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(['/usr/bin/sips', '-Z', '1440', '-s', 'formatOptions', '60', str(path)], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                data = path.read_bytes()
            except (OSError, subprocess.SubprocessError):
                raise Problem('macOS no permitió capturar la pantalla. Da permiso de Grabación de Pantalla a la Terminal que arranca JOE HQ.', 503)
            self.frame = {'time': time.time(), 'data': data}
            return data

    # ------------------------------------------------------------------ voz
    def transcribe(self, bot_id, data):
        self.store.bot(bot_id)
        mime = data.get('mime', 'audio/webm')
        extension = {'audio/webm': '.webm', 'audio/webm;codecs=opus': '.webm', 'audio/mp4': '.m4a', 'audio/wav': '.wav', 'audio/ogg': '.ogg'}.get(mime)
        if not extension:
            raise Problem('Formato de audio no admitido.')
        encoded = data.get('audio')
        if not isinstance(encoded, str) or len(encoded) > 28000000:
            raise Problem('Audio demasiado grande.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise Problem('Audio inválido.')
        if not raw:
            raise Problem('Audio vacío.')
        folder = self.store.root / 'data' / self.store.bot(bot_id)['scope'] / bot_id / 'dictados'
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / (secrets.token_hex(10) + extension)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        result = self.run_json('voice.py', {'command': 'transcribe', 'input_path': str(path), 'language': 'es'})
        self.stt_ok = time.time()
        return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'JOE-HQ'
    protocol_version = 'HTTP/1.1'

    @property
    def app(self):
        return self.server.app

    def log_message(self, *args):
        # No logs de URL, mensajes, cookies ni identificadores de usuario.
        return

    def reply(self, status, data, extra=None, ctype='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.close_connection = True
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Permissions-Policy', 'camera=(), geolocation=(), microphone=(self)')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def guard(self, mutating=False):
        port = self.app.port
        if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
            raise Problem('Host no permitido.', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
            raise Problem('Origen no permitido.', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Solicitud de otro sitio bloqueada.', 403)
        if mutating and (self.headers.get('Content-Type', '').split(';')[0] != 'application/json'):
            raise Problem('Se requiere JSON.', 415)

    def authenticated(self, csrf=False):
        try:
            cookie = cookies.SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie['joe_session'].value if 'joe_session' in cookie else ''
        except cookies.CookieError:
            token = ''
        session = self.app.store.session(token)
        if not session:
            raise Problem('Inicia sesión con tu contraseña local.', 401)
        if csrf and not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise Problem('Token de sesión inválido; recarga la página.', 403)
        return session

    def json_body(self):
        if self.headers.get('Transfer-Encoding'):
            raise Problem('Transferencia no admitida.', 400)
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise Problem('Tamaño inválido.')
        if length < 1 or length > 29000000:
            raise Problem('Carga vacía o demasiado grande.', 413)
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            raise Problem('JSON inválido.')
        if not isinstance(body, dict):
            raise Problem('Se requiere un objeto JSON.')
        return body

    def do_GET(self):
        try:
            self.guard()
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            if path == '/api/session':
                try:
                    s = self.authenticated()
                except Problem:
                    s = None
                return self.reply(200, {'authenticated': bool(s), 'setupRequired': not bool(self.app.store.setting('password')), 'csrf': s['csrf'] if s else None})
            if path.startswith('/api/'):
                self.authenticated()  # TODA la API exige la contraseña local
                if path == '/api/state':
                    return self.reply(200, self.app.state())
                if path == '/api/apps':
                    return self.reply(200, self.app.mcp.status(force=parse_qs(parsed.query).get('refresh') == ['1']))
                if path == '/api/computer/frame':
                    return self.reply(200, self.app.screen(), ctype='image/jpeg')
                if path.startswith('/api/audio/'):
                    return self.reply(200, self.app.voice_out.audio(path[len('/api/audio/'):]), ctype='audio/wav')
                parts = path.strip('/').split('/')
                if len(parts) in (3, 4) and parts[:2] == ['api', 'bots']:
                    bot_id = parts[2]
                    if len(parts) == 3:
                        detail = self.app.store.detail(bot_id)
                        detail['files'] = [f for f in detail['files'] if not f['name'].startswith(('audio/', 'dictados/'))]
                        return self.reply(200, detail)
                    if parts[3] == 'files':
                        return self.reply(200, self.app.store.read_file(bot_id, parse_qs(parsed.query).get('name', [''])[0]))
                raise Problem('Ruta no encontrada.', 404)
            if path in ('/', '/index.html'):
                file = APP / 'local_web/index.html'
            elif path in ('/app.js', '/styles.css', '/upstream-tokens.css'):
                file = APP / 'local_web' / path[1:]
            else:
                raise Problem('Ruta no encontrada.', 404)
            return self.reply(200, file.read_bytes(), ctype=(mimetypes.guess_type(file.name)[0] or 'text/plain') + '; charset=utf-8')
        except Problem as exc:
            self.reply(exc.status, {'error': str(exc)})
        except (OSError, ValueError):
            self.reply(503, {'error': 'No se pudo leer el recurso local.'})

    def do_POST(self):
        try:
            self.guard(True)
            path = urlsplit(self.path).path
            data = self.json_body()
            app, store = self.app, self.app.store
            if path == '/api/engine/tool':
                auth = self.headers.get('Authorization', '')
                if not auth.startswith('Bearer '):
                    raise Problem('Credencial requerida.', 401)
                return self.reply(200, {'ok': True, 'result': app.engine_tool(auth[7:], data)})
            if path in ('/api/login', '/api/setup'):
                port = app.port
                if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
                    raise Problem('Inicia sesión desde la página local.', 403)
                with app.login_lock:
                    app.login_attempts = [x for x in app.login_attempts if x > time.time() - 60]
                    if len(app.login_attempts) >= 8:
                        raise Problem('Espera un minuto antes de volver a intentar.', 429)
                    app.login_attempts.append(time.time())
                    if path == '/api/setup':
                        store.setup_password(data.get('password'))
                    if not store.password_ok(data.get('password')):
                        raise Problem('Contraseña incorrecta.', 401)
                token, s = store.login()
                return self.reply(200, {'authenticated': True, 'csrf': s['csrf']}, {'Set-Cookie': f'joe_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200'})
            self.authenticated(True)
            if path == '/api/logout':
                token = cookies.SimpleCookie(self.headers.get('Cookie', ''))['joe_session'].value
                with store.lock:
                    store.sessions.pop(token, None)
                return self.reply(200, {'ok': True}, {'Set-Cookie': 'joe_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if path == '/api/bots':
                return self.reply(201, store.create_bot(data.get('name'), data.get('scope')))
            if path == '/api/apps/assign':
                if data.get('scope') != 'ninguno':
                    known = {a['id'] for row in app.mcp.status()['apps'] if row['toolkit'] == data.get('toolkit') for a in row['accounts']}
                    if data.get('account_id') not in known:
                        raise Problem('Esa cuenta no está activa en Composio.', 404)
                store.assign_account(data.get('toolkit'), data.get('account_id') or 'ninguna', data.get('scope'))
                log.info('apps: %s asignada a %s', data.get('toolkit'), data.get('scope'))
                return self.reply(200, app.mcp.status())
            if path == '/api/apps/key':
                kind = save_env_key(data.get('key'))
                app.mcp.session_id, app.mcp.tool_names, app.mcp.cache = None, {}, None
                status = app.mcp.status(force=True)
                log.info('apps: llave Composio guardada en .env (%s)', kind)
                return self.reply(200, {**status, 'saved': True, 'kind': kind})
            if path == '/api/voice':
                if data.get('voice') not in app.voice_out.voices():
                    raise Problem('Voz no encontrada.', 404)
                store.setting('voice', data['voice'])
                return self.reply(200, {'voice': data['voice']})
            if path == '/api/computer/decide':
                return self.reply(200, app.computer_decide(data.get('id'), data.get('decision')))
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[:2] == ['api', 'approvals']:
                result = store.decide(parts[2], data.get('decision'), app.mcp.execute_action)
                log.info('aprobación %s: %s -> %s', parts[2], data.get('decision'), result.get('status'))
                return self.reply(200, result)
            if len(parts) == 4 and parts[:2] == ['api', 'bots']:
                bot_id, action = parts[2:]
                store.bot(bot_id)
                if action == 'message':
                    return self.reply(202, app.send(bot_id, data.get('text')))
                if action == 'session':
                    result = store.new_session(bot_id)
                elif action == 'profile':
                    result = store.profile(bot_id, data.get('profile'))
                elif action == 'memory':
                    result = store.memory(bot_id, data)
                elif action == 'tasks':
                    result = store.task(bot_id, data.get('title'))
                elif action == 'files':
                    result = store.save_file(bot_id, data.get('name'), data.get('content'))
                elif action == 'relay':
                    result = app.relay(bot_id, data.get('target_id'), data.get('text'))
                elif action == 'computer':
                    result = app.control(bot_id, data.get('owner'), data.get('mode') or 'step')
                elif action == 'drive':
                    result = app.mcp.list(bot_id, data.get('folder_id'), data.get('page_token'))
                elif action == 'drive-read':
                    result = app.mcp.read_text(bot_id, data.get('file_id'))
                elif action == 'transcribe':
                    result = app.transcribe(bot_id, data)
                elif action == 'speak':
                    result = app.voice_out.speak(data.get('text'))
                elif action == 'proposal':
                    result = app.propose(bot_id, data.get('action'), data.get('payload'))
                else:
                    raise Problem('Acción no encontrada.', 404)
                return self.reply(200, result)
            raise Problem('Ruta no encontrada.', 404)
        except Problem as exc:
            self.reply(exc.status, {'error': str(exc)})
        except Exception:
            log.exception('POST')
            self.reply(500, {'error': 'La operación local no se completó. No se ejecutó ninguna alternativa.'})


def doctor():
    report = {'volume_mounted': ROOT.is_mount(), 'hermes_python': HERMES_PYTHON.is_file(),
              'voice_environment': VOICE_PYTHON.is_file(), 'composio_oauth_present': TOKEN_FILE.is_file(),
              'paid_provider_fallback': False, 'localhost': '127.0.0.1:8787', 'global_hermes_modified': False}
    try:
        preflight()
        report['storage'] = 'listo'
    except (Problem, OSError) as exc:
        report['storage'] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['storage'] == 'listo' else 1


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='JOE HQ local en español')
    parser.add_argument('--doctor', action='store_true', help='Diagnóstico local sin arrancar HTTP')
    parser.add_argument('--staging', action='store_true', help='Ensayo: datos de prueba en cache/staging, puerto 8788')
    args = parser.parse_args()
    if args.doctor:
        return doctor()
    root, port = (STAGING_ROOT, 8788) if args.staging else (ROOT, 8787)
    try:
        # La app no arranca si el volumen no está montado: nada cae al disco interno.
        if not ROOT.is_mount():
            raise Problem('JOE_HQ no está montado en /Volumes/JOE_HQ. Conecta el disco y vuelve a iniciar.', 503)
        preflight(root)
        os.environ.update(cache_environment())
        handler = RotatingFileHandler(root / 'logs' / 'joe-hq.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        logging.basicConfig(level=logging.INFO, handlers=[handler])
        store = Store(root)
        server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        server.app = Application(store, port, args.staging)
        server.daemon_threads = True
        log.info('JOE HQ %s iniciado en 127.0.0.1:%s (ensayo=%s)', VERSION, port, args.staging)
        print(f'JOE HQ: http://127.0.0.1:{port} — entra con tu contraseña local. Control+C para cerrar.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            for process in list(store.active_processes.values()):
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            server.app.voice_out.stop()
            server.server_close()
            store.db.close()
        return 0
    except (Problem, OSError) as exc:
        print('JOE HQ no pudo iniciar: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
