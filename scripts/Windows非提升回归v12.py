"""Pure contract tests plus an explicitly requested real Windows token smoke test."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

spec = importlib.util.spec_from_file_location('medium_process', Path(__file__).with_name('Windows非提升进程v12.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class ProcessContractTests(unittest.TestCase):
    def test_native_creation_is_detached_without_bypassing_security(self):
        self.assertEqual(m.NATIVE_CREATION_FLAGS, 0x4 | 0x200 | 0x400 | 0x8)
        self.assertEqual(m.NATIVE_CREATION_FLAGS & (0x10 | 0x08000000 | 0x01000000 | 0x02000000), 0)
    def test_environment_unicode_sorted_and_double_terminated(self):
        self.assertEqual(m.environment_block({'z':'2','A':'中文'}), 'A=中文\0z=2\0\0')
    def test_rejects_environment_injection(self):
        for env in [{'A=B':'x'}, {'A':'x\0B=evil'}, {'':'x'}, {'A':1}, {'A\0':'x'}]:
            with self.subTest(env=env), self.assertRaises(ValueError): m.environment_block(env)
    def test_token_must_be_non_elevated_and_medium_or_lower(self):
        m.require_standard({'elevated':False,'integrity_rid':8192})
        for state in [{}, {'elevated':True,'integrity_rid':8192}, {'elevated':False,'integrity_rid':12288}, {'elevated':False,'integrity_rid':True}]:
            with self.subTest(state=state), self.assertRaises(RuntimeError): m.require_standard(state)
    def test_non_fixture_launch_refused(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            m.launch(Path(sys.executable), {})

if __name__ == '__main__':
    real = '--require-native' in sys.argv
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProcessContractTests)
    if not unittest.TextTestRunner().run(suite).wasSuccessful(): raise SystemExit(1)
    if real:
        if sys.platform != 'win32': raise RuntimeError('real Windows required, not a skip')
        process = m.launch(Path(sys.executable), dict(os.environ), [str(Path(__file__).with_name('Windows桌面冒烟v15.py').resolve())])
        try:
            assert process.wait(15) == 0
            m.require_standard(process.security['child'])
            print(json.dumps({'passed': True, 'real_windows_token': process.security, 'real_interactive_window_created': True}))
        finally:
            process.terminate_tree()
    else:
        print('pure contracts only; native Windows token smoke not run')
