"""Evidence classifier regression: unrelated failures must not become red witnesses."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("run_probe.py"))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class EvidenceTests(unittest.TestCase):
    def test_one_exact_pass(self):
        self.assertEqual(probe.classify(0, "test result: ok. 1 passed; 0 failed; 0 ignored;", None), "pass")

    def test_exact_red_witness(self):
        self.assertEqual(probe.classify(101, "SANDBOX_GAP_X\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;", "SANDBOX_GAP_X"), "gap_confirmed")

    def test_compile_error_is_not_a_witness(self):
        self.assertEqual(probe.classify(101, "error: SANDBOX_GAP_X", "SANDBOX_GAP_X"), "invalid_evidence")

    def test_zero_tests_is_not_a_pass(self):
        self.assertEqual(probe.classify(0, "test result: ok. 0 passed; 0 failed; 0 ignored;", None), "invalid_evidence")

    def test_ignored_test_is_not_a_pass(self):
        self.assertEqual(probe.classify(0, "test result: ok. 0 passed; 0 failed; 1 ignored;", None), "invalid_evidence")

    def test_wrong_marker_is_not_a_witness(self):
        self.assertEqual(probe.classify(101, "OTHER_FAILURE\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;", "SANDBOX_GAP_X"), "invalid_evidence")

    def test_setup_failure_is_not_a_witness(self):
        text = "SANDBOX_GAP_X PROBE_SETUP: failed\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;"
        self.assertEqual(probe.classify(101, text, "SANDBOX_GAP_X"), "invalid_evidence")

    def test_timeout_is_not_a_witness(self):
        self.assertEqual(probe.classify(124, "SANDBOX_GAP_X\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;", "SANDBOX_GAP_X"), "invalid_evidence")

    def test_multiple_test_summaries_are_rejected(self):
        text = "test result: ok. 1 passed; 0 failed; 0 ignored;\n" * 2
        self.assertEqual(probe.classify(0, text, None), "invalid_evidence")


if __name__ == "__main__":
    unittest.main()
