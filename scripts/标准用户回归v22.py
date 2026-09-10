"""Pure ownership/fixture contracts; actual standard-user GUI is a CI gate."""
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('standard_v22', Path(__file__).with_name('Windows标准用户验收v22.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class StandardUserContracts(unittest.TestCase):
    def test_normal_token_selection_requires_exact_standard_state(self):
        state = {'elevated': False, 'integrity_rid': 8192}
        self.assertTrue(m.medium.use_normal_user_process(state, False))
        for other in ({}, {'elevated': True, 'integrity_rid': 8192},
                      {'elevated': False, 'integrity_rid': 8192.0},
                      {'elevated': False, 'integrity_rid': 12288}):
            self.assertFalse(m.medium.use_normal_user_process(other, False))
        self.assertFalse(m.medium.use_normal_user_process(state, True))
        self.assertFalse(m.medium.use_normal_user_process(state, None))

    def test_account_ownership_is_exact(self):
        name, sid, marker = 'ctmcpv22_123456789a', 'S-1-5-21-1-2-3-1001', 'coding-tools-native-v22:1234'
        m.owned_account(name, sid, marker, (name,sid,marker))
        for actual in [('Administrator',sid,marker), (name,sid+'2',marker), (name,sid,'other')]:
            with self.assertRaises(RuntimeError): m.owned_account(name,sid,marker,actual)
        with self.assertRaises(RuntimeError): m.owned_account('Administrator',sid,marker,('Administrator',sid,marker))

    def test_no_account_activity_on_user_machine(self):
        with patch.dict(m.os.environ,{},clear=True), patch.object(m, 'AccountApi') as api:
            with self.assertRaises(RuntimeError): m.require_ci()
            api.assert_not_called()

    def test_scoped_paths_reject_parent_and_sibling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(m.inside(root/'child',root),root/'child')
            for invalid in (root, root.parent, root.parent/'sibling'):
                with self.assertRaises(ValueError): m.inside(invalid,root)

    def test_source_snapshot_rejects_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p=root/'test.py';p.write_text('original')
            hashes={'test.py':hashlib.sha256(p.read_bytes()).hexdigest()}
            m.verify_sources(root,hashes)
            p.write_text('modified')
            with self.assertRaises(ValueError): m.verify_sources(root,hashes)
            with self.assertRaises(ValueError): m.verify_sources(root,{'../outside.py':'0'*64})

    def test_no_broad_acl_or_unowned_sid(self):
        with patch.object(m.subprocess,'run') as execute:
            for sid,access in [('Everyone','(RX)'), ('S-1-5-21-1-2-3-1001','(F)')]:
                with self.assertRaises(ValueError): m.grant(Path('fixture'),sid,access)
            execute.assert_not_called()

    def test_standard_launch_keeps_original_product_and_sandbox(self):
        text=Path(m.__file__).read_text(encoding='utf-8')
        self.assertNotIn('--no-sandbox',text)
        self.assertNotIn('SANDBOX_INERT',text)
        self.assertNotIn('Set-ItemProperty',text)
        self.assertIn('CreateProcessWithTokenW(token, 1',text)
        self.assertIn('api.NetUserDel(None, name)',text)
        self.assertIn('credentials_scan_completed',text)
        self.assertIn("password.encode('utf-16-le')",text)

if __name__=='__main__': unittest.main()
