"""Test the actual lifecycle runner without Cargo, listener injection or child mocks in Rust.

Only the Python driver subprocesses use fakes; these are evidence/cleanup contracts,
not native sandbox evidence. The real Rust suite still requires native CI.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests/cloud-gateway/sandbox-lifecycle/run_probe.py"
SPEC = importlib.util.spec_from_file_location("linux_lifecycle_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
PASS = "test result: ok. 1 passed; 0 failed; 0 ignored;"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.out = self.root / "evidence"
        self.auth = self.root / "src-tauri/src/auth/mod.rs"
        self.auth.parent.mkdir(parents=True)
        self.original = b"// original production auth module\n"
        self.auth.write_bytes(self.original)
        for name in (*probe.GOLDEN, *probe.PAYLOADS.values()):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.target = self.auth.with_name("sandbox_lifecycle_probe.rs")
        self.calls = []

    def execute(self, code=0, output=PASS, compile_code=0, error=None):
        def run(cmd, **kwargs):
            self.calls.append((cmd, kwargs))
            if "--no-run" in cmd:
                self.assertEqual(self.auth.read_bytes(), self.original + probe.INJECTION)
                for name, source in probe.PAYLOADS.items():
                    self.assertEqual(self.auth.with_name(name).read_bytes(),
                                     (self.root / source).read_bytes())
                if error == "compile-timeout":
                    return 124, "PROBE_SETUP: compile deadline exceeded"
                if error == "missing-cargo":
                    return 127, "PROBE_SETUP: cargo missing"
                return compile_code, ""
            if error == "test-timeout":
                return 124, "partial test output\nPROBE_SETUP: test deadline exceeded"
            return code, output
        with patch.object(probe.platform, "system", return_value="Linux"), \
                patch.object(probe.platform, "machine", return_value="x86_64"), \
                patch.object(probe.subprocess, "check_output", return_value="fixed-source\n"), \
                patch.object(probe, "run_owned", side_effect=run):
            result = probe.run_probe(self.root, self.out)
        receipt = json.loads((self.out / "result.json").read_text())
        return result, receipt

    def assert_restored(self, receipt):
        self.assertEqual(self.auth.read_bytes(), self.original)
        for name in probe.PAYLOADS:
            self.assertFalse(self.auth.with_name(name).exists())
        self.assertTrue(receipt["production_source_restored"])
        self.assertTrue(receipt["golden_unchanged"])

    def test_exact_seven_cases_pass_and_restore(self):
        result, receipt = self.execute()
        self.assertEqual(result, 0)
        self.assertTrue(receipt["acceptance_passed"])
        self.assertEqual(set(receipt["tests"]), set(probe.CASES))
        self.assertEqual(len(receipt["tests"]), 7)
        self.assert_restored(receipt)
        self.assertEqual(receipt["head"], "fixed-source")
        self.assertIn("probe_sha256", receipt)
        self.assertTrue((self.out / "sha256.json").exists())

    def test_compile_failure_stops_cases_and_restores(self):
        result, receipt = self.execute(compile_code=101)
        self.assertEqual(result, 1)
        self.assertEqual(receipt["compile_exit"], 101)
        self.assertEqual(receipt["tests"], {})
        self.assertEqual(len(self.calls), 1)
        self.assert_restored(receipt)

    def test_compile_timeout_preserves_failed_receipt(self):
        result, receipt = self.execute(error="compile-timeout")
        self.assertEqual(result, 1)
        self.assertEqual(receipt["compile_exit"], 124)
        self.assertIn("PROBE_SETUP:", receipt["error"])
        self.assert_restored(receipt)

    def test_missing_cargo_is_not_native_evidence(self):
        result, receipt = self.execute(error="missing-cargo")
        self.assertEqual(result, 1)
        self.assertEqual(receipt["tests"], {})
        self.assert_restored(receipt)

    def test_zero_match_is_not_pass(self):
        result, receipt = self.execute(output=PASS.replace("1 passed", "0 passed"))
        self.assertEqual(result, 1)
        self.assertFalse(receipt["acceptance_passed"])
        self.assert_restored(receipt)

    def test_ignored_case_is_not_pass(self):
        result, _ = self.execute(output=PASS.replace("1 passed", "0 passed").replace("0 ignored", "1 ignored"))
        self.assertEqual(result, 1)

    def test_multiple_or_mixed_summaries_are_not_pass(self):
        for text in (PASS + "\n" + PASS,
                     PASS + "\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;"):
            with self.subTest(output=text):
                self.assertEqual(self.execute(output=text)[0], 1)

    def test_nonzero_exit_with_passing_summary_is_not_pass(self):
        for code in (1, 101, 124, -9):
            with self.subTest(code=code):
                self.assertEqual(self.execute(code=code)[0], 1)

    def test_assertion_red_is_not_acceptance(self):
        result, receipt = self.execute(
            code=101, output="SANDBOX_GAP_X\ntest result: FAILED. 0 passed; 1 failed; 0 ignored;")
        self.assertEqual(result, 1)
        self.assertTrue(all(v["status"] == "invalid_evidence" for v in receipt["tests"].values()))

    def test_setup_marker_cannot_hide_in_passing_summary(self):
        result, _ = self.execute(output="PROBE_SETUP: fixture problem\n" + PASS)
        self.assertEqual(result, 1)

    def test_per_case_timeout_keeps_partial_logs_and_continues(self):
        result, receipt = self.execute(error="test-timeout")
        self.assertEqual(result, 1)
        self.assertEqual(len(receipt["tests"]), 7)
        for name in probe.CASES:
            self.assertIn("partial test output", (self.out / (name + ".txt")).read_text())
            self.assertEqual(receipt["tests"][name]["exit_code"], 124)
        self.assert_restored(receipt)

    def test_preexisting_module_is_never_overwritten(self):
        self.target.write_text("keep me")
        result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(self.target.read_text(), "keep me")
        self.assertEqual(self.auth.read_bytes(), self.original)
        self.assertFalse(receipt["acceptance_passed"])
        self.assertEqual(self.calls, [])

    def test_preexisting_registration_is_never_overwritten(self):
        self.original += probe.INJECTION
        self.auth.write_bytes(self.original)
        result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(self.auth.read_bytes(), self.original)
        self.assertFalse(receipt["acceptance_passed"])

    def test_concurrent_golden_injection_is_rejected(self):
        target = self.auth.with_name("sandbox_dispatch_probe.rs")
        target.write_text("golden owner")
        result, _ = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(target.read_text(), "golden owner")
        self.assertEqual(self.calls, [])

    def test_changed_golden_bytes_are_rejected(self):
        (self.root / next(iter(probe.GOLDEN))).write_text("changed")
        result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertFalse(receipt["golden_unchanged"])
        self.assertEqual(self.calls, [])

    def test_exact_test_selection_and_bounded_native_environment(self):
        self.execute()
        for name, (cmd, kwargs) in zip(probe.CASES, self.calls[1:], strict=True):
            self.assertIn(probe.CASE_PATHS[name], cmd)
            self.assertIn("--exact", cmd)
            self.assertIn("--test-threads=1", cmd)
            self.assertEqual(kwargs["env"]["CTM_LIFECYCLE_HOST_ONLY"], "synthetic-host-value")
            self.assertTrue(kwargs["env"]["PATH"].startswith("/usr/bin:/bin:"))
            self.assertLessEqual(kwargs["timeout"], 40)
        self.assertEqual(probe.TOTAL_TIMEOUT, 75 * 60)

    def test_total_deadline_does_not_spawn(self):
        with patch.object(probe.time, "monotonic", return_value=5), \
                patch.object(probe, "run_owned") as run:
            code, text = probe.run_case(self.root, probe.CASES[0], {}, 4)
        self.assertEqual(code, 124)
        self.assertIn("PROBE_SETUP:", text)
        run.assert_not_called()

    def test_failed_source_restoration_keeps_failed_receipt(self):
        original_write = Path.write_bytes
        def fail_restore(path, data):
            if path == self.auth and data == self.original:
                raise OSError("synthetic restore failure")
            return original_write(path, data)
        with patch.object(Path, "write_bytes", fail_restore):
            result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertFalse(receipt["production_source_restored"])
        self.assertFalse(receipt["acceptance_passed"])
        self.assertIn("source restoration failed", receipt["cleanup_errors"][0])
        self.assertFalse(self.target.exists())

    def test_failed_module_removal_keeps_failed_receipt(self):
        original_unlink = Path.unlink
        def fail_remove(path, *args, **kwargs):
            if path == self.target:
                raise OSError("synthetic unlink failure")
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_remove):
            result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(self.auth.read_bytes(), self.original)
        self.assertFalse(receipt["acceptance_passed"])
        self.assertIn("injected module removal failed", receipt["cleanup_errors"][0])
        self.assertTrue(self.target.exists())

    def test_missing_golden_source_still_records_failure(self):
        (self.root / next(iter(probe.GOLDEN))).unlink()
        result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertIn("golden source unavailable", receipt["error"])
        self.assertFalse(receipt["golden_unchanged"])
        self.assertEqual(self.calls, [])

    def test_unsupported_platform_cannot_report_native_pass(self):
        with patch.object(probe.platform, "system", return_value="Windows"):
            result = probe.run_probe(self.root, self.out)
        receipt = json.loads((self.out / "result.json").read_text())
        self.assertEqual(result, 1)
        self.assertFalse(receipt["acceptance_passed"])
        self.assertEqual(receipt["tests"], {})
        self.assertIn("requires native Linux", receipt["error"])

    def test_original_golden_hashes_are_unchanged(self):
        self.assertEqual(probe.hashes(ROOT), probe.GOLDEN)

    def test_required_case_list_includes_http_and_direct_negatives(self):
        self.assertEqual(probe.CASES, (
            "authenticated_environment_and_child_boundary_are_truthful",
            "authenticated_child_environment_stdin_and_temp_are_confined",
            "authenticated_zero_yield_input_completes_without_replay",
            "authenticated_dangerous_mode_still_denies_network",
            "approved_primary_missing_policy_fails_closed_without_hooks",
            "authenticated_timeout_stops_sandboxed_process_tree",
            "authenticated_kill_session_stops_sandboxed_process_tree",
        ))

    def test_either_negative_case_failure_rejects_acceptance(self):
        for failed in ("authenticated_dangerous_mode_still_denies_network",
                       "approved_primary_missing_policy_fails_closed_without_hooks",
                       *probe.CASES[-2:]):
            def case_result(root, name, env, deadline):
                if name == failed:
                    return 101, "test result: FAILED. 0 passed; 1 failed; 0 ignored;"
                return 0, PASS
            with self.subTest(failed=failed), \
                    patch.object(probe, "run_case", side_effect=case_result):
                result, receipt = self.execute()
            self.assertEqual(result, 1)
            self.assertFalse(receipt["acceptance_passed"])
            self.assertEqual(receipt["tests"][failed]["status"], "invalid_evidence")
            for name in set(probe.CASES) - {failed}:
                self.assertEqual(receipt["tests"][name]["status"], "pass")
            self.assert_restored(receipt)


    def test_every_payload_hash_is_bound_to_source_bytes(self):
        result, receipt = self.execute()
        self.assertEqual(result, 0)
        expected = {source: hashlib.sha256((self.root / source).read_bytes()).hexdigest()
                    for source in probe.PAYLOADS.values()}
        self.assertEqual(receipt["payload_sha256"], expected)
        self.assertEqual(receipt["probe_sha256"], expected[probe.PAYLOADS[self.target.name]])
        for name in probe.CASES:
            self.assertEqual(receipt["tests"][name]["test_filter"], probe.CASE_PATHS[name])

    def test_changed_payload_has_its_own_hash(self):
        source = probe.PAYLOADS["linux_sandbox_deadline.rs"]
        path = self.root / source
        path.write_bytes(path.read_bytes() + b"\n// changed fixture\n")
        result, receipt = self.execute()
        self.assertEqual(result, 0)
        self.assertEqual(receipt["payload_sha256"][source], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertNotEqual(receipt["payload_sha256"][source], hashlib.sha256((ROOT / source).read_bytes()).hexdigest())

    def test_each_preexisting_payload_is_preserved(self):
        for name in probe.PAYLOADS:
            with self.subTest(name=name):
                target = self.auth.with_name(name)
                target.write_bytes(b"other owner")
                self.calls.clear()
                result, receipt = self.execute()
                self.assertEqual(result, 1)
                self.assertFalse(receipt["acceptance_passed"])
                self.assertEqual(target.read_bytes(), b"other owner")
                self.assertEqual(self.auth.read_bytes(), self.original)
                self.assertEqual(self.calls, [])
                target.unlink()

    def test_missing_payload_prevents_all_injection(self):
        for source in probe.PAYLOADS.values():
            with self.subTest(source=source):
                path = self.root / source
                payload = path.read_bytes()
                path.unlink()
                self.calls.clear()
                result, receipt = self.execute()
                self.assertEqual(result, 1)
                self.assertEqual(self.calls, [])
                self.assert_restored(receipt)
                path.write_bytes(payload)

    def test_partial_payload_write_removes_every_owned_file(self):
        original_open = Path.open
        for name in probe.PAYLOADS:
            target = self.auth.with_name(name)
            def partial(path, mode="r", *args, **kwargs):
                stream = original_open(path, mode, *args, **kwargs)
                if path != target or mode != "xb":
                    return stream
                class PartialWrite:
                    def __enter__(self):
                        return self
                    def __exit__(self, *error):
                        stream.close()
                    def write(self, payload):
                        stream.write(payload[:5])
                        raise OSError("synthetic partial payload write")
                return PartialWrite()
            with self.subTest(name=name), patch.object(Path, "open", partial):
                result, receipt = self.execute()
            self.assertEqual(result, 1)
            self.assertEqual(self.calls, [])
            self.assert_restored(receipt)

    def test_partial_registration_write_restores_original_bytes(self):
        original_write = Path.write_bytes
        def partial(path, payload):
            if path == self.auth and payload == self.original + probe.INJECTION:
                original_write(path, payload[:5])
                raise OSError("synthetic partial registration")
            return original_write(path, payload)
        with patch.object(Path, "write_bytes", partial):
            result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertEqual(self.calls, [])
        self.assert_restored(receipt)

    def test_each_removal_failure_still_removes_other_payloads(self):
        original_unlink = Path.unlink
        for name in probe.PAYLOADS:
            target = self.auth.with_name(name)
            def fail(path, *args, **kwargs):
                if path == target:
                    raise OSError("synthetic selected removal")
                return original_unlink(path, *args, **kwargs)
            with self.subTest(name=name), patch.object(Path, "unlink", fail):
                result, receipt = self.execute()
            self.assertEqual(result, 1)
            self.assertFalse(receipt["production_source_restored"])
            self.assertEqual(self.auth.read_bytes(), self.original)
            self.assertTrue(target.exists())
            for other in set(probe.PAYLOADS) - {name}:
                self.assertFalse(self.auth.with_name(other).exists())
            target.unlink()

    def test_payload_creation_is_exclusive(self):
        original_open = Path.open
        target = self.auth.with_name("linux_sandbox_lifecycle_support.rs")
        def concurrent(path, mode="r", *args, **kwargs):
            if path == target and mode == "xb":
                with original_open(path, "wb") as stream:
                    stream.write(b"concurrent owner")
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, "open", concurrent):
            result, receipt = self.execute()
        self.assertEqual(result, 1)
        self.assertFalse(receipt["acceptance_passed"])
        self.assertEqual(target.read_bytes(), b"concurrent owner")
        self.assertEqual(self.auth.read_bytes(), self.original)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
