"""Pure tests: a failed browser check must be diagnosable without credential leaks."""
import contextlib
import io
import json
import runpy
from unittest.mock import patch
import unittest
from service_diagnostics import SAFE_CHECKS, failure_report


class DiagnosticsContracts(unittest.TestCase):
    def test_each_declared_check_is_reported(self):
        for code in SAFE_CHECKS:
            report = failure_report(RuntimeError(code))
            self.assertEqual(report["reason"], code)
            self.assertEqual(report["result"], "FAIL")
            self.assertFalse(report["browser_gate_passed"])

    def test_unknown_runtime_text_is_not_reported(self):
        secret = "canary-never-export-this-credential"
        result = failure_report(RuntimeError("https://localhost/callback?code=" + secret))
        self.assertEqual(result["reason"], "acceptance_error")
        self.assertNotIn(secret, json.dumps(result))

    def test_arbitrary_exception_is_not_trusted(self):
        self.assertEqual(failure_report(ValueError("browser_login"))["reason"], "acceptance_error")

    def test_non_string_and_multiple_args_are_not_trusted(self):
        for error in (RuntimeError({"token": "canary"}), RuntimeError(), RuntimeError("browser_login", "canary")):
            self.assertEqual(failure_report(error)["reason"], "acceptance_error")
            self.assertNotIn("canary", json.dumps(failure_report(error)))

    def test_administrative_block_is_retained_without_url(self):
        text = "ERR_BLOCKED_BY_ADMINISTRATOR at https://localhost/?code=canary"
        report = failure_report(RuntimeError(text))
        self.assertEqual(report["result"], "BLOCKED")
        self.assertNotIn("canary", json.dumps(report))
        self.assertFalse(report["browser_gate_passed"])

    def test_runtime_subclass_cannot_inject_case(self):
        class Untrusted(RuntimeError):
            pass
        self.assertEqual(failure_report(Untrusted("browser_login"))["reason"], "acceptance_error")

    def test_ci_wrapper_preserves_failed_exit(self):
        output = io.StringIO()
        with patch("run_service_acceptance.main", side_effect=RuntimeError("browser_begin")):
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
                runpy.run_module("run_service_browser_ci", run_name="__main__")
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())["reason"], "browser_begin")

    def test_ci_wrapper_preserves_policy_block(self):
        output = io.StringIO()
        with patch("run_service_acceptance.main", side_effect=RuntimeError("ERR_BLOCKED_BY_ADMINISTRATOR secret-canary")):
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
                runpy.run_module("run_service_browser_ci", run_name="__main__")
        self.assertEqual(error.exception.code, 78)
        self.assertNotIn("secret-canary", output.getvalue())


if __name__ == "__main__":
    unittest.main()
