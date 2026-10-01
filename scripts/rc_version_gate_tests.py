from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib
import unittest

import cloud_release_bundle as cloud

MODULE_PATH = Path(__file__).with_name("rc_version_gate.py")
spec = importlib.util.spec_from_file_location("rc_version_gate", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)

ROOT = MODULE_PATH.parent.parent
PRODUCT_FILES = (
    "package.json", "package-lock.json", "src-tauri/Cargo.toml",
    "src-tauri/Cargo.lock", "src-tauri/tauri.conf.json",
    "services/cloud-gateway/Cargo.toml", "services/cloud-gateway/Cargo.lock",
)
INDEPENDENT_FILES = (
    "services/cloud-agent/Cargo.toml", "services/cloud-agent/Cargo.lock",
    "services/local-agent/Cargo.toml", "services/local-agent/Cargo.lock", "pnpm-lock.yaml",
)


def expected_version_bytes(name: str, raw: bytes, previous: str, version: str) -> bytes:
    """Test-only exact token transition; never reserialize or write source files."""
    if name not in PRODUCT_FILES or not module.RC_VERSION.fullmatch(version):
        raise ValueError("invalid product transition")
    old, new = previous.encode(), version.encode()
    if name == "package-lock.json":
        prefixes = (
            b'  "name": "coding-tools-mcp-desktop",\n  "version": "',
            b'    "": {\n      "name": "coding-tools-mcp-desktop",\n      "version": "',
        )
    elif name.endswith(".json"):
        prefixes = (b'  "version": "',)
    else:
        package = "coding-tools-cloud-gateway" if name.startswith("services/") else module.PACKAGE
        prefixes = (f'name = "{package}"\nversion = "'.encode(),)
    result = raw
    for prefix in prefixes:
        token = prefix + old + b'"'
        if result.count(token) != 1:
            raise ValueError("own-version token must be unique: " + name)
        result = result.replace(token, prefix + new + b'"', 1)
    return result


def verify_metadata_transition(root: Path, baseline: str, version: str) -> dict:
    """Read a fixed Git baseline and prove that only the eight product fields moved."""
    if not module.SHA.fullmatch(baseline):
        raise ValueError("exact baseline SHA required")
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline, "HEAD"], cwd=root,
                   check=True, capture_output=True, timeout=20)
    actual, _ = module.project_versions(root)
    if actual != version:
        raise ValueError("unexpected current product version")
    components = cloud.versions(root, version)
    files = {}
    for name in (*PRODUCT_FILES, *INDEPENDENT_FILES):
        before = subprocess.check_output(["git", "show", baseline + ":" + name], cwd=root, timeout=20)
        after = (root / name).read_bytes()
        expected = before
        if name in PRODUCT_FILES:
            if name.endswith(".json"):
                previous = json.loads(before)["version"]
            elif name.endswith(".toml"):
                previous = tomllib.loads(before.decode())["package"]["version"]
            else:
                package = "coding-tools-cloud-gateway" if name.startswith("services/") else module.PACKAGE
                entries = [p for p in tomllib.loads(before.decode())["package"] if p["name"] == package]
                if len(entries) != 1:
                    raise ValueError("baseline self-lock identity is not unique")
                previous = entries[0]["version"]
            expected = expected_version_bytes(name, before, previous, version)
        if after != expected:
            raise ValueError("unexpected metadata/dependency bytes: " + name)
        files[name] = {"before_sha256": hashlib.sha256(before).hexdigest(),
                       "after_sha256": hashlib.sha256(after).hexdigest(),
                       "product_fields_only": name in PRODUCT_FILES}
    return {"scope": "engineering-product-version-transition-only", "passed": True,
            "baseline_sha": baseline, "version": version, "component_versions": components,
            "files": files, "publish_approved": False}


def product_fixture(root: Path, version: str = "0.7.0-rc.1") -> None:
    """Copy actual metadata into a disposable fixture, with independent components."""
    for name in (*PRODUCT_FILES, *INDEPENDENT_FILES):
        raw = (ROOT / name).read_bytes()
        if name in PRODUCT_FILES:
            if name.startswith("services/"):
                previous = tomllib.loads((ROOT / "services/cloud-gateway/Cargo.toml").read_text())["package"]["version"]
            else:
                previous = json.loads((ROOT / "package.json").read_bytes())["version"]
            raw = expected_version_bytes(name, raw, previous, version)
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


class RcVersionGateTests(unittest.TestCase):
    def test_rc_regex_accepts_only_numbered_rc(self):
        self.assertTrue(module.RC_VERSION.fullmatch("0.6.0-rc.1"))
        for value in ["0.6.0", "0.6.0-beta.1", "0.6.0-rc", "01.6.0-rc.1"]:
            self.assertFalse(module.RC_VERSION.fullmatch(value), value)

    def test_project_versions_requires_all_six_fields(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src-tauri").mkdir()
            version = "0.6.0-rc.1"
            (root / "package.json").write_text(json.dumps({"name": module.PACKAGE, "version": version}), encoding="utf-8")
            (root / "package-lock.json").write_text(json.dumps({
                "name": module.PACKAGE, "version": version,
                "packages": {"": {"name": module.PACKAGE, "version": version}},
            }), encoding="utf-8")
            (root / "src-tauri/Cargo.toml").write_text(
                f'[package]\nname = "{module.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
            (root / "src-tauri/Cargo.lock").write_text(
                f'[[package]]\nname = "{module.PACKAGE}"\nversion = "{version}"\n', encoding="utf-8")
            (root / "src-tauri/tauri.conf.json").write_text(json.dumps({"version": version}), encoding="utf-8")
            actual, fields = module.project_versions(root)
            self.assertEqual(actual, version)
            self.assertEqual(len(fields), 6)
            changed = json.loads((root / "package-lock.json").read_text())
            changed["packages"][""]["version"] = "0.6.0-rc.2"
            (root / "package-lock.json").write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differ"):
                module.project_versions(root)

    def test_new_minor_rc_and_actual_product_authorities_are_coherent(self):
        self.assertTrue(module.RC_VERSION.fullmatch("0.7.0-rc.1"))
        version, fields = module.project_versions(ROOT)
        self.assertEqual(len(fields), 6)
        components = cloud.versions(ROOT, version)
        self.assertEqual(components["coding-tools-cloud-gateway"], version)

    def test_each_desktop_version_field_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name, occurrence in (("package.json", 0), ("package-lock.json", 0),
                                     ("package-lock.json", 1), ("src-tauri/Cargo.toml", 0),
                                     ("src-tauri/Cargo.lock", 0), ("src-tauri/tauri.conf.json", 0)):
                with self.subTest(name=name, occurrence=occurrence):
                    product_fixture(root)
                    path = root / name
                    data = path.read_bytes()
                    positions = [m.start() for m in re.finditer(b"0\\.7\\.0-rc\\.1", data)]
                    index = positions[occurrence]
                    path.write_bytes(data[:index] + b"0.7.0-rc.2" + data[index + len(b"0.7.0-rc.1"):])
                    with self.assertRaisesRegex(ValueError, "differ"):
                        module.project_versions(root)

    def test_gateway_manifest_lock_and_product_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for names in (("Cargo.toml",), ("Cargo.lock",), ("Cargo.toml", "Cargo.lock")):
                with self.subTest(names=names):
                    product_fixture(root)
                    for name in names:
                        path = root / "services/cloud-gateway" / name
                        path.write_bytes(path.read_bytes().replace(b"0.7.0-rc.1", b"0.7.0-rc.2"))
                    with self.assertRaisesRegex(ValueError, "component lock|gateway product"):
                        cloud.versions(root, "0.7.0-rc.1")

    def test_independent_component_versions_are_not_forced_to_product(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            product_fixture(root)
            for folder in ("cloud-agent", "local-agent"):
                name = "coding-tools-" + folder
                for filename in ("Cargo.toml", "Cargo.lock"):
                    path = root / "services" / folder / filename
                    token = f'name = "{name}"\nversion = "0.1.0"'.encode()
                    data = path.read_bytes()
                    self.assertEqual(data.count(token), 1)
                    path.write_bytes(data.replace(token, token.replace(b"0.1.0", b"0.2.0"), 1))
            components = cloud.versions(root, "0.7.0-rc.1")
            self.assertEqual(components["coding-tools-cloud-agent"], "0.2.0")
            self.assertEqual(components["coding-tools-local-agent"], "0.2.0")

    def test_byte_transition_preserves_dependency_and_checksum_tokens(self):
        before = (b'[[package]]\nname = "coding-tools-cloud-gateway"\nversion = "0.1.0"\n'
                  b'\n[[package]]\nname = "dependency"\nversion = "0.1.0"\nchecksum = "abc"\n')
        expected = before.replace(b'version = "0.1.0"', b'version = "0.7.0-rc.1"', 1)
        result = expected_version_bytes("services/cloud-gateway/Cargo.lock", before, "0.1.0", "0.7.0-rc.1")
        self.assertEqual(result, expected)
        for changed in (expected.replace(b'checksum = "abc"', b'checksum = "def"'),
                        expected.replace(b'version = "0.1.0"', b'version = "0.7.0-rc.1"'),
                        expected + b"\n"):
            self.assertNotEqual(result, changed)
        for bad in (before.replace(b"coding-tools-cloud-gateway", b"wrong-name"), before + before):
            with self.assertRaisesRegex(ValueError, "unique"):
                expected_version_bytes("services/cloud-gateway/Cargo.lock", bad, "0.1.0", "0.7.0-rc.1")

    def test_fixed_git_transition_rejects_extra_bytes_and_unavailable_base(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            product_fixture(root, "0.6.0-rc.4")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Metadata fixture", "-c",
                            "user.email=fixture@example.invalid", "commit", "-qm", "fixture"],
                           cwd=root, check=True)
            baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            product_fixture(root)
            proof = verify_metadata_transition(root, baseline, "0.7.0-rc.1")
            self.assertTrue(proof["passed"])
            self.assertFalse(proof["publish_approved"])
            for name in (*PRODUCT_FILES, *INDEPENDENT_FILES):
                with self.subTest(name=name):
                    path = root / name
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n")
                    with self.assertRaisesRegex(ValueError, "unexpected metadata/dependency bytes"):
                        verify_metadata_transition(root, baseline, "0.7.0-rc.1")
                    path.write_bytes(original)
            path = root / "services/cloud-gateway/Cargo.lock"
            original = path.read_bytes()
            for changed in (re.sub(rb'(checksum = ")[0-9a-f]', rb'\g<1>z', original, count=1),
                            original.replace(b'version = "0.1.0"', b'version = "0.2.0"', 1)):
                path.write_bytes(changed)
                with self.assertRaisesRegex(ValueError, "unexpected metadata/dependency bytes"):
                    verify_metadata_transition(root, baseline, "0.7.0-rc.1")
            path.write_bytes(original)
            with self.assertRaises(subprocess.CalledProcessError):
                verify_metadata_transition(root, "a" * 40, "0.7.0-rc.1")


if __name__ == "__main__":
    unittest.main()
