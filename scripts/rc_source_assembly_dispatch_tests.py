"""Synthetic dispatch and quiet-browser evidence regressions.

Windows process creation and filesystem presence are mocked explicitly. These
contracts neither launch Windows processes nor claim hosted/native acceptance.
"""
from collections.abc import MutableMapping
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_source_assembly as assembly
import rc_source_assembly_tests as contracts
import rc_source_assembly_frontend as frontend
from rc_source_assembly_tests import frontend_fixture

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = r'C:\Program Files\Git\bin\bash.exe'
WSL_BASH = r'C:\Windows\System32\bash.exe'
ARGV = ['bash', '-euo', 'pipefail', '-c', 'printf synthetic-witness']


class WindowsGitBashDispatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='git-bash-witness-')
        self.addCleanup(temp.cleanup)
        self.evidence = Path(temp.name)
        self.present = True
        self.resolved = WSL_BASH
        self.started = []
        self.fake_os = SimpleNamespace(name='nt', environ={'COMSPEC': r'C:\Windows\System32\cmd.exe'},
            path=SimpleNamespace(isfile=lambda value: self.present and value == GIT_BASH))
        self.enterContext(patch.object(assembly, 'os', self.fake_os))
        self.enterContext(patch.object(assembly, 'shutil', SimpleNamespace(which=lambda value: self.resolved)))
        self.enterContext(patch.object(assembly, 'sys', SimpleNamespace(
            stdout=SimpleNamespace(buffer=io.BytesIO()), stderr=SimpleNamespace(buffer=io.BytesIO()))))
        self.enterContext(patch.object(assembly.subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True))
        self.enterContext(patch.object(assembly.subprocess, 'Popen', side_effect=self.spawn))

    def spawn(self, argv, **kwargs):
        self.started.append((argv, kwargs))
        kwargs['stdout'].write(b'SYNTHETIC dispatcher test, no process launched\n')
        return SimpleNamespace(wait=lambda timeout: 0)

    def capture(self, name='witness', argv=None):
        argv = list(ARGV if argv is None else argv)
        self.assertEqual(assembly.capture_command(ROOT, self.evidence, name, 30, argv), 0)
        return json.loads((self.evidence / 'commands' / name / 'command.json').read_text())

    def test_windows_uses_fixed_git_bash_even_when_path_resolves_wsl(self):
        receipt = self.capture()
        self.assertEqual(receipt['command'], ARGV)
        self.assertEqual(receipt['executed_command'], [GIT_BASH, *ARGV[1:]])
        self.assertEqual(self.started[0][0], [GIT_BASH, *ARGV[1:]])
        assembly.command_result(self.evidence, 'witness', ARGV)

    def test_missing_git_bash_never_spawns_or_accepts_receipt(self):
        self.capture('existing')
        self.started.clear()
        self.present = False
        with self.assertRaisesRegex(ValueError, 'missing_windows_git_bash'):
            assembly.capture_command(ROOT, self.evidence, 'missing', 30, ARGV)
        self.assertEqual(self.started, [])
        with self.assertRaisesRegex(ValueError, 'missing_windows_git_bash'):
            assembly.command_result(self.evidence, 'existing', ARGV)

    def test_verifier_rejects_unresolved_wsl_and_substituted_absolute_paths(self):
        receipt = self.capture()
        path = self.evidence / 'commands/witness/command.json'
        for wrong in ['bash', WSL_BASH, r'C:\untrusted\Git\bin\bash.exe']:
            with self.subTest(executable=wrong):
                assembly.write(path, {**receipt, 'executed_command': [wrong, *ARGV[1:]]})
                with self.assertRaisesRegex(ValueError, 'wrong_executed_command_witness'):
                    assembly.command_result(self.evidence, 'witness', ARGV)

    def test_windows_cmd_and_bat_dispatch_remain_unchanged(self):
        for extension in ['cmd', 'bat']:
            with self.subTest(extension=extension):
                self.resolved = r'C:\Program Files\nodejs\npm.' + extension
                argv = ['npm', 'ci']
                expected = [self.fake_os.environ['COMSPEC'], '/d', '/s', '/c',
                            subprocess.list2cmdline([self.resolved, *argv[1:]])]
                receipt = self.capture(extension, argv)
                self.assertEqual(receipt['command'], argv)
                self.assertEqual(receipt['executed_command'], expected)
                assembly.command_result(self.evidence, extension, argv)

    def test_linux_bash_dispatch_remains_unchanged(self):
        self.fake_os.name = 'posix'
        self.present = False
        receipt = self.capture()
        self.assertEqual(receipt['command'], ARGV)
        self.assertEqual(receipt['executed_command'], ARGV)
        self.assertTrue(self.started[0][1]['start_new_session'])
        assembly.command_result(self.evidence, 'witness', ARGV)


class QuietUIEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='quiet-ui-contract-')
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name) / 'evidence'
        frontend_fixture(Path(self.temp.name) / 'root', self.evidence)
        (self.evidence / 'commands/ui-browser/stdout.txt').write_bytes(b'')

    def test_known_quiet_ui_requires_complete_browser_proof(self):
        frontend.commands(self.evidence)

    def test_quiet_ui_rejects_missing_streams_and_missing_or_invalid_reports(self):
        for name in ('commands/ui-browser/stdout.txt', 'commands/ui-browser/stderr.txt',
                     'existing-ui/result.json', 'existing-ui/state-results.json',
                     'existing-ui/source-manifest.json',
                     'existing-ui/workspace-overview-1280x800-light.png'):
            path = self.evidence / name
            original = path.read_bytes()
            path.unlink()
            with self.subTest(missing=name), self.assertRaises(ValueError):
                frontend.commands(self.evidence)
            path.write_bytes(original)
        for payload in (b'{}', b'{"ok":false}', b'not JSON'):
            path = self.evidence / 'existing-ui/result.json'
            original = path.read_bytes()
            path.write_bytes(payload)
            with self.subTest(invalid=payload), self.assertRaises(ValueError):
                frontend.commands(self.evidence)
            path.write_bytes(original)

    def test_other_commands_still_require_nonempty_stdout(self):
        for name in frontend.COMMANDS.keys() - {'ui-browser'}:
            path = self.evidence / 'commands' / name / 'stdout.txt'
            original = path.read_bytes()
            path.write_bytes(b'')
            with self.subTest(command=name), self.assertRaises(ValueError):
                frontend.commands(self.evidence)
            path.write_bytes(original)


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = contracts.SourceHistoryTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()

    def test_only_exact_legacy_inventory_precedes_required_dispatch_module(self):
        fixture = self.fixture
        history = assembly.verify_history(fixture.root, fixture.first)
        self.assertEqual([row['sha'] for row in history], [fixture.legacy, fixture.first])
        self.assertEqual(set(history[0]['delta_blobs']), assembly.LEGACY_ADDED | assembly.MODIFIED)
        self.assertEqual(set(history[1]['delta_blobs']), assembly.SCOPE)
        self.assertNotIn(assembly.DISPATCH_TESTS, history[0]['delta_blobs'])
        self.assertIn(assembly.DISPATCH_TESTS, history[1]['delta_blobs'])

    def test_forged_legacy_identity_or_tree_rejects(self):
        for field in ('LEGACY_IMPLEMENTATION', 'LEGACY_TREE'):
            with self.subTest(field=field), patch.object(assembly, field, 'f' * 40):
                with self.assertRaisesRegex(ValueError, 'wrong_legacy_'):
                    assembly.verify_history(self.fixture.root, self.fixture.first)

    def test_later_missing_dispatch_module_and_drop_then_restore_reject(self):
        fixture = self.fixture
        path = fixture.root / assembly.DISPATCH_TESTS
        original = path.read_bytes()
        path.unlink()
        missing = fixture.commit('synthetic forbidden dispatch deletion')
        with self.assertRaisesRegex(ValueError, 'wrong_added_removed_paths'):
            assembly.verify_history(fixture.root, missing)
        path.write_bytes(original)
        restored = fixture.commit('synthetic forbidden deletion concealed by restore')
        with self.assertRaisesRegex(ValueError, 'wrong_added_removed_paths'):
            assembly.verify_history(fixture.root, restored)

    def test_sixteen_path_descendant_cannot_replace_legacy_predecessor(self):
        fixture = self.fixture
        fixture.git('checkout', '-qb', 'synthetic-foreign', fixture.anchor)
        for name in assembly.ADDED:
            contracts.write(fixture.root, name, 'synthetic replacement ' + name)
        contracts.write(fixture.root, 'scripts/engineering_dependency_capture.py', 'synthetic adapter')
        replacement = fixture.commit('synthetic unreviewed replacement integration')
        with self.assertRaisesRegex(ValueError, 'wrong_legacy_implementation'):
            assembly.verify_history(fixture.root, replacement)


class UppercaseEnvironment(MutableMapping):
    """Synthetic Windows key casing without reading or saving host values."""
    def __init__(self, values):
        self.values = {key.upper(): value for key, value in values.items()}

    def __getitem__(self, key):
        return self.values[key.upper()]

    def __setitem__(self, key, value):
        self.values[key.upper()] = value

    def __delitem__(self, key):
        del self.values[key.upper()]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class EnvironmentKeyCaseTests(unittest.TestCase):
    def test_missing_image_label_fixture_removes_uppercase_windows_key(self):
        cases = [
            (contracts.SourceHistoryTests, 'test_explicit_matrix_survives_missing_image_label_but_cannot_be_missing', 'verify_source'),
            (contracts.WiringTests, 'test_missing_image_label_cannot_skip_ubuntu24_browser_acceptance', 'finish'),
        ]
        for test_class, name, target in cases:
            environment = UppercaseEnvironment({'ImageOS': 'synthetic-host-label'})
            original, observed = getattr(assembly, target), []
            def check_absent(*args, **kwargs):
                self.assertNotIn('IMAGEOS', {key.upper() for key in contracts.os.environ})
                observed.append(True)
                return original(*args, **kwargs)
            result = unittest.TestResult()
            with self.subTest(fixture=name), patch.object(contracts.os, 'environ', environment), \
                    patch.object(assembly, target, side_effect=check_absent):
                test_class(name).run(result)
                self.assertEqual(result.errors, [])
                self.assertEqual(result.failures, [])
                self.assertEqual(len(observed), 2)


if __name__ == '__main__':
    unittest.main()
