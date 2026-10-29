"""Stable-channel x.y.z admission for the RC packaging gate path; RC behaviour stays unchanged."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

# Kept in a subdirectory so the frozen top-level scripts/*.py inventory of
# Windows标准用户验收v22.py stays within its 300-entry cap; the modules under test
# remain top-level in scripts/ and are imported from there explicitly.
SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import rc_native_gate  # noqa: E402
import rc_packages  # noqa: E402
import rc_version_gate as gate  # noqa: E402

RC_PATTERN = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-rc\.(?:0|[1-9]\d*)"
NEGATIVE = ("0.7.0-beta.1", "0.7.0+x", "v0.7.0", "07.0.0", "0.07.0", "0.7.00", "0.7", "0.7.0.0",
            "0.7.0\n", " 0.7.0", "٠.7.0", "", "0.7.0-rc", "0.7.0-rc.03")


def write_tree(root: Path, version: str, *, lock_root: str | None = None) -> None:
    (root / "src-tauri").mkdir(exist_ok=True)
    (root / "package.json").write_text(json.dumps({"name": gate.PACKAGE, "version": version}), encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({
        "name": gate.PACKAGE, "version": version,
        "packages": {"": {"name": gate.PACKAGE, "version": lock_root or version}},
    }), encoding="utf-8")
    (root / "src-tauri/Cargo.toml").write_text(
        f'[package]\nname = "{gate.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
    (root / "src-tauri/Cargo.lock").write_text(
        f'[[package]]\nname = "{gate.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
    (root / "src-tauri/tauri.conf.json").write_text(json.dumps({"version": version}), encoding="utf-8")


def git_tree(root: Path, version: str, **kwargs) -> str:
    write_tree(root, version, **kwargs)
    env = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "t"]):
        subprocess.run(["git", *args], cwd=root, check=True, env={**env, "PATH": "/usr/bin:/bin"},
                       stdout=subprocess.DEVNULL)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True,
                          capture_output=True).stdout.strip()


class StableChannelRegexTests(unittest.TestCase):
    def test_rc_regex_is_byte_identical(self):
        self.assertEqual(gate.RC_VERSION.pattern, RC_PATTERN)
        self.assertEqual(rc_native_gate.RC_VERSION.pattern, RC_PATTERN)
        self.assertEqual(rc_packages.RC_VERSION.pattern,
                         r"((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))-rc\.((?:0|[1-9]\d*))")

    def test_stable_regex_accepts_only_strict_xyz(self):
        for value in ("0.7.0", "0.0.0", "10.20.30"):
            self.assertTrue(gate.STABLE_VERSION.fullmatch(value), value)
            self.assertTrue(rc_native_gate.STABLE_VERSION.fullmatch(value), value)
            self.assertEqual(gate.version_channel(value), "stable")
        for value in NEGATIVE + ("0.7.0-rc.3",):
            self.assertFalse(gate.STABLE_VERSION.fullmatch(value), repr(value))
            self.assertFalse(rc_native_gate.STABLE_VERSION.fullmatch(value), repr(value))
            self.assertEqual(gate.version_channel(value), "rc")

    def test_rc_regex_still_rejects_stable(self):
        self.assertFalse(gate.RC_VERSION.fullmatch("0.7.0"))
        self.assertTrue(gate.RC_VERSION.fullmatch("0.7.0-rc.3"))


class StableChannelProjectTests(unittest.TestCase):
    def test_stable_positive_on_stable_channel(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0")
            self.assertEqual(gate.project_versions(Path(raw), "stable")[0], "0.7.0")
            self.assertEqual(gate.source_channel(Path(raw)), "stable")

    def test_rc_positive_on_rc_channel_unchanged(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0-rc.3")
            self.assertEqual(gate.project_versions(Path(raw))[0], "0.7.0-rc.3")
            self.assertEqual(gate.project_versions(Path(raw), "rc")[0], "0.7.0-rc.3")
            self.assertEqual(gate.source_channel(Path(raw)), "rc")

    def test_rc_version_via_stable_channel_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0-rc.3")
            with self.assertRaisesRegex(ValueError, "strict major.minor.patch"):
                gate.project_versions(Path(raw), "stable")

    def test_stable_version_via_rc_channel_rejects_with_original_message(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0")
            with self.assertRaisesRegex(ValueError, re.escape("candidate versions must all use major.minor.patch-rc.N")):
                gate.project_versions(Path(raw))

    def test_negative_versions_reject_on_both_channels(self):
        for value in NEGATIVE:
            if not value or "\n" in value:
                continue
            with tempfile.TemporaryDirectory() as raw:
                write_tree(Path(raw), value)
                for channel in ("stable", "rc"):
                    with self.assertRaises(ValueError, msg=(value, channel)):
                        gate.project_versions(Path(raw), channel)

    def test_mixed_channel_fields_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0", lock_root="0.7.0-rc.3")
            for channel in ("stable", "rc"):
                with self.assertRaises(ValueError, msg=channel):
                    gate.project_versions(Path(raw), channel)

    def test_unknown_channel_rejects(self):
        with tempfile.TemporaryDirectory() as raw:
            write_tree(Path(raw), "0.7.0")
            with self.assertRaisesRegex(ValueError, "unknown version channel"):
                gate.project_versions(Path(raw), "beta")


class StableChannelVerifySourceTests(unittest.TestCase):
    def test_verify_source_stable_and_rc_positive(self):
        for version in ("0.7.0", "0.7.0-rc.3"):
            with tempfile.TemporaryDirectory() as raw:
                sha = git_tree(Path(raw), version)
                report = gate.verify_source(Path(raw), sha, version)
                self.assertEqual((report["version"], report["source_sha"], report["passed"]), (version, sha, True))
                self.assertEqual(report["scope"], "release-candidate-version-and-source")

    def test_cli_accepts_stable_and_rc(self):
        for version in ("0.7.0", "0.7.0-rc.3"):
            with tempfile.TemporaryDirectory() as raw:
                sha = git_tree(Path(raw), version)
                result = subprocess.run([sys.executable, str(SCRIPTS / "rc_version_gate.py"), "--root", raw,
                                         "--expect-sha", sha, "--expect-version", version],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_expected_negatives_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            sha = git_tree(Path(raw), "0.7.0")
            for value in NEGATIVE:
                with self.assertRaises(ValueError, msg=repr(value)):
                    gate.verify_source(Path(raw), sha, value)

    def test_cross_channel_expected_versions_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            sha = git_tree(Path(raw), "0.7.0")
            with self.assertRaises(ValueError):
                gate.verify_source(Path(raw), sha, "0.7.0-rc.3")
            with self.assertRaises(ValueError):
                gate.verify_source(Path(raw), sha, "0.7.0", channel="rc")
            with self.assertRaises(ValueError):
                gate.verify_source(Path(raw), sha)  # no expected version keeps the rc-only default
        with tempfile.TemporaryDirectory() as raw:
            sha = git_tree(Path(raw), "0.7.0-rc.3")
            with self.assertRaises(ValueError):
                gate.verify_source(Path(raw), sha, "0.7.0")
            with self.assertRaises(ValueError):
                gate.verify_source(Path(raw), sha, "0.7.0-rc.3", channel="stable")


class StableChannelPackageAndNativeTests(unittest.TestCase):
    def test_deb_package_version(self):
        self.assertEqual(rc_packages.deb_package_version("0.7.0"), "0.7.0")
        self.assertEqual(rc_packages.deb_package_version("0.7.0-rc.3"), "0.7.0~rc3")
        with self.assertRaises(ValueError):
            rc_packages.debian_version("0.7.0")  # RC mapping itself stays RC-only
        for value in NEGATIVE:
            with self.assertRaises(ValueError, msg=repr(value)):
                rc_packages.deb_package_version(value)

    def test_native_gate_version_check(self):
        base = dict(source="a" * 40, run_id="1", kind="nsis", binary_sha256="b" * 64)
        for value in NEGATIVE:
            with self.assertRaisesRegex(Exception, "invalid release-candidate version", msg=repr(value)):
                rc_native_gate.verify({}, version=value, **base)
        for value in ("0.7.0", "0.7.0-rc.3"):
            try:
                rc_native_gate.verify({}, version=value, **base)
            except Exception as error:  # later evidence checks fail on the empty record, not the version
                self.assertNotIn("invalid release-candidate version", str(error))

    def test_windows_install_ps1_regexes(self):
        text = (SCRIPTS / "rc_windows_install.ps1").read_text(encoding="utf-8")
        rc = r"'^(?<major>0|[1-9][0-9]*)\.(?<minor>0|[1-9][0-9]*)\.(?<patch>0|[1-9][0-9]*)-rc\.(?<rc>0|[1-9][0-9]*)$'"
        stable = r"'^(?<major>0|[1-9][0-9]*)\.(?<minor>0|[1-9][0-9]*)\.(?<patch>0|[1-9][0-9]*)\z'"
        self.assertIn(rc, text)
        self.assertIn(stable, text)
        self.assertLess(text.index(rc), text.index(stable))
        pattern = re.compile(stable.strip("'").replace(r"\z", r"\Z").replace("(?<", "(?P<"))
        self.assertTrue(pattern.match("0.7.0"))
        for value in NEGATIVE + ("0.7.0-rc.3",):
            self.assertIsNone(pattern.match(value), repr(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
