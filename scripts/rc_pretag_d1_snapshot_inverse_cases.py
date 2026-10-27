"""Positive and negative cases for the finite D1 snapshot/transport inverse; never a release gate."""
import hashlib
from pathlib import Path
import subprocess
import unittest
import rc_pretag_d1_snapshot_inverse as x
import rc_pretag_ownership_profile as o

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'scripts/rc_consumer_snapshot.py'
TRANSPORT = 'scripts/rc_consumer_transport_tests.py'
TIP = '5dfea66b6379c6d6d91c0b103cc25e8bfc086474'


class D1SnapshotInverseCases(unittest.TestCase):
    def test_sealed_d1_bytes_invert_exactly_to_163_tip_bytes(self):
        for path in x.BASE_PINS:
            tip = subprocess.check_output(['git', 'show', TIP + ':' + path], cwd=ROOT)
            self.assertEqual(o.pin(tip), tuple(x.BASE_PINS[path][1:3]), path)
            self.assertEqual(x.normalize(path, (ROOT / path).read_bytes()), tip, path)
            self.assertEqual(x.normalize(path, tip), tip, path)
            self.assertEqual(len(x.FRAGMENTS[path]), len(set(x.FRAGMENTS[path])), path)

    def test_unrelated_paths_and_unknown_bytes_are_never_rewritten(self):
        self.assertEqual(x.normalize('scripts/other.py', b'x\n'), b'x\n')
        for path in (SOURCE, TRANSPORT):
            current = (ROOT / path).read_bytes()
            for mutant in (current + b'#\n', current.replace(b'import', b'imports', 1), b''):
                with self.assertRaises(AssertionError):
                    x.normalize(path, mutant)

    def test_each_hunk_is_exact_once_and_required(self):
        for path, hunks in x.FRAGMENTS.items():
            current = (ROOT / path).read_bytes()
            for before, _ in hunks:
                self.assertEqual(current.count(before), 1, path)
                with self.assertRaises(AssertionError):
                    x.normalize(path, current.replace(before, b'', 1))
                with self.assertRaises(AssertionError):
                    x.normalize(path, current.replace(before, before + before, 1))


if __name__ == '__main__':
    unittest.main()
