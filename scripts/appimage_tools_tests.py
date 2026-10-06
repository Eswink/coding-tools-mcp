"""Twenty hermetic cases; downloaded payloads are never executed."""
import functools
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import appimage_tools as app


class AppImageToolsTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="appimage-tests-")
        self.addCleanup(self.scratch.cleanup)
        self.base = Path(self.scratch.name)
        self.root = self.base / "checkout"
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        (self.root / "src-tauri").mkdir()
        (self.root / app.LAUNCHER).write_bytes((Path(__file__).parent.parent / app.LAUNCHER).read_bytes())
        (self.root / "source.txt").write_text("tracked source\n")
        self.real_run = subprocess.run
        self.git("init", "-q", "--template=", "--initial-branch=main")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.source = self.git("rev-parse", "HEAD").stdout.decode().strip()
        self.target = self.root / "src-tauri/target"
        self.target.mkdir()
        self.directory = self.base / "originals"
        self.output = self.base / "prepare.json"
        self.real_tools = app.TOOLS
        self.real_normalized = app.NORMALIZED_SHA256
        self.data = {tool["name"]: (b"\x7fELFxxxxAI\x02payload" if index == 0 else f"inert fixture {index}\n".encode())
                     for index, tool in enumerate(self.real_tools)}
        pins = tuple(dict(t, size=len(self.data[t["name"]]), sha256=hashlib.sha256(self.data[t["name"]]).hexdigest())
                     for t in self.real_tools)
        raw = self.data[pins[0]["name"]]
        normalized_digest = hashlib.sha256(raw[:8] + b"\0\0\0" + raw[11:]).hexdigest()
        for name, value in (("TOOLS", pins), ("NORMALIZED_SHA256", normalized_digest)):
            patch = mock.patch.object(app, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.calls, self.override, self.failure = [], None, None
        self.status = b"200\nhttps://release-assets.githubusercontent.com/fixture\n"
        patch = mock.patch.object(app.subprocess, "run", side_effect=self.transport)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.dict(os.environ, {"LDAI_RUNTIME_FILE": str(self.directory / "runtime-x86_64")})
        patch.start()
        self.addCleanup(patch.stop)

    def git(self, *args):
        return self.real_run(["/usr/bin/git", *args], cwd=self.root, env=dict(app.CURL_ENV,
                             GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null"),
                             check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def transport(self, command, **kwargs):
        if command[0] == "cargo":
            return subprocess.CompletedProcess(command, 0, json.dumps({"target_directory": str(self.target)}).encode())
        if command[0] != "/usr/bin/curl":
            return self.real_run(command, **kwargs)
        self.calls.append((command, kwargs))
        if self.failure:
            raise self.failure
        tool = next(t for t in app.TOOLS if t["url"] == command[-1])
        os.write(kwargs["pass_fds"][0], self.data[tool["name"]] if self.override is None else self.override)
        kwargs["stdout"].write(self.status)
        return subprocess.CompletedProcess(command, 0)

    def acquire(self):
        self.directory.mkdir(exist_ok=True)
        app.download(app.TOOLS[0], self.directory, time.monotonic() + 300)

    def prepare(self):
        return app.prepare(self.root, self.target, self.directory, self.source, self.output)

    def verify(self, phase="before", filename="verify.json"):
        return app.verify(self.root, self.target, self.directory, self.source, phase, self.base / filename)

    def launcher(self):
        path = self.target / ".tauri/AppRun-x86_64"
        path.write_bytes((self.root / app.LAUNCHER).read_bytes())
        path.chmod(0o755)
        return path

    def test_manifest_has_exact_five_reviewed_sources_and_pin_provenance(self):
        expected = (
            ("linuxdeploy-x86_64.AppImage", 13264064, "e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef",
             182515537, "https://github.com/tauri-apps/binary-releases/releases/download/linuxdeploy/linuxdeploy-x86_64.AppImage"),
            ("linuxdeploy-plugin-appimage-x86_64.AppImage", 16488952, "49d6a17160675a6bd1781699aae6bdf7692d98552e02a3671d2183d10547842e",
             602435573, "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage"),
            ("runtime-x86_64", 944632, "156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074",
             596078161, "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"),
            ("linuxdeploy-plugin-gtk.sh", 14622, "7804c9eef13e59bf2783aad9882ef9db8f3f3f9e8d631874b1d348d550a3693f",
             "dda522bce37387f1b853d9095713bfaa924c8423", "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gtk/dda522bce37387f1b853d9095713bfaa924c8423/linuxdeploy-plugin-gtk.sh"),
            ("linuxdeploy-plugin-gstreamer.sh", 4857, "c107b49d84edbffc6ab226ed1007e0626a4f7aa2c3a36b7782bef62351d49e94",
             "2a2e67491c32995a3f279ad0ecbe77abd512b42a", "https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gstreamer/2a2e67491c32995a3f279ad0ecbe77abd512b42a/linuxdeploy-plugin-gstreamer.sh"),
        )
        self.assertEqual(tuple((t["name"], t["size"], t["sha256"], t.get("asset_id", t.get("commit")), t["url"])
                               for t in self.real_tools), expected)
        self.assertEqual(sum(t["size"] for t in self.real_tools), 30717127)
        self.assertEqual(self.real_normalized, "20eebde3c18ae2e44279bd624fc72482503aece216d5d77f10932235342f71c1")
        self.assertEqual(self.real_tools[0]["provenance"], "first-observed; upstream API digest null")
        self.assertEqual([t["provenance"] for t in self.real_tools[1:3]], ["upstream API SHA256"] * 2)
        self.assertEqual([t["cache_name"] for t in self.real_tools], ["linuxdeploy-x86_64.AppImage",
                         "linuxdeploy-plugin-appimage.AppImage", None, "linuxdeploy-plugin-gtk.sh", "linuxdeploy-plugin-gstreamer.sh"])

    def test_download_uses_bounded_https_curl_without_credentials_or_retry(self):
        with mock.patch.dict(os.environ, {"HTTPS_PROXY": "invalid", "CURL_CA_BUNDLE": "invalid", "LD_PRELOAD": "invalid"}):
            self.acquire()
        command, options = self.calls[0]
        self.assertEqual(command[:2], ["/usr/bin/curl", "--disable"])
        for key, value in (("--proto", "=https"), ("--proto-redir", "=https"), ("--max-redirs", "3"),
                           ("--max-filesize", str(app.TOOLS[0]["size"])), ("--connect-timeout", "20")):
            self.assertEqual(command[command.index(key) + 1], value)
        self.assertEqual(options["env"], {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"})
        self.assertTrue(0 < options["timeout"] <= 60)
        self.assertEqual(options["preexec_fn"].args, (app.TOOLS[0]["size"],))
        self.assertFalse(set(command) & {"-k", "--insecure", "--retry", "--netrc", "--user", "--config"})
        self.assertIn(f"/proc/self/fd/{options['pass_fds'][0]}", command)
        self.assertEqual(options["stderr"], subprocess.DEVNULL)

    def test_download_requires_http_200_and_allowed_final_host(self):
        for result in (b"206\nhttps://github.com/a\n", b"200\nhttp://github.com/a\n",
                       b"200\nhttps://evil.example/a\n", b"200\nhttps://user@github.com/a\n",
                       b"200\nhttps://github.com:444/a\n", b"200\nhttps://github.com/a\nextra\n", b"x" * 4097):
            with self.subTest(result=result[:50]):
                self.status = result
                with self.assertRaises(ValueError):
                    self.acquire()
                (self.directory / app.TOOLS[0]["name"]).unlink()
        self.assertEqual(len(self.calls), 7)

    def test_download_rejects_curl_failure(self):
        self.failure = subprocess.CalledProcessError(22, "/usr/bin/curl")
        with self.assertRaises(subprocess.CalledProcessError):
            self.prepare()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(list((self.target / ".tauri").iterdir()), [])

    def test_download_timeout_is_terminal_without_retry(self):
        self.failure = subprocess.TimeoutExpired("curl", 60)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.prepare()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, "deadline"):
            app.download(app.TOOLS[1], self.directory, time.monotonic() - 1)
        self.assertEqual(len(self.calls), 1)
        self.failure = None
        with mock.patch.object(app.time, "monotonic", side_effect=[0, 301]):
            with self.assertRaisesRegex(ValueError, "deadline"):
                app.download(app.TOOLS[1], self.directory, 300)
        self.assertEqual(len(self.calls), 2)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.real_run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.05,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def test_download_rejects_short_bytes(self):
        self.override = self.data[app.TOOLS[0]["name"]][:-1]
        with self.assertRaisesRegex(ValueError, "length"):
            self.acquire()
        self.assertEqual(len(self.calls), 1)

    def test_download_rejects_overflow_bytes(self):
        self.override = self.data[app.TOOLS[0]["name"]] + b"x"
        with self.assertRaisesRegex(ValueError, "length"):
            self.acquire()
        output = self.base / "bounded"
        with output.open("wb") as stream:
            result = self.real_run([sys.executable, "-c", "import os; os.write(1,b'x'*4096); os.write(1,b'x')"],
                                   stdout=stream, stderr=subprocess.DEVNULL, timeout=5,
                                   preexec_fn=functools.partial(app._file_limit, 8))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.stat().st_size, 8)

    def test_download_rejects_wrong_digest(self):
        self.override = b"x" * app.TOOLS[0]["size"]
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.acquire()
        self.assertFalse((self.directory / app.TOOLS[0]["name"]).stat().st_mode & 0o111)

    def test_prepare_preserves_originals_and_stages_expected_names(self):
        result = self.prepare()
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(result["phase"], "prepare")
        self.assertEqual(set(result["cache"]), {t["cache_name"] for t in app.TOOLS if t["cache_name"]})
        for tool in app.TOOLS:
            original = self.directory / tool["name"]
            self.assertEqual(original.read_bytes(), self.data[tool["name"]])
            self.assertEqual(stat.S_IMODE(original.stat().st_mode), 0o444)
            if tool["cache_name"]:
                cache = self.target / ".tauri" / tool["cache_name"]
                self.assertNotEqual(original.stat().st_ino, cache.stat().st_ino)
                self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o755)
        self.assertEqual(self.verify()["phase"], "before")

    def test_linuxdeploy_normalization_changes_only_three_marker_bytes(self):
        raw = self.data[app.TOOLS[0]["name"]]
        changed = app.normalized(raw)
        self.assertEqual([i for i, (a, b) in enumerate(zip(raw, changed)) if a != b], [8, 9, 10])
        self.assertEqual(len(raw), len(changed))
        self.assertEqual(changed[8:11], b"\0\0\0")
        with self.assertRaisesRegex(ValueError, "marker"):
            app.normalized(changed)
        with self.assertRaisesRegex(ValueError, "pin"):
            app.normalized(raw + b"altered")

    def test_prepare_rejects_existing_output_or_tools_directory(self):
        for path in (self.directory, self.target / ".tauri", self.output):
            with self.subTest(path=path):
                path.mkdir() if path != self.output else path.write_text("existing")
                with self.assertRaisesRegex(ValueError, "fresh|exists"):
                    self.prepare()
                self.assertEqual(len(self.calls), 0)
                path.rmdir() if path.is_dir() else path.unlink()

    def test_prepare_rejects_linked_parent_and_output_paths(self):
        alias = self.base / "alias"
        alias.symlink_to(self.base, target_is_directory=True)
        for directory, output in ((alias / "new", self.output), (self.directory, alias / "new.json")):
            with self.subTest(directory=directory, output=output), self.assertRaisesRegex(ValueError, "linked"):
                app.prepare(self.root, self.target, directory, self.source, output)
        self.output.symlink_to(self.base / "absent")
        with self.assertRaisesRegex(ValueError, "linked"):
            self.prepare()
        self.output.unlink()
        alias_target = self.base / "target-alias"
        alias_target.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "linked"):
            app.prepare(self.root, alias_target, self.directory, self.source, self.output)
        self.assertEqual(self.calls, [])

    def test_verification_rejects_symlink_and_hardlink_files(self):
        self.prepare()
        for directory in (self.directory, self.target / ".tauri"):
            path = directory / "linuxdeploy-x86_64.AppImage"
            original = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
            backup = self.base / "linked-content"
            for hard in (False, True):
                path.unlink()
                backup.write_bytes(original)
                backup.chmod(mode)
                os.link(backup, path) if hard else path.symlink_to(backup)
                with self.assertRaisesRegex(ValueError, "linked|single-link"):
                    self.verify()
                path.unlink()
                backup.unlink()
                path.write_bytes(original)
                path.chmod(mode)

    def test_verification_rejects_missing_or_extra_tools(self):
        self.prepare()
        for directory in (self.directory, self.target / ".tauri"):
            path = next(directory.iterdir())
            saved = self.base / "temporarily-removed"
            path.rename(saved)
            with self.assertRaisesRegex(ValueError, "inventory"):
                self.verify()
            saved.rename(path)
            extra = directory / "unexpected"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "inventory"):
                self.verify()
            extra.unlink()

    def test_verification_rejects_changed_cache_content(self):
        self.prepare()
        for tool in app.TOOLS:
            if not tool["cache_name"]:
                continue
            path = self.target / ".tauri" / tool["cache_name"]
            original = path.read_bytes()
            path.write_bytes(b"x" * len(original))
            with self.assertRaisesRegex(ValueError, "SHA256"):
                self.verify()
            path.write_bytes(original)
            path.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "mode"):
                self.verify()
            path.chmod(0o755)

    def test_runtime_environment_is_exact_local_pinned_file(self):
        self.prepare()
        runtime = self.directory / "runtime-x86_64"
        for value in ("", "runtime-x86_64", "https://github.com/runtime", str(runtime) + "/../runtime-x86_64"):
            with mock.patch.dict(os.environ, {"LDAI_RUNTIME_FILE": value}):
                with self.assertRaisesRegex(ValueError, "LDAI_RUNTIME_FILE"):
                    self.verify()
        self.assertEqual(self.verify()["runtime_file"], str(runtime))

    def test_before_phase_rejects_preexisting_apprun(self):
        self.prepare()
        self.launcher()
        with self.assertRaisesRegex(ValueError, "AppRun phase"):
            self.verify()

    def test_after_phase_requires_exact_project_launcher(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.verify("after")
        launcher = self.launcher()
        correct = launcher.read_bytes()
        launcher.write_bytes(b"x" * app.LAUNCHER_SIZE)
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.verify("after")
        launcher.write_bytes(correct)
        self.assertEqual(self.verify("after")["cache"]["AppRun-x86_64"]["sha256"], app.LAUNCHER_SHA256)

    def test_after_phase_preserves_all_original_tool_bytes(self):
        self.prepare()
        self.launcher()
        for tool in app.TOOLS:
            path = self.directory / tool["name"]
            path.chmod(0o644)
            path.write_bytes(b"x" * tool["size"])
            path.chmod(0o444)
            with self.assertRaisesRegex(ValueError, "SHA256"):
                self.verify("after")
            path.chmod(0o644)
            path.write_bytes(self.data[tool["name"]])
            path.chmod(0o444)
        self.assertTrue(self.verify("after")["passed"])

    def test_receipts_bind_source_and_keep_engineering_limits(self):
        (self.root / "evidence").mkdir()
        (self.root / "evidence/build.log").write_text("expected untracked output")
        with mock.patch.dict(os.environ, {"GIT_DIR": "/does/not/exist", "GIT_WORK_TREE": "/", "GIT_INDEX_FILE": "/bad",
                                         "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/bad", "GIT_CONFIG_COUNT": "1",
                                         "GIT_CONFIG_KEY_0": "core.worktree", "GIT_CONFIG_VALUE_0": "/bad"}):
            result = self.prepare()
        self.assertEqual(result["source_sha"], self.source)
        self.assertEqual(result["source_tree"], self.git("rev-parse", "HEAD^{tree}").stdout.decode().strip())
        self.assertEqual(result["source_root"], str(self.root))
        self.assertEqual(result["target_directory"], str(self.target))
        self.assertEqual(result["pins"], app.TOOLS)
        for field in ("security_approved", "release_approved", "publish_approved"):
            self.assertIs(result[field], False)
        self.assertTrue(result["engineering_only"] and result["untracked_outputs_allowed"])
        self.assertIn("No reproducible-source equivalence", result["limits"])
        self.assertEqual(json.loads(self.output.read_text())["source_sha"], self.source)
        with self.assertRaisesRegex(ValueError, "target directory mismatch"):
            app.target_path(self.root, self.base / "other-target")
        path = self.root / "source.txt"
        for flag in ("--assume-unchanged", "--skip-worktree"):
            self.git("update-index", flag, "source.txt")
            path.write_text("hidden worktree drift")
            with self.assertRaisesRegex(ValueError, "tracked worktree drift"):
                app.source_identity(self.root, self.source)
            path.write_text("tracked source\n")
            self.git("update-index", "--no-" + flag[2:], "source.txt")
        path.write_text("staged drift")
        self.git("add", "source.txt")
        path.write_text("tracked source\n")
        with self.assertRaises(subprocess.CalledProcessError):
            app.source_identity(self.root, self.source)
        self.git("reset", "-q", "HEAD", "--", "source.txt")
        for relative in ("objects/info/alternates", "commondir"):
            alternate = self.root / ".git" / relative
            alternate.write_text("/unrelated\n")
            with self.assertRaisesRegex(ValueError, "alternate"):
                app.source_identity(self.root, self.source)
            alternate.unlink()
        with self.assertRaisesRegex(ValueError, "actual HEAD"):
            app.source_identity(self.root, "0" * 40)
        self.git("pack-refs", "--all")
        self.assertEqual(app.source_identity(self.root, self.source)["source_sha"], self.source)
        # Neither local Git config nor ambient Git variables select this checkout.
        (self.root / ".git/config").write_text("invalid config that must never be parsed\n")
        self.assertEqual(app.source_identity(self.root, self.source)["source_sha"], self.source)


if __name__ == "__main__":
    unittest.main()
