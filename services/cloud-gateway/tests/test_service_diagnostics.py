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


    def test_ci_exception_summary_maps_target_closed_without_url(self):
        from service_diagnostics import ci_exception_summary

        class TargetClosedError(Exception):
            pass

        secret = "https://localhost/callback?code=canary-secret\n/home/runner/.cache/ms-playwright/evil"
        text = ci_exception_summary(
            TargetClosedError("Target page, context or browser has been closed " + secret)
        )
        self.assertIsInstance(text, str)
        lines = text.splitlines()
        self.assertGreaterEqual(len(lines), 1)
        self.assertLessEqual(len(lines), 2)
        joined = "\n".join(lines)
        self.assertIn("class=TargetClosedError", joined)
        self.assertIn("signal=target_closed", joined)
        self.assertNotIn("canary-secret", joined)
        self.assertNotIn("https://", joined)
        self.assertNotIn("/home/", joined)
        self.assertNotIn("ms-playwright", joined)
        self.assertNotIn("\n\n", text)

    def test_ci_exception_summary_reports_allowlisted_phase_only(self):
        from service_diagnostics import ci_exception_summary
        text = ci_exception_summary(RuntimeError("browser_launch"))
        self.assertIn("phase=browser_launch", text)
        self.assertIn("class=RuntimeError", text)
        self.assertLessEqual(len(text.splitlines()), 2)

    def test_ci_exception_summary_does_not_echo_raw_unknown_text(self):
        from service_diagnostics import ci_exception_summary
        payload = "token=leak-me\npath=/etc/passwd\nhttps://evil.test/?x=1"
        text = ci_exception_summary(ValueError(payload))
        self.assertLessEqual(len(text.splitlines()), 2)
        self.assertIn("signal=unclassified", text)
        self.assertNotIn("leak-me", text)
        self.assertNotIn("/etc/passwd", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("evil.test", text)
        # Must not be a scrubbed copy of the raw message
        self.assertNotIn("token=", text)

    def test_ci_exception_summary_not_in_failure_report_json(self):
        from service_diagnostics import ci_exception_summary
        class TargetClosedError(Exception):
            pass
        exc = TargetClosedError("Target page, context or browser has been closed https://x/?code=canary")
        report = failure_report(RuntimeError("browser_launch"))
        dumped = json.dumps(report)
        self.assertNotIn("ci_diag", dumped)
        self.assertNotIn("signal=", dumped)
        summary = ci_exception_summary(exc)
        self.assertTrue(summary.startswith("ci_diag "))

    def test_ci_wrapper_prints_summary_on_stderr_only(self):
        from service_diagnostics import browser_phase
        err = io.StringIO()
        out = io.StringIO()
        with patch("run_service_acceptance.main", side_effect=RuntimeError("browser_launch")):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                runpy.run_module("run_service_browser_ci", run_name="__main__")
        stdout = out.getvalue()
        stderr = err.getvalue()
        payload = json.loads(stdout)
        self.assertEqual(payload["reason"], "browser_launch")
        self.assertNotIn("ci_diag", stdout)
        self.assertIn("ci_diag ", stderr)
        self.assertIn("phase=browser_launch", stderr)
        self.assertLessEqual(len([ln for ln in stderr.splitlines() if ln.startswith("ci_diag ")]), 2)


    def test_browser_phase_preserves_cause_chain(self):
        from service_diagnostics import browser_phase

        class TargetClosedError(Exception):
            pass

        with self.assertRaises(RuntimeError) as raised:
            with browser_phase("browser_launch"):
                raise TargetClosedError("No usable sandbox! https://evil/?code=canary")
        self.assertEqual(raised.exception.args, ("browser_launch",))
        self.assertIsNotNone(raised.exception.__cause__)
        self.assertEqual(type(raised.exception.__cause__).__name__, "TargetClosedError")

    def test_ci_summary_classifies_sandbox_from_cause_chain(self):
        from service_diagnostics import ci_exception_summary

        class TargetClosedError(Exception):
            pass

        inner = TargetClosedError("No usable sandbox! visit https://evil/?token=secret\n/usr/lib/evil.so")
        outer = RuntimeError("browser_launch")
        outer.__cause__ = inner
        text = ci_exception_summary(outer)
        self.assertIn("phase=browser_launch", text)
        self.assertIn("signal=sandbox_unavailable", text)
        self.assertLessEqual(len(text.splitlines()), 2)
        self.assertNotIn("secret", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("/usr/", text)
        self.assertNotIn("evil", text)

    def test_ci_summary_classifies_userns_missing_lib_exec_crash(self):
        from service_diagnostics import ci_exception_summary
        cases = [
            ("Failed to move to new namespace: Operation not permitted", "userns_denied"),
            ("error while loading shared libraries: libx.so", "missing_shared_library"),
            ("cannot open shared object file: No such file", "missing_shared_library"),
            ("Executable doesn't exist at /tmp/chrome", "executable_missing"),
            ("Executable does not exist", "executable_missing"),
            ("Target crashed", "process_crash"),
            ("browser has crashed (exit code 139)", "process_crash"),
        ]
        for message, signal in cases:
            with self.subTest(signal=signal):
                text = ci_exception_summary(RuntimeError(message + " https://x/?c=canary\n/home/runner/secret"))
                self.assertIn(f"signal={signal}", text)
                self.assertNotIn("canary", text)
                self.assertNotIn("https://", text)
                self.assertNotIn("/home/", text)
                self.assertNotIn("secret", text)
                self.assertLessEqual(len(text.splitlines()), 2)

    def test_ci_summary_unknown_stays_unclassified_without_echo(self):
        from service_diagnostics import ci_exception_summary
        payload = "weird-token=leak\npath=/etc/shadow\nhttps://evil.test/a"
        text = ci_exception_summary(ValueError(payload))
        self.assertIn("signal=unclassified", text)
        self.assertNotIn("leak", text)
        self.assertNotIn("/etc/", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("evil.test", text)
        self.assertNotIn("weird-token", text)

    def test_ci_summary_dynamic_class_name_not_echoed(self):
        from service_diagnostics import ci_exception_summary

        class SuperSecretInternalError(Exception):
            pass

        text = ci_exception_summary(SuperSecretInternalError("No usable sandbox"))
        self.assertIn("class=Other", text)
        self.assertNotIn("SuperSecretInternalError", text)
        self.assertIn("signal=sandbox_unavailable", text)

    def test_ci_summary_exception_cycle_is_bounded(self):
        from service_diagnostics import ci_exception_summary
        a = RuntimeError("browser_launch")
        b = ValueError("No usable sandbox! https://cycle/?x=1")
        a.__cause__ = b
        b.__cause__ = a
        text = ci_exception_summary(a)
        self.assertIn("phase=browser_launch", text)
        self.assertIn("signal=sandbox_unavailable", text)
        self.assertNotIn("https://", text)
        self.assertLessEqual(len(text.splitlines()), 2)

    def test_ci_summary_deep_cause_chain_respects_depth_cap(self):
        from service_diagnostics import ci_exception_summary
        # Deep chain: only the deepest has a known phrase; depth cap must still
        # find it within bound OR safely stop — implementation uses max depth 8.
        cur = ValueError("No usable sandbox")
        for _ in range(20):
            nxt = RuntimeError("wrapper")
            nxt.__cause__ = cur
            cur = nxt
        # Attach allowlisted phase at the top
        top = RuntimeError("browser_launch")
        top.__cause__ = cur
        text = ci_exception_summary(top)
        self.assertIn("phase=browser_launch", text)
        # With depth cap 8, sandbox at depth 21 may be unreachable → unclassified
        # OR found if walking enough — either way must not hang or leak.
        self.assertLessEqual(len(text.splitlines()), 2)
        self.assertTrue(
            ("signal=sandbox_unavailable" in text) or ("signal=unclassified" in text)
            or text.count("signal=") == 0 and "phase=browser_launch" in text
        )
        self.assertNotIn("wrapper", text)

    def test_failure_report_semantics_unchanged_with_cause(self):
        from service_diagnostics import browser_phase, failure_report

        class TargetClosedError(Exception):
            pass

        with self.assertRaises(RuntimeError) as raised:
            with browser_phase("browser_launch"):
                raise TargetClosedError("No usable sandbox! https://x/?code=canary")
        report = failure_report(raised.exception)
        self.assertEqual(report["reason"], "browser_launch")
        self.assertEqual(report["class"], "RuntimeError")
        self.assertNotIn("canary", json.dumps(report))
        self.assertNotIn("sandbox", json.dumps(report))



if __name__ == "__main__":
    unittest.main()
