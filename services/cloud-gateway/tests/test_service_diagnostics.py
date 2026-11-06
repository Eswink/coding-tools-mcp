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

    def test_launch_and_context_phases_are_allowlisted(self):
        for code in ("browser_launch", "browser_context"):
            self.assertIn(code, SAFE_CHECKS)
            report = failure_report(RuntimeError(code))
            self.assertEqual(report["reason"], code)
            self.assertNotIn("http", json.dumps(report))

    def test_target_closed_during_phase_becomes_allowlisted_reason(self):
        from service_diagnostics import browser_phase

        class TargetClosedError(Exception):
            pass

        with self.assertRaises(RuntimeError) as raised:
            with browser_phase("browser_launch"):
                raise TargetClosedError(
                    "Target page, context or browser has been closed https://localhost/?code=canary"
                )
        self.assertEqual(raised.exception.args, ("browser_launch",))
        report = failure_report(raised.exception)
        self.assertEqual(report["reason"], "browser_launch")
        self.assertNotIn("canary", json.dumps(report))
        self.assertNotIn("https://", json.dumps(report))

    def test_target_closed_context_phase_distinct_from_begin(self):
        from service_diagnostics import browser_phase

        class TargetClosedError(Exception):
            pass

        with self.assertRaises(RuntimeError) as raised:
            with browser_phase("browser_context"):
                raise TargetClosedError("closed")
        self.assertEqual(raised.exception.args, ("browser_context",))
        self.assertEqual(failure_report(raised.exception)["reason"], "browser_context")
        # begin remains a separate allowlisted navigation assertion name
        self.assertIn("browser_begin", SAFE_CHECKS)
        self.assertNotEqual("browser_begin", "browser_context")

    def test_browser_phase_rejects_unknown_name(self):
        from service_diagnostics import browser_phase
        with self.assertRaises(ValueError):
            with browser_phase("not_a_safe_check"):
                pass

    def test_non_target_closed_still_propagates(self):
        from service_diagnostics import browser_phase
        with self.assertRaises(ValueError) as raised:
            with browser_phase("browser_launch"):
                raise ValueError("canary-leave-me")
        self.assertIn("canary-leave-me", str(raised.exception))

    def test_ci_wrapper_reports_launch_phase_without_url(self):
        output = io.StringIO()
        with patch("run_service_acceptance.main", side_effect=RuntimeError("browser_launch")):
            with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as error:
                runpy.run_module("run_service_browser_ci", run_name="__main__")
        self.assertEqual(error.exception.code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["reason"], "browser_launch")
        self.assertNotIn("http", output.getvalue())



if __name__ == "__main__":
    unittest.main()
