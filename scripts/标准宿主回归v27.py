"""The early bootstrap must neither access ChatGPT nor weaken native acceptance."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

class BootstrapContracts(unittest.TestCase):
    def test_windowless_interpreter_from_same_installation(self):
        code = (ROOT/'Windows标准用户验收v22.py').read_text(encoding='utf-8')
        self.assertIn("Path(sys.executable).with_name('pythonw.exe')", code)
        self.assertIn("interpreter.is_symlink()", code)
        self.assertIn("api.CreateProcessWithTokenW(token, 1, str(interpreter), command,", code)
        self.assertIn("if count != 1:", code)

    def test_bootstrap_records_before_native_import(self):
        code = (ROOT/'标准宿主引导v27.py').read_text(encoding='utf-8')
        self.assertLess(code.index('bootstrap_entered'),code.index('runpy.run_path'))
        self.assertNotIn('http',code)
        self.assertIn('faulthandler.cancel_dump_traceback_later()',code)
        ast.parse(code)

    def test_trace_stops_before_oauth_and_log_is_collected(self):
        code = (ROOT/'Windows标准用户验收v22.py').read_text(encoding='utf-8')
        self.assertLess(code.index('faulthandler.cancel_dump_traceback_later()'),code.index("with (state_root / '标准用户执行v22.log')"))
        self.assertIn('candidates.append(bootstrap_log)',code)
        self.assertIn('password.encode() in raw',code)

    def test_real_acceptance_keeps_no_redirect(self):
        code = (ROOT/'聊天授权原生验收v6.py').read_text(encoding='utf-8')
        self.assertIn('NoRedirect()',code)
        self.assertIn('assert len(evidence["tests"]) == 8',code)

if __name__ == '__main__': unittest.main()
