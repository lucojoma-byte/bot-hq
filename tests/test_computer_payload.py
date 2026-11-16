"""Pruebas sin pantalla, red ni Hermes de la carga exacta que Joe autoriza."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_engine.computer_payload import (PayloadError, MAX_PAYLOAD_BYTES, freeze_payload,
                                           verify_payload, approved_arguments)
from local_engine.hermes_bridge import describe_step, guarded_computer_handler


class ComputerPayloadTests(unittest.TestCase):
    def test_full_unicode_text_and_suffix_survive_without_truncation(self):
        text = 'á🙂' * 2100 + '\nSUFIJO_VISIBLE_A_JOE'
        args = {'action': 'type', 'text': text, 'app': 'TextEdit', 'bring_to_front': False}
        step = describe_step('type', args)
        self.assertEqual(step['text'], text)
        self.assertEqual(step['payload']['arguments'], args)
        self.assertIn('SUFIJO_VISIBLE_A_JOE', step['payload']['arguments']['text'])
        self.assertEqual(verify_payload(step['payload'], step['digest'])['arguments']['text'], text)

    def test_keys_and_value_are_not_shortened(self):
        for action, key, value in [('key', 'keys', 'shift+' * 100 + 'return'),
                                   ('set_value', 'value', 'Valor de prueba ' * 100)]:
            with self.subTest(action=action):
                step = describe_step(action, {'action': action, key: value})
                self.assertEqual(step[key], value)
                self.assertEqual(step['payload']['arguments'][key], value)

    def test_canonical_hash_stable_and_preserves_json_types(self):
        first = {'action': 'click', 'coordinate': [12.5, 20], 'count': 1,
                 'foreground': False, 'flags': [True, False, None], 'nested': {'texto': 'José'}}
        second = dict(reversed(list(first.items())))
        payload, digest = freeze_payload('computer_use', first)
        self.assertEqual(freeze_payload('computer_use', second)[1], digest)
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), digest)
        self.assertIs(payload['arguments']['foreground'], False)
        self.assertIs(payload['arguments']['flags'][0], True)
        self.assertIsNone(payload['arguments']['flags'][2])
        self.assertIsInstance(payload['arguments']['coordinate'][0], float)
        self.assertIsInstance(payload['arguments']['coordinate'][1], int)

    def test_snapshot_is_detached_from_original_nested_arguments(self):
        args = {'action': 'click', 'coordinate': [5, 6], 'metadata': {'label': 'original'}}
        payload, digest = freeze_payload('computer_use', args)
        args['coordinate'][0] = 100
        args['metadata']['label'] = 'cambiado'
        self.assertEqual(payload['arguments']['coordinate'], [5, 6])
        self.assertEqual(payload['arguments']['metadata']['label'], 'original')
        self.assertEqual(verify_payload(payload, digest), payload)

    def test_changed_arguments_missing_digest_and_wrong_tool_are_denied(self):
        payload, digest = freeze_payload('computer_use', {'action': 'type', 'text': 'aprobado'})
        for invalid in ('', None, '0' * 64, 'x' * 64):
            with self.subTest(digest=invalid), self.assertRaises(PayloadError):
                verify_payload(payload, invalid)
        payload['arguments']['text'] = 'distinto'
        with self.assertRaises(PayloadError):
            verify_payload(payload, digest)
        other, other_digest = freeze_payload('open_app', {'name': 'Calculator'})
        with self.assertRaises(PayloadError):
            verify_payload(other, other_digest)
        self.assertEqual(verify_payload(other, other_digest, expected_tool='open_app'), other)

    def test_oversized_utf8_rejected_without_truncation(self):
        for text in ('x' * MAX_PAYLOAD_BYTES, 'é' * (MAX_PAYLOAD_BYTES // 2)):
            with self.subTest(length=len(text)), self.assertRaises(PayloadError):
                freeze_payload('computer_use', {'action': 'type', 'text': text})
        # El límite se aplica a bytes UTF8, con margen para el sobre JSON.
        accepted, _ = freeze_payload('computer_use', {'action': 'type', 'text': 'é' * 30000})
        self.assertEqual(len(accepted['arguments']['text']), 30000)

    def test_non_json_and_non_finite_arguments_rejected(self):
        for args in ({1: 'clave no textual'}, {'v': float('nan')}, {'v': float('inf')},
                     {'v': (1, 2)}, {'v': object()}, ['lista'], {'v': '\ud800'}):
            with self.subTest(kind=type(args).__name__), self.assertRaises(PayloadError):
                freeze_payload('computer_use', args)
        recursive = {}; recursive['self'] = recursive
        with self.assertRaises(PayloadError):
            freeze_payload('computer_use', recursive)

    def test_verdict_must_authorize_same_digest_explicitly(self):
        payload, digest = freeze_payload('computer_use', {'action': 'capture'})
        for verdict in (None, {}, {'ok': True, 'result': {'allow': True}},
                        {'ok': True, 'result': {'allow': True, 'digest': '0' * 64}},
                        {'ok': True, 'result': {'allow': False, 'digest': digest}},
                        {'ok': False, 'result': {'allow': True, 'digest': digest}},
                        {'ok': True, 'result': {'allow': 1, 'digest': digest}}):
            with self.subTest(verdict=verdict), self.assertRaises(PayloadError):
                approved_arguments(payload, digest, verdict)
        self.assertEqual(approved_arguments(payload, digest, {'ok': True, 'result': {'allow': True, 'digest': digest}}),
                         {'action': 'capture'})

    def test_guard_executes_only_complete_approved_snapshot(self):
        original = {'action': 'type', 'text': 'A' * 2200 + ' SUFIJO_APROBADO'}
        seen = []; called = []
        def callback(name, step, **kwargs):
            if name == 'computer_gate':
                seen.append(step['payload']['arguments']['text'])
                original['text'] = 'CAMBIO_NO_APROBADO'
                return {'ok': True, 'result': {'allow': True, 'digest': step['digest']}}
            return {'ok': True}
        handler = guarded_computer_handler(lambda args, **kw: called.append(args) or 'captura de prueba', callback)
        self.assertEqual(handler(original), 'captura de prueba')
        self.assertEqual(called[0]['text'], seen[0])
        self.assertTrue(called[0]['text'].endswith('SUFIJO_APROBADO'))
        self.assertNotEqual(called[0]['text'], original['text'])

    def test_guard_denies_missing_or_changed_receipt_and_tampered_payload(self):
        for mode in ('missing', 'digest', 'payload'):
            with self.subTest(mode=mode):
                called = []
                def callback(name, step, **kwargs):
                    if mode == 'payload':
                        step['payload']['arguments']['text'] = 'carga cambiada'
                    reply = {'allow': True}
                    if mode != 'missing':
                        reply['digest'] = '0' * 64 if mode == 'digest' else step['digest']
                    return {'ok': True, 'result': reply}
                result = guarded_computer_handler(lambda args, **kw: called.append(args), callback)(
                    {'action': 'type', 'text': 'texto aprobado'})
                self.assertFalse(json.loads(result)['ok'])
                self.assertFalse(called)

    def test_guard_rejects_oversized_before_gate_and_native(self):
        called = []
        result = guarded_computer_handler(lambda args, **kw: called.append('native'),
                                         lambda *args, **kw: called.append('gate'))(
            {'action': 'type', 'text': 'x' * MAX_PAYLOAD_BYTES})
        self.assertFalse(json.loads(result)['ok'])
        self.assertEqual(called, [])

    def test_guard_reports_native_failure_without_exception_details(self):
        events = []
        def native(args, **kw):
            raise RuntimeError('TOKEN_PRIVADO_NO_DEBE_APARECER')
        def callback(name, step, **kw):
            if name == 'computer_gate':
                return {'ok': True, 'result': {'allow': True, 'digest': step['digest']}}
            events.append(step)
            return {'ok': True}
        result = guarded_computer_handler(native, callback)({'action': 'capture'})
        self.assertNotIn('TOKEN_PRIVADO', result)
        self.assertFalse(json.loads(result)['ok'])
        self.assertFalse(events[0]['ok'])

    def test_action_and_payload_action_must_agree(self):
        with self.assertRaises(PayloadError):
            describe_step('capture', {'action': 'click', 'element': 7})


if __name__ == '__main__':
    unittest.main(verbosity=2)
