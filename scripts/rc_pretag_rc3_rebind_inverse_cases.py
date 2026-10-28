"""Positive and negative cases for the finite rc.3 S1/S2 rebind inverse; never a release gate."""
import subprocess
import unittest
from pathlib import Path
from rc_pretag_integration_admission_profile import normalize as integration_bytes
import rc_pretag_ownership_profile as o
import rc_pretag_rc3_rebind_inverse as x

ROOT = Path(__file__).resolve().parents[1]


class Rc3RebindInverseCases(unittest.TestCase):
    def rc2(self, path):
        data = (ROOT / path).read_bytes()
        restored = x.normalize(path, data)
        self.assertEqual(o.pin(restored), tuple(x.BASE_PINS[path][1:3]), path)
        return restored

    def test_rc3_bytes_invert_exactly_to_rc2_bytes_and_chain_through_integration(self):
        for path in x.BASE_PINS:
            restored = self.rc2(path)
            self.assertEqual(x.normalize(path, restored), restored, path)
            self.assertEqual(x.normalize(path, integration_bytes(path, (ROOT / path).read_bytes())), restored, path)
            self.assertEqual(len(x.FRAGMENTS[path]), len(set(x.FRAGMENTS[path])), path)

    def test_unrelated_paths_and_unknown_bytes_are_never_rewritten(self):
        self.assertEqual(x.normalize('scripts/other.py', b'x\n'), b'x\n')
        for path in x.BASE_PINS:
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
