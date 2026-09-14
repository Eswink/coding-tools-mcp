"""Synthetic publication contracts; packages and images here are NOT native evidence."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import exclusive_release_tests as old
import ui_release as release
import ui_release_evidence as visual
from ui_refactor_native import PAGES, SIZES, THEMES

SOURCE,TREE,RUN=old.SOURCE,old.TREE,old.RUN
VERSION='0.5.0'

def put(root, name, value): return old.put(root,name,value)
def png(path,w=1280,h=800):
    # Deliberately only a byte-contract fixture, never decoded or published.
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\rIHDR'+struct.pack('>II',w,h)+b'NOT-NATIVE'*600)

def fixture(root,checkout):
    with patch.object(old,'VERSION',VERSION):old.fixture(root,checkout)
    for path in root.rglob('exclusive-native.json'):
        value=json.loads(path.read_text());value['version']=VERSION;rows=[]
        for w,h in SIZES:
            for theme in THEMES:
                for page in PAGES:
                    name=f'ui-native-{page}-{w}x{h}-{theme}.png';png(path.parent/name,w,h)
                    rows.append({'page':page,'requested_window':[w,h],'viewport':[w,h],'theme':theme,
                        'file':name,'sha256':visual.sha(path.parent/name),'passed':True,'overflow':[]})
        value['ui_refactor']={'scenario':'ui-refactor-v1','passed':True,'mock_transport':False,
            'interaction_source':'native-webdriver-clicks','screens':rows,'publish_approved':False}
        path.write_text(json.dumps(value))
    put(checkout,'docs/releases/verification-v0.5.0.md','# Synthetic guide, not a release')
    for path in root.glob('exclusive-regression-*/frontend-tests.txt'):
        tap='TAP version 13\n'+'\n'.join(f'ok {n} - test {n}' for n in range(1,181))
        path.write_text(tap+'\n1..180\n# tests 180\n# suites 0\n# pass 180\n# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 1\n')
    put(checkout,'tests/fixtures/ui-refactor-ipc.js','synthetic fixture')
    folder=root/'ui-refactor-pages-candidate';folder.mkdir()
    rows=[]
    for theme in ('light','dark'):
        for w,h in visual.SIZES:
            for page in visual.PAGES:
                name=f'{page}-{w}x{h}-{theme}.png';png(folder/name,w,h)
                rows.append({'page':page,'width':w,'height':h,'theme':theme,'file':name,'overflow':[]})
    states=[]
    for state in visual.STATES:
        name=f'state-{state}.png';png(folder/name)
        states.append({'name':state,'file':name,'ok':True,'native_verified':False})
    put(folder,'state-results.json',states)
    put(folder,'result.json',{'mode':'candidate','ok':True,'transport':'mocked Tauri IPC; actual production build/routes',
        'native_verified':False,'real_chatgpt_verified':False,'screens':rows,'browser_errors':[],
        'scenarios':[{'name':str(n),'ok':True} for n in range(10)],'state_scenarios':states})
    put(folder,'source-manifest.json',{'files':{str(p.relative_to(checkout)):visual.sha(p) for p in (checkout/'src').rglob('*') if p.is_file()},
        'fixture_sha256':visual.sha(checkout/'tests/fixtures/ui-refactor-ipc.js')})
    put(folder,'provenance.json',{'source_sha':SOURCE,'source_tree':TREE,'run_id':RUN,'observed':visual.inspect(folder,checkout)})

class UIReleaseContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.evidence=self.root/'evidence';self.checkout=self.root/'checkout'
        fixture(self.evidence,self.checkout)
    def compose(self,**kwargs):
        fields=dict(source=SOURCE,tree=TREE,run_id=RUN,version=VERSION,ref=release.REF);fields.update(kwargs)
        return release.compose(self.evidence,self.root/'delivery',self.checkout,**fields)
    def change(self,name,fn):
        path=self.evidence/name;v=json.loads(path.read_text());fn(v);path.write_text(json.dumps(v))
    def test_complete_ui_plus_security_produces_seven_assets(self):
        assets,summary=self.compose()
        self.assertEqual(len(assets),7);self.assertIn('UI-evidence_v0.5.0.zip',[a['name'] for a in assets])
        self.assertEqual(len(summary['installed_matrix']),5)
        self.assertTrue(all(m['ui_screens']==20 and m['native_stages']==12 for m in summary['installed_matrix']))
        self.assertEqual(summary['validation']['ui_routes']['route_screens'],40)
        self.assertEqual(summary['validation']['ui_routes']['route_states'],8)
        self.assertTrue(summary['prerelease']);self.assertFalse(summary['real_chatgpt_verified'])
    def test_other_branch_or_version_never_publishes(self):
        for fields in ({'ref':'refs/heads/main'},{'version':'0.4.0'},{'run_id':'999'},{'source':'f'*40}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):self.compose(**fields)
    def test_legacy_publisher_still_rejects_ui_release(self):
        with self.assertRaises(ValueError):old.release.compose(self.evidence,self.root/'old',self.checkout,
            source=SOURCE,tree=TREE,version=VERSION,run_id=RUN,ref=release.REF)
    def test_missing_ui_does_not_fall_back_to_security_only(self):
        self.change('exclusive-windows-package/exclusive-native.json',lambda d:d.pop('ui_refactor'))
        with self.assertRaises(ValueError):self.compose()
    def test_missing_original_security_stage_rejected(self):
        self.change('exclusive-windows-package/exclusive-native.json',lambda d:d['tests'].pop())
        with self.assertRaises(ValueError):self.compose()
    def test_wrong_source_native_record_rejected(self):
        self.change('exclusive-installed-ubuntu-22.04-deb/exclusive-native.json',lambda d:d.update(source_sha='f'*40))
        with self.assertRaises(ValueError):self.compose()
    def test_changed_installed_ui_image_rejected(self):
        path=self.evidence/'exclusive-windows-package/ui-native-workspace-1280x800-light.png';path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.compose()
    def test_failed_route_browser_rejected(self):
        self.change('ui-refactor-pages-candidate/result.json',lambda d:d.update(ok=False))
        with self.assertRaises(ValueError):self.compose()
    def test_source_or_run_in_visual_provenance_rejected(self):
        for key,value in [('source_sha','f'*40),('source_tree','f'*40),('run_id','999')]:
            path=self.evidence/'ui-refactor-pages-candidate/provenance.json';old_value=path.read_text()
            self.change('ui-refactor-pages-candidate/provenance.json',lambda d:d.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):self.compose()
            path.write_text(old_value)
    def test_duplicate_route_coverage_rejected(self):
        self.change('ui-refactor-pages-candidate/result.json',lambda d:d['screens'].__setitem__(1,d['screens'][0]))
        with self.assertRaises(ValueError):self.compose()
    def test_route_png_geometry_checked(self):
        png(self.evidence/'ui-refactor-pages-candidate/workspace-overview-1586x992-light.png',1,1)
        with self.assertRaises(ValueError):self.compose()
    def test_route_image_digest_binding_rejected(self):
        with (self.evidence/'ui-refactor-pages-candidate/workspace-overview-1586x992-light.png').open('ab') as f:f.write(b'changed')
        with self.assertRaises(ValueError):self.compose()
    def test_missing_route_state_rejected(self):
        self.change('ui-refactor-pages-candidate/result.json',lambda d:d['state_scenarios'].pop())
        with self.assertRaises(ValueError):self.compose()
    def test_edited_production_source_rejected(self):
        (self.checkout/'src/new-component.svelte').write_text('changed')
        with self.assertRaises(ValueError):self.compose()
    def test_visual_mock_cannot_be_claimed_native(self):
        self.change('ui-refactor-pages-candidate/result.json',lambda d:d.update(native_verified=True))
        with self.assertRaises(ValueError):self.compose()
    def test_elevated_windows_identity_rejected(self):
        self.change('exclusive-windows-package/标准用户隔离结果v22.json',lambda d:d['actual_logon']['token'].update(elevated=True))
        with self.assertRaises(ValueError):self.compose()
    def test_main_movement_blocks_release_mutation(self):
        client=release.AnchoredGitHub('synthetic-not-live',SOURCE)
        with patch.object(release.transport.GitHub,'request',return_value={'object':{'sha':'f'*40}}) as call:
            with self.assertRaises(ValueError):client.request('POST','/releases',{'tag_name':'v0.5.0'})
            call.assert_called_once_with('GET','/git/ref/heads/main')
    def test_workflow_requires_all_three_gates_and_ui_scenario(self):
        text=Path(__file__).parents[1].joinpath('.github/workflows/ui-release.yml').read_text()
        for fragment in ('needs: [prepare, validate, packages]','scenario: ui-refactor','workflows/ui-refactor.yml','release/ui-v0.5.0','--publish'):
            self.assertIn(fragment,text)
        self.assertEqual(text.count('contents: write'),1)
        self.assertNotIn('continue-on-error',text)

if __name__=='__main__':unittest.main(verbosity=2)
