"""Retain PR77's evidence-classifier cases in normal delivery test discovery.

Only import the real classifier; never run Cargo or inject the native probe.
A diagnostic red witness is distinct from a passing acceptance test.
"""
import importlib.util
from pathlib import Path
import unittest


SCRIPT = (Path(__file__).resolve().parents[1]
          / "cloud-gateway/sandbox-dispatch/run_probe.py")
SPEC = importlib.util.spec_from_file_location("sandbox_dispatch_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

PASS = "test result: ok. 1 passed; 0 failed; 0 ignored;"
FAIL = "test result: FAILED. 0 passed; 1 failed; 0 ignored;"
MARKER = "SANDBOX_GAP_X"
RED = MARKER + "\n" + FAIL


class EvidenceTests(unittest.TestCase):
    # The original nine PR77 cases, including their exact input semantics.
    def test_one_exact_pass(self):
        self.assertEqual(probe.classify(0, PASS, None), "pass")

    def test_exact_red_witness(self):
        self.assertEqual(probe.classify(101, RED, MARKER), "gap_confirmed")

    def test_compile_error_is_not_a_witness(self):
        self.assertEqual(probe.classify(101, "error: SANDBOX_GAP_X", MARKER),
                         "invalid_evidence")

    def test_zero_tests_is_not_a_pass(self):
        text = "test result: ok. 0 passed; 0 failed; 0 ignored;"
        self.assertEqual(probe.classify(0, text, None), "invalid_evidence")

    def test_ignored_test_is_not_a_pass(self):
        text = "test result: ok. 0 passed; 0 failed; 1 ignored;"
        self.assertEqual(probe.classify(0, text, None), "invalid_evidence")

    def test_wrong_marker_is_not_a_witness(self):
        text = "OTHER_FAILURE\n" + FAIL
        self.assertEqual(probe.classify(101, text, MARKER), "invalid_evidence")

    def test_setup_failure_is_not_a_witness(self):
        text = "SANDBOX_GAP_X PROBE_SETUP: failed\n" + FAIL
        self.assertEqual(probe.classify(101, text, MARKER), "invalid_evidence")

    def test_timeout_is_not_a_witness(self):
        self.assertEqual(probe.classify(124, RED, MARKER), "invalid_evidence")

    def test_multiple_test_summaries_are_rejected(self):
        text = (PASS + "\n") * 2
        self.assertEqual(probe.classify(0, text, None), "invalid_evidence")

    def test_pass_requires_zero_exit_code(self):
        for code in (1, 101, 124, -9):
            with self.subTest(returncode=code):
                self.assertEqual(probe.classify(code, PASS, None), "invalid_evidence")

    def test_red_requires_cargo_test_failure_exit_code(self):
        for code in (0, 1, 124, -9):
            with self.subTest(returncode=code):
                self.assertEqual(probe.classify(code, RED, MARKER), "invalid_evidence")

    def test_red_requires_a_nonempty_matching_marker(self):
        for marker in (None, "", "SANDBOX_GAP_Y"):
            with self.subTest(marker=marker):
                self.assertEqual(probe.classify(101, RED, marker), "invalid_evidence")

    def test_each_real_probe_marker_preserves_pass_and_red_distinction(self):
        self.assertTrue(probe.GAPS)
        for marker in probe.GAPS.values():
            with self.subTest(marker=marker):
                self.assertEqual(probe.classify(0, PASS, marker), "pass")
                self.assertEqual(probe.classify(101, marker + "\n" + FAIL, marker),
                                 "gap_confirmed")

    def test_no_summary_is_not_a_pass(self):
        for text in ("", "error: failed to compile", "running 1 test"):
            with self.subTest(output=text):
                self.assertEqual(probe.classify(0, text, None), "invalid_evidence")

    def test_additional_selected_or_ignored_tests_are_rejected(self):
        for code, status, counts in (
            (0, "ok", "2 passed; 0 failed; 0 ignored;"),
            (0, "ok", "1 passed; 0 failed; 1 ignored;"),
            (0, "ok", "1 passed; 1 failed; 0 ignored;"),
            (101, "FAILED", "0 passed; 0 failed; 0 ignored;"),
            (101, "FAILED", "0 passed; 2 failed; 0 ignored;"),
            (101, "FAILED", "1 passed; 1 failed; 0 ignored;"),
            (101, "FAILED", "0 passed; 1 failed; 1 ignored;"),
        ):
            with self.subTest(returncode=code, status=status, counts=counts):
                text = f"{MARKER}\ntest result: {status}. {counts}"
                self.assertEqual(probe.classify(code, text, MARKER), "invalid_evidence")

    def test_multiple_red_or_mixed_summaries_are_rejected(self):
        for code, summaries in (
            (101, (FAIL, FAIL)),
            (101, (FAIL, PASS)),
            (101, (PASS, FAIL)),
            (0, (PASS, FAIL)),
            (0, (FAIL, PASS)),
        ):
            with self.subTest(returncode=code, summaries=summaries):
                text = MARKER + "\n" + "\n".join(summaries)
                self.assertEqual(probe.classify(code, text, MARKER), "invalid_evidence")

    def test_summary_status_must_match_exit_status(self):
        for code, text in ((0, RED), (101, MARKER + "\n" + PASS),
                           (0, PASS.replace("ok.", "FAILED.")),
                           (101, RED.replace("FAILED.", "ok."))):
            with self.subTest(returncode=code, output=text):
                self.assertEqual(probe.classify(code, text, MARKER), "invalid_evidence")


if __name__ == "__main__":
    unittest.main()
