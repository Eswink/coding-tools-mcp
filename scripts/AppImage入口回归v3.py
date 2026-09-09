"""AppImage entry regression; shell execution cases require Linux, not a native GUI."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
import venv
from unittest.mock import patch
import AppImage入口配置v3 as entry

ROOT = Path(__file__).resolve().parents[1]


class EntryConfigurationTests(unittest.TestCase):
    def test_ubuntu_config_uses_project_tools_and_hook(self):
        config = json.loads((ROOT / "src-tauri/Ubuntu桌面v1.json").read_text(encoding="utf-8"))
        self.assertTrue(config["bundle"]["useLocalToolsDir"])
        self.assertEqual(config["build"]["beforeBundleCommand"], "python3 scripts/AppImage入口配置v3.py")

    def test_launcher_has_no_python_or_path_mutation(self):
        script = (ROOT / entry.LAUNCHER).read_text(encoding="utf-8")
        for forbidden in ("export PYTHONHOME", "export PYTHONPATH", "unset PYTHON", "export PATH=", "env -i"):
            self.assertNotIn(forbidden, script)
        self.assertIn('exec "$app" "$@"', script)

    def test_missing_host_python_proof_blocks_publication(self):
        import Ubuntu发布回归v1 as fixtures
        import Ubuntu发布v1 as release
        fixture = fixtures.UbuntuReleaseTests("test_valid_package_digests")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        report = fixture.report("ubuntu-24.04", "appimage")
        value = json.loads(report.read_text())
        del value["host_python_environment_preserved"]
        report.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "host Python environment"):
            release.validate_reports(fixture.evidence, fixtures.SOURCE)

    def test_failed_host_python_proof_blocks_publication(self):
        import Ubuntu发布回归v1 as fixtures
        import Ubuntu发布v1 as release
        fixture = fixtures.UbuntuReleaseTests("test_valid_package_digests")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.mutate("host_python_environment_preserved", False)
        with self.assertRaisesRegex(ValueError, "host Python environment"):
            release.validate_reports(fixture.evidence, fixtures.SOURCE)

    def test_unreviewed_cli_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            (root / "package-lock.json").write_text(json.dumps({"packages": {
                "node_modules/@tauri-apps/cli": {"version": "99.0.0"}}}))
            with patch.object(platform, "system", return_value="Linux"), patch.object(platform, "machine", return_value="x86_64"):
                with self.assertRaisesRegex(RuntimeError, "CLI changed"):
                    entry.install(root)


@unittest.skipUnless(sys.platform == "linux", "Linux AppImage process-entry cases")
class EntryProcessTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="入口 空格v3-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.appdir = self.root / "软件目录v3"
        self.bin = self.appdir / "usr/bin/coding-tools-mcp-desktop"
        self.bin.parent.mkdir(parents=True)
        self.launcher = self.appdir / "AppRun.wrapped"
        shutil.copyfile(ROOT / entry.LAUNCHER, self.launcher)
        self.env = dict(os.environ)
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
            self.env.pop(key, None)

    def execute(self, program, args=()):
        self.bin.write_text(f"#!{sys.executable}\n" + program, encoding="utf-8")
        self.bin.chmod(0o755)
        return subprocess.run(["/bin/bash", str(self.launcher), *args], cwd=self.root,
                              env=self.env, text=True, capture_output=True, timeout=10)

    def test_python_with_unset_configuration_starts(self):
        result = self.execute("import encodings,os;print(os.getenv('PYTHONHOME'));print(os.getenv('PYTHONPATH'))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "None\nNone\n")

    def test_valid_custom_python_home_and_module_path_survive(self):
        modules = self.root / "用户模块v3"
        modules.mkdir()
        (modules / "用户模块v3.py").write_text("VALUE='用户Python环境保留'\n", encoding="utf-8")
        self.env.update(PYTHONHOME=sys.base_prefix, PYTHONPATH=str(modules))
        result = self.execute("import 用户模块v3,os;print(用户模块v3.VALUE);print(os.environ['PYTHONHOME']);print(os.environ['PYTHONPATH'])")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["用户Python环境保留", sys.base_prefix, str(modules)])

    def test_empty_python_configuration_remains_empty(self):
        self.env.update(PYTHONHOME="", PYTHONPATH="")
        result = self.execute("import os,json;print(json.dumps([os.getenv('PYTHONHOME'),os.getenv('PYTHONPATH')]))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["", ""])

    def test_path_arguments_cwd_and_original_library_suffix(self):
        self.env["LD_LIBRARY_PATH"] = "/host/custom/lib"
        args = ["中文 空格", "a'b", "$literal", "--option=value", ""]
        result = self.execute("import os,sys,json;print(json.dumps([os.environ['PATH'],sys.argv[1:],os.getcwd(),os.environ['LD_LIBRARY_PATH']]))", args)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value[:3], [self.env["PATH"], args, str(self.appdir / "usr")])
        self.assertEqual(value[3], f"{self.appdir}/usr/lib:{self.appdir}/usr/lib/x86_64-linux-gnu:/host/custom/lib")

    def test_virtual_environment_path_is_preserved(self):
        environment = self.root / "虚拟环境v3"
        venv.EnvBuilder(with_pip=False).create(environment)
        self.env["PATH"] = str(environment / "bin") + os.pathsep + self.env["PATH"]
        result = self.execute("import subprocess;subprocess.run(['python3','-c','import sys;print(sys.prefix)'],check=True)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(environment))

    def test_payload_failure_is_propagated(self):
        self.assertEqual(self.execute("raise SystemExit(23)").returncode, 23)

    def test_missing_payload_fails_closed(self):
        result = subprocess.run(["/bin/bash", str(self.launcher)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 126)

    def test_existing_generic_launcher_is_replaced_and_digest_matches(self):
        (self.root / "package-lock.json").write_bytes((ROOT / "package-lock.json").read_bytes())
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / entry.LAUNCHER, self.root / entry.LAUNCHER)
        target = self.root / "构建v3"
        tools = target / ".tauri"
        tools.mkdir(parents=True)
        (tools / "AppRun-x86_64").write_bytes(b"old-generic-launcher")
        with patch.object(entry.subprocess, "check_output", return_value=json.dumps({"target_directory": str(target)})):
            path = entry.install(self.root)
        self.assertEqual(entry.digest(path), entry.digest(ROOT / entry.LAUNCHER))
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def test_cargo_metadata_uses_the_tauri_directory(self):
        (self.root / "package-lock.json").write_bytes((ROOT / "package-lock.json").read_bytes())
        (self.root / "scripts").mkdir()
        shutil.copyfile(ROOT / entry.LAUNCHER, self.root / entry.LAUNCHER)
        target = self.root / "相对目标v3"
        with patch.object(entry.subprocess, "check_output", return_value=json.dumps({"target_directory": str(target)})) as metadata:
            entry.install(self.root)
        self.assertEqual(metadata.call_args.kwargs.get("cwd"), self.root / "src-tauri")

    def test_symlink_tools_directory_is_rejected(self):
        (self.root / "package-lock.json").write_bytes((ROOT / "package-lock.json").read_bytes())
        target = self.root / "构建v3"
        target.mkdir()
        (target / ".tauri").symlink_to(self.appdir, target_is_directory=True)
        with patch.object(entry.subprocess, "check_output", return_value=json.dumps({"target_directory": str(target)})):
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                entry.install(self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
