from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest

MODULE_PATH = Path(__file__).with_name("rc_packages.py")
spec = importlib.util.spec_from_file_location("rc_packages", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class RcPackageVersionTests(unittest.TestCase):
    def test_debian_version_uses_tilde_prerelease_ordering(self):
        self.assertEqual(module.debian_version("0.6.0-rc.1"), "0.6.0~rc1")
        self.assertEqual(module.debian_version("10.2.3-rc.12"), "10.2.3~rc12")

    def test_debian_version_rejects_non_rc_app_versions(self):
        for value in ("0.6.0", "0.6.0-beta.1", "01.6.0-rc.1", "0.6.0-rc"):
            with self.assertRaises(ValueError, msg=value):
                module.debian_version(value)

    @unittest.skipUnless(shutil.which("dpkg"), "dpkg comparison is Linux package-manager evidence")
    def test_debian_rc_sorts_below_corresponding_stable_release(self):
        candidate = module.debian_version("0.6.0-rc.1")
        result = subprocess.run(
            ["dpkg", "--compare-versions", candidate, "lt", "0.6.0"],
            check=False,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
