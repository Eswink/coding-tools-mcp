"""Owned runner-process and workflow wiring contracts, split without dropping cases."""
import os
from pathlib import Path
import re
import sys
import time
import unittest

from test_linux_lifecycle_probe import ROOT, probe


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
        self.assertIn("branches: ['test/linux-auth-deadlines-20261001']", self.workflow)
        self.assertNotIn("pull_request:", self.workflow)
        self.assertNotIn("workflow_dispatch:", self.workflow)
        self.assertEqual(self.workflow.count("github.ref == 'refs/heads/test/linux-auth-deadlines-20261001'"), 2)
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
        for module in ("sandbox_dispatch_probe", *(Path(name).stem for name in probe.PAYLOADS)):
            self.assertIn(f"test ! -e src-tauri/src/auth/{module}.rs", self.workflow[final:])
        for digest in probe.GOLDEN.values():
            self.assertIn(digest, self.workflow[final:])
        self.assertIn("| sha256sum --check", self.workflow[final:])

    def test_stdin_uses_owned_native_keyring_before_unchanged_tests(self):
        dependencies = self.workflow.split("- name: Native Linux development libraries", 1)[1].split("- name:", 1)[0]
        self.assertIn("dbus-x11 gnome-keyring", dependencies)
        stdin = self.workflow.split("- name: Six unchanged child stdin and deadline contracts", 1)[1].split("- name:", 1)[0]
        command = "cargo test --locked --manifest-path src-tauri/Cargo.toml --test exec_input_contract 2>&1 | tee evidence/exec-input.txt"
        ordered = (
            'export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}" RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"',
            'fixture_root="$(mktemp -d "$RUNNER_TEMP/linux-lifecycle-stdin.XXXXXX")"',
            'trap \'rm -rf -- "$fixture_root"\' EXIT',
            'export HOME="$fixture_root/home"',
            'mkdir -p "$HOME"',
            'chmod 700 "$HOME"',
            'unset DBUS_SESSION_BUS_ADDRESS GNOME_KEYRING_CONTROL SSH_AUTH_SOCK',
            "dbus-run-session -- bash -euo pipefail -c '",
            'printf "%s" "isolated-rc-ci-fixture" | gnome-keyring-daemon --unlock --components=secrets',
            command,
            '"$HOST_PYTHON" -',
        )
        offsets = [stdin.index(part) for part in ordered]
        self.assertEqual(offsets, sorted(offsets))
        for name, directory in (("XDG_RUNTIME_DIR", "runtime"), ("XDG_DATA_HOME", "data"),
                                ("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"),
                                ("XDG_CACHE_HOME", "cache")):
            self.assertIn(f'{name}="$fixture_root/{directory}"', stdin)
            for prefix in ('mkdir -p "$HOME"', 'chmod 700 "$HOME"'):
                line = next(line for line in stdin.splitlines() if prefix in line)
                self.assertIn(f'"${name}"', line)
        self.assertEqual(stdin.count(command), 1)
        self.assertNotIn("--test-threads", stdin)
        self.assertNotIn("--features", stdin)
        self.assertNotIn("--skip", stdin)
        self.assertIn("[('ok', '6', '0', '0', '0', '0')]", stdin)

    def test_full_integration_retains_golden_then_adds_lifecycle(self):
        full = (ROOT / ".github/workflows/dot-rc-integration.yml").read_text()
        golden_command = "python3 tests/cloud-gateway/sandbox-dispatch/run_probe.py --evidence evidence/sandbox-dispatch"
        new_command = "python3 tests/cloud-gateway/sandbox-lifecycle/run_probe.py --evidence evidence/sandbox-lifecycle"
        self.assertEqual(full.count(golden_command), 1)
        self.assertEqual(full.count(new_command), 1)
        self.assertIn(golden_command + "\n          " + new_command, full)

    def test_exact_seven_native_cases_and_no_snapshot_metadata_grafting(self):
        source = (ROOT / "tests/cloud-gateway/linux_sandbox_lifecycle.rs").read_text()
        names = re.findall(r"#\[(?:tokio::)?test\]\n(?:async )?fn (\w+)", source)
        deadline = (ROOT / "tests/cloud-gateway/linux_sandbox_deadline.rs").read_text()
        names += re.findall(r"#\[(?:tokio::)?test\]\n(?:async )?fn (\w+)", deadline)
        self.assertEqual(tuple(names), probe.CASES)
        self.assertEqual(len(names), 7)
        self.assertIn("A/D/deadline HTTP and E direct dispatcher", self.workflow)
        self.assertIn("Six HTTP cases and one direct primary dispatcher case", self.workflow)
        support = (ROOT / "tests/cloud-gateway/linux_sandbox_lifecycle_support.rs").read_text()
        collector = support.split("async fn collect_terminal", 1)[1].split("async fn close", 1)[0]
        self.assertNotIn("sandbox_enforced", collector)
        self.assertNotIn("as_object_mut", collector)
        self.assertIn('raw = self', collector)
        self.assertEqual(probe.INJECTION, b'\n#[cfg(all(test, target_os = "linux", target_arch = "x86_64"))]\nmod sandbox_lifecycle_probe;\n')


    def test_three_payload_paths_hashes_and_module_wiring_are_exact(self):
        self.assertEqual(probe.PAYLOADS, {
            "sandbox_lifecycle_probe.rs": "tests/cloud-gateway/linux_sandbox_lifecycle.rs",
            "linux_sandbox_lifecycle_support.rs": "tests/cloud-gateway/linux_sandbox_lifecycle_support.rs",
            "linux_sandbox_deadline.rs": "tests/cloud-gateway/linux_sandbox_deadline.rs",
        })
        root = (ROOT / probe.PAYLOADS["sandbox_lifecycle_probe.rs"]).read_text()
        for name, module in (("linux_sandbox_lifecycle_support.rs", "support"),
                             ("linux_sandbox_deadline.rs", "deadline")):
            self.assertIn(f'#[path = "{name}"]\nmod {module};', root)
        self.assertEqual(len(set(probe.CASE_PATHS.values())), 7)
        for name in probe.CASES:
            prefix = "deadline::" if name in probe.CASES[-2:] else ""
            self.assertEqual(probe.CASE_PATHS[name], "auth::sandbox_lifecycle_probe::" + prefix + name)

    def test_all_payloads_are_formatted_and_all_contracts_discovered(self):
        command = next(line for line in self.workflow.splitlines() if "rustfmt --edition" in line)
        self.assertIn("--check", command)
        for source in probe.PAYLOADS.values():
            self.assertIn(source, command)
        self.assertIn("-p 'test_linux_lifecycle_*.py'", self.workflow)
        paths = [*probe.PAYLOADS.values(), "tests/cloud-gateway/sandbox-lifecycle/run_probe.py",
                 "tests/delivery/test_linux_lifecycle_probe.py", "tests/delivery/test_linux_lifecycle_wiring.py"]
        for path in paths:
            with self.subTest(path=path):
                self.assertLessEqual(len((ROOT / path).read_text().splitlines()), 500)

    def test_deadline_fixture_has_real_controls_and_panic_safe_cleanup(self):
        source = (ROOT / "tests/cloud-gateway/linux_sandbox_deadline.rs").read_text()
        script = source.split('const TREE: &str = r#"', 1)[1].split('"#;', 1)[0]
        compile(script, "owned-tree-fixture", "exec")
        for proof in ("subprocess.Popen([sys.executable", "temporary.replace(root / name)",
                      "child.wait(timeout=1)", "os.getpid()", "os.getppid()", "os.getpgrp()",
                      "except PermissionError as error", "socket.socket(socket.AF_INET", "time.monotonic() + 20"):
            self.assertIn(proof, script)
        for proof in ("timeout_at(until, s.rpc", '"filesystem": 13, "network": 1',
                      "current.start == item.start", 'current.state != "Z"',
                      "owned[1].ppid, owned[0].pid", "owned[0].pid, owned[1].pid",
                      "TREE_CONTROL_EFFECTS", "TREE_READY", "TREE_PROGRESS", "TREE_STOPPED",
                      "TREE_NO_LATER_EFFECT", 'Some("TREE_CONTROL_OK\\n")',
                      "readiness exceeded deadline", "owned cleanup unconfirmed", "std::panic::resume_unwind(error.into_panic())"):
            self.assertIn(proof, source)
        case = source.split("async fn run_case", 1)[1]
        self.assertLess(case.index("control(&server"), case.index("exercise(&server"))
        self.assertLess(case.index("exercise(&server"), case.index("tree.cleanup(server)"))
        self.assertLess(case.index("tree.cleanup(server)"), case.index("server.close()"))
        self.assertLess(case.index("server.close()"), case.index("std::panic::resume_unwind"))
        quiet = source.split("async fn no_later_effect", 1)[1].split("async fn cleanup", 1)[0]
        self.assertIn("let before = self.counters()", quiet)
        self.assertIn("Duration::from_millis(500)", quiet)
        self.assertNotIn("as_object_mut", source)
        self.assertNotIn("--no-sandbox", source)
        self.assertNotIn("pkill", source)


if __name__ == "__main__":
    unittest.main()
