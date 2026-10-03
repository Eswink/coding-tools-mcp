#!/usr/bin/env python3
"""Finite source audit and synthetic artifact contracts; never Windows execution."""
import ast
import hashlib
import pathlib
import re
import runpy
import sys
import unittest

from cmd_observation_artifact import evaluate_cmd_observation_artifact
import cmd_observation_artifact_tests

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parents[1]
OLD = runpy.run_path(str(HERE / 'cmd-sentinel-audit.py'))
OLD_NAMES = OLD['OLD_NAMES'] | set(OLD['NAMES'])
NAMES = ('PilotCmdObservations.cs', 'PilotCmdObservationsTests.cs')
PYTHON = ('cmd_observation_artifact.py', 'cmd_observation_contracts.py',
          'cmd_observation_fixtures.py', 'cmd_observation_artifact_tests.py', 'cmd_observation_failure_fixtures.py')
PINS = {'PilotCmdObservations.cs': '1611c700bf080e8c69ccc1af8bf8e7a5edaad2862a7810c1ab50926bb4df3822', 'PilotCmdObservationsTests.cs': 'c7a1847f6db94aa257452e0aa8a28b14b5850912ef3ba5fb76aad86de51adea5'}
SPANS = (
    ('PilotSubjects.cs', '            IntPtr candidateSid=IntPtr.Zero;int hr;\n', 8935, 'd7063c0d7f2e76b52976e9d9fba899283a30830cb341a0720ee1b976cd6c88df'),
    ('PilotRunner.cs', '    static void ClassifyPilotCase(PilotCaseReceipt row,string evidence) {\n', 1156, '21d8e6982d3316622c1e9178285fa8b2c34b59ac6ad9cfc46acd2f83f7197860'),
    ('PilotRunner.cs', '            r.Stage="inspect_actual_suspended_target";\n', 4045, '78afd29c1c99572f5d8f760995aedd0766cd9c36e5eb81f00fe02a0eaefb24e2'),
    ('PilotRunner.cs', '                ClassifyPilotCase(row,evidence);\n', 1869, '3f1d2f592775061ac70e60d59511229a83a33d1af80fefda752befe271e8bb20'),
    ('PilotRunner.cs', '            journal.VerifyPending();markerGuard(new string[]{journal.Path});\n', 1063, 'b977365bcaf5ff8555f6aef192000a4d7b1ca3ccd20a9181dbcbebcb6534c0ed'),
    ('run-pilot.ps1', 'function Assert-PilotRecoveryScope([string[]]$Allowed) {\n', 3654, '277dcdf7654c665e7e8f7a8947c0ff0314b93a1a36af9b667ccee47754756e28'),
    ('run-pilot.ps1', "    if(-not $result.AllFourOfflineCasesPassed) {throw 'one or more required offline pilot observations failed; original gates remain independent'}\n", 431, '7c06057180010d3303e401c38e8db896f04488032fc3f0409f1fd454fe882730'),
    ('PilotClassification.cs', '        row.PositivePassed=false;row.OfflineReferenceRouteValid=false;row.NetworkDenialProven=false;row.CmdExit23Observed=false;row.CmdBatchExit23Observed=false;\n', 162, 'c712ac1fc1d1a8221cc7a389b757ad067c3e5fdde17b1108edc791d567c7b52c'),
    ('PilotClassification.cs', '        if(row.Case=="cmd-exit23") {ClassifyPilotCmdSentinel(row);return;}\n', 153, 'da205ab588f00b16d999da40906efcd35176cd5c02eab7b064503996ed7af64b'))
HELPERS = {'PilotCmdObservationKind', 'FixedPilotCmdCwdCommand', 'FixedPilotCmdReadCommand',
           'CapturePilotCmdReadBatchUsing', 'CapturePilotCmdReadBatch', 'PilotCmdObservationExpectedBytes',
           'ReadPilotCmdObservationUsing', 'ReadPilotCmdObservation', 'PilotCmdObservationEvidenceVerified',
           'ClassifyPilotCmdObservation', 'PilotCmdCwdRawMatched', 'PilotCmdReadRawMatched'}


def coverage(names):
    assert len(OLD_NAMES) == 28
    assert names == OLD_NAMES | set(NAMES), 'unknown/missing executable fixture'
    assert len(names) == len({name.casefold() for name in names}) == 30


def immutable(sources):
    for name, anchor, count, sha in SPANS:
        source = sources[name].encode()
        anchors = [m.start() for m in re.finditer(re.escape(anchor.encode()), source)]
        matches = [offset for offset in anchors if hashlib.sha256(source[offset:offset + count]).hexdigest() == sha]
        assert len(matches) == 1, (name, 'immutable span changed')


def pure_python(files):
    assert set(files) == set(PYTHON)
    allowed = {'hashlib', 're', 'copy', 'json', 'unittest', 'cmd_observation_contracts',
               'cmd_observation_artifact', 'cmd_observation_fixtures', 'cmd_observation_failure_fixtures'}
    for name, source in files.items():
        assert len(source.splitlines()) <= (140 if name == 'cmd_observation_failure_fixtures.py' else 480), name
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [node.module] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names]
                assert all(item in allowed for item in names), (name, names)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ('open', 'eval', 'exec', 'compile', '__import__', 'input', 'getattr', 'setattr'), name
            if isinstance(node, ast.Attribute):
                assert not node.attr.startswith('__') or (node.attr == '__init__' and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == 'super'), name
                assert node.attr not in ('skip', 'skipIf', 'skipUnless', 'SkipTest'), 'required synthetic tests cannot be skipped'


def inspect(new, old, python, workflow, pins=True):
    assert set(new) == set(NAMES) and set(old) == OLD_NAMES
    coverage(set(new) | set(old))
    immutable(old)
    pure_python(python)
    if pins:
        assert set(PINS) == set(NAMES)
        for name in NAMES:
            assert hashlib.sha256(new[name].encode()).hexdigest() == PINS[name]
    methods = OLD['SELECTED']['PARENT']['PILOT']['declared_methods']
    uncomment = OLD['SELECTED']['PARENT']['PILOT']['uncomment']
    prior = set().union(*(methods(s) for n, s in old.items() if n.endswith('.cs')))
    added = set()
    for name, source in new.items():
        plain = uncomment(source)
        declared = methods(plain)
        assert not declared & (prior | added), 'new partial member collides'
        added |= declared
        expected = {'BrokerDirectLauncher'} | ({'PilotCmdObservationTrace'} if name == NAMES[1] else set())
        assert set(re.findall(r'\bclass\s+(\w+)', plain)) == expected
        assert not re.search(r'\b(?:struct|interface|enum)\s+\w+', plain)
        for type_name in expected:
            assert not re.search(r'\bstatic\s+' + type_name + r'\s*\(', plain), 'type initializer rejected'
        assert not re.search(r'using\s+\w+\s*=', plain)
        assert set(re.findall(r'^using ([\w.]+);', plain, re.M)) == {'System', 'System.IO', 'System.Collections.Generic'}
        for token in ('DllImport', 'ModuleInitializer', 'static readonly', 'CreateProcess(', 'ResumeThread(',
                      'AssignProcessToJobObject(', 'OpenProcessToken(', 'DuplicateToken', 'AccessCheck(',
                      'Impersonate', 'SetThreadToken(', 'SetTokenInformation(', 'OwnedAcl(', 'Registry.',
                      'File.', 'Directory.', 'System.Linq', 'HashSet<', '.TryAdd('):
            assert token not in plain, (name, token)
        assert len(source.splitlines()) <= (350 if name == NAMES[0] else 480)
    helper, tests = new[NAMES[0]], new[NAMES[1]]
    assert methods(helper) == HELPERS
    for token in ('PilotCmdNativeCaptureOperations(', 'ReadPilotCmdObservation(', 'CapturePilotCmdReadBatch(',
                  'PilotOpenHandle(', 'OpenPrivate('):
        assert token not in tests, token
    for token in (' /d /q /c cd"', ' /d /q /c type direct.cmd"', 'CapturePilotCmdBatchCore(s,evidence,ops,true);',
                  'PilotCmdObservationExpectedBytes("cmd-read-direct",s.Workspace)',
                  '"pilot_case_id","cmd-read-direct"', 's.Receipt.CreateAttempted || s.Receipt.Created',
                  'foreach(char c in exactWorkspace) if(c>127) return null;', 'bytes[bytes.Length-2]=13;bytes[bytes.Length-1]=10;',
                  'full!=exactWorkspace', 'Path.GetFullPath(exactWorkspace)!=exactWorkspace', 'Path.GetFileName(full)!="workspace"',
                  '!s.OwnershipCertain || !s.ProfileCreated || !s.ProcessStopped || !s.JobDrained',
                  's.Process.process!=IntPtr.Zero', '!PilotStdioClosed(r)', 'individual_stop_drain_close_confirmed',
                  'r.Numbers["pilot_cmd_observation_raw_complete"]=0;', 'r.Numbers["pilot_cmd_observation_raw_complete"]=1;',
                  '"pilot_cmd_stdout_source",ops)', '"pilot_cmd_stdout_evidence",ops)',
                  '"pilot_cmd_stderr_source",ops)', '"pilot_cmd_stderr_evidence",ops)',
                  '!PilotCmdRawEqual(output,outputCopy)', '!PilotCmdRawEqual(error,errorCopy)',
                  'r.Identities.ContainsKey(label+"_close_exception")', 'new long[]{0,2147483648,0,1,1,0}',
                  '!PilotNumber(r,"pilot_cmd_observation_expected_supported",1)', '!PilotPinnedMethodDiagnostics(r)',
                  '!PilotKnownAccessCheckKey(key)', '!PilotTokenSid(r,"appcontainer_sid",r.ProfileSid',
                  'PilotDescriptorDecision(r,"mixed",1,2', 'PilotDescriptorDecision(r,"aap",0,0',
                  'r.TokenVerified || r.Wait!=WAIT_OBJECT_0 || r.Exit!=0',
                  'row.CmdCwdObserved=false;row.CmdReadObserved=false;', 'cmd_cwd_expected_encoding_unsupported',
                  'PilotCaseReceipt row=rows[8];', 'PilotCaseReceipt row=rows[9];',
                  'RunPilotCmdObservationContractTests()'):
        assert token in (tests if token == 'RunPilotCmdObservationContractTests()' else helper), token
    for field in ('PositivePassed', 'OfflineReferenceRouteValid', 'NativeFiveAssertionsPassed', 'NetworkDenialProven'):
        assert 'row.' + field + '=true' not in helper
    for method in ('PilotCmdCwdRawMatched', 'PilotCmdReadRawMatched'):
        body = helper[helper.index('    static bool ' + method + '('):]
        if method == 'PilotCmdCwdRawMatched':
            body = body[:body.index('    static bool PilotCmdReadRawMatched')]
        assert 'row.Fatal' not in body and 'PilotMayAdvance' not in body and 'ScopedLifecycleCleanupConfirmed' not in body
    runner, subjects, facts = old['PilotRunner.cs'], old['PilotSubjects.cs'], old['PilotClassification.cs']
    sequence = '"ordinary","reference","node","cmd","powershell","pwsh","cmd-exit23","cmd-batch-exit23","cmd-cwd","cmd-read-direct"'
    assert runner.count(sequence) == 2
    for field, reducer in [('CmdCwdRawObservationMatched', 'PilotCmdCwdRawMatched'), ('CmdReadRawObservationMatched', 'PilotCmdReadRawMatched')]:
        assert runner.count('result.' + field + '=' + reducer + '(result.Cases);') == 2
    assert 'if(PilotCmdObservationKind(kind)) ReadPilotCmdObservation(s,evidence);' in runner
    assert runner.index('if(PilotCmdObservationKind(kind)) ReadPilotCmdObservation(s,evidence);') > runner.index('if(!captured) throw')
    assert 'CapturePilotCmdReadBatch(s,evidence);' in subjects
    assert subjects.index('CapturePilotCmdReadBatch(s,evidence);') < subjects.index('CreateAppContainerProfile(')
    assert facts.index('row.CmdCwdObserved=false;row.CmdReadObserved=false;') < facts.index('if(row.Fatal) return;')
    assert facts.index('ClassifyPilotCmdBatch(row);return;') < facts.index('ClassifyPilotCmdObservation(row);return;')
    assert 'CmdCwdObservationPassed' not in runner + helper + subjects
    assert 'CmdReadObservationPassed' not in runner + helper + subjects
    assert workflow.count('python tests/windows-broker-direct/cmd-observations-audit.py') == 1
    assert workflow.count('[BrokerDirectLauncher]::RunPilotCmdObservationContractTests()') == 1
    assert workflow.count('& tests/windows-broker-direct/run-pilot.ps1') == 1
    assert 'continue-on-error' not in workflow


class CmdObservationSourceAudit(unittest.TestCase):
    def setUp(self):
        self.new = {name: (HERE / name).read_text(encoding='utf-8') for name in NAMES}
        self.old = {name: (HERE / name).read_text(encoding='utf-8') for name in OLD_NAMES}
        self.python = {name: (HERE / name).read_text(encoding='utf-8') for name in PYTHON}
        self.workflow = (ROOT / '.github/workflows/windows-lpac-runtime-diagnostic.yml').read_text(encoding='utf-8')

    def test_exact_scope(self):
        coverage({p.name for p in HERE.iterdir() if p.suffix in ('.cs', '.ps1')})
        inspect(self.new, self.old, self.python, self.workflow)

    def test_explicit_utf8_reads_and_unicode_fixture(self):
        audit = (HERE / 'cmd-observations-audit.py').read_text(encoding='utf-8')
        calls = [node for node in ast.walk(ast.parse(audit)) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute) and node.func.attr == 'read_text']
        self.assertEqual(len(calls), 5)
        for call in calls:
            self.assertTrue(any(arg.arg == 'encoding' and isinstance(arg.value, ast.Constant)
                                and arg.value.value == 'utf-8' for arg in call.keywords))
        source = self.new['PilotCmdObservationsTests.cs']
        encoded = r'C:\\synthetic-pil\u00f6t'
        self.assertTrue(source.isascii())
        self.assertIn('Subject.Parent=unicode?"' + encoded + '":', source)
        self.assertEqual(encoded.encode('ascii').decode('unicode_escape'), r'C:\synthetic-pil' + chr(0xf6) + 't')
        self.assertIn('trace=new PilotCmdObservationTrace(kind,true)', source)
        self.assertIn('cmd_cwd_expected_encoding_unsupported', source)

    def test_union_rejects_unknown_missing_collision(self):
        names = OLD_NAMES | set(NAMES)
        for values in (names | {'Unknown.cs'}, names - {NAMES[0]}, names | {'pilotcmdobservations.cs'}):
            with self.subTest(values=values), self.assertRaises(AssertionError):
                coverage(values)

    def test_every_immutable_span_mutation(self):
        for name, anchor, count, sha in SPANS:
            changed = dict(self.old)
            source = changed[name]
            start = next(m.start() for m in re.finditer(re.escape(anchor), source)
                         if hashlib.sha256(source[m.start():m.start() + count].encode()).hexdigest() == sha)
            changed[name] = source[:start] + '!' + source[start + 1:]
            with self.subTest(span=sha), self.assertRaises(AssertionError):
                inspect(self.new, changed, self.python, self.workflow, False)

    def test_python_acquisition_rejected(self):
        for code in ('import socket', 'open("artifact.zip")', 'eval("1")', '__import__("os")'):
            changed = dict(self.python)
            changed[PYTHON[0]] += '\n' + code
            with self.subTest(code=code), self.assertRaises(AssertionError):
                pure_python(changed)

    def test_semantic_mutations_without_pins(self):
        mutations = [(' /d /q /c cd"', ' /d /q /c pwd"'), (' /d /q /c type direct.cmd"', ' /d /q /c direct.cmd"'),
                     ('!s.OwnershipCertain || !s.ProfileCreated || !s.ProcessStopped || !s.JobDrained', 'false'),
                     ('full!=exactWorkspace', 'false'), ('Path.GetFullPath(exactWorkspace)!=exactWorkspace', 'false'),
                     ('foreach(char c in exactWorkspace) if(c>127) return null;', ''),
                     ('r.Numbers["pilot_cmd_observation_raw_complete"]=0;', ''),
                     ('!PilotCmdRawEqual(output,outputCopy)', 'false'), ('!PilotCmdRawEqual(error,errorCopy)', 'false'),
                     ('r.Identities.ContainsKey(label+"_close_exception")', 'false'),
                     ('!PilotNumber(r,"pilot_cmd_observation_expected_supported",1)', 'false'),
                     ('!PilotPinnedMethodDiagnostics(r)', 'false'), ('!PilotKnownAccessCheckKey(key)', 'false'),
                     ('r.TokenVerified || r.Wait!=WAIT_OBJECT_0 || r.Exit!=0', 'false'),
                     ('PilotCaseReceipt row=rows[8];', 'PilotCaseReceipt row=rows[9];'),
                     ('PilotCaseReceipt row=rows[9];', 'PilotCaseReceipt row=rows[8];'),
                     ('row.CmdCwdObserved=false;row.CmdReadObserved=false;', ''),
                     ('CapturePilotCmdBatchCore(s,evidence,ops,true);', 'CapturePilotCmdBatchCore(s,evidence,ops,false);')]
        for before, after in mutations:
            changed = dict(self.new)
            self.assertIn(before, changed[NAMES[0]])
            changed[NAMES[0]] = changed[NAMES[0]].replace(before, after)
            with self.subTest(mutation=before), self.assertRaises(AssertionError):
                inspect(changed, self.old, self.python, self.workflow, False)


def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromModule(cmd_observation_artifact_tests))
    return tests


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    print('Discovered unittest methods:', suite.countTestCases())
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    print('Executed unittest methods:', outcome.testsRun, '(synthetic/source contracts only)')
    sys.exit(not outcome.wasSuccessful())
