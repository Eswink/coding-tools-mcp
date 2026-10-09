"""Owned ordinary byte/parser controls, not original755 methods/family proof."""
import hashlib
import json
import subprocess
import sys
import unittest
import audit
from audit import expected_events, verify_saved_events

encode = lambda value: (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
record = {'entry': 'owned-ordinary', 'raw_loaded_ids': ['Owned.test_x'],
          'raw_executed_ids': ['Owned.test_x'], 'raw_success_ids': ['Owned.test_x'],
          'full_loaded_ids': ['Owned.test_x']}


class Controls(unittest.TestCase):
    def raw(self, group='consumer'):
        return b''.join(encode(row) for row in expected_events(record, group))

    def test_positive_consumer(self):
        result = verify_saved_events(self.raw(), [record], 'consumer', encode)
        self.assertEqual(result['events'], 4)
        self.assertEqual(result['starts'], 1)
        self.assertEqual(result['successes'], 1)
        self.assertEqual(result['sha256'], hashlib.sha256(self.raw()).hexdigest())

    def test_positive_pretag(self):
        self.assertEqual(verify_saved_events(self.raw('pretag'), [record], 'pretag', encode)['events'], 5)

    def test_missing_success(self):
        rows = expected_events(record, 'consumer')
        with self.assertRaises(AssertionError):
            verify_saved_events(b''.join(encode(x) for x in rows if 'success' not in x), [record], 'consumer', encode)

    def test_duplicate_success(self):
        with self.assertRaises(AssertionError):
            verify_saved_events(self.raw() + encode({'entry': record['entry'], 'success': 'Owned.test_x'}), [record], 'consumer', encode)

    def test_reverse_order(self):
        with self.assertRaises(AssertionError):
            verify_saved_events(b''.join(encode(x) for x in reversed(expected_events(record, 'consumer'))), [record], 'consumer', encode)

    def test_truncated_newline(self):
        with self.assertRaises(AssertionError):
            verify_saved_events(self.raw()[:-1], [record], 'consumer', encode)

    def test_noncanonical_spaces(self):
        with self.assertRaises(AssertionError):
            verify_saved_events(b''.join((json.dumps(x) + '\n').encode() for x in expected_events(record, 'consumer')), [record], 'consumer', encode)

    def test_oversize(self):
        with self.assertRaises(AssertionError):
            verify_saved_events(b'x' * 1024**2 + b'\n', [record], 'consumer', encode)

    def test_receipt_raw_success_mismatch(self):
        changed = dict(record, raw_success_ids=[])
        with self.assertRaises(AssertionError):
            expected_events(changed, 'consumer')

    def test_observer_cancellation_propagates(self):
        marker = KeyboardInterrupt('owned ordinary cancellation')
        def cancelled(value):
            raise marker
        with self.assertRaises(KeyboardInterrupt) as caught:
            verify_saved_events(self.raw(), [record], 'consumer', cancelled)
        self.assertIs(caught.exception, marker)

    def test_rootexit_explicit_positive(self):
        self.assertEqual(audit.validate_root_wrapper_exit(0), 0)

    def test_rootexit_missing(self):
        with self.assertRaises(TypeError):
            audit.audit_full755(None)

    def test_rootexit_nonzero(self):
        for code in [1, -9, 130]:
            with self.assertRaises(ValueError):
                audit.validate_root_wrapper_exit(code)

    def test_rootexit_bool_none_float(self):
        for value in [False, True, None, 0.0, '0']:
            with self.assertRaises(TypeError):
                audit.validate_root_wrapper_exit(value)

    def test_original_default_consumer_hex_print(self):
        raw = b'owned ordinary event\n'
        expected = (json.dumps(dict(entry='owned-ordinary', raw_events_hex=raw.hex(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())) + '\n').encode()
        self.assertEqual(audit.consumer_hex_print('owned-ordinary', raw), expected)
        audit.verify_consumer_hex_print(expected, 'owned-ordinary', raw)

    def test_actual_owned_stdout_capture(self):
        raw = b'owned ordinary event\n'
        code = "import hashlib,json;raw=b'owned ordinary event\\n';print(json.dumps(dict(entry='owned-ordinary',raw_events_hex=raw.hex(),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())))"
        child = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, check=True)
        self.assertEqual(child.stderr, b'')
        self.assertEqual(child.stdout, audit.consumer_hex_print('owned-ordinary', raw))
        audit.verify_consumer_hex_print(child.stdout, 'owned-ordinary', raw)

    def test_compact_consumer_print_rejected(self):
        raw = b'owned ordinary event\n'
        wrong = encode(dict(entry='owned-ordinary', raw_events_hex=raw.hex(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        with self.assertRaises(AssertionError):
            audit.verify_consumer_hex_print(wrong, 'owned-ordinary', raw)

    def test_missing_duplicate_hexprint_rejected(self):
        raw = b'owned ordinary event\n'
        expected = audit.consumer_hex_print('owned-ordinary', raw)
        for stdout in [b'', expected + expected]:
            with self.assertRaises(AssertionError):
                audit.verify_consumer_hex_print(stdout, 'owned-ordinary', raw)


if __name__ == '__main__':
    unittest.main(verbosity=2)
