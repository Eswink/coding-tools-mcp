"""Test the actual lifecycle runner without Cargo, listener injection or child mocks in Rust.

Only the Python driver subprocesses use fakes; these are evidence/cleanup contracts,
not native sandbox evidence. The real Rust suite still requires native CI.
"""
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
        for name in (*probe.GOLDEN, "tests/cloud-gateway/linux_sandbox_lifecycle.rs"):
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
                self.assertTrue(self.target.exists())
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
        self.assertFalse(self.target.exists())
        self.assertTrue(receipt["production_source_restored"])
        self.assertTrue(receipt["golden_unchanged"])

    def test_exact_three_cases_pass_and_restore(self):
        result, receipt = self.execute()
        self.assertEqual(result, 0)
        self.assertTrue(receipt["acceptance_passed"])
        self.assertEqual(set(receipt["tests"]), set(probe.CASES))
        self.assertEqual(len(receipt["tests"]), 3)
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
        self.assertEqual(len(receipt["tests"]), 3)
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
            self.assertIn(f"auth::sandbox_lifecycle_probe::{name}", cmd)
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


@unittest.skipUnless(sys.platform == "linux", "process group proof requires Linux")
class OwnedProcessTests(unittest.TestCase):
    def test_real_subprocess_success_preserves_output(self):
        code, text = probe.run_owned([sys.executable, "-c", "print('owned-output')"],
                                    cwd=ROOT, env=os.environ.copy(), timeout=5)
        self.assertEqual((code, text), (0, "owned-output\n"))

    def test_real_timeout_kills_and_reaps_owned_group(self):
        started = time.monotonic()
        code, text = probe.run_owned(
            [sys.executable, "-u", "-c", "import time; print('before-timeout'); time.sleep(60)"],
            cwd=ROOT, env=os.environ.copy(), timeout=0.2)
        self.assertEqual(code, 124)
        self.assertIn("before-timeout", text)
        self.assertIn("PROBE_SETUP:", text)
        self.assertLess(time.monotonic() - started, 5)

    def test_timeout_stops_inherited_grandchild_group(self):
        script = ("import subprocess,sys,time; "
                  "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                  "print(p.pid,flush=True); time.sleep(60)")
        code, text = probe.run_owned([sys.executable, "-u", "-c", script],
                                    cwd=ROOT, env=os.environ.copy(), timeout=0.2)
        self.assertEqual(code, 124)
        pid = int(text.splitlines()[0])
        deadline = time.monotonic() + 2
        while True:
            try:
                stat = Path(f"/proc/{pid}/stat").read_text()
            except FileNotFoundError:
                break
            if stat.rsplit(") ", 1)[1].startswith("Z "):
                break  # Reparented zombie cannot execute or hold a live child workload.
            self.assertLess(time.monotonic(), deadline, "live grandchild escaped owned group")
            time.sleep(0.01)

    def test_missing_executable_is_a_failed_setup(self):
        code, text = probe.run_owned(["/nonexistent/lifecycle-fixture-cargo"],
                                    cwd=ROOT, env=os.environ.copy(), timeout=5)
        self.assertEqual(code, 127)
        self.assertIn("PROBE_SETUP:", text)


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/linux-authenticated-lifecycle.yml").read_text()

    def test_validation_trigger_is_exact_branch_only(self):
        self.assertIn("branches: ['test/linux-auth-lifecycle-20261001']", self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertNotIn("workflow_dispatch:", self.workflow)
        self.assertEqual(self.workflow.count("github.ref == 'refs/heads/test/linux-auth-lifecycle-20261001'"), 2)
        self.assertIn("os: [ubuntu-22.04, ubuntu-24.04]", self.workflow)
        self.assertIn("timeout-minutes: 75", self.workflow)

    def test_actions_are_pinned_and_permissions_are_read_only(self):
        actions = re.findall(r"uses: (\S+)", self.workflow)
        self.assertTrue(actions)
        for action in actions:
            self.assertRegex(action, r"^[\w/-]+@[a-f0-9]{40}$")
        self.assertIn("permissions:\n  contents: read", self.workflow)
        self.assertNotIn("write", self.workflow.split("permissions:", 1)[1].split("env:", 1)[0])
        self.assertNotIn("secrets.", self.workflow)
        self.assertNotIn("continue-on-error", self.workflow)
        self.assertEqual(self.workflow.count("persist-credentials: false"), 2)

    def test_four_native_results_are_independent_and_exact(self):
        self.assertEqual(self.workflow.count("if: always() && steps.compile.outcome == 'success'"), 4)
        for name in ("golden", "lifecycle", "kernel", "stdin"):
            self.assertIn("id: " + name, self.workflow)
            self.assertIn("steps." + name + ".outcome", self.workflow)
        self.assertIn("[('ok', '14', '0', '0', '0', '0')]", self.workflow)
        self.assertIn("[('ok', '6', '0', '0', '0', '0')]", self.workflow)
        self.assertIn('cargo test --locked --manifest-path src-tauri/Cargo.toml --test exec_input_contract 2>&1', self.workflow)

    def test_source_receipts_precede_setup_and_cleanup_precedes_upload(self):
        self.assertLess(self.workflow.index("git rev-parse HEAD"), self.workflow.index("actions/setup-python@"))
        self.assertEqual(self.workflow.count('test "$(cat evidence/source-sha.txt)" = "$GITHUB_SHA"'), 2)
        self.assertIn('export PATH="/usr/bin:$PATH"', self.workflow)
        final = self.workflow.index("name: Preserve all outcomes")
        self.assertLess(final, self.workflow.rindex("actions/upload-artifact@"))
        for module in ("sandbox_dispatch_probe", "sandbox_lifecycle_probe"):
            self.assertIn(f"test ! -e src-tauri/src/auth/{module}.rs", self.workflow[final:])
        for digest in probe.GOLDEN.values():
            self.assertIn(digest, self.workflow[final:])
        self.assertIn("| sha256sum --check", self.workflow[final:])

    def test_full_integration_retains_golden_then_adds_lifecycle(self):
        full = (ROOT / ".github/workflows/dot-rc-integration.yml").read_text()
        golden_command = "python3 tests/cloud-gateway/sandbox-dispatch/run_probe.py --evidence evidence/sandbox-dispatch"
        new_command = "python3 tests/cloud-gateway/sandbox-lifecycle/run_probe.py --evidence evidence/sandbox-lifecycle"
        self.assertEqual(full.count(golden_command), 1)
        self.assertEqual(full.count(new_command), 1)
        self.assertIn(golden_command + "\n          " + new_command, full)

    def test_only_three_native_cases_and_no_snapshot_metadata_grafting(self):
        source = (ROOT / "tests/cloud-gateway/linux_sandbox_lifecycle.rs").read_text()
        names = re.findall(r"#\[tokio::test\]\nasync fn (\w+)", source)
        self.assertEqual(tuple(names), probe.CASES)
        collector = source.split("async fn collect_terminal", 1)[1].split("async fn close", 1)[0]
        self.assertNotIn("sandbox_enforced", collector)
        self.assertNotIn("as_object_mut", collector)
        self.assertIn('raw = self', collector)
        self.assertEqual(probe.INJECTION, b'\n#[cfg(all(test, target_os = "linux", target_arch = "x86_64"))]\nmod sandbox_lifecycle_probe;\n')


if __name__ == "__main__":
    unittest.main()
