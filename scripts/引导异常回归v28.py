"""Exercise bootstrap failures; ensure the earliest import error is retained."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bootstrap_v28", Path(__file__).with_name("标准宿主引导v27.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class BootstrapFailures(unittest.TestCase):
    def test_import_failure_is_persisted_before_stream_close(self):
        original = sys.stdout, sys.stderr, sys.argv
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.standard-account-fixture-v22').touch()
            (root/'state').mkdir(); manifest=root/'manifest.json'; manifest.write_text('{}')
            with patch.object(sys,'platform','win32'), patch.object(sys,'argv',['bootstrap',str(manifest)]), \
                 patch.object(m,'faulthandler') as fault, \
                 patch.object(m.runpy,'run_path', side_effect=ImportError('DLL load failed: fixture-import')):
                argv=sys.argv
                with self.assertRaises(ImportError): m.main()
                self.assertIs(sys.stdout,original[0]); self.assertIs(sys.stderr,original[1]); self.assertIs(sys.argv,argv)
                fault.disable.assert_called_once()
            text=(root/'state'/'标准宿主引导v27.log').read_text(encoding='utf-8')
            self.assertIn('bootstrap_entered',text)
            self.assertIn('ImportError: DLL load failed: fixture-import',text)
            self.assertIn('runpy.run_path',text)

    def test_regular_native_system_exit_has_no_exception_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.standard-account-fixture-v22').touch(); (root/'state').mkdir()
            manifest=root/'manifest.json'; manifest.write_text('{}')
            with patch.object(sys,'platform','win32'), patch.object(sys,'argv',['bootstrap',str(manifest)]), \
                 patch.object(m,'faulthandler'), patch.object(m.runpy,'run_path',side_effect=SystemExit(1)):
                with self.assertRaises(SystemExit): m.main()
            text=(root/'state'/'标准宿主引导v27.log').read_text(encoding='utf-8')
            self.assertIn('bootstrap_exit_type=SystemExit',text)
            self.assertNotIn('Traceback',text)

if __name__ == '__main__': unittest.main()
