"""Finite warning-only adoption proofs; synthetic parser cases are not native evidence."""
import ast
from collections import Counter
from contextlib import chdir
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
from rc_pretag_integration_admission_profile import normalize as integration_bytes
import rc_pretag_publication_profile as p
import rc_pretag_publication_adapters as adapters
import rc_pretag_publication_tests as pt
from rc_pretag_appimage_profile import inverse_appimage_adapter

FILESYSTEM = 'src-tauri/src/workspace_snapshots/filesystem.rs'
MODEL = 'src-tauri/src/workspace_snapshots/model.rs'
WORKFLOW = '.github/workflows/windows-snapshot-warning-scope.yml'
CASES = 'scripts/rc_pretag_snapshot_warning_cases.py'
JOIN_TESTS = 'scripts/rc_pretag_join_once_tests.py'
CLASS = 'rc_pretag_snapshot_warning_cases.SnapshotWarningCompositionTests'
DIGEST = '94cd89ce8d62e001f8ec0e256dd031462cdbf8c34ed8edb06dd7189b52c42e75'
DONOR = {FILESYSTEM: 'f3de379c5f107ddfe558fcdc885a344c71cf7054', MODEL: 'c639b79bf3d852e30d532a2a3e647d6dcd88b0ee'}
PROTECTED = ('src-tauri/src/workspace_snapshots/' + name for name in ('mod.rs', 'restore.rs', 'tests.rs', 'metadata_tests.rs'))
PROTECTED = (*PROTECTED, 'src-tauri/src/commands/workspace_snapshots.rs',
    'src-tauri/src/commands/workspace_snapshot_control_tests.rs', 'src-tauri/src/harness/worktree_snapshot.rs')


def workflow_inverse(text):
    begin, end = '    # BEGIN EXACT WARNING CASE STEP\n', '    # END EXACT WARNING CASE STEP\n'
    assert text.count(begin) == text.count(end) == 1
    step = begin + text.split(begin)[1].split(end)[0] + end
    assert hashlib.sha256(step.encode()).hexdigest() == 'e00a6ca58d0dbaa9f3e20183403e9d46a1a211bde90488d24ac2aa75ff83e3a4'
    assert text.count('        git diff --exit-code HEAD --\n' + step + '    - name: Native formatting gate\n') == 1
    text = c._replace_once(text, step, '')
    for current, old, count in (
        ('    - fix/windows-snapshot-warning-scope-m6edd4e6\n', '    - fix/windows-snapshot-warning-scope\n', 1),
        (p.WARNING_B, 'c3fcfb1f2617d56f8f395317a18d93884d551789', 3),
        (p.WARNING_TREE, '2066e8ae62522e3a9ee579e03d36ebfbdddeafd0', 1),
        ('Bind exact ten-path candidate', 'Bind exact six-path candidate', 1),
        ("'candidate scope differs from approved ten paths'", "'candidate scope differs from approved six paths'", 1),
        (", 'scripts/rc_pretag_publication_profile.py', 'scripts/rc_pretag_publication_adapters.py', "
         "'scripts/rc_pretag_join_once_tests.py', 'scripts/rc_pretag_snapshot_warning_cases.py']", ']', 1)):
        assert text.count(current) == count
        text = text.replace(current, old)
    data = text.encode()
    assert (len(data), len(data.splitlines())) == (22443, 362)
    assert o.pin(data) == ('a80db5b7f0848d071461bd507aba3efc84a58d49',
                         '4efaa35cfe031b8c793b92a8c51671e23f65fc7f5be29842e787320c2b144214')
    return data


def workflow_scripts():
    blocks = re.findall(r"        (?:python - <<|cat > evidence/\S+ <<)'PY'\n(.*?)        PY", (c.ROOT / WORKFLOW).read_text(), re.S)
    assert len(blocks) == 5
    return [textwrap.dedent(block) for block in blocks]


def namespace(script):
    scope = {'__name__': 'synthetic_fixture'}
    exec(compile(script, WORKFLOW, 'exec'), scope)
    return scope


class SnapshotWarningCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.original = c._entries(p.WARNING_B, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(inverse_appimage_adapter(path, (c.ROOT / path).read_bytes()))) for path in p.WARNING_CAPS}
        self.pure = self.commit([p.WARNING_B], self.good)
        self.feature = self.commit([p.WARNING_B, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)

    def frozen(self, path):
        return c._git('show', p.WARNING_B + ':' + path, root=self.repo)

    def selected(self, ref, git=c._git):
        return p.selected_profile(ref, self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def content(self, ref, git=c._git):
        return p.warning_content(ref, self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([p.WARNING_B] if parents is None else parents, entries)
        p.warning_topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)

    def rejects(self, parents):
        ref = self.commit(parents, self.good)
        with self.assertRaises(o.TopologyError):
            p.warning_topology(ref, self.repo, c._git, p.R)
        with patch.object(p, 'warning_content') as content, self.assertRaises(o.TopologyError):
            self.selected(ref)
        content.assert_not_called()

    def test_exact_6edd_anchor_tree_parents_and_historical_validation(self):
        self.assertEqual((p.WARNING_B, p.WARNING_TREE, p.WARNING_PARENTS),
            ('6edd4e6137a6947319183b3ac8801bfa608ac722', '35cfad529c2427bac17c344089686b2cf3d46823',
             ('9c5c031d24aadc5d704160bb5a5a65bff126c10c', '02ea77dda8d65ea15dd6b0ffbfce13aae800fc3f')))
        self.assertEqual(self.selected(p.WARNING_B), self.original)
        # No mutable-result or historical-validation cache: every invocation is fresh.
        with patch.object(p, 'join_once_content', wraps=p.join_once_content) as historical:
            self.assertEqual(self.content(self.pure), self.good)
            self.assertEqual(self.content(self.pure), self.good)
            self.assertEqual(historical.call_count, 2)
            self.bad_content(self.changed(FILESYSTEM, (c.ROOT / FILESYSTEM).read_bytes() + b'\n'))
            self.assertEqual(historical.call_count, 3)
        for command, replacement, error in ((('show', '-s', '--format=%P', p.WARNING_B), b'\n', o.TopologyError),
                (('rev-parse', p.WARNING_B + '^{tree}'), b'0' * 40 + b'\n', AssertionError)):
            def wrong(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(error):
                self.selected(self.pure, wrong)
        with patch.object(p, 'join_once_content', side_effect=AssertionError('fresh historical failure')), \
             self.assertRaisesRegex(AssertionError, 'fresh historical failure'):
            self.content(self.pure)

    def test_candidate_has_only_ten_reviewed_paths(self):
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(self.original), len(self.good), len(p.WARNING_CAPS)), (1693, 1698, 10))
        self.assertEqual({path for path in self.good if self.good[path] != self.original.get(path)}, p.WARNING_CAPS.keys())
        self.assertEqual(p.WARNING_PINS.keys(), p.WARNING_CAPS.keys() - {p.PROFILE})
        for path, row in p.WARNING_PINS.items():
            data = inverse_appimage_adapter(path, (c.ROOT / path).read_bytes())
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.bad_content(self.changed(path, data + b'\n'))
        row = p.WARNING_PINS[FILESYSTEM]
        for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
            changed = list(row)
            changed[index] = value
            with patch.dict(p.WARNING_PINS, {FILESYSTEM: tuple(changed)}), self.assertRaises(AssertionError):
                self.content(self.pure)
        for pins in ({k: v for k, v in p.WARNING_PINS.items() if k != FILESYSTEM}, p.WARNING_PINS | {'extra': row}):
            with patch.dict(p.WARNING_PINS, pins, clear=True), self.assertRaises(AssertionError):
                self.content(self.pure)

    def test_ordered_feature_merge_requires_entire_candidate_tree(self):
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(p.warning_topology(self.feature, self.repo, c._git, p.R), ('nonrelease', self.feature, self.pure))
        for entries in (self.original, self.changed(FILESYSTEM, self.frozen(FILESYSTEM)), self.overlay):
            self.bad_content(entries, [p.WARNING_B, self.pure])

    def test_release_overlay_requires_exact_four_historical_documents(self):
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual(len(c.RELEASE_DOCS), 4)
        self.assertEqual(p.R_DOCUMENTS, c.RELEASE_DOCS)
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_missing_reversed_extra_duplicate_nested_parents_reject(self):
        for parents in ([], [self.pure], [self.pure, p.WARNING_B], [p.WARNING_B, self.pure, p.R],
                        [p.WARNING_B, p.WARNING_B], [p.WARNING_B, self.feature], [p.R], [p.R, self.pure],
                        [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release]):
            with self.subTest(parents=parents):
                self.rejects(parents)

    def test_unknown_same_tree_anchors_and_correction_chains_reject(self):
        impostor = self.commit([], self.original)
        correction = self.commit([self.pure], self.good)
        for parents in ([impostor], [impostor, self.pure], [correction], [p.WARNING_B, correction],
                        ['0a18f3bcf562e32a1fd29477491a84a1bf0e6d0c'], ['86b5310000000000000000000000000000000000']):
            self.rejects(parents)
        with self.assertRaises(o.TopologyError):
            p.warning_topology(self.pure, self.repo, c._git, impostor)

    def test_two_production_blobs_match_pr106_donor(self):
        for path, blob in DONOR.items():
            self.assertEqual(c._blob((c.ROOT / path).read_bytes()), blob)
            self.assertEqual(self.good[path], ('100644', 'blob', blob))

    def test_four_edits_preserve_linux_bodies_and_other_refusals(self):
        original = self.frozen(FILESYSTEM).decode()
        current = (c.ROOT / FILESYSTEM).read_text()
        expected = c._replace_once(original, '    io::{Read, Write},\n', '')
        expected = c._replace_once(expected, 'use std::{\n    collections::BTreeMap,\n    fs::File,\n    path::Path,\n};\n',
                                  'use std::{collections::BTreeMap, fs::File, path::Path};\n')
        expected = c._replace_once(expected, '    ffi::CString,\n', '    ffi::CString,\n    io::{Read, Write},\n')
        expected = c._replace_once(expected, '    pub file: File,\n', '    #[cfg(target_os = "linux")]\n    pub file: File,\n')
        before, refusal = expected.split('#[cfg(not(target_os = "linux"))]\n', 1)
        refusal = c._replace_once(refusal, '    pub fn sync(&self) -> Result<()> {\n        Err(SnapshotError::Unsupported)\n    }\n', '')
        self.assertEqual(current, before + '#[cfg(not(target_os = "linux"))]\n' + refusal)
        self.assertEqual((c.ROOT / MODEL).read_text(), c._replace_once(self.frozen(MODEL).decode(),
            '    Busy,\n', '    #[cfg(target_os = "linux")]\n    Busy,\n'))

    def test_protected_snapshot_tests_adapters_and_authority_unchanged(self):
        self.assertEqual(len(PROTECTED), 7)
        for path in PROTECTED:
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)
            self.bad_content(self.changed(path, self.frozen(path) + b'\n'))
        positive = (c.ROOT / PROTECTED[-2]).read_text()
        self.assertIn('async fn exact_native_restore_lease_waits_for_real_work_and_restores_saved_tree()', positive)
        self.assertIn('assert!(report.retained_backup);', positive)
        self.assertIn('"committed contents"', positive)

    def test_workflow_inverse_allows_only_anchor_scope_branch_and_case_step(self):
        current = (c.ROOT / WORKFLOW).read_text()
        workflow_inverse(current)
        self.assertEqual(current.count("if: always() && steps.prepare.outcome == 'success'"), 6)
        for altered in (current + '# drift\n', current.replace('contents: read', 'contents: write'),
                        current.replace('set -euo pipefail', 'set -eu', 1), current.replace('python -B scripts/', 'python scripts/'),
                        current.replace('    # BEGIN EXACT WARNING CASE STEP\n', ''),
                        current.replace('    # END EXACT WARNING CASE STEP\n', '    # END EXACT WARNING CASE STEP\n' * 2)):
            with self.assertRaises(AssertionError):
                workflow_inverse(altered)

    def test_baseline_and_candidate_native_source_bindings_fail_closed(self):
        def exercise(index, fault=None):
            script = workflow_scripts()[index]
            tree = ast.parse(script)
            pins = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)
                                        and any(isinstance(t, ast.Name) and t.id == 'expected' for t in node.targets)))
            with tempfile.TemporaryDirectory() as folder, chdir(folder), patch.dict(os.environ, GITHUB_SHA=self.pure, RUNNER_OS='synthetic'):
                for path in pins:
                    destination = Path(path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(self.frozen(path) if index == 0 else (c.ROOT / path).read_bytes())
                def git(command, **kwargs):
                    args = tuple(command[1:])
                    if args == ('rev-parse', 'HEAD'):
                        return 'wrong' if fault == 'head' else p.WARNING_B if index == 0 else self.pure
                    if args == ('rev-parse', 'HEAD^{tree}'):
                        return 'wrong' if fault == 'tree' else p.WARNING_TREE
                    if args == ('diff', 'HEAD'):
                        return 'dirty' if fault == 'dirty' else ''
                    if args[:2] == ('diff', '--name-only'):
                        self.assertEqual(args[2:], (p.WARNING_B, 'HEAD'))
                        return '\n'.join(list(p.WARNING_CAPS)[:-1] if fault == 'scope' else p.WARNING_CAPS)
                    path = args[1].removeprefix('HEAD:')
                    return 'wrong' if fault == args[0] else pins[path]
                with patch('subprocess.check_output', side_effect=git):
                    namespace(script)
                return json.loads(Path('evidence/source-binding.json').read_text())
        for index in (0, 2):
            self.assertEqual(len(exercise(index)['files']), 9)
            for fault in ('head', 'dirty', 'rev-parse', 'hash-object', 'tree' if index == 0 else 'scope'):
                with self.subTest(index=index, fault=fault), self.assertRaises(AssertionError):
                    exercise(index, fault)

    def test_original_warning_runtime_positive_parsers_are_unchanged(self):
        scripts = workflow_scripts()
        baseline, runtime, positive = (namespace(scripts[index]) for index in (1, 3, 4))
        messages = []
        for message, (code, filename, line) in baseline['EXPECTED'].items():
            messages.append(dict(reason='compiler-message', target=dict(name='coding_tools_mcp_desktop_lib',
                kind=['rlib', 'staticlib', 'cdylib'], crate_types=['rlib', 'staticlib', 'cdylib']),
                message=dict(level='error', message=message, code=dict(code=code),
                    spans=[dict(is_primary=True, file_name=filename, line_start=line)])))
        messages.append(dict(reason='build-finished', success=False))
        encode = lambda rows: '\n'.join(map(json.dumps, rows))
        self.assertEqual(baseline['validate'](encode(messages), '', 101)['diagnostic_count'], 4)
        for rows, stderr, status in ((messages[:-1], '', 101), (messages[1:], '', 101), (messages + messages[:1], '', 101),
                (messages, '', 0), (messages, 'error: unrelated failure', 101),
                (messages[:-1] + [dict(reason='build-finished', success=True)], '', 101)):
            with self.assertRaises(AssertionError):
                baseline['validate'](encode(rows), stderr, status)
        for field, value in (('message', 'other warning'), ('code', {'code': 'wrong'}),
                             ('spans', [dict(is_primary=True, file_name='wrong.rs', line_start=6)])):
            changed = json.loads(json.dumps(messages))
            changed[0]['message'][field] = value
            with self.assertRaises(AssertionError):
                baseline['validate'](encode(changed), '', 101)
        changed = json.loads(json.dumps(messages))
        changed[0]['target']['name'] = 'unrelated_crate'
        with self.assertRaises(AssertionError):
            baseline['validate'](encode(changed), '', 101)
        name = positive['NAME']
        header = '     Running unittests src/lib.rs (target/debug/deps/synthetic)\n'
        inventory = header + name + ': test\nordinary: test\n2 tests, 0 benchmarks\n'
        good = header + f'test {name} ... ok\ntest ordinary ... ok\ntest result: ok. 2 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
        self.assertEqual(runtime['inspect'](inventory, good, 0)['inventory_total'], 2)
        failed = good.replace('ordinary ... ok', 'ordinary ... FAILED').replace('ok. 2 passed; 0 failed', 'FAILED. 1 passed; 1 failed')
        self.assertEqual(runtime['inspect'](inventory, failed, 101)['exit'], 101)
        for listed, output, status in ((inventory, failed, 0), (inventory, good.replace('0 filtered', '1 filtered'), 0),
                (inventory, good.replace('test ordinary ... ok\n', ''), 0), (inventory.replace('ordinary:', name + ':'), good, 0),
                (inventory.replace(name, 'other'), good.replace(name, 'other'), 0), (inventory, good.replace('2 passed', '1 passed'), 0),
                (inventory, good.replace('ordinary ... ok', 'ordinary ... ignored'), 0),
                (inventory, good.replace('test ordinary ... ok\n', 'test ordinary ... ok\n' * 2), 0)):
            with self.assertRaises(AssertionError):
                runtime['inspect'](listed, output, status)
        single = f'test {name} ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 9 filtered out;\n'
        self.assertEqual(positive['inspect'](single, 0)['passed'], 1)
        refusal = single.replace('... ok', '... FAILED').replace('ok. 1 passed; 0 failed', 'FAILED. 0 passed; 1 failed') + 'Unsupported\n'
        self.assertEqual(positive['inspect'](refusal, 101)['failed'], 1)
        for output, status in ((refusal, 0), (single.replace(name, 'wrong'), 0), (single + single, 0), (single.replace('0 ignored', '1 ignored'), 0)):
            with self.assertRaises(AssertionError):
                positive['inspect'](output, status)

    def test_missing_extra_rename_mode_symlink_gitlink_binary_reject(self):
        for path in p.WARNING_CAPS:
            missing = {key: value for key, value in self.good.items() if key != path}
            changes = [missing, missing | {path + '.renamed': self.good[path]}]
            changes += [self.good | {path: entry} for entry in (('100755', *self.good[path][1:]),
                ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', p.WARNING_B))]
            for entries in (*changes, self.changed(path, b'\0binary\xff')):
                with self.subTest(path=path):
                    self.bad_content(entries)
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))

    def test_individual_and_aggregate_budgets_reject(self):
        self.assertEqual((p.WARNING_DELTA_LIMIT, sum(cap[1] for cap in p.WARNING_CAPS.values())), (1500, 1583))
        for path, (_, delta) in p.WARNING_CAPS.items():
            lines = len(inverse_appimage_adapter(path, (c.ROOT / path).read_bytes()).splitlines())
            with patch.dict(p.WARNING_CAPS, {path: (lines - 1, delta)}), self.assertRaises(AssertionError):
                self.content(self.pure)
            def oversized(*args, root):
                return f'{delta + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', p.WARNING_B, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.content(self.pure, oversized)
        def aggregate(*args, root):
            if args[:5] == ('diff', '--numstat', p.WARNING_B, self.pure, '--'):
                return f'{p.WARNING_CAPS[args[5]][1]}\t0\t{args[5]}\n'.encode()
            return c._git(*args, root=root)
        with self.assertRaisesRegex(AssertionError, 'delta_budget'):
            self.content(self.pure, aggregate)
        for row in (b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', b'1\t0\t' + path.encode() + b'\nextra'):
            def malformed(*args, root):
                return row if args == ('diff', '--numstat', p.WARNING_B, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.content(self.pure, malformed)

    def test_current_inverses_recover_complete_6edd_files(self):
        self.assertEqual(adapters.WARNING_BASE_PINS.keys(), {p.PROFILE, p.JOIN_ONCE_HELPER, JOIN_TESTS})
        for path in adapters.WARNING_BASE_PINS:
            data = inverse_appimage_adapter(path, (c.ROOT / path).read_bytes())
            self.assertEqual(adapters.inverse_warning_adapter(path, data), self.frozen(path))
            for changed in (data + b'# outside\n', data.replace(b'assert ', b'# assert ', 1)):
                with self.assertRaises(AssertionError):
                    adapters.inverse_warning_adapter(path, changed)
        current = (c.ROOT / JOIN_TESTS).read_bytes()
        for before, _ in adapters.WARNING_JOIN_ONCE_FRAGMENTS:
            for replacement in ('', before * 2):
                with self.assertRaises(AssertionError):
                    adapters.inverse_warning_adapter(JOIN_TESTS, current.replace(before.encode(), replacement.encode(), 1))

    def test_historical_profiles_pins_shapes_and_assertions_preserved(self):
        for path in (p.COMPOSITION, p.TESTS, p.DESKTOP_TESTS, p.NGINX_TESTS, p.TWO_HOP_TESTS, p.AUTHENTICATED_TESTS,
                     'scripts/rc_pretag_ownership_profile.py', p.authenticated.PROFILE, 'scripts/rc_pretag_two_hop_profile.py',
                     'scripts/rc_pretag_desktop_profile.py', 'scripts/rc_pretag_nginx_profile.py'):
            self.assertEqual(integration_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)
        for ref in (p.desktop.X, p.nginx.F, p.two_hop.F, p.authenticated.M, p.N, p.JOIN_ONCE_M, p.WARNING_B):
            self.assertEqual(self.selected(ref), c._entries(ref, self.repo))
        frozen = ast.parse(self.frozen(JOIN_TESTS))
        restored = ast.parse(adapters.inverse_warning_adapter(JOIN_TESTS, integration_bytes(JOIN_TESTS, (c.ROOT / JOIN_TESTS).read_bytes())))
        self.assertEqual(ast.dump(frozen), ast.dump(restored))
        methods = lambda tree: {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        old, new = methods(frozen), methods(ast.parse(integration_bytes(JOIN_TESTS, (c.ROOT / JOIN_TESTS).read_bytes())))
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual(sum(name.startswith('test_') for name in old), 20)
        assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
        for name in old:
            self.assertEqual(assertions(old[name]), assertions(new[name]), name)
        self.assertEqual(p.PROFILE_ID, 'engineering/issue88-publication-core-composition-v1')

    def test_selected_content_failure_is_terminal_without_fallback(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(p, 'warning_content', side_effect=error('terminal warning')), \
                 patch.object(p, 'join_once_content') as old, self.assertRaisesRegex(error, 'terminal warning'):
                self.selected(self.pure)
            old.assert_not_called()
            with patch.object(p, 'join_once_content', side_effect=error('terminal historical')), \
                 patch.object(p, 'warning_content') as new, self.assertRaisesRegex(error, 'terminal historical'):
                self.selected(p.WARNING_B)
            new.assert_not_called()
            with patch.object(p, 'warning_content', return_value=self.good), \
                 patch.object(o, 'release_content', side_effect=error('terminal release')), \
                 patch.object(p, 'publication_content') as old, self.assertRaisesRegex(error, 'terminal release'):
                self.selected(self.release)
            old.assert_not_called()

    def test_mutable_refs_and_ambient_git_cannot_change_identity(self):
        calls = []
        def moving(*args, root):
            calls.append(args)
            if args == ('rev-parse', '--verify', 'moving^{commit}'):
                return ((self.pure if calls.count(args) == 1 else self.release) + '\n').encode()
            return c._git(*args, root=root)
        hostile = {name: '/nonexistent' for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                   'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}
        with patch.dict(os.environ, hostile):
            self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_exact_303_and_452_ids_and_separate_twenty_cases(self):
        loaded = [case.id() for case in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), 'rc_pretag*_tests.py'))]
        pt.inventory_ids(loaded, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        added = [case.id() for case in c._flatten(unittest.defaultTestLoader.loadTestsFromName(CLASS))]
        expected = [prefix + '.' + name for prefix, names in p.WARNING_GROUPS.items() for name in names.split()]
        pt.inventory_ids(added, 20, DIGEST)
        self.assertEqual(Counter(added), Counter(expected))
        self.assertFalse(set(loaded) & set(added))
        method = next(node for node in ast.walk(ast.parse(self.frozen(p.TESTS))) if isinstance(node, ast.FunctionDef)
                      and node.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        old = [case.id() for module in modules for case in c._flatten(unittest.defaultTestLoader.loadTestsFromName(module)) if case.id().split('.', 1)[0] == module]
        pt.inventory_ids(old, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
        for ids in (added[:-1], added + added[:1], added[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                pt.inventory_ids(ids, 20, DIGEST)

    def test_held_scope_versions_and_release_permissions_unchanged(self):
        protected = self.original.keys() - p.WARNING_CAPS.keys()
        self.assertTrue(all(self.good[path] == self.original[path] for path in protected))
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md',
                'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py',
                 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        for path in held:
            self.assertFalse((c.ROOT / path).exists() or (c.ROOT / path).is_symlink(), path)
        for path in ('package.json', 'package-lock.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock', 'src-tauri/tauri.conf.json',
                     p.CHECKS, p.CONTRACTS, '.github/workflows/rc-pretag-evidence.yml', '.github/workflows/final-rc-packages.yml',
                     'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py'):
            self.assertEqual(integration_bytes(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName(CLASS)
    loaded = [test.id() for test in c._flatten(suite)]
    expected = [prefix + '.' + name for prefix, names in p.WARNING_GROUPS.items() for name in names.split()]
    pt.inventory_ids(loaded, 20, DIGEST)
    assert Counter(loaded) == Counter(expected)
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    executed = getattr(result, 'executed_ids', [])
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=executed, loaded=len(loaded), executed=result.testsRun)))
    return 0 if (result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
                 and Counter(executed) == Counter(loaded) and len(set(executed)) == result.testsRun == 20) else 1


if __name__ == '__main__':
    raise SystemExit(main())
