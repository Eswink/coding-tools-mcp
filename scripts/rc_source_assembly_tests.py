"""Synthetic assembly contracts, never hosted/browser/native acceptance."""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_source_assembly as assembly
import rc_source_assembly_frontend as frontend
import engineering_dependency_capture as capture
import engineering_dependency_capture_tests as original_capture

ROOT = Path(__file__).resolve().parents[1]


def write(base, name, value):
    path = base / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value)).encode())


class SourceHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='assembly-contract-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'fixture')
        write(self.root, 'protected.txt', 'immutable source\n')
        write(self.root, 'scripts/engineering_dependency_capture.py', 'original\n')
        self.anchor = self.commit('synthetic anchor')
        self.anchor_tree = self.git('rev-parse', 'HEAD^{tree}')
        self.enterContext(patch.object(assembly, 'ANCHOR', self.anchor))
        self.enterContext(patch.object(assembly, 'ANCHOR_TREE', self.anchor_tree))
        self.enterContext(patch.object(assembly, 'COMPONENTS', {self.anchor: (self.anchor_tree, [])}))
        for name in assembly.ADDED:
            write(self.root, name, 'synthetic addition ' + name + '\n')
        write(self.root, 'scripts/engineering_dependency_capture.py', 'synthetic approved adapter\n')
        self.first = self.commit('synthetic integration')
        self.event = self.base / 'event.json'
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY=assembly.REPOSITORY,
                        GITHUB_REF='refs/heads/' + assembly.BRANCH, GITHUB_EVENT_NAME='push',
                        GITHUB_WORKFLOW_REF=assembly.WORKFLOW, GITHUB_SHA=self.first,
                        GITHUB_WORKFLOW_SHA=self.first, WORKFLOW_SHA=self.first,
                        GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1', GITHUB_JOB='capture',
                        GITHUB_EVENT_PATH=str(self.event), RUNNER_OS='Linux', ImageOS='ubuntu24',
                        ASSEMBLY_MATRIX_OS='ubuntu-24.04')
        self.enterContext(patch.dict(os.environ, self.env))
        self.push(self.first)

    def git(self, *args):
        return subprocess.check_output(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost',
                                        *args], cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def commit(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def push(self, sha, before='0' * 40):
        for key in ('GITHUB_SHA', 'GITHUB_WORKFLOW_SHA', 'WORKFLOW_SHA'):
            os.environ[key] = sha
        write(self.base, 'event.json', dict(ref='refs/heads/' + assembly.BRANCH, after=sha, before=before,
              forced=False, deleted=False, created=before == '0' * 40, repository={'full_name': assembly.REPOSITORY}))

    def verify(self):
        return assembly.verify_source(self.root, self.git('rev-parse', 'HEAD'))

    def test_valid_first_source_binds_every_input_and_fourteen_delta_paths(self):
        report = self.verify()
        self.assertEqual(report['anchor'], self.anchor)
        self.assertEqual(set(report['history'][0]['delta_blobs']), assembly.SCOPE)
        self.assertEqual(len(assembly.SCOPE), 15)
        self.assertEqual(report['inputs']['protected.txt']['sha256'], hashlib.sha256(b'immutable source\n').hexdigest())
        self.assertFalse(report['full_release_eligible'])

    def test_authorized_append_only_correction_preserves_anchor(self):
        write(self.root, 'scripts/rc_source_assembly_tests.py', 'corrected synthetic contract\n')
        sha = self.commit('synthetic append-only correction')
        self.push(sha, self.first)
        result = self.verify()
        self.assertEqual([x['sha'] for x in result['history']], [self.first, sha])
        self.assertEqual(result['anchor'], self.anchor)

    def test_wrong_github_context_is_rejected(self):
        for key, value in [('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_REF', 'refs/heads/other'),
                           ('GITHUB_EVENT_NAME', 'workflow_dispatch'), ('GITHUB_WORKFLOW_REF', capture.WORKFLOW),
                           ('GITHUB_WORKFLOW_SHA', 'f' * 40), ('WORKFLOW_SHA', 'f' * 40),
                           ('GITHUB_ACTIONS', 'false'), ('GITHUB_RUN_ID', '0'), ('GITHUB_RUN_ATTEMPT', '01'),
                           ('GITHUB_JOB', 'build'), ('ASSEMBLY_MATRIX_OS', 'ubuntu-20.04'), ('RUNNER_OS', 'Windows')]:
            with self.subTest(key=key), patch.dict(os.environ, {key: value}), self.assertRaises(ValueError):
                self.verify()

    def test_explicit_matrix_survives_missing_image_label_but_cannot_be_missing(self):
        environment = dict(os.environ)
        environment.pop('ImageOS', None)
        with patch.dict(os.environ, environment, clear=True):
            report = self.verify()
            self.assertEqual(report['matrix_os'], 'ubuntu-24.04')
            self.assertIsNone(report['runner_image'])
            os.environ.pop('ASSEMBLY_MATRIX_OS')
            with self.assertRaises(ValueError):
                self.verify()

    def test_event_before_forced_deleted_and_created_are_checked(self):
        original = json.loads(self.event.read_text())
        for change in ({'before': 'f' * 40, 'created': False}, {'forced': True}, {'deleted': True},
                       {'created': False}, {'after': 'f' * 40}, {'ref': 'refs/heads/other'}):
            write(self.base, 'event.json', {**original, **change})
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.verify()
        write(self.base, 'event.json', original)
        self.verify()

    def test_protected_intermediate_drift_cannot_be_hidden_by_revert(self):
        write(self.root, 'protected.txt', 'forbidden change')
        self.commit('synthetic forbidden intermediate')
        write(self.root, 'protected.txt', 'immutable source\n')
        self.push(self.commit('synthetic reverted head'), self.first)
        with self.assertRaises(ValueError):
            self.verify()

    def test_addition_deletion_or_reverted_adapter_rejects(self):
        for operation in ('addition', 'deletion', 'adapter'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                clone = Path(tmp) / 'clone'
                subprocess.run(['git', 'clone', '-q', '--no-hardlinks', str(self.root), str(clone)], check=True)
                if operation == 'addition':
                    write(clone, 'unreviewed.txt', 'extra')
                elif operation == 'deletion':
                    (clone / 'scripts/rc_source_assembly.py').unlink()
                else:
                    write(clone, 'scripts/engineering_dependency_capture.py', 'original\n')
                subprocess.run(['git', 'add', '-A'], cwd=clone, check=True)
                subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@localhost', 'commit', '-qm', operation], cwd=clone, check=True)
                sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clone, text=True).strip()
                with self.assertRaises(ValueError):
                    assembly.verify_history(clone, sha)

    def test_symlink_and_executable_modes_are_rejected(self):
        self.git('update-index', '--chmod=+x', 'scripts/rc_source_assembly.py')
        self.git('commit', '-qm', 'synthetic mode drift')
        with self.assertRaises(ValueError):
            assembly.verify_history(self.root, self.git('rev-parse', 'HEAD'))

    def test_foreign_merge_after_anchor_is_rejected(self):
        self.git('checkout', '-qb', 'side')
        write(self.root, assembly.SPEC + 'README.md', 'side change')
        self.commit('side correction')
        self.git('checkout', '-q', 'fixture')
        write(self.root, assembly.SPEC + 'design.md', 'main change')
        self.commit('main correction')
        self.git('merge', '--no-ff', '-qm', 'synthetic forbidden merge', 'side')
        with self.assertRaises(ValueError):
            assembly.verify_history(self.root, self.git('rev-parse', 'HEAD'))

    def test_component_and_anchor_drift_rejects(self):
        with patch.object(assembly, 'COMPONENTS', {self.anchor: ('f' * 40, [])}), self.assertRaises(ValueError):
            self.verify()
        with patch.object(assembly, 'ANCHOR', self.first), self.assertRaises(ValueError):
            self.verify()

    def test_untracked_or_modified_worktree_rejects(self):
        write(self.root, 'unexpected.tmp', 'untracked')
        with self.assertRaises(ValueError):
            self.verify()
        (self.root / 'unexpected.tmp').unlink()
        write(self.root, 'protected.txt', 'dirty')
        with self.assertRaises(ValueError):
            self.verify()

    def test_bounded_history_rejects_more_than_thirty_two_descendants(self):
        for number in range(32):
            self.commit('synthetic empty correction ' + str(number))
        with self.assertRaises(ValueError):
            assembly.verify_history(self.root, self.git('rev-parse', 'HEAD'))

    def test_actual_capture_cli_order_and_nonzero_exit(self):
        for name, script, code in [('ok', 'print("receipt")', 0), ('bad', 'raise SystemExit(7)', 7),
                                   ('timeout', 'import time; time.sleep(5)', 124)]:
            args = [sys.executable, str(ROOT / 'scripts/rc_source_assembly.py'), 'run', '--root', str(self.root),
                    '--evidence', str(self.base / 'evidence'), '--name', name, '--timeout', '1', '--', sys.executable, '-c', script]
            result = subprocess.run(args, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, code, result.stderr)
            record = json.loads((self.base / 'evidence/commands' / name / 'command.json').read_text())
            self.assertEqual(record['exit'], code)
            self.assertEqual(record['command'], [sys.executable, '-c', script])
            if code:
                with self.assertRaises(ValueError):
                    assembly.command_result(self.base / 'evidence', name)
            else:
                self.assertIn('receipt', assembly.command_result(self.base / 'evidence', name)[0])


class AssemblyCaptureTests(original_capture.EngineeringCaptureTests):
    """Run the unchanged original rejection cases with an assembly producer fixture."""
    def setUp(self):
        super().setUp()
        self.source_gate = self.enterContext(patch.object(assembly, 'verify_source', return_value={'synthetic': True}))
        self.enterContext(patch.dict(os.environ, {'GITHUB_WORKFLOW_REF': assembly.WORKFLOW}))

    def noncloud(self):
        # Synthetic fixture creation only. Production code never rewrites GitHub context.
        with patch.dict(os.environ, {'GITHUB_WORKFLOW_REF': capture.WORKFLOW}):
            super().noncloud()
        path = self.output / 'noncloud/raw-audit-capture.json'
        value = json.loads(path.read_text())
        value.update(capture.producer(self.source['sha'], self.root))
        capture.write_json(path, value)

    def test_both_collect_and_independent_verify_require_source_gate(self):
        self.collect()
        self.assertTrue(self.source_gate.called)
        self.source_gate.reset_mock()
        with patch.dict(os.environ, {'GITHUB_JOB': 'verify'}):
            self.verify()
        self.source_gate.assert_called_with(self.root, self.source['sha'])
        self.source_gate.side_effect = ValueError('bad assembled history')
        with self.assertRaises(ValueError):
            self.verify()

    def test_no_root_wrong_job_or_unlisted_tuple_rejects(self):
        with self.assertRaises(ValueError):
            capture.producer(self.source['sha'])
        for change in ({'GITHUB_JOB': 'portable'}, {'GITHUB_WORKFLOW_REF': assembly.WORKFLOW + '-other'}):
            with patch.dict(os.environ, change), self.assertRaises(ValueError):
                capture.producer(self.source['sha'], self.root)


class WiringTests(unittest.TestCase):
    def test_original_symbols_workflows_and_tests_are_preserved(self):
        original = subprocess.check_output(['git', 'show', assembly.ANCHOR + ':scripts/engineering_dependency_capture.py'], cwd=ROOT, text=True)
        current = (ROOT / 'scripts/engineering_dependency_capture.py').read_text()
        omit = {'producer', 'collect', 'verify'}
        clean = lambda text: [ast.dump(n, include_attributes=False) for n in ast.parse(text).body
                              if not isinstance(n, ast.FunctionDef) or n.name not in omit]
        self.assertEqual(clean(original), clean(current))
        excluded = [':(exclude)' + p for p in assembly.SCOPE]
        self.assertEqual(subprocess.run(['git', 'diff', '--quiet', assembly.ANCHOR, '--', '.', *excluded], cwd=ROOT).returncode, 0)

    def test_new_workflow_is_exact_read_only_and_complete(self):
        text = (ROOT / '.github/workflows/rc-source-assembly.yml').read_text()
        self.assertIn("branches: ['" + assembly.BRANCH + "']", text)
        self.assertIn('permissions:\n  contents: read', text)
        self.assertNotIn('continue-on-error', text)
        self.assertNotIn('secrets.', text)
        self.assertNotIn('workflow_dispatch', text)
        self.assertEqual(text.count('persist-credentials: false'), 4)
        self.assertIn('os: [ubuntu-22.04, ubuntu-24.04, windows-2025]', text)
        self.assertIn('os: [ubuntu-22.04, ubuntu-24.04]', text)
        import re
        for action in re.findall(r'uses:\s*(\S+)', text):
            self.assertRegex(action, r'^[\w/-]+@[a-f0-9]{40}$')
        for command in ('--test service_contracts', '--test enrollment_contracts', '--test linux_sandbox',
                        '--test exec_input_contract', 'sandbox-dispatch/run_probe.py', 'sandbox-lifecycle/run_probe.py',
                        'dbus-run-session', 'gnome-keyring-daemon --unlock --components=secrets',
                        'chromium_sandbox=True', 'npm audit --json', '--expected-receipt-sha256 "$RECEIPT_SHA256"'):
            self.assertIn(command, text)
        for name in assembly.SCOPE:
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            self.assertLessEqual(len(path.read_text().splitlines()), 500, name)

    def test_zero_filtered_or_missing_result_counts_reject(self):
        valid = 'test result: ok. 14 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;'
        assembly.rust_counts(valid, expected=14)
        for text in ('', valid.replace('14 passed', '0 passed'), valid.replace('0 filtered', '1 filtered'), valid + valid):
            with self.subTest(text=text), self.assertRaises(ValueError):
                assembly.rust_counts(text, expected=14)
        valid_node = '\n'.join('# ' + key + ' ' + str(n) for key, n in [('tests',233),('pass',233),('fail',0),('cancelled',0),('skipped',0),('todo',0)])
        assembly.node_counts(valid_node, 233)
        with self.assertRaises(ValueError):
            assembly.node_counts(valid_node.replace('233', '232'), 233)

    def test_missing_image_label_cannot_skip_ubuntu24_browser_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence = Path(temp)
            source, outcomes = portable_fixture(ROOT, evidence)
            environment = dict(os.environ, GITHUB_SHA=source['source_sha'],
                               ASSEMBLY_MATRIX_OS='ubuntu-24.04', STEP_OUTCOMES=json.dumps(outcomes))
            environment.pop('ImageOS', None)
            with patch.dict(os.environ, environment, clear=True), patch.object(assembly, 'verify_source', return_value=source), \
                    patch.object(frontend, 'verify', return_value={'passed': False}) as browser:
                result = assembly.finish(ROOT, evidence, 'portable')
                self.assertFalse(result['passed'])
                self.assertIn('frontend_acceptance_failed', str(result['failures']))
                outcomes['acceptance']['outcome'] = 'success'
                os.environ['STEP_OUTCOMES'] = json.dumps(outcomes)
                self.assertFalse(assembly.finish(ROOT, evidence, 'portable')['passed'])
                self.assertEqual(browser.call_count, 1)

    def test_source_failure_still_retains_actual_step_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence = Path(temp)
            assembly.write(evidence / 'source.json', {'source_sha': 'a' * 40})
            steps = {'source': {'outcome': 'success'}, 'lifecycle': {'outcome': 'failure'}}
            with patch.dict(os.environ, {'STEP_OUTCOMES': json.dumps(steps)}), patch.object(assembly, 'verify_source', side_effect=ValueError('leftover injection')):
                result = assembly.finish(ROOT, evidence, 'native')
            self.assertFalse(result['passed'])
            self.assertEqual(json.loads((evidence / 'step-outcomes.json').read_text()), steps)
            self.assertIn('leftover injection', str(result['failures']))
            self.assertIn('failed/skipped step: lifecycle', result['failures'])

    def test_incomplete_finish_never_claims_release_or_security_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = assembly.finish(ROOT, Path(tmp), 'portable')
            self.assertFalse(result['passed'])
            self.assertFalse(result['full_release_eligible'])
            self.assertFalse(result['publish_approved'])
            self.assertEqual(result['security_acceptance'], 'not_evaluated')


def portable_fixture(root,evidence):
    from rc_source_assembly_evidence_tests import portable_fixture as complete_fixture
    return complete_fixture(root, evidence)


# The frontend fixture below is deliberately synthetic; real browser evidence is required in CI.
def frontend_fixture(root,evidence):
    for name in frontend.REQUIRED_INPUTS|{'src/example.svelte','.github/workflows/issue84-frontend-acceptance.yml','.github/workflows/rc-source-assembly.yml'}:
        write(root,name,'fixture:'+name)
    write(root,'src-tauri/tauri.conf.json',{'app':{'windows':[{'minWidth':960,'minHeight':640}]}})
    write(root,'build/index.html','<html>synthetic</html>');write(root,'build/app.js','synthetic')
    inputs={p.relative_to(root).as_posix():{'sha256':frontend.sha256(p.read_bytes()),'git_blob':'c'*40} for p in root.rglob('*') if p.is_file() and 'build' not in p.relative_to(root).parts}
    report={'source_sha':'a'*40,'source_tree':'b'*40,'workflow_sha':'a'*40,'workflow_ref':frontend.WORKFLOW,'repository':frontend.REPOSITORY,'ref':frontend.REF,'run_id':'123','run_attempt':'1','inputs':inputs,'engineering_only':True,'release_approved':False,'publish_approved':False,'native_verified':False,'real_chatgpt_verified':False}
    write(evidence,'source.json',report);write(evidence,'step-outcomes.json',{k:{'outcome':'success','conclusion':'success'} for k in frontend.STEPS})
    for name,argv in frontend.COMMANDS.items():
        prefix='commands/'+name+'/'
        write(evidence,prefix+'command.json',{'command':argv,'exit':0,'started_at':'2026-10-02T00:00:00.000000Z','completed_at':'2026-10-02T00:00:01.000000Z'})
        for filename,content in [('exit-code.txt','0\n'),('stdout.txt','synthetic output\n'),('stderr.txt','')]:write(evidence,prefix+filename,content)
    audit={'vulnerabilities':{},'metadata':{'vulnerabilities':{k:0 for k in ['info','low','moderate','high','critical','total']},'dependencies':{'total':42}}}
    write(evidence,'npm-audit.json',audit);write(evidence,'commands/npm-audit/stdout.txt',audit);write(evidence,'npm-audit.stderr.txt','')
    write(evidence,'commands/npm-ls-devalue/stdout.txt',{'dependencies':{'devalue':{'version':'5.6.3'}}})
    full='\n'.join(f'# {k} {v}' for k,v in [('tests',233),('pass',233),('fail',0),('cancelled',0),('skipped',0),('todo',0)])+'\nboth lockfiles select the same verified devalue package and integrity\nserialized Set rejects an out-of-bounds reference\nsupported serialization still round-trips shared values\n'
    write(evidence,'commands/frontend-full/stdout.txt',full)
    write(evidence,'commands/sandbox-preflight/stdout.txt',{'chromium_sandbox':True,'native_verified':False,'browser_version':'150.0.0.0'})
    write(evidence,'chrome-version.txt','Google Chrome 150.0.0.0\n');write(evidence,'chrome-sha256.txt','d'*64+'  /opt/google/chrome/chrome\n');write(evidence,'playwright-version.txt','Name: playwright\nVersion: 1.58.0\n')
    def image(name):write(evidence,name,b'\x89PNG\r\n\x1a\nfixture')
    cloud={'states':sorted(frontend.CLOUD_STATES),'errors':[],'native_verified':False,'real_host_verified':False}
    cloud.update({x:True for x in ['ok','global_drain_warning_outside_workspace','confirmation_cancelled_without_submit','explicit_normal_start_without_initialization']});write(evidence,'cloud-ui/report.json',cloud)
    for name in cloud['states']+['connected-390','connected-1280','global-drain-warning']:image('cloud-ui/'+name+'.png')
    ui={'ok':True,'mode':'candidate','browser_errors':[],'native_verified':False,'real_chatgpt_verified':False,'screens':[],'scenarios':[{'name':s,'ok':True} for s in frontend.UI_SCENARIOS],'state_scenarios':[]}
    for page in ['workspace-overview','general-settings','credentials-and-keys','frp-configuration','software-management']:
        for w,h in [(1586,992),(1280,800),(960,640),(1920,1080)]:
            for t in ['light','dark']:
                filename=f'{page}-{w}x{h}-{t}.png';image('existing-ui/'+filename);ui['screens'].append({'page':page,'width':w,'height':h,'theme':t,'file':filename,'overflow':[]})
    for state in frontend.UI_STATES:
        filename='state-'+state+'.png';image('existing-ui/'+filename);ui['state_scenarios'].append({'name':state,'ok':True,'native_verified':False,'file':filename})
    write(evidence,'existing-ui/result.json',ui);write(evidence,'existing-ui/state-results.json',ui['state_scenarios'])
    write(evidence,'existing-ui/source-manifest.json',{'files':{p:v['sha256'] for p,v in inputs.items() if p.startswith('src/')},'fixture_sha256':inputs['tests/fixtures/ui-refactor-ipc.js']['sha256']})
    for directory,stem,height,controls in [('hooks-ui','preview',1000,['manifest','review','approval']),('snapshot-ui','restore-plan',900,['workspace','plan','restore'])]:
        report={'ok':True,'errors':[],'native_verified':False,'real_host_verified':False,'mobile_visual_acceptance':False,'native_window_contract':{'source':'src-tauri/tauri.conf.json','min_width':960,'min_height':640},'viewport_evidence':[]}
        if directory=='hooks-ui':report['scenarios']=sorted(frontend.HOOK_SCENARIOS)
        else:report.update({x:True for x in ['owner_cancel_preserved','plan_bound_restore','no_auto_capture']})
        for w in [390,960,1280]:
            v={'width':w,'height':height,'classification':'supported_native_window' if w>=960 else 'diagnostic_outside_native_window_contract','checkpoints':[]}
            for i,control in enumerate(controls):
                filename=f'{stem}-{w}.png' if i==2 else f'{stem}-{w}-{control}.png';image(directory+'/'+filename)
                v['checkpoints'].append({'control':control,'image':filename,'image_scope':'visible_viewport','minimum_intersection_ratio':0.98,'enabled':i!=2,'actionability_checked_without_click':i!=2})
            report['viewport_evidence'].append(v)
        write(evidence,directory+'/report.json',report)
    return inputs


class FrontendEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='assembly-frontend-contract-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'root'
        self.evidence = Path(self.temp.name) / 'evidence'
        inputs = frontend_fixture(self.root, self.evidence)
        def git(root, *args):
            if args == ('rev-parse', 'HEAD'):
                return 'a' * 40
            if args == ('rev-parse', 'HEAD^{tree}'):
                return 'b' * 40
            if args[0] == 'ls-files':
                return '\0'.join(inputs)
            if args[0] == 'rev-parse' and args[1].startswith('HEAD:'):
                return 'c' * 40
            raise ValueError(args)
        self.enterContext(patch.object(frontend, 'git', git))
        self.enterContext(patch.object(frontend.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'', stderr=b'')))
        self.enterContext(patch.dict(os.environ, dict(GITHUB_SHA='a' * 40, GITHUB_WORKFLOW_SHA='a' * 40, WORKFLOW_SHA='a' * 40, GITHUB_WORKFLOW_REF=frontend.WORKFLOW,
                          GITHUB_REPOSITORY=frontend.REPOSITORY, GITHUB_REF=frontend.REF,
                          GITHUB_RUN_ID='123', GITHUB_RUN_ATTEMPT='1')))

    def test_complete_synthetic_frontend_fixture_passes(self):
        result = frontend.verify(self.root, self.evidence)
        self.assertTrue(result['passed'], result['failures'])
        self.assertFalse(result['native_verified'])

    def test_frontend_cli_persists_supplied_step_outcomes(self):
        path = self.evidence / 'step-outcomes.json'
        outcomes = path.read_text()
        path.unlink()
        argv = ['frontend', '--root', str(self.root), '--evidence', str(self.evidence)]
        with patch.object(sys, 'argv', argv), patch.dict(os.environ, {'STEP_OUTCOMES': outcomes}):
            self.assertEqual(frontend.main(), 0)
        self.assertEqual(json.loads(path.read_text()), json.loads(outcomes))

    def test_frontend_identity_command_and_browser_mutations_reject(self):
        mutations = [
            ('source.json', lambda d: d.update(run_id='456')),
            ('source.json', lambda d: d.update(workflow_sha='e' * 40)),
            ('source.json', lambda d: d.update(release_approved=True)),
            ('source.json', lambda d: d['inputs'].pop('src/example.svelte')),
            ('source.json', lambda d: d['inputs']['src/example.svelte'].update(git_blob='e' * 40)),
            ('step-outcomes.json', lambda d: d['install'].update(outcome='skipped')),
            ('commands/npm-audit/command.json', lambda d: d['command'].append('--omit=dev')),
            ('commands/frontend-build/command.json', lambda d: d.update(exit=1)),
            ('commands/frontend-check/command.json', lambda d: d.update(completed_at='2026-10-01T23:00:00Z')),
            ('commands/sandbox-preflight/stdout.txt', lambda d: d.update(chromium_sandbox=False)),
            ('cloud-ui/report.json', lambda d: d['states'].pop()),
            ('existing-ui/result.json', lambda d: d['screens'].pop()),
            ('existing-ui/result.json', lambda d: d['scenarios'].pop()),
            ('hooks-ui/report.json', lambda d: d['viewport_evidence'][0].update(width=400)),
            ('snapshot-ui/report.json', lambda d: d.update(native_verified=True)),
            ('npm-audit.json', lambda d: d['metadata']['dependencies'].update(total=43)),
        ]
        for name, mutate in mutations:
            path = self.evidence / name
            before = path.read_bytes()
            value = json.loads(before)
            mutate(value)
            write(self.evidence, name, value)
            with self.subTest(name=name):
                self.assertFalse(frontend.verify(self.root, self.evidence)['passed'])
            path.write_bytes(before)

    def test_zero_tests_empty_logs_bad_image_and_raw_bytes_reject(self):
        for name, data in [('commands/frontend-full/stdout.txt', b'# tests 0\n'),
                           ('commands/npm-ci/stdout.txt', b''), ('commands/frontend-build/exit-code.txt', b'1\n'),
                           ('cloud-ui/approved.png', b'bad image'), ('npm-audit.json', b'{"x":1,"x":2}')]:
            path = self.evidence / name
            before = path.read_bytes()
            path.write_bytes(data)
            with self.subTest(name=name):
                self.assertFalse(frontend.verify(self.root, self.evidence)['passed'])
            path.write_bytes(before)
        self.assertTrue(frontend.verify(self.root, self.evidence)['passed'])
        write(self.root, 'build/app.js', 'changed built output')
        self.assertFalse(frontend.verify(self.root, self.evidence)['passed'])


if __name__ == '__main__':
    unittest.main()
