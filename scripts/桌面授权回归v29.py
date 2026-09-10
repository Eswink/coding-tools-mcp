"""Bounded logon-SID grants, immutable unrelated ACEs and explicit cleanup."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('desktop_contract_v29', Path(__file__).with_name('临时桌面授权v29.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SID = bytes([1, 3, 0, 0, 0, 0, 0, 5]) + struct.pack('<III', 5, 17, 1234)
OTHER = bytes([1, 1, 0, 0, 0, 0, 0, 1]) + struct.pack('<I', 0)

def entry(sid, mask=1, kind=0, flags=0):
    return struct.pack('<BBHI',kind,flags,8+len(sid),mask)+sid

def acl(*entries):
    return struct.pack('<BBHHH',2,0,8+sum(map(len,entries)),len(entries),0)+b''.join(entries)

class DesktopAclContracts(unittest.TestCase):
    def test_add_remove_preserves_all_other_aces(self):
        original=acl(entry(OTHER,1,1),entry(OTHER,2),entry(OTHER,4,0,16))
        owned=m.logon_ace(SID,m.DESKTOP_RIGHTS)
        result=m.add_owned_ace(original,owned)
        self.assertEqual(m.acl_entries(result), [entry(OTHER,1,1),entry(OTHER,2),owned,entry(OTHER,4,0,16)])
        self.assertEqual(m.remove_owned_ace(result,owned),original)

    def test_cleanup_keeps_concurrent_unrelated_changes(self):
        original=acl(entry(OTHER))
        owned=m.logon_ace(SID,m.WINDOW_RIGHTS)
        applied=m.add_owned_ace(original,owned)
        concurrent=m.pack_acl(applied,m.acl_entries(applied)+[entry(OTHER,3)])
        self.assertEqual(m.acl_entries(m.remove_owned_ace(concurrent,owned)),[entry(OTHER),entry(OTHER,3)])

    def test_duplicate_or_unowned_grant_is_rejected(self):
        owned=m.logon_ace(SID,m.WINDOW_RIGHTS)
        with self.assertRaises(ValueError): m.add_owned_ace(acl(owned),owned)
        for raw in (acl(),acl(owned,owned)):
            with self.assertRaises(RuntimeError): m.remove_owned_ace(raw,owned)
        with self.assertRaises(ValueError): m.logon_ace(OTHER,m.WINDOW_RIGHTS)

    def test_no_admin_or_owner_rights_are_granted(self):
        for rights in (m.WINDOW_RIGHTS,m.DESKTOP_RIGHTS):
            self.assertEqual(rights & (0x40000|0x80000|0x10000|0xf0000000),0)
            self.assertEqual(m.logon_ace(SID,rights)[1],0)
        for rights in (0x10000000,0x1f01ff,0,m.DESKTOP_RIGHTS|8):
            with self.assertRaises(ValueError): m.logon_ace(SID,rights)

    def test_truncated_acl_cannot_expand_permissions(self):
        good=acl(entry(OTHER))
        for raw in (b'',good[:6],good[:-1],b'\x01'+good[1:],good[:2]+b'\xff\xff'+good[4:]):
            with self.assertRaises(ValueError): m.acl_entries(raw)

    def test_local_user_machine_cannot_create_desktop_grant(self):
        with patch.dict(m.os.environ,{},clear=True):
            with self.assertRaises(RuntimeError): m.DesktopAccess(None,None)

    def test_cleanup_failure_remains_failure_and_closes_all_handles(self):
        item=object.__new__(m.DesktopAccess)
        class Api:
            def check(self,value):
                if not value: raise RuntimeError('handle close failed')
        item.api=Api(); item.proof={}; item.applied=[('desktop',1,m.DESKTOP_RIGHTS,b'bad')]
        closed=[]; item.resources=[(1,lambda h: closed.append(h) or True)]
        item.snapshot=lambda *args: (acl(),False)
        with self.assertRaises(RuntimeError): item.close()
        self.assertEqual(closed,[1]); self.assertIs(item.proof['owned_aces_removed'],False)

    def test_binding_and_cleanup_are_in_the_real_wrapper(self):
        text=Path(__file__).with_name('Windows标准用户验收v22.py').read_text(encoding='utf-8')
        self.assertIn("startup.desktop = r'winsta0\\default'",text)
        self.assertIn('desktop_access.apply()',text)
        self.assertLess(text.index('process.terminate_tree()'),text.index('desktop_access.close()'))
        self.assertLess(text.index('desktop_access.close()'),text.index('api.NetUserDel(None, name)'))

if __name__=='__main__': unittest.main()
