"""Exercise the existing configuration check under a legacy Windows text default."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import Ubuntu发布回归v1 as fixtures


class EncodingTests(unittest.TestCase):
    def test_unicode_config_does_not_depend_on_system_text_encoding(self):
        case = fixtures.UbuntuReleaseTests("test_linux_overlay_preserves_shared_product_identity")
        case.setUp()
        self.addCleanup(case.doCleanups)
        read_text = Path.read_text
        calls = []

        def legacy_default(path, encoding=None, errors=None):
            calls.append((path, encoding))
            return read_text(path, encoding=encoding or "cp1252", errors=errors)

        with patch.object(Path, "read_text", legacy_default):
            case.test_linux_overlay_preserves_shared_product_identity()
        target = fixtures.ROOT / "src-tauri/Ubuntu桌面v1.json"
        self.assertIn((target, "utf-8"), calls)
        # Do not escape or remove the Chinese source path to make the test pass.
        config = json.loads(read_text(target, encoding="utf-8"))
        self.assertEqual(config["build"]["beforeBundleCommand"], "python3 scripts/AppImage入口配置v3.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
