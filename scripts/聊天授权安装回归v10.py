"""Unit tests for package provenance (not actual package-installation evidence)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("packages_v10", Path(__file__).with_name("聊天授权安装核验v10.py"))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class PackageTests(unittest.TestCase):
    def test_exact_artifact_bytes_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); file = root / "候选包.deb"; file.write_bytes(b"canary")
            value = p.record(file)
            self.assertEqual(p.verify_record(root, value), file)
            file.write_bytes(b"changed")
            with self.assertRaises(ValueError): p.verify_record(root, value)

    def test_path_traversal_empty_and_invalid_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["../secret", "a/b", "a\\b", ".", "..", "", "/etc/passwd"]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    p.verify_record(Path(tmp), {"name":name,"size":1,"sha256":"a"*64})
            for size in [0, -1, True, "10"]:
                with self.subTest(size=size), self.assertRaises(ValueError):
                    p.verify_record(Path(tmp), {"name":"a.deb","size":size,"sha256":"a"*64})
            with self.assertRaises(ValueError): p.verify_record(Path(tmp), {"name":"a.deb","size":1,"sha256":"invalid"})

    def test_zero_length_directory_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); file = root / "empty"; file.touch()
            for path in [file,root]:
                with self.assertRaises(ValueError): p.record(path)
            file.write_bytes(b"test")
            link = root / "link"
            link.symlink_to(file)  # This unit suite runs on the Linux package builder.
            with self.assertRaises(ValueError): p.record(link)

    def test_elf_architecture_cannot_be_assumed_from_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "app"
            for header in [b"", b"MZ" + b"x"*30, b"\x7fELF\x01\x01" + b"x"*30]:
                file.write_bytes(header)
                with self.assertRaises(ValueError): p.elf(file)
            file.write_bytes(b"\x7fELF\x02\x01" + b"\0"*12 + b"\x3e\0")
            p.elf(file)

if __name__ == "__main__": unittest.main()
