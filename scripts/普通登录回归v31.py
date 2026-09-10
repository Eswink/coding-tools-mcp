"""Logon uses actual child credentials; these are contracts, not a GUI PASS."""
import ctypes as c
from ctypes import wintypes as w
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

p = Path(__file__).with_name('普通登录核验v31.py')
spec = importlib.util.spec_from_file_location('ordinary_logon_v31', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SID = 'S-1-5-21-1-2-3-1001'

class LogonContracts(unittest.TestCase):
    def test_actual_standard_identity_and_interactive_session(self):
        proof = m.validate_identity(SID, SID, {'elevated': False, 'integrity_rid': 8192}, False, 1, 1)
        self.assertIs(proof['actual_child_identity_verified'], True)
        self.assertIs(proof['manual_desktop_acl'], False)
        self.assertNotIn(SID, str(proof))

    def test_rejects_different_account(self):
        with self.assertRaises(RuntimeError):
            m.validate_identity(SID, SID+'2', {'elevated':False,'integrity_rid':8192}, False, 1, 1)

    def test_elevation_restriction_and_invalid_types_fail_closed(self):
        for state, restricted in [({},False),({'elevated':True,'integrity_rid':8192},False),
                ({'elevated':False,'integrity_rid':8192.0},False),
                ({'elevated':False,'integrity_rid':12288},False),
                ({'elevated':False,'integrity_rid':8192},True),
                ({'elevated':False,'integrity_rid':8192},None)]:
            with self.assertRaises(RuntimeError):
                m.validate_identity(SID,SID,state,restricted,1,1)

    def test_cross_session_zero_and_unknown_are_rejected(self):
        for parent,child in [(1,2),(0,0),(None,1),(True,1),(1,1.0)]:
            with self.assertRaises(RuntimeError):
                m.validate_identity(SID,SID,{'elevated':False,'integrity_rid':8192},False,parent,child)

    def test_bounded_token_record(self):
        api=Mock()
        def invalid(*args):
            args[-1]._obj.value=100_000
            return False
        api.GetTokenInformation.side_effect=invalid
        with self.assertRaises(RuntimeError): m.token_sid(api,1)
        api.sid_text.assert_not_called()

    def test_session_requires_dword_result(self):
        api=Mock()
        def query(*args):
            args[-1]._obj.value=1
            return True
        api.GetTokenInformation.side_effect=query
        with self.assertRaises(RuntimeError): m.token_session(api,1)

    def test_handles_closed_when_actual_identity_query_fails(self):
        api=Mock(); handles=[]
        def opened(process,mask,out):
            out._obj.value=100+len(handles);handles.append(out._obj.value)
            return True
        api.OpenProcessToken.side_effect=opened
        api.GetTokenInformation.side_effect=RuntimeError('token query failure')
        with self.assertRaises(RuntimeError): m.verify_child(api,Mock(),44,SID)
        self.assertEqual(len(handles),2)
        self.assertEqual([call.args[0].value for call in api.CloseHandle.call_args_list],list(reversed(handles)))

    def test_both_handles_are_attempted_when_one_close_fails(self):
        api=Mock(); handles=[]
        def opened(process,mask,out):
            out._obj.value=100+len(handles);handles.append(out._obj.value)
            return True
        api.OpenProcessToken.side_effect=opened
        api.GetTokenInformation.side_effect=RuntimeError('token query failure')
        api.CloseHandle.side_effect=[OSError('close failed'), True]
        with self.assertRaisesRegex(RuntimeError,'handle cleanup failed'):
            m.verify_child(api,Mock(),44,SID)
        self.assertEqual(api.CloseHandle.call_count,2)

    def test_account_check_is_before_thread_resume(self):
        source=Path(__file__).with_name('Windows标准用户验收v22.py').read_text(encoding='utf-8')
        start=source.index('api.CreateProcessWithLogonW(')
        own=source.index('api.AssignProcessToJobObject(job',start)
        check=source.index('logon_module.verify_child(',start)
        resume=source.index('api.ResumeThread(',start)
        self.assertLess(own,check);self.assertLess(check,resume)
        self.assertNotIn('desktop_access.apply()',source)
        self.assertIn('startup.desktop = None',source)

if __name__ == '__main__': unittest.main()
