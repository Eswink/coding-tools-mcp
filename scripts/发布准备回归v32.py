"""Object-specific access mapping and version-matched release documentation."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desktop_maps_v32',ROOT/'scripts/临时桌面授权v29.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReleasePreparationContracts(unittest.TestCase):
    def test_window_station_generic_mapping_is_not_requested_rights(self):
        result=m.object_mapping(m.WINDOW_RIGHTS)
        self.assertEqual((result.read,result.write,result.execute,result.all),(0x20303,0x2001c,0x20060,0xf037f))
        self.assertEqual(m.WINDOW_RIGHTS,0x20337)

    def test_desktop_generic_mapping_is_not_requested_rights(self):
        result=m.object_mapping(m.DESKTOP_RIGHTS)
        self.assertEqual((result.read,result.write,result.execute,result.all),(0x20041,0x200be,0x20100,0xf01ff))
        self.assertEqual(m.DESKTOP_RIGHTS,0x201c7)

    def test_unknown_object_mapping_fails_closed(self):
        for wrong in (0,0x10000000,True,0x20337+1):
            with self.assertRaises(ValueError):m.object_mapping(wrong)

    def test_release_guide_uses_current_version_without_legacy_fallback(self):
        source=(ROOT/'scripts/聊天授权发布v26.py').read_text(encoding='utf-8')
        self.assertIn("f'聊天授权安装与本地核验v{version}.md'",source)
        self.assertNotIn("guide = root / 'docs/releases/聊天授权安装与本地核验v0.3.0.md'",source)
        for version in ('0.3.0','0.3.1'):
            self.assertTrue((ROOT/f'docs/releases/聊天授权安装与本地核验v{version}.md').is_file())

if __name__=='__main__':unittest.main()
