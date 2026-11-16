"""Adversarial stdlib tests; all fixtures persist on JOE_HQ for audit.

Run: PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
No HTTP socket is bound, no external service called, no fixture is deleted.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from local_engine.core import Store, Problem, preflight, safe_path, MAX_DM_HOPS
from local_engine import composio_mcp
from local_engine.composio_mcp import ComposioMCP
from server import Application, Handler, HERMES_PYTHON

RUN_ROOT = APP / '.test-runtime' / ('unittest-' + uuid.uuid4().hex)
RUN_ROOT.mkdir(parents=True, exist_ok=False)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.root = RUN_ROOT / (self.id().split('.')[-1] + '-' + uuid.uuid4().hex[:8])
        self.root.mkdir()
        preflight(self.root, require_mount=False)
        self.store = Store(self.root)
        self.app = Application(self.store)

    def problem(self, status, function, *args, **kwargs):
        with self.assertRaises(Problem) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.status, status)

    def tearDown(self):
        # Close handles only; retain fixture databases, memories and files.
        self.store.db.close()


class StoreIsolationTests(Fixture):
    def test_codex_profile_switch_preserves_business_memory(self):
        self.store.memory('guardian', {'memory': 'Solo memoria de Guardián'})
        changed=self.store.profile('guardian','codex_sol')
        self.assertEqual(changed['model'],'gpt-5.6-sol')
        self.assertEqual(changed['scope'],'guardian')
        self.assertEqual(self.store.memory('guardian')['memory'],'Solo memoria de Guardián')
        self.assertEqual(self.store.memory('casa_kiraz')['memory'],'')
        self.assertEqual(self.store.profile('guardian','codex')['model'],'gpt-5.6-terra')

    def test_three_initial_persistent_bots(self):
        self.assertEqual([b['id'] for b in self.store.bots()], ['guardian', 'casa_kiraz', 'holding'])
        self.assertTrue((self.store.home('guardian') / 'memories/MEMORY.md').is_file())
        again = Store(self.root)
        self.assertEqual(len(again.bots()), 3)
        again.db.close()

    def test_maximum_five_even_with_concurrent_creations(self):
        def create(index):
            try:
                return self.store.create_bot('Bot ' + str(index), 'guardian')['id']
            except Problem as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(create, range(8)))
        self.assertEqual(sum(isinstance(r, str) for r in results), 2)
        self.assertTrue(all(isinstance(r, str) or r == 409 for r in results))
        self.assertEqual(len(self.store.bots()), 5)

    def test_unknown_business_rejected(self):
        self.problem(400, self.store.create_bot, 'Otro', 'unscoped')

    def test_distinct_business_files_and_memories(self):
        self.store.save_file('guardian', 'ficha.txt', 'SOLO_GUARDIAN_FICTICIO')
        self.store.save_file('casa_kiraz', 'ficha.txt', 'SOLO_KIRAZ_FICTICIO')
        self.assertEqual(self.store.read_file('guardian', 'ficha.txt')['content'], 'SOLO_GUARDIAN_FICTICIO')
        self.assertEqual(self.store.read_file('casa_kiraz', 'ficha.txt')['content'], 'SOLO_KIRAZ_FICTICIO')
        self.store.memory('guardian', {'memory': 'MEMORIA_GUARDIAN_FICTICIA'})
        self.assertNotIn('MEMORIA_GUARDIAN_FICTICIA', self.store.memory('casa_kiraz')['memory'])
        extra = self.store.create_bot('Guardián apoyo', 'guardian')
        self.assertNotEqual(self.store.home(extra['id']), self.store.home('guardian'))
        self.assertEqual(self.store.memory(extra['id'])['memory'], '')

    def test_traversal_absolute_and_backslash_rejected(self):
        for name in ('../casa_kiraz/secreto.txt', '/etc/passwd', 'a/../../x', 'dir\\secreto', '', '\x00x'):
            with self.subTest(name=repr(name)):
                self.problem(403, safe_path, self.store.workspace('guardian'), name)

    def test_file_symlink_cannot_read_other_business(self):
        self.store.save_file('casa_kiraz', 'privado.txt', 'DATO_FICTICIO')
        (self.store.workspace('guardian') / 'enlace.txt').symlink_to(self.store.workspace('casa_kiraz') / 'privado.txt')
        self.problem(403, self.store.read_file, 'guardian', 'enlace.txt')
        self.assertNotIn('enlace.txt', [f['name'] for f in self.store.detail('guardian')['files']])

    def test_directory_symlink_cannot_write_other_business(self):
        (self.store.workspace('guardian') / 'otra_unidad').symlink_to(self.store.workspace('casa_kiraz'), target_is_directory=True)
        self.problem(403, self.store.save_file, 'guardian', 'otra_unidad/no.txt', 'FICTICIO')
        self.assertFalse((self.store.workspace('casa_kiraz') / 'no.txt').exists())

    def test_overwrite_is_blocked_and_original_preserved(self):
        self.store.save_file('guardian', 'conservar.txt', 'original')
        self.problem(409, self.store.save_file, 'guardian', 'conservar.txt', 'reemplazo')
        self.assertEqual(self.store.read_file('guardian', 'conservar.txt')['content'], 'original')

    def test_memory_edit_preserves_backup(self):
        before = self.store.memory('guardian')['soul']
        self.store.memory('guardian', {'soul': 'Identidad nueva de prueba'})
        backups = list((self.root / 'backups/guardian').glob('*/SOUL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), before)
        self.assertEqual(self.store.memory('guardian')['soul'], 'Identidad nueva de prueba')

    def test_memory_backup_symlink_cannot_mix_businesses(self):
        (self.root / 'backups/guardian').symlink_to(self.store.workspace('casa_kiraz'), target_is_directory=True)
        self.problem(403, self.store.memory, 'guardian', {'soul': 'No debe cruzar negocios'})
        self.assertEqual(list(self.store.workspace('casa_kiraz').rglob('SOUL.md')), [])

    def test_memory_cannot_change_during_turn(self):
        self.store.db.execute("UPDATE bots SET status='pensando' WHERE id='guardian'")
        self.store.db.commit()
        self.problem(409, self.store.memory, 'guardian', {'memory': 'No actualizar'})

    def test_cross_business_messages_and_holding_bridge_denied(self):
        for source, target in [('guardian', 'casa_kiraz'), ('casa_kiraz', 'guardian'), ('holding', 'guardian'), ('holding', 'casa_kiraz')]:
            with self.subTest(source=source, target=target):
                self.problem(403, self.store.dm_create, source, target, 'FICTICIO')
                # El roster del bot ni siquiera contiene al otro negocio.
                self.problem(404, self.app.message_agent, source, {'target': target, 'body': 'FICTICIO'})
                self.problem(404, self.app.relay, source, target, 'FICTICIO')
        self.assertEqual(self.store.detail('casa_kiraz')['messages'], [])
        self.assertEqual(self.app.jobs, [])

    def test_same_business_message_is_queued_with_native_ack(self):
        extra = self.store.create_bot('Apoyo Guardián', 'guardian')
        self.assertEqual(extra['handle'], 'apoyo_guardian')
        self.assertEqual([t['id'] for t in self.store.teammates('guardian')], [extra['id']])
        self.app.jobs = _Hold()  # la entrega real (turno Hermes) no se ejecuta en pruebas
        ack = self.app.message_agent('guardian', {'target': '@apoyo_guardian', 'body': 'Mensaje ficticio', 'expects_reply': True})
        self.assertEqual(ack['status'], 'queued')
        dm = self.store.dm(ack['delivery_id'])
        self.assertEqual((dm['from_bot'], dm['to_bot'], dm['depth'], dm['status']), ('guardian', extra['id'], 1, 'en_cola'))
        self.assertEqual(self.app.jobs.items, [{'kind': 'deliver', 'dm': ack['delivery_id']}])

    def test_message_chains_are_bounded(self):
        extra = self.store.create_bot('Apoyo Guardián', 'guardian')
        self.problem(409, self.store.dm_create, 'guardian', extra['id'], 'x', True, 'cadena', MAX_DM_HOPS + 1)
        self.app.jobs = _Hold()
        self.app.turn_context['guardian'] = {'chain': 'cadena', 'depth': 1, 'sent': 0}
        for _ in range(8):
            self.store.dm_create('guardian', extra['id'], 'x', True, 'cadena', 1)
        self.problem(409, self.app.message_agent, 'guardian', {'target': 'apoyo_guardian', 'body': 'uno más'})

    def test_reply_goes_back_to_sender_only_when_expected(self):
        extra = self.store.create_bot('Apoyo Guardián', 'guardian')
        self.app.jobs = _Hold()
        wanted = self.store.dm_create('guardian', extra['id'], 'pregunta', True)
        silent = self.store.dm_create('guardian', extra['id'], 'aviso', False)
        self.app.after_turn(wanted, {'mode': 'incoming'}, 'respuesta', 'completo')
        self.app.after_turn(silent, {'mode': 'incoming'}, 'ok', 'completo')
        self.assertEqual(self.store.dm(wanted)['reply'], 'respuesta')
        self.assertEqual(self.app.jobs.items, [{'kind': 'reply', 'dm': wanted}])

    def test_paid_profiles_and_tampered_model_rejected(self):
        for profile in ('grok', 'investigacion', 'anthropic', 'xai', 'gemini'):
            with self.subTest(profile=profile):
                self.problem(400, self.store.profile, 'guardian', profile)
        self.store.db.execute("UPDATE bots SET model='xai/grok-3-mini' WHERE id='guardian'")
        self.store.db.commit()
        self.problem(403, self.app.send, 'guardian', 'No ejecutar')


class ApprovalAndAuthTests(Fixture):
    def test_password_hashed_and_setup_once(self):
        password = 'Prueba-local-aislada-123'
        self.problem(400, self.store.setup_password, 'corta')
        self.store.setup_password(password)
        self.assertNotIn(password, self.store.setting('password'))
        self.assertTrue(self.store.password_ok(password))
        self.assertFalse(self.store.password_ok('incorrecta'))
        self.problem(409, self.store.setup_password, 'Otra-clave-local-123')

    def test_session_expiration(self):
        token, session = self.store.login()
        self.assertIsNotNone(self.store.session(token))
        session['expires'] = time.time() - 1
        self.assertIsNone(self.store.session(token))

    def test_approval_executes_exact_payload_once_under_concurrency(self):
        payload = {'to': 'ficticio@example.invalid', 'body': 'Borrador ficticio'}
        approval = self.store.approval('guardian', 'gmail_send', payload)
        barrier = threading.Barrier(8)
        calls = []
        calls_lock = threading.Lock()
        def execute(bot_id, action, actual):
            with calls_lock:
                calls.append((bot_id, action, actual))
            return {'local_test': True}
        def decide(_):
            barrier.wait(timeout=5)
            try:
                return self.store.decide(approval['id'], 'approve', execute)['status']
            except Problem as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(decide, range(8)))
        self.assertEqual(calls, [('guardian', 'gmail_send', payload)])
        self.assertEqual(results.count('completa'), 1)
        self.assertEqual(results.count(409), 7)

    def test_rejected_expired_and_tampered_approvals_do_not_execute(self):
        calls = []
        execute = lambda *args: calls.append(args)
        rejected = self.store.approval('guardian', 'gmail_send', {'body': 'ficticio'})
        self.assertEqual(self.store.decide(rejected['id'], 'reject', execute)['status'], 'rechazada')
        self.problem(409, self.store.decide, rejected['id'], 'approve', execute)
        expired = self.store.approval('guardian', 'calendar_create', {'title': 'ficticio'})
        self.store.db.execute('UPDATE approvals SET created=? WHERE id=?', (time.time() - 901, expired['id']))
        self.store.db.commit()
        self.problem(409, self.store.decide, expired['id'], 'approve', execute)
        tampered = self.store.approval('guardian', 'gmail_send', {'body': 'original'})
        self.store.db.execute('UPDATE approvals SET payload=? WHERE id=?', ('{"body":"cambiado"}', tampered['id']))
        self.store.db.commit()
        self.problem(403, self.store.decide, tampered['id'], 'approve', execute)
        self.assertEqual(calls, [])

    def test_unassigned_account_fails_closed_and_never_calls_composio(self):
        approval = self.store.approval('guardian', 'gmail_send', {'para': ['a@example.com'], 'asunto': 'x', 'cuerpo': 'No enviar'})
        with patch.object(self.app.mcp, 'discover', return_value=FAKE_STATUS), patch.object(self.app.mcp, 'call') as call:
            result = self.store.decide(approval['id'], 'approve', self.app.mcp.execute_action)
        self.assertEqual(result['status'], 'fallida')
        self.assertIn('no está asignado', result['result']['error'])
        call.assert_not_called()
        self.problem(409, self.store.decide, approval['id'], 'approve', self.app.mcp.execute_action)

    def test_exclusive_account_belongs_to_one_business(self):
        self.store.assign_account('gmail', 'gmail_ficticia', 'casa_kiraz')
        with patch.object(self.app.mcp, 'discover', return_value=FAKE_STATUS):
            self.assertEqual(self.app.mcp.account_for('casa_kiraz', 'gmail'), 'gmail_ficticia')
            self.problem(403, self.app.mcp.account_for, 'guardian', 'gmail')
            self.problem(403, self.app.mcp.account_for, 'holding', 'gmail')
            self.problem(403, self.app.mcp.gmail_search, 'guardian', '')
            self.store.assign_account('gmail', 'gmail_ficticia', 'ninguno')
            self.problem(403, self.app.mcp.account_for, 'casa_kiraz', 'gmail')
        self.problem(400, self.store.assign_account, 'googledrive', 'x_cuenta', 'guardian')
        self.problem(400, self.store.assign_account, 'gmail', 'gmail_ficticia', 'otro_negocio')

    def test_proposal_is_normalized_and_never_executes(self):
        self.store.assign_account('gmail', 'gmail_ficticia', 'guardian')
        with patch.object(self.app.mcp, 'discover', return_value=FAKE_STATUS), patch.object(self.app.mcp, 'call') as call:
            made = self.app.propose('guardian', 'gmail_send', {'to': 'cliente@example.com', 'subject': 'Hola', 'body': 'Texto'})
            self.problem(400, self.app.propose, 'guardian', 'gmail_send', {'to': 'no-es-correo', 'subject': 'Hola', 'body': 'Texto'})
            self.problem(403, self.app.propose, 'guardian', 'wire_transfer', {})
            self.problem(403, self.app.propose, 'casa_kiraz', 'gmail_send', {'to': 'cliente@example.com', 'subject': 'Hola', 'body': 'Texto'})
        call.assert_not_called()
        row = self.store.approvals('guardian')[0]
        self.assertEqual((row['id'], row['status']), (made['approval_id'], 'pendiente'))
        self.assertEqual(row['payload'], {'para': ['cliente@example.com'], 'cc': [], 'bcc': [], 'asunto': 'Hola', 'cuerpo': 'Texto'})

    def test_approved_write_uses_only_the_business_account_once(self):
        self.store.assign_account('gmail', 'gmail_ficticia', 'guardian')
        sent = []
        def call(key, arguments, timeout=90):
            sent.append((key, arguments))
            return {'data': {'results': [{'response': {'successful': True, 'data': {'id': 'msg1'}}}]}}, False
        with patch.object(self.app.mcp, 'discover', return_value=FAKE_STATUS), patch.object(self.app.mcp, 'call', side_effect=call):
            made = self.app.propose('guardian', 'gmail_send', {'to': 'cliente@example.com', 'subject': 'Hola', 'body': 'Texto'})
            self.assertEqual(sent, [])
            result = self.store.decide(made['approval_id'], 'approve', self.app.mcp.execute_action)
            self.problem(409, self.store.decide, made['approval_id'], 'approve', self.app.mcp.execute_action)
        self.assertEqual(result['status'], 'completa')
        self.assertEqual(len(sent), 1)
        tool = sent[0][1]['tools'][0]
        self.assertEqual((sent[0][0], tool['tool_slug'], tool['account']), ('COMPOSIO_MULTI_EXECUTE_TOOL', 'GMAIL_SEND_EMAIL', 'gmail_ficticia'))
        self.assertEqual(tool['arguments']['recipient_email'], 'cliente@example.com')

    def test_composio_key_is_validated_and_stored_private(self):
        self.problem(400, self.app.mcp.check_key, 'corta')
        self.problem(400, self.app.mcp.check_key, 'con espacios y símbolos !!')
        target = self.root / 'env-ficticio'
        with patch.object(composio_mcp, 'ENV_FILE', target):
            self.assertIsNone(composio_mcp.read_env_key())
            composio_mcp.save_env_key('ck_llave_ficticia_0123456789')
            self.assertEqual(composio_mcp.read_env_key(), 'ck_llave_ficticia_0123456789')
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            composio_mcp.save_env_key('ck_otra_llave_ficticia_987654')
            self.assertEqual(target.read_text().count('COMPOSIO_API_KEY='), 1)

    def test_engine_token_bound_to_bot_and_expiration(self):
        self.store.engine_tickets['ficticio-efimero'] = {'bot_id': 'guardian', 'expires': time.time() + 30}
        self.problem(403, self.app.engine_tool, 'invalido', {'bot_id': 'guardian', 'tool': 'list_files'})
        self.problem(403, self.app.engine_tool, 'ficticio-efimero', {'bot_id': 'casa_kiraz', 'tool': 'list_files'})
        self.problem(403, self.app.engine_tool, 'ficticio-efimero', {'bot_id': 'guardian', 'tool': 'terminal'})
        task = self.app.engine_tool('ficticio-efimero', {'bot_id': 'guardian', 'tool': 'task_create', 'arguments': {'title': 'Prueba local'}})
        self.assertEqual(task['bot_id'], 'guardian')
        self.store.engine_tickets['ficticio-efimero']['expires'] = time.time() - 1
        self.problem(403, self.app.engine_tool, 'ficticio-efimero', {'bot_id': 'guardian', 'tool': 'list_files'})

    def test_computer_needs_grant_and_only_one_bot_holds_it(self):
        deny = self.app.computer_gate('guardian', {'action': 'click', 'summary': 'clic'})
        self.assertFalse(deny['allow'])
        self.assertFalse(self.app.computer_gate('guardian', {'action': 'capture', 'free': True})['allow'])
        self.problem(404, self.app.screen)
        self.assertFalse(self.app.open_app('guardian', 'Calculator')['opened'])
        state = self.app.control('guardian', 'agent', 'session')
        self.assertEqual((state['owner'], state['bot_id'], state['mode']), ('agent', 'guardian', 'session'))
        self.assertTrue(self.app.computer_gate('guardian', {'action': 'click', 'summary': 'clic'})['allow'])
        self.assertFalse(self.app.computer_gate('casa_kiraz', {'action': 'capture', 'free': True})['allow'])
        self.problem(409, self.app.control, 'casa_kiraz', 'agent', 'session')
        self.problem(400, self.app.control, 'guardian', 'agent', 'modo_inventado')

    def test_step_mode_waits_for_joe_and_respects_denial(self):
        self.app.control('guardian', 'agent', 'step')
        self.assertTrue(self.app.computer_gate('guardian', {'action': 'capture', 'free': True})['allow'])
        for decision, expected in (('allow', True), ('deny', False)):
            with self.subTest(decision=decision):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(self.app.computer_gate, 'guardian', {'action': 'click', 'summary': 'clic en Enviar'})
                    for _ in range(100):
                        pending = self.app.computer_state()['pending']
                        if pending:
                            break
                        time.sleep(0.02)
                    self.assertEqual(pending['summary'], 'clic en Enviar')
                    self.problem(409, self.app.computer_decide, 'otro-id', 'allow')
                    self.app.computer_decide(pending['id'], decision)
                    self.assertEqual(future.result(timeout=5)['allow'], expected)
                self.assertIsNone(self.app.computer_state()['pending'])

    def test_taking_control_stops_holder_and_expiry_revokes(self):
        stopped = []
        fake = SimpleNamespace(pid=999999, poll=lambda: None)
        self.app.control('guardian', 'agent', 'step')
        self.store.active_processes['guardian'] = fake
        with ThreadPoolExecutor(max_workers=1) as pool, patch('server.os.killpg', side_effect=lambda pid, sig: stopped.append(pid)):
            future = pool.submit(self.app.computer_gate, 'guardian', {'action': 'type', 'summary': 'escribir'})
            for _ in range(100):
                if self.app.computer_state()['pending']:
                    break
                time.sleep(0.02)
            result = self.app.control('guardian', 'user')
            self.assertFalse(future.result(timeout=5)['allow'])
        self.assertEqual(stopped, [999999])
        self.assertEqual((result['owner'], result['bot_id'], result['pending']), ('user', None, None))
        self.assertFalse(self.app.computer_gate('guardian', {'action': 'capture', 'free': True})['allow'])
        self.app.control('guardian', 'agent', 'session')
        self.store.computer['expires'] = time.time() - 1
        self.assertFalse(self.app.computer_gate('guardian', {'action': 'click'})['allow'])
        self.assertEqual(self.app.computer_state()['owner'], 'user')


class HTTPMemoryTests(Fixture):
    def request(self, method='GET', path='/api/state', data=None, headers=None, raw=None):
        handler = Handler.__new__(Handler)
        handler.server = SimpleNamespace(app=self.app)
        handler.path = path
        handler.command = method
        handler.headers = Message()
        defaults = {'Host': '127.0.0.1:8787'}
        if method == 'POST':
            defaults.update({'Origin': 'http://127.0.0.1:8787', 'Content-Type': 'application/json'})
        defaults.update(headers or {})
        body = raw if raw is not None else json.dumps(data or {}).encode()
        if method == 'POST':
            defaults.setdefault('Content-Length', str(len(body)))
        for name, value in defaults.items():
            if value is not None:
                handler.headers[name] = value
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        response = {'headers': {}}
        handler.send_response = lambda status: response.update(status=status)
        handler.send_header = lambda key, value: response['headers'].update({key: value})
        handler.end_headers = lambda: None
        getattr(handler, 'do_' + method)()
        response['data'] = json.loads(handler.wfile.getvalue())
        return response

    def session_headers(self, csrf=True):
        token, session = self.store.login()
        result = {'Cookie': 'joe_session=' + token}
        if csrf:
            result['X-CSRF-Token'] = session['csrf']
        return result

    def test_unauthenticated_api_is_denied(self):
        self.assertEqual(self.request()['status'], 401)
        response = self.request(path='/api/session')
        self.assertEqual(response['status'], 200)
        self.assertFalse(response['data']['authenticated'])
        self.assertIsNone(response['data']['csrf'])

    def test_new_private_routes_require_the_password(self):
        for path in ('/api/apps', '/api/computer/frame', '/api/audio/ficticio', '/api/bots/guardian'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)['status'], 401)
        for path, data in (('/api/apps/key', {'key': 'ck_llave_ficticia_0123456789'}), ('/api/apps/assign', {'toolkit': 'gmail', 'scope': 'guardian'}),
                           ('/api/computer/decide', {'id': 'x', 'decision': 'allow'}), ('/api/bots/guardian/computer', {'owner': 'agent'}),
                           ('/api/bots/guardian/speak', {'text': 'hola'}), ('/api/voice', {'voice': 'x'})):
            with self.subTest(path=path):
                self.assertEqual(self.request('POST', path, data)['status'], 401)
                self.assertEqual(self.request('POST', path, data, self.session_headers(csrf=False))['status'], 403)
        self.assertEqual(self.store.computer['owner'], 'user')
        self.assertEqual(self.store.account_map(), {})

    def test_stale_tabs_are_told_to_reload(self):
        import server
        headers = self.session_headers()
        state = self.request(headers=headers)['data']
        self.assertEqual(state['build'], server.build_id())
        self.assertEqual(self.request(path='/api/session')['data']['build'], state['build'])
        # Pestaña anterior a una actualización: no manda la huella (o manda una vieja).
        for stale in ({}, {'X-JOE-Build': 'huella-antigua'}):
            detail = self.request(path='/api/bots/guardian', headers={**headers, **stale})['data']
            self.assertEqual(detail['error'], server.STALE_TAB)
        fresh = self.request(path='/api/bots/guardian', headers={**headers, 'X-JOE-Build': state['build']})['data']
        self.assertNotIn('error', fresh)

    def test_staging_never_touches_the_real_env_file(self):
        staged = Application(self.store, 8788, staging=True)
        self.assertEqual(staged.mcp.env_file, self.root / '.env')
        self.assertIsNone(self.app.mcp.env_file)  # producción: app/.env
        with patch.object(staged.mcp, 'check_key'):
            staged.mcp.save_key('ck_llave_ficticia_0123456789')
        self.assertEqual(staged.mcp.key(), 'ck_llave_ficticia_0123456789')
        self.assertEqual(staged.mcp.auth_mode(), 'Llave propia en .env')
        with patch.dict('os.environ', {'JOE_HQ_COMPOSIO_SIMULADO': 'https://sitio-externo.example/mcp'}):
            self.problem(503, Application, self.store, 8788, True)
            self.assertEqual(Application(self.store, 8787, False).mcp.endpoint, composio_mcp.ENDPOINT)

    def test_host_origin_and_cross_site_are_rejected(self):
        for headers in ({'Host': 'evil.invalid'}, {'Host': 'localhost:8787.evil.invalid'},
                        {'Origin': 'https://evil.invalid'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(path='/api/session', headers=headers)['status'], 403)

    def test_csrf_required_for_authenticated_mutation(self):
        for csrf in (None, 'incorrecto'):
            headers = self.session_headers(csrf=False)
            headers['X-CSRF-Token'] = csrf
            response = self.request('POST', '/api/bots/guardian/tasks', {'title': 'No crear'}, headers)
            self.assertEqual(response['status'], 403)
        response = self.request('POST', '/api/bots/guardian/tasks', {'title': 'Crear local'}, self.session_headers())
        self.assertEqual(response['status'], 200)
        self.assertEqual(response['data']['bot_id'], 'guardian')

    def test_login_requires_local_origin_and_json(self):
        self.assertEqual(self.request('POST', '/api/setup', {'password': 'Una-clave-local-123'}, {'Origin': None})['status'], 403)
        self.assertEqual(self.request('POST', '/api/setup', {'password': 'Una-clave-local-123'}, {'Content-Type': 'text/plain'})['status'], 415)

    def test_setup_cookie_is_httponly_and_samesite(self):
        response = self.request('POST', '/api/setup', {'password': 'Una-clave-local-123'})
        self.assertEqual(response['status'], 200)
        self.assertIn('HttpOnly', response['headers']['Set-Cookie'])
        self.assertIn('SameSite=Strict', response['headers']['Set-Cookie'])
        self.assertTrue(response['data']['csrf'])

    def test_login_rate_limit(self):
        self.store.setup_password('Una-clave-local-123')
        for _ in range(8):
            self.assertEqual(self.request('POST', '/api/login', {'password': 'incorrecta'})['status'], 401)
        self.assertEqual(self.request('POST', '/api/login', {'password': 'incorrecta'})['status'], 429)

    def test_invalid_json_and_chunked_rejected(self):
        for raw in (b'[]', b'{malformado'):
            self.assertEqual(self.request('POST', '/api/login', raw=raw)['status'], 400)
        self.assertEqual(self.request('POST', '/api/login', headers={'Transfer-Encoding': 'chunked'})['status'], 400)

    def test_engine_callback_has_own_bearer_auth(self):
        self.assertEqual(self.request('POST', '/api/engine/tool', {'bot_id': 'guardian', 'tool': 'list_files'})['status'], 401)
        self.store.engine_tickets['solo-prueba-local'] = {'bot_id': 'guardian', 'expires': time.time() + 30}
        headers = {'Authorization': 'Bearer solo-prueba-local', 'Origin': None}
        wrong = self.request('POST', '/api/engine/tool', {'bot_id': 'casa_kiraz', 'tool': 'list_files'}, headers)
        self.assertEqual(wrong['status'], 403)
        right = self.request('POST', '/api/engine/tool', {'bot_id': 'guardian', 'tool': 'list_files'}, headers)
        self.assertEqual(right['status'], 200)

    def test_security_headers_are_present(self):
        response = self.request(path='/api/session')
        headers = response['headers']
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])


class _Hold:
    """Cola de entregas que solo registra: evita lanzar turnos Hermes reales en pruebas."""
    def __init__(self): self.items = []
    def append(self, job): self.items.append(job)
    def remove(self, job): self.items.remove(job)
    def __iter__(self): return iter(())


FAKE_STATUS = {name: {'active': True, 'accounts': [{'id': name + '_ficticia', 'label': 'ficticia'}]}
               for name in ('googledrive', 'googlesheets', 'gmail', 'googlecalendar', 'instagram', 'github')}


class DriveScopeTests(Fixture):
    def metadata(self, key, **extra):
        return {'id': key, 'name': 'Ficticio', 'mimeType': 'text/plain', 'parents': [], **extra}

    def test_only_read_tool_slugs_are_available(self):
        self.problem(403, self.app.mcp.execute, 'guardian', 'GMAIL_SEND_EMAIL', {})
        self.problem(403, self.app.mcp.execute, 'guardian', 'GOOGLEDRIVE_DELETE_FILE', {})
        self.problem(403, self.app.mcp.execute, 'guardian', 'GOOGLEDRIVE_DELETE_FILE', {}, True)
        self.problem(403, self.app.mcp.execute, 'guardian', 'COMPOSIO_REMOTE_BASH_TOOL', {}, True)

    def test_cross_business_drive_root_is_rejected(self):
        foreign = next(iter(self.app.mcp.permitted_roots('casa_kiraz')))
        with patch.object(self.app.mcp, 'execute', return_value=self.metadata(foreign)):
            self.problem(403, self.app.mcp.authorize, 'guardian', foreign)

    def test_child_in_own_folder_allowed_but_shortcut_denied(self):
        guardian_root = next(iter(self.app.mcp.permitted_roots('guardian')))
        leaf = 'ficticio_doc_12345'
        def fetch(bot_id, slug, arguments, write=False):
            key = arguments['fileId']
            return self.metadata(key, parents=[guardian_root] if key == leaf else [])
        with patch.object(self.app.mcp, 'execute', side_effect=fetch):
            self.assertEqual(self.app.mcp.authorize('guardian', leaf)['id'], leaf)
        with patch.object(self.app.mcp, 'execute', return_value=self.metadata(leaf, parents=[guardian_root], mimeType='application/vnd.google-apps.shortcut')):
            self.problem(403, self.app.mcp.authorize, 'guardian', leaf)

    def test_parent_cycles_and_invalid_ids_rejected(self):
        leaf = 'ficticio_cycle_123'
        with patch.object(self.app.mcp, 'execute', return_value=self.metadata(leaf, parents=[leaf])):
            self.problem(403, self.app.mcp.authorize, 'guardian', leaf)
        self.problem(403, self.app.mcp.authorize, 'guardian', '../../invalid')

    def test_delete_and_append_are_fenced_to_the_business_folder(self):
        guardian_root = next(iter(self.app.mcp.permitted_roots('guardian')))
        leaf = 'ficticio_doc_12345'
        def fetch(bot_id, slug, arguments, write=False):
            self.assertFalse(write)
            key = arguments['fileId']
            return self.metadata(key, parents=[guardian_root] if key == leaf else [], mimeType='application/vnd.google-apps.spreadsheet')
        with patch.object(self.app.mcp, 'execute', side_effect=fetch):
            ok = self.app.mcp.validate_action('guardian', 'drive_delete', {'file_id': leaf})
            self.assertEqual(ok['file_id'], leaf)
            self.problem(403, self.app.mcp.validate_action, 'casa_kiraz', 'drive_delete', {'file_id': leaf})
            self.problem(403, self.app.mcp.validate_action, 'guardian', 'drive_delete', {'file_id': guardian_root})
            self.problem(403, self.app.mcp.validate_action, 'casa_kiraz', 'sheets_append', {'spreadsheet_id': leaf, 'rango': 'A1', 'filas': [['x']]})
            self.problem(400, self.app.mcp.validate_action, 'guardian', 'sheets_append', {'spreadsheet_id': leaf, 'rango': 'A1', 'filas': 'no-lista'})

    def test_listing_discards_foreign_parents_and_shortcuts(self):
        guardian_root = next(iter(self.app.mcp.permitted_roots('guardian')))
        rows = [self.metadata('ficticio_good_123', parents=[guardian_root]),
                self.metadata('ficticio_wrong_123', parents=['otra_unidad']),
                self.metadata('ficticio_shortcut_123', parents=[guardian_root], mimeType='application/vnd.google-apps.shortcut')]
        with patch.object(self.app.mcp, 'execute', return_value={'files': rows}):
            result = self.app.mcp.list('guardian')
        self.assertEqual([r['id'] for r in result['files']], ['ficticio_good_123'])


class BridgeSmokeTests(unittest.TestCase):
    def test_json_diagnostics_and_paid_model_rejection_without_model_network(self):
        if not HERMES_PYTHON.is_file():
            self.skipTest('Runtime Hermes existente ausente; no se instala otro.')
        fixture = RUN_ROOT / ('bridge-' + uuid.uuid4().hex)
        fixture.mkdir()
        base = {'home': str(fixture / 'home'), 'workspace': str(fixture / 'files')}
        for command, values in [('diagnose', {}), ('diagnose', {'model': 'xai/grok-3-mini'})]:
            request = dict(base, command=command, **values)
            process = subprocess.run([str(HERMES_PYTHON), '-B', str(APP / 'local_engine/hermes_bridge.py')],
                                     input=json.dumps(request), capture_output=True, text=True, timeout=15)
            result = json.loads(process.stdout)
            self.assertEqual(process.stderr, '')
            self.assertNotIn('access_token', process.stdout)
            if values:
                self.assertFalse(result['ok'])
                self.assertIn('Solo se permiten', result['error'])
            else:
                self.assertIn('diagnosis', result)
                self.assertEqual(result['diagnosis']['provider'], 'openai-codex')


if __name__ == '__main__':
    unittest.main(verbosity=2)
