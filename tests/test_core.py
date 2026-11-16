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

    def test_roster_lists_every_bot_with_its_relation(self):
        team = {t['id']: t['relation'] for t in self.store.teammates('guardian')}
        self.assertEqual(team, {'casa_kiraz': 'sibling', 'holding': 'parent'})
        extra = self.store.create_bot('Apoyo Guardián', 'guardian')
        self.assertEqual(extra['handle'], 'apoyo_guardian')
        self.assertEqual({t['id']: t['relation'] for t in self.store.teammates('holding')},
                         {'guardian': 'parent', 'casa_kiraz': 'parent', extra['id']: 'parent'})
        self.problem(404, self.app.message_agent, 'guardian', {'target': 'no_existe', 'body': 'x'})
        self.problem(400, self.store.dm_create, 'guardian', 'guardian', 'x')

    def test_same_business_and_holding_messages_are_queued_directly(self):
        extra = self.store.create_bot('Apoyo Guardián', 'guardian')
        self.app.jobs = _Hold()  # la entrega real (turno Hermes) no se ejecuta en pruebas
        for source, target in (('guardian', 'apoyo_guardian'), ('guardian', 'holding'), ('holding', 'casa_kiraz'), ('casa_kiraz', 'holding')):
            with self.subTest(source=source, target=target):
                ack = self.app.message_agent(source, {'target': '@' + target, 'body': 'Mensaje ficticio', 'expects_reply': True})
                self.assertEqual(ack['status'], 'queued')
                dm = self.store.dm(ack['delivery_id'])
                self.assertEqual((dm['from_bot'], dm['depth'], dm['status']), (source, 1, 'en_cola'))
                self.assertEqual(self.app.jobs.items[-1], {'kind': 'deliver', 'dm': ack['delivery_id'], 'task_id': None})
        self.assertEqual(self.store.approvals(), [])

    def test_guardian_and_kiraz_messages_wait_for_joe(self):
        self.app.jobs = _Hold()
        for source, target in (('guardian', 'casa_kiraz'), ('casa_kiraz', 'guardian')):
            with self.subTest(source=source):
                ack = self.app.message_agent(source, {'target': target, 'body': 'Propuesta de promoción conjunta', 'expects_reply': True})
                self.assertEqual(ack['status'], 'awaiting_joe_approval')
                self.assertEqual(self.store.dms(source), [])            # nada cruzó todavía
                self.assertEqual(self.app.jobs.items, [])
                row = self.store.approvals(source)[0]
                self.assertEqual((row['action'], row['status'], row['payload']['mensaje']), ('cross_message', 'pendiente', 'Propuesta de promoción conjunta'))
                self.assertEqual(self.store.decide(row['id'], 'reject', self.app.execute_approved)['status'], 'rechazada')
                self.assertEqual(self.store.dms(source), [])
        # Aprobado por Joe: se entrega una sola vez.
        ack = self.app.message_agent('guardian', {'target': 'casa_kiraz', 'body': 'Texto aprobado', 'expects_reply': True})
        done = self.store.decide(ack['approval_id'], 'approve', self.app.execute_approved)
        self.assertEqual(done['status'], 'completa')
        dm = self.store.dm(done['result']['delivery_id'])
        self.assertEqual((dm['from_bot'], dm['to_bot'], dm['body']), ('guardian', 'casa_kiraz', 'Texto aprobado'))
        self.assertEqual(len(self.app.jobs.items), 1)
        self.problem(409, self.store.decide, ack['approval_id'], 'approve', self.app.execute_approved)
        # Un bot no puede fabricar esa aprobación por request_action, ni mandar textos largos a otro negocio.
        with patch.object(self.app.mcp, 'discover', return_value=FAKE_STATUS):
            self.problem(403, self.app.propose, 'guardian', 'cross_message', {'de_id': 'guardian', 'para_id': 'casa_kiraz', 'mensaje': 'x'})
        self.problem(400, self.app.message_agent, 'guardian', {'target': 'holding', 'body': 'x' * 4001})

    def test_holding_never_bridges_guardian_and_kiraz(self):
        self.app.jobs = _Hold()
        for first, other in (('guardian', 'casa_kiraz'), ('casa_kiraz', 'guardian')):
            with self.subTest(first=first):
                ack = self.app.message_agent(first, {'target': 'holding', 'body': 'Dato interno ficticio'})
                chain = self.store.dm(ack['delivery_id'])['chain']
                self.app.turn_context['holding'] = {'chain': chain, 'depth': 1, 'sent': 0}   # Holding atendiendo ese mensaje
                self.problem(403, self.app.message_agent, 'holding', {'target': other, 'body': 'Reenvío'})
                self.problem(403, self.app.assign_task, 'holding', {'target': other, 'title': 'Reenviar', 'details': 'x'})
                self.assertEqual(self.app.message_agent('holding', {'target': first, 'body': 'Respuesta'})['status'], 'queued')
                self.assertEqual([d for d in self.store.dms(other) if d['chain'] == chain and other in (d['from_bot'], d['to_bot'])], [])
                self.assertEqual(self.store.detail(other)['tasks'], [])
                self.app.turn_context.pop('holding')

    def test_turn_policies_between_businesses(self):
        policy = Application.turn_policy
        self.assertIsNone(policy('guardian', None))
        self.assertIsNone(policy('guardian', {'mode': 'incoming', 'relation': 'same'}))
        self.assertEqual(policy('casa_kiraz', {'mode': 'incoming', 'relation': 'sibling'}), 'clean')
        self.assertEqual(policy('guardian', {'mode': 'incoming', 'relation': 'sibling'}), 'clean')
        self.assertIsNone(policy('guardian', {'mode': 'reply', 'relation': 'sibling'}))   # la respuesta nació en sala limpia
        for mode in ('incoming', 'reply'):
            self.assertEqual(policy('holding', {'mode': mode, 'relation': 'parent'}), 'no_persist')
            self.assertIsNone(policy('guardian', {'mode': mode, 'relation': 'parent'}))

    def test_server_enforces_policy_on_tool_calls(self):
        self.store.engine_tickets['limpia'] = {'bot_id': 'casa_kiraz', 'expires': time.time() + 30, 'policy': 'clean'}
        self.store.engine_tickets['hold'] = {'bot_id': 'holding', 'expires': time.time() + 30, 'policy': 'no_persist'}
        call = lambda token, bot, tool, **a: self.app.engine_tool(token, {'bot_id': bot, 'tool': tool, 'arguments': a})
        for tool in ('list_files', 'save_file', 'drive_list', 'drive_read', 'gmail_search', 'request_action', 'message_agent',
                     'assign_task', 'computer_gate', 'open_app', 'sheets_read', 'calendar_list'):
            with self.subTest(tool=tool):
                self.problem(403, call, 'limpia', 'casa_kiraz', tool)
        self.assertEqual(call('limpia', 'casa_kiraz', 'task_create', title='Revisar propuesta')['bot_id'], 'casa_kiraz')
        for tool in ('save_file', 'computer_gate', 'open_app'):
            self.problem(403, call, 'hold', 'holding', tool, path='x.md', content='x', name='Calculator')
        self.assertEqual(call('hold', 'holding', 'list_files'), {'files': []})
        self.assertEqual(self.store.detail('holding')['files'], [])

    def test_tasks_travel_between_bots_with_origin(self):
        self.app.jobs = _Hold()
        ack = self.app.assign_task('guardian', {'target': 'holding', 'title': 'Consolidar ventas', 'details': 'Semana 46'})
        self.assertEqual(ack['status'], 'queued')
        task = self.store.detail('holding')['tasks'][0]
        self.assertEqual((task['title'], task['origin'], task['status']), ('Consolidar ventas', 'Guardián Ventas', 'pendiente'))
        self.assertEqual(self.app.jobs.items[-1]['task_id'], task['id'])
        self.assertIn('[TASK ' + task['id'] + ']', self.store.dm(ack['delivery_id'])['body'])
        self.problem(404, self.store.task_complete, 'guardian', task['id'])      # solo el dueño la cierra
        self.assertEqual(self.store.task_complete('holding', task['id'])['status'], 'completa')
        # Entre hermanos la tarea también espera a Joe y no aparece antes.
        ack = self.app.assign_task('guardian', {'target': 'casa_kiraz', 'title': 'Promo conjunta', 'details': 'Viernes'})
        self.assertEqual(ack['status'], 'awaiting_joe_approval')
        self.assertEqual(self.store.detail('casa_kiraz')['tasks'], [])
        self.store.decide(ack['approval_id'], 'approve', self.app.execute_approved)
        self.assertEqual(self.store.detail('casa_kiraz')['tasks'][0]['origin'], 'Guardián Ventas')

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

    EFFECTS = [{'action': 'click', 'element': {'index': 4, 'role': 'AXButton', 'label': 'Enviar', 'known': True}},
               {'action': 'click', 'coordinate': [10, 20]}, {'action': 'double_click', 'element': {'index': 1, 'role': 'AXCell', 'label': 'x', 'known': True}},
               {'action': 'right_click', 'coordinate': [1, 1]}, {'action': 'middle_click', 'coordinate': [1, 1]},
               {'action': 'drag', 'from': [1, 1], 'to': [9, 9]}, {'action': 'type', 'text': 'hola'}, {'action': 'key', 'keys': 'return'},
               {'action': 'key', 'keys': 'cmd+backspace'}, {'action': 'set_value', 'value': '5', 'element': {'index': 2, 'role': 'AXPopUpButton', 'label': 'x', 'known': True}},
               {'action': 'scroll', 'coordinate': [5, 5]}, {'action': 'scroll'}, {'action': 'scroll', 'modifiers': ['cmd'], 'element': {'index': 1, 'role': 'AXScrollArea', 'label': '', 'known': True}},
               {'action': 'scroll', 'element': {'index': 3, 'role': 'AXSlider', 'label': 'Volumen', 'known': True}},
               {'action': 'scroll', 'element': {'index': 9, 'role': '', 'label': '', 'known': False}},
               {'action': 'accion_que_no_existe'}, {'action': ''}, {}]
    LOOKS = [{'action': 'capture'}, {'action': 'list_apps'}, {'action': 'list_windows'}, {'action': 'wait'}, {'action': 'focus_app', 'app': 'Safari'},
             {'action': 'scroll', 'element': {'index': 1, 'role': 'AXScrollArea', 'label': '', 'known': True}},
             {'action': 'scroll', 'element': {'index': 2, 'role': 'AXWebArea', 'label': 'Página', 'known': True}}]

    def test_computer_needs_grant_and_only_one_bot_holds_it(self):
        for step in self.LOOKS + self.EFFECTS:
            self.assertFalse(self.app.computer_gate('guardian', step)['allow'])       # sin préstamo: nada, ni mirar
        self.problem(404, self.app.screen)
        with patch('server.subprocess.run') as run:
            self.assertFalse(self.app.open_app('guardian', 'Calculator')['opened'])
            run.assert_not_called()
        state = self.app.control('guardian', 'agent', 'view')
        self.assertEqual((state['owner'], state['bot_id'], state['mode']), ('agent', 'guardian', 'view'))
        self.assertFalse(self.app.computer_gate('casa_kiraz', {'action': 'capture'})['allow'])
        self.problem(409, self.app.control, 'casa_kiraz', 'agent', 'view')
        for mode in ('session', 'modo_inventado', '', None):
            self.problem(400, self.app.control, 'guardian', 'agent', mode)

    def test_view_mode_can_look_but_never_act(self):
        self.app.control('guardian', 'agent', 'view')
        for step in self.LOOKS:
            with self.subTest(look=step):
                self.assertTrue(self.app.computer_gate('guardian', step)['allow'])
        for step in self.EFFECTS:
            with self.subTest(effect=step):
                started = time.time()
                verdict = self.app.computer_gate('guardian', step)
                self.assertIs(verdict['allow'], False)
                self.assertIn('solo ver', verdict['reason'])
                self.assertLess(time.time() - started, 1)                 # se niega al instante: no hay a quién pedirle
                self.assertIsNone(self.app.computer_state()['pending'])   # ni siquiera se ofrece aprobarlo
        blocked = [e for e in self.store.computer['events'] if e.get('blocked')]
        self.assertEqual(len(blocked), len(self.EFFECTS))
        # Abrir apps: solo traer al frente una que ya corre; una cerrada no se lanza.
        with patch.object(self.app, 'app_running', return_value=False), patch('server.subprocess.run') as run:
            result = self.app.open_app('guardian', 'Mail')
            self.assertFalse(result['opened'])
            run.assert_not_called()
        with patch.object(self.app, 'app_running', return_value=True), patch('server.time.sleep'), \
                patch('server.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(self.app.open_app('guardian', 'Mail')['opened'])
            run.assert_called_once()

    def decide_when_pending(self, decision):
        for _ in range(200):
            pending = self.app.computer_state()['pending']
            if pending:
                self.app.computer_decide(pending['id'], decision)
                return pending
            time.sleep(0.01)
        self.fail('el paso nunca quedó pendiente')

    def test_step_mode_asks_joe_for_each_exact_step(self):
        self.app.control('guardian', 'agent', 'step')
        for step in self.LOOKS:
            self.assertTrue(self.app.computer_gate('guardian', step)['allow'])
        send = self.EFFECTS[0]
        with ThreadPoolExecutor(max_workers=1) as pool:
            for decision, expected in (('allow', True), ('deny', False), ('allow', True)):
                with self.subTest(decision=decision):
                    future = pool.submit(self.app.computer_gate, 'guardian', send)
                    pending = self.decide_when_pending(decision)
                    self.assertEqual(pending['summary'], 'Clic en botón «Enviar»')
                    self.assertIn('enviar', pending['warning'])
                    self.assertEqual(future.result(timeout=5)['allow'], expected)
                    self.assertIsNone(self.app.computer_state()['pending'])
            # Un permiso vale para UN paso: el siguiente vuelve a esperar, y todos los de efecto preguntan.
            for step in self.EFFECTS:
                with self.subTest(effect=step):
                    future = pool.submit(self.app.computer_gate, 'guardian', step)
                    self.assertFalse(future.done())
                    self.decide_when_pending('deny')
                    self.assertFalse(future.result(timeout=5)['allow'])
            future = pool.submit(self.app.computer_gate, 'guardian', {'action': 'type', 'text': 'Total: $1,250'})
            pending = self.decide_when_pending('allow')
            self.assertEqual(pending['summary'], 'Escribir texto «Total: $1,250»')
            self.assertTrue(future.result(timeout=5)['allow'])
            self.problem(409, self.app.computer_decide, 'otro-id', 'allow')
            self.problem(400, self.app.computer_decide, pending['id'], 'quizas')

    def test_changing_mode_or_taking_control_voids_a_pending_step(self):
        stopped = []
        fake = SimpleNamespace(pid=999999, poll=lambda: None)
        with ThreadPoolExecutor(max_workers=1) as pool, patch('server.os.killpg', side_effect=lambda pid, sig: stopped.append(pid)):
            # Joe cambia a «solo ver» mientras hay un paso esperando: aunque llegara un «permitir», no se ejecuta.
            self.app.control('guardian', 'agent', 'step')
            future = pool.submit(self.app.computer_gate, 'guardian', self.EFFECTS[0])
            for _ in range(200):
                pending = self.store.computer['pending']
                if pending:
                    break
                time.sleep(0.01)
            self.app.control('guardian', 'agent', 'view')
            pending['decision'] = 'allow'
            with self.app.gate:
                self.app.gate.notify_all()
            self.assertFalse(future.result(timeout=5)['allow'])
            # Tomar control: niega el paso pendiente y detiene el turno del bot.
            self.app.control('guardian', 'agent', 'step')
            self.store.active_processes['guardian'] = fake
            future = pool.submit(self.app.computer_gate, 'guardian', {'action': 'type', 'text': 'x'})
            for _ in range(200):
                if self.app.computer_state()['pending']:
                    break
                time.sleep(0.01)
            result = self.app.control('guardian', 'user')
            self.assertFalse(future.result(timeout=5)['allow'])
        self.assertEqual(stopped, [999999])
        self.assertEqual((result['owner'], result['bot_id'], result['pending']), ('user', None, None))
        self.assertFalse(self.app.computer_gate('guardian', {'action': 'capture'})['allow'])
        self.app.control('guardian', 'agent', 'step')
        self.store.computer['expires'] = time.time() - 1
        self.assertFalse(self.app.computer_gate('guardian', {'action': 'capture'})['allow'])
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
