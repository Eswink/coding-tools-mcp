"""Negative evidence contracts; these tests are not installed GUI acceptance."""
from __future__ import annotations
import copy
import hashlib
import tempfile
from pathlib import Path
import unittest
from exclusive_native_contract_tests import record, SOURCE, RUN, VERSION, DIGEST
from native_scenario import script_name
from ui_refactor_native import PAGES, THEMES, SIZES, SCENARIO
from ui_refactor_native_gate import verify

class UIEvidenceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.value = record(); rows=[]
        # Minimal byte fixture solely for digest/path contracts, NOT a screenshot.
        raw=b'\x89PNG\r\n\x1a\nsynthetic-contract-image'
        for w,h in SIZES:
            for theme in THEMES:
                for page in PAGES:
                    name=f'ui-native-{page}-{w}x{h}-{theme}.png';(self.root/name).write_bytes(raw)
                    rows.append({'page':page,'requested_window':[w,h],'viewport':[w,h], 'theme':theme,
                        'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'overflow':[],'passed':True})
        self.value['ui_refactor']={'scenario':SCENARIO,'passed':True,'mock_transport':False,
            'interaction_source':'native-webdriver-clicks','screens':rows,'publish_approved':False}
    def check(self):
        return verify(self.value,directory=self.root,source=SOURCE,run_id=RUN,version=VERSION,kind='nsis',binary_sha256=DIGEST)
    def test_complete_is_review_candidate_not_publication(self):
        v=self.check();self.assertEqual(v['native_stages'],12);self.assertEqual(v['ui_screens'],20);self.assertFalse(v['publish_approved'])
    def test_original_security_stages_remain_required(self):
        self.value['tests'].pop()
        with self.assertRaises(ValueError):self.check()
    def test_old_record_cannot_satisfy_ui_acceptance(self):
        self.value.pop('ui_refactor')
        with self.assertRaises(ValueError):self.check()
    def test_missing_duplicate_or_reordered_screens_fail(self):
        original=copy.deepcopy(self.value)
        for kind in ['missing','duplicate','reordered']:
            self.value=copy.deepcopy(original);rows=self.value['ui_refactor']['screens']
            if kind=='missing':rows.pop()
            elif kind=='duplicate':rows[1]=rows[0]
            else:rows.reverse()
            with self.subTest(kind=kind),self.assertRaises(ValueError):self.check()
    def test_browser_mock_and_publication_claim_rejected(self):
        for k,v in [('mock_transport',True),('interaction_source','mock-ipc'),('publish_approved',True),('passed',False)]:
            original=copy.deepcopy(self.value);self.value['ui_refactor'][k]=v
            with self.subTest(key=k),self.assertRaises(ValueError):self.check()
            self.value=original
    def test_layout_failure_or_unobserved_geometry_rejected(self):
        row=self.value['ui_refactor']['screens'][0];original=copy.deepcopy(row)
        for k,v in [('overflow',[{'excess':10}]),('viewport',[0,0]),('passed',False)]:
            row.update({k:v})
            with self.subTest(key=k),self.assertRaises(ValueError):self.check()
            row.update(original)
    def test_missing_or_changed_image_rejected(self):
        file=self.root/self.value['ui_refactor']['screens'][0]['file'];file.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.check()
        file.unlink()
        with self.assertRaises(ValueError):self.check()
    def test_path_escape_rejected(self):
        self.value['ui_refactor']['screens'][0]['file']='../outside.png'
        with self.assertRaises(ValueError):self.check()
    def test_entrypoint_is_allowlisted_without_changing_default(self):
        self.assertEqual(script_name('ui-refactor'),'ui_refactor_native_acceptance.py')
        self.assertEqual(script_name('exclusive'),'exclusive_native_acceptance.py')
        for arg in ['ui-refactor;bash','../../file','ui-refactor.py']:
            with self.assertRaises(ValueError):script_name(arg)
    def test_callback_is_opt_in_and_never_replaces_original_stages(self):
        source=Path(__file__).with_name('exclusive_native_acceptance.py').read_text()
        self.assertIn('def run(args, *, ui_review=None)',source)
        self.assertIn("evidence['ui_refactor'] = ui_review(session, profile, output)",source)
        self.assertEqual(source.count('        passed('),12)
        workflow=Path(__file__).parents[1].joinpath('.github/workflows/ui-refactor-native.yml').read_text()
        self.assertIn('contents: read',workflow);self.assertNotIn('contents: write',workflow)
        self.assertNotIn('publish',workflow)

if __name__=='__main__':unittest.main(verbosity=2)
