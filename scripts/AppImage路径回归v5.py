"""Regression for release WebKit's package-relative helper layout, without GUI mocks."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import AppImage入口配置v3 as entry

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path('usr/lib/x86_64-linux-gnu/webkit2gtk-4.1')

class PackageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='布局v5-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('WebKitNetworkProcess', 'WebKitWebProcess', 'injected-bundle/libwebkit2gtkinjectedbundle.so'):
            path = self.root / PREFIX / name
            path.parent.mkdir(parents=True, exist_ok=True)
            header = bytearray(20)
            header[:6] = b'\x7fELF\x02\x01'
            header[18:20] = b'\x3e\x00'
            path.write_bytes(header)
            path.chmod(0o755)

    def test_all_required_helpers_are_validated(self):
        result = entry.verify_helpers(self.root)
        self.assertEqual(len(result), 3)
        for name, summary in result.items():
            self.assertEqual(summary['sha256'], hashlib.sha256((self.root / name).read_bytes()).hexdigest())

    def test_missing_helper_fails_closed(self):
        (self.root / PREFIX / 'WebKitNetworkProcess').unlink()
        with self.assertRaises(RuntimeError):
            entry.verify_helpers(self.root)

    def test_wrong_architecture_fails_closed(self):
        path = self.root / PREFIX / 'WebKitWebProcess'
        raw = bytearray(path.read_bytes()); raw[18:20] = b'\xb7\x00'; path.write_bytes(raw)
        with self.assertRaises(RuntimeError):
            entry.verify_helpers(self.root)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux file mode contract')
    def test_non_executable_helper_fails_closed(self):
        (self.root / PREFIX / 'WebKitWebProcess').chmod(0o644)
        with self.assertRaises(RuntimeError):
            entry.verify_helpers(self.root)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux AppImage process entry')
    def test_baked_relative_path_resolves_outside_the_appdir(self):
        executable = self.root / 'usr/bin/coding-tools-mcp-desktop'
        executable.parent.mkdir()
        executable.write_text('#!' + sys.executable + '\nimport os,pathlib\np=pathlib.Path("././/lib/x86_64-linux-gnu/webkit2gtk-4.1/WebKitNetworkProcess")\nassert p.is_file(), (os.getcwd(),str(p))\nprint("webkit-layout-ok")\n')
        executable.chmod(0o755)
        launcher = self.root / 'AppRun.wrapped'
        shutil.copyfile(ROOT / entry.LAUNCHER, launcher)
        with tempfile.TemporaryDirectory(prefix='外部工作目录v5-') as caller:
            result = subprocess.run(['/bin/bash', str(launcher)], cwd=caller, text=True,
                                    capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'webkit-layout-ok')

if __name__ == '__main__':
    unittest.main(verbosity=2)
