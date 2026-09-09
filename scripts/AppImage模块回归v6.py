"""AppImage GIO ABI-isolation regressions; ordinary unit fixtures, not native GUI proof."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import AppImage入口配置v3 as entry

ROOT = Path(__file__).resolve().parents[1]

class GioModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='模块路径v6-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'usr/lib/x86_64-linux-gnu/gio/modules/libgiognutls.so'
        self.module.parent.mkdir(parents=True)
        header = bytearray(20); header[:6] = b'\x7fELF\x02\x01'; header[18:20] = b'\x3e\x00'
        self.module.write_bytes(header)

    def test_bundled_tls_module_is_required(self):
        self.assertEqual(entry.verify_gio_module(self.root)['sha256'], entry.digest(self.module))
        self.module.unlink()
        with self.assertRaises(RuntimeError):
            entry.verify_gio_module(self.root)

    def test_wrong_tls_module_architecture_is_rejected(self):
        self.module.write_bytes(b'not-a-shared-library')
        with self.assertRaises(RuntimeError):
            entry.verify_gio_module(self.root)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux AppImage launcher')
    def test_default_module_search_is_package_local_not_host(self):
        executable = self.root / 'usr/bin/coding-tools-mcp-desktop'
        executable.parent.mkdir()
        executable.write_text('#!' + sys.executable + '\nimport os,json\nprint(json.dumps({k:os.getenv(k) for k in ("GIO_MODULE_DIR","GIO_EXTRA_MODULES","PYTHONHOME","PYTHONPATH","PATH")}))\n')
        executable.chmod(0o755)
        launcher = self.root / 'AppRun.wrapped'
        shutil.copyfile(ROOT / entry.LAUNCHER, launcher)
        env = dict(os.environ, GIO_MODULE_DIR='/host/incompatible/gio', GIO_EXTRA_MODULES='/host/incompatible/extra', PYTHONHOME=sys.base_prefix, PYTHONPATH='/fixture/user-python')
        result = subprocess.run(['/bin/bash', str(launcher)], env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['GIO_MODULE_DIR'], str(self.module.parent))
        self.assertEqual(value['GIO_EXTRA_MODULES'], str(self.module.parent))
        for key in ('PYTHONHOME', 'PYTHONPATH', 'PATH'):
            self.assertEqual(value[key], env[key])

if __name__ == '__main__':
    unittest.main(verbosity=2)
