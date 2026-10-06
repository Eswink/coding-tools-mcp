"""Frozen M adoption fixtures; synthetic parser checks are never native evidence."""
import ast
from collections import Counter
from contextlib import chdir
import hashlib
import io
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
import rc_pretag_authenticated_two_hop_tests as at
import rc_pretag_publication_profile as p
import rc_pretag_publication_adapters as adapters
import rc_pretag_publication_tests as pt
from rc_pretag_publication_adapters import inverse_warning_adapter
PROCESS = 'services/local-agent/src/process.rs'
SUPERVISOR = 'services/local-agent/src/process_supervisor.rs'
REGRESSIONS = 'services/local-agent/src/process_io_join_tests.rs'
WORKFLOW = '.github/workflows/local-agent-runtime.yml'
DONOR_BLOBS = {PROCESS: 'f3a8c96a5c19f2fb9a6ff1949bf646c60dceca96',
    SUPERVISOR: '0e7d7b33b195631882d77799f6be6bd16404ad3c',
    'services/local-agent/src/process_tests.rs': 'bc966ea8738e2a09793b100cfbfc84313aa30588',
    REGRESSIONS: '1727d5eb9ca69a2b9baed0718c4619d708cce289'}
DONOR_WORKFLOW = '89602b2cb8508326f08eba6c96e6523d869caf70'
DONOR_WORKFLOW_SHA256 = '750890c959b149a158df2859be38ed92cce34ff11ecff6c2636a9ccb0e4ff6b7'
FAILED = ('stdout_ready_stderr_pending_times_out_without_repoll',
    'both_readers_ready_stdin_pending_times_out_without_repoll',
    'failed_readers_stdin_pending_times_out_without_repoll')
CONTROL = 'all_pending_timeout_control_is_incomplete'


def segment(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def workflow_scripts():
    text = (c.ROOT / WORKFLOW).read_text()
    blocks = re.findall(r"          python - <<'PYCODE'\n(.*?)          PYCODE", text, re.S)
    assert len(blocks) == 2
    return [textwrap.dedent(block) for block in blocks]


def witness():
    results = ''.join(f'test process::io_join_tests::{name} ... FAILED\n' for name in FAILED)
    blocks = ''.join(f'---- process::io_join_tests::{name} stdout ----\n'
                     'JoinHandle polled after completion\n' for name in FAILED)
    return ('running 4 tests\n' + results + f'test process::io_join_tests::{CONTROL} ... ok\n'
            + blocks + 'failures:\n'
            'test result: FAILED. 1 passed; 3 failed; 0 ignored; 0 measured; 91 filtered out;\n')


class JoinOnceCompositionTests(unittest.TestCase):
    def setUp(self):
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.original = c._entries(p.JOIN_ONCE_M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(inverse_warning_adapter(path, (c.ROOT / path).read_bytes())))
                                     for path in p.JOIN_ONCE_CAPS}
        self.pure = self.commit([p.JOIN_ONCE_M], self.good)
        self.feature = self.commit([p.JOIN_ONCE_M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self._baseline_select, self._baseline_cache = p.selected_profile, None
        self._baseline_ref = p.JOIN_ONCE_M
        self._baseline_args = (self.repo, c._git, c._entries, c._feature_profile,
                               c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def frozen(self, path):
        return c._git('show', p.JOIN_ONCE_M + ':' + path, root=self.repo)

    def selected(self, ref, git=c._git):
        return p.selected_profile(ref, self.repo, git, c._entries, c._feature_profile,
                                  c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def verified_baseline(self, ref, root, git, entries, historical, release, release_tree, documents, **kwargs):
        arguments = (root, git, entries, historical, release, release_tree, documents)
        callbacks_match = all(actual is expected for actual, expected in zip(arguments[1:4], self._baseline_args[1:4]))
        if ref != self._baseline_ref or kwargs or not callbacks_match or arguments != self._baseline_args:
            return self._baseline_select(ref, *arguments, **kwargs)
        if self._baseline_cache is None:
            self._baseline_cache = dict(self._baseline_select(ref, *arguments))
        return dict(self._baseline_cache)

    def content(self, ref, git=c._git):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return p.join_once_content(ref, self.repo, git, c._entries, c._feature_profile,
                                       c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([p.JOIN_ONCE_M] if parents is None else parents, entries)
        p.join_once_topology(ref, self.repo, c._git, p.R)
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline), self.assertRaises(AssertionError):
            self.selected(ref)

    def rejects(self, parents, entries=None):
        ref = self.commit(parents, self.good if entries is None else entries)
        with self.assertRaises(o.TopologyError):
            p.join_once_topology(ref, self.repo, c._git, p.R)
        with patch.object(p, 'join_once_content') as content, self.assertRaises(o.TopologyError):
            self.selected(ref)
        content.assert_not_called()

    def test_exact_m_anchor_tree_parents_and_historical_validation(self):
        self.assertEqual((p.JOIN_ONCE_M, p.JOIN_ONCE_TREE, p.JOIN_ONCE_PARENTS),
            ('9c5c031d24aadc5d704160bb5a5a65bff126c10c', 'dafa6aa8dce10cf396971329244aeb8ac36d4ed3',
             ('e459c9bec1dc6006eaad6df5f65111491c7b7572', '5e8808e6046fe435de82a51d8989811455307a19')))
        self.assertEqual(self.selected(p.JOIN_ONCE_M), self.original)
        with patch.object(p, 'amendment_content', wraps=p.amendment_content) as historical, \
             patch.object(p.authenticated, '_budgets', wraps=p.authenticated._budgets) as budgets:
            self.assertEqual(self.content(self.pure), self.good)
            self.assertEqual(self.content(self.pure), self.good)
            self.assertEqual(sum(call.args[-1] == 'join_once_delta_budget' for call in budgets.call_args_list), 2)
            historical.assert_called_once()
            self.bad_content(self.changed(PROCESS, (c.ROOT / PROCESS).read_bytes() + b'\n'))
            historical.assert_called_once()
        copy = self.verified_baseline(p.JOIN_ONCE_M, *self._baseline_args)
        copy.clear()
        self.assertEqual(self.verified_baseline(p.JOIN_ONCE_M, *self._baseline_args), self.original)
        with patch.object(self, '_baseline_select', side_effect=AssertionError('delegated')):
            for replacements, kwargs in (({}, {'profile': p.PROFILE_ID}), ({1: lambda: None}, {}),
                                         ({6: dict(c.RELEASE_DOCS, extra=('100644', 'blob', 'wrong'))}, {})):
                arguments = list(self._baseline_args)
                for index, value in replacements.items():
                    arguments[index] = value
                with self.assertRaisesRegex(AssertionError, 'delegated'):
                    self.verified_baseline(p.JOIN_ONCE_M, *arguments, **kwargs)
            with patch.dict(c.RELEASE_DOCS, {'extra': ('100644', 'blob', 'wrong')}), self.assertRaisesRegex(AssertionError, 'delegated'):
                self.verified_baseline(p.JOIN_ONCE_M, *self._baseline_args[:-1], c.RELEASE_DOCS)
        for command, replacement, error in ((('show', '-s', '--format=%P', p.JOIN_ONCE_M), b'\n', o.TopologyError),
                (('rev-parse', p.JOIN_ONCE_M + '^{tree}'), b'0' * 40 + b'\n', AssertionError)):
            def wrong(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(error):
                self.selected(self.pure, wrong)

    def test_direct_child_accepts_only_seventeen_reviewed_paths(self):
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(self.original), len(self.good), len(p.JOIN_ONCE_CAPS)), (1685, 1693, 17))
        self.assertEqual({path for path in self.good if self.good[path] != self.original.get(path)}, p.JOIN_ONCE_CAPS.keys())
        self.assertEqual(p.JOIN_ONCE_PINS.keys(), p.JOIN_ONCE_CAPS.keys() - {p.PROFILE})
        for path, row in p.JOIN_ONCE_PINS.items():
            data = inverse_warning_adapter(path, (c.ROOT / path).read_bytes())
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.bad_content(self.changed(path, data + b'\n'))
        path = PROCESS
        row = p.JOIN_ONCE_PINS[path]
        for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
            altered = list(row)
            altered[index] = value
            with patch.dict(p.JOIN_ONCE_PINS, {path: tuple(altered)}), self.assertRaises(AssertionError):
                self.content(self.pure)
        for pins in ({key: value for key, value in p.JOIN_ONCE_PINS.items() if key != path},
                     p.JOIN_ONCE_PINS | {'unreviewed': row}):
            with patch.dict(p.JOIN_ONCE_PINS, pins, clear=True), self.assertRaises(AssertionError):
                self.content(self.pure)

    def test_ordered_feature_merge_requires_entire_child_tree(self):
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(p.join_once_topology(self.feature, self.repo, c._git, p.R), ('nonrelease', self.feature, self.pure))
        for entries in (self.original, self.changed(PROCESS, self.frozen(PROCESS)), self.good | c.RELEASE_DOCS):
            self.bad_content(entries, [p.JOIN_ONCE_M, self.pure])

    def test_release_overlay_requires_exact_four_r_documents(self):
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual(len(c.RELEASE_DOCS), 4)
        self.assertEqual(p.R_DOCUMENTS, c.RELEASE_DOCS)
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_missing_reversed_extra_duplicate_nested_parents_reject(self):
        for parents in ([], [self.pure], [self.pure, p.JOIN_ONCE_M], [p.JOIN_ONCE_M, self.pure, p.R],
                        [p.JOIN_ONCE_M, p.JOIN_ONCE_M], [p.JOIN_ONCE_M, self.feature], [p.R],
                        [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release]):
            with self.subTest(parents=parents):
                self.rejects(parents)

    def test_unknown_same_tree_anchors_and_correction_chains_reject(self):
        impostor = self.commit([], self.original)
        correction = self.commit([self.pure], self.good)
        for parents in ([impostor], [impostor, self.pure], [correction], [p.JOIN_ONCE_M, correction],
                        ['e853c8b6e39e9f50d7e66aace96e690425f9a688'], ['c3fcfb1f2617d56f8f395317a18d93884d551789']):
            self.rejects(parents)
        with self.assertRaises(o.TopologyError):
            p.join_once_topology(self.pure, self.repo, c._git, impostor)

    def test_four_runtime_blobs_and_shared_regressions_match_reviewed_donor(self):
        for path, blob in DONOR_BLOBS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(c._blob(data), blob)
            self.assertEqual(data, c._git('cat-file', 'blob', blob, root=self.repo))
        text = (c.ROOT / REGRESSIONS).read_text()
        self.assertEqual(set(re.findall(r'async fn (\w+)\(', text)), set(FAILED) | {CONTROL})
        self.assertEqual(text.count('assert!(!done.stdout && !done.stderr && !done.stdin);'), 4)
        self.assertIn('stderr.abort();', text)
        self.assertIn('panic!("intentional reader task panic")', text)

    def test_mechanical_supervisor_extraction_preserves_tokens_and_outcomes(self):
        old = self.frozen(PROCESS).decode()
        current = (c.ROOT / PROCESS).read_text()
        supervisor = (c.ROOT / SUPERVISOR).read_text().replace('pub(super) ', '')
        start = segment(old, '    pub async fn start(', '\n}\n\nimpl Default')
        self.assertEqual(start, segment(supervisor, '    pub async fn start(', '\n}\n\nasync fn read_bounded'))
        for begin, end in (('async fn read_bounded', '\nasync fn join_io'), ('fn take_stream', '\nfn uncertain_outcome')):
            expected = segment(old, begin, end)
            actual = segment(supervisor, begin, end if 'read_bounded' in begin else '\n#[cfg(test)]')
            self.assertEqual(actual, expected)
        tests = segment(old, '#[cfg(test)]\nmod tests {', '\n#[cfg(all(test, unix))]')
        self.assertEqual(textwrap.dedent(tests.split('{\n', 1)[1].rsplit('}\n', 1)[0]),
                         (c.ROOT / 'services/local-agent/src/process_tests.rs').read_text())
        restored = old.replace('\n\n' + start, '', 1)
        removed = segment(old, 'async fn read_bounded', 'fn uncertain_outcome')
        restored = restored.replace(removed, '', 1).replace(tests, '#[cfg(test)]\n#[path = "process_tests.rs"]\nmod tests;\n', 1)
        restored += '\n#[path = "process_supervisor.rs"]\nmod supervisor;\n#[cfg(all(test, unix))]\nuse supervisor::confirm_group_exit;\n#[cfg(test)]\nuse supervisor::{read_bounded, take_stream};\n'
        self.assertEqual(current, restored)
        self.assertIn('const READER_WAIT: Duration = Duration::from_secs(2);', current)

    def test_workflow_inverse_allows_only_m_base_tree_and_branch(self):
        current = (c.ROOT / WORKFLOW).read_text()
        added = [line for line in current.splitlines(True) if 'EXPECTED_BASELINE_TREE' in line]
        self.assertEqual(len(added), 2)
        donor = current.replace(added[0], '', 1).replace(added[1], '', 1)
        donor = c._replace_once(donor, "'fix/process-io-join-once-m9c5c031'", "'fix/process-io-join-once'")
        donor = c._replace_once(donor, f'BASELINE = "{p.JOIN_ONCE_M}"', 'BASELINE = "c3fcfb1f2617d56f8f395317a18d93884d551789"')
        before = donor.replace("'fix/process-io-join-once'", "'fix/process-io-join-once-m9c5c031'", 1)
        before = before.replace('BASELINE = "c3fcfb1f2617d56f8f395317a18d93884d551789"', f'BASELINE = "{p.JOIN_ONCE_M}"', 1)
        self.assertEqual(len(current.splitlines()), 243)
        self.assertEqual(current.replace(added[0], '', 1).replace(added[1], '', 1), before)
        self.assertEqual(added, [f'          EXPECTED_BASELINE_TREE = "{p.JOIN_ONCE_TREE}"\n',
            '              assert git("rev-parse", BASELINE + "^{tree}").decode().strip() == EXPECTED_BASELINE_TREE\n'])
        self.assertEqual(c._blob(donor.encode()), DONOR_WORKFLOW)
        self.assertEqual(hashlib.sha256(donor.encode()).hexdigest(), DONOR_WORKFLOW_SHA256)

    def test_baseline_overlay_preserves_exact_m_production_prefix(self):
        script = workflow_scripts()[0]
        namespace = {'__name__': 'synthetic_fixture'}
        exec(compile(script, WORKFLOW, 'exec'), namespace)
        production = self.frozen(PROCESS)
        self.assertEqual(c._blob(production), '47bf41f30f67724a873953313f2f31bcdff439a9')
        def exercise(fault=None):
            # Execute real workflow orchestration with synthetic Git/build responses only.
            with tempfile.TemporaryDirectory() as folder, chdir(folder), patch.dict(os.environ, RUNNER_TEMP=folder):
                root, worktree = Path(folder), Path(folder) / 'process-io-baseline'
                (root / REGRESSIONS).parent.mkdir(parents=True)
                (root / REGRESSIONS).write_bytes((c.ROOT / REGRESSIONS).read_bytes())
                (root / 'evidence').mkdir()
                def run(command, **kwargs):
                    if command[0] == 'git':
                        self.assertEqual(command, ['git', '-c', 'core.autocrlf=false', 'worktree', 'add',
                                                  '--detach', str(worktree), p.JOIN_ONCE_M])
                        (worktree / PROCESS).parent.mkdir(parents=True)
                        (worktree / PROCESS).write_bytes(b'wrong' if fault == 'prefix' else production)
                        return None
                    if '--no-run' in command:
                        code, output = (1 if fault == 'build' else 0), b'synthetic build\n'
                    elif '--list' in command:
                        names = FAILED if fault == 'inventory' else (*FAILED, CONTROL)
                        code, output = 0, ''.join(f'process::io_join_tests::{name}: test\n' for name in names).encode()
                    else:
                        code, output = (0 if fault == 'exit' else 101), witness().encode()
                    return namespace['subprocess'].CompletedProcess(command, code, output)
                def git(command, **kwargs):
                    anchor = 'wrong' if fault == 'commit' else p.JOIN_ONCE_M
                    answers = {('rev-parse', 'HEAD'): anchor if kwargs['cwd'] == worktree else self.pure,
                        ('rev-parse', p.JOIN_ONCE_M + '^{tree}'): 'wrong' if fault == 'tree' else p.JOIN_ONCE_TREE,
                        ('rev-parse', p.JOIN_ONCE_M + ':' + PROCESS): 'wrong' if fault == 'blob' else namespace['EXPECTED_BLOB'],
                        ('hash-object', PROCESS): namespace['EXPECTED_BLOB'],
                        ('diff', '--name-only'): 'extra' if fault == 'paths' else PROCESS,
                        ('ls-files', '--others', '--exclude-standard'): 'extra' if fault == 'untracked' else REGRESSIONS}
                    if command[1] == 'show':
                        return production
                    value = answers[tuple(command[1:])] + '\n'
                    return value if kwargs.get('text') else value.encode()
                with patch('subprocess.run', side_effect=run), patch('subprocess.check_output', side_effect=git), \
                     patch('sys.stdout', new=io.StringIO()):
                    namespace['main']()
                proof = json.loads((root / 'evidence/baseline-proof.json').read_text())
                self.assertEqual((worktree / PROCESS).read_bytes()[:len(production)], production)
                self.assertEqual((worktree / REGRESSIONS).read_bytes(), (root / REGRESSIONS).read_bytes())
                self.assertEqual(proof['production_prefix_sha256'], hashlib.sha256(production).hexdigest())
                return proof
        proof = exercise()
        self.assertEqual([item['exit_code'] for item in proof['commands']], [0, 0, 101])
        for fault in ('commit', 'prefix', 'tree', 'blob', 'paths', 'untracked', 'build', 'inventory', 'exit'):
            with self.subTest(fault=fault), self.assertRaises(AssertionError):
                exercise(fault)

    def test_native_witness_and_candidate_parsers_reject_false_evidence(self):
        baseline, candidate = workflow_scripts()
        scope = {'__name__': 'synthetic_fixture'}
        exec(compile(baseline, WORKFLOW, 'exec'), scope)
        validate = scope['validate_witness']
        good = witness()
        # The filtered baseline subset is intentional; build/provenance checks are in main.
        validate(good)
        for altered in (good.replace(FAILED[0], 'unknown'), good.replace(FAILED[0], FAILED[1]),
                        good.replace(f'test process::io_join_tests::{CONTROL} ... ok\n', ''),
                        good.replace('running 4 tests', 'running 3 tests'), good + f'test x::io_join_tests::{CONTROL} ... ok\n',
                        good.replace('JoinHandle polled after completion', 'unrelated panic'),
                        good.replace('0 ignored', '1 ignored'), good.replace('1 passed; 3 failed', '2 passed; 2 failed'),
                        good + 'could not compile', good + 'error[E0000]'):
            with self.assertRaises(AssertionError):
                validate(altered)
        names = ['process::io_join_tests::' + name for name in (*FAILED, CONTROL)] + ['ordinary']
        def parse(inventory, results=None, summary=None, hashes=None):
            results = results if results is not None else [(name, 'ok') for name in inventory]
            summary = summary or f'test result: ok. {len(results)} passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'
            with tempfile.TemporaryDirectory() as folder, chdir(folder):
                Path('evidence').mkdir()
                Path(REGRESSIONS).parent.mkdir(parents=True)
                data = (c.ROOT / REGRESSIONS).read_bytes()
                Path(REGRESSIONS).write_bytes(data)
                digest = hashlib.sha256(data).hexdigest()
                files = {'test-inventory.txt': ''.join(name + ': test\n' for name in inventory),
                    'tests.txt': ''.join(f'test {name} ... {state}\n' for name, state in results) + summary,
                    'baseline-proof.json': json.dumps(hashes or dict(test_sha256=digest, candidate_test_sha256=digest)),
                    'source-commit.txt': 'synthetic-unverified', 'source-tree.txt': 'synthetic-unverified'}
                for name, text in files.items():
                    (Path('evidence') / name).write_text(text)
                with patch('subprocess.check_output', return_value=''):
                    exec(compile(candidate, WORKFLOW, 'exec'), {})
                return json.loads(Path('evidence/candidate-test-counts.json').read_text())
        self.assertEqual(parse(names)['passed'], 5)
        # These accepted limitations require the separate actual native artifact audit.
        self.assertEqual(parse(names + ['ordinary'])['passed'], 6)
        self.assertEqual(parse(names + ['unknown'])['passed'], 6)
        self.assertEqual(parse(names)['source_commit'], 'synthetic-unverified')
        self.assertEqual(parse(names)['source_tree'], 'synthetic-unverified')
        for inventory, kwargs in ((names[1:], {}), (names + [names[0]], {}),
                (names, {'results': [(name, 'ok') for name in names[:-1]]}),
                (names, {'results': [(name, 'ok') for name in names] + [('extra', 'ok')]}),
                (names, {'results': [(name if name != 'ordinary' else 'different', 'ok') for name in names]}),
                (names, {'results': [(name, 'ignored' if name == 'ordinary' else 'ok') for name in names]}),
                (names, {'results': [(name, 'FAILED' if name == 'ordinary' else 'ok') for name in names]}),
                (names, {'summary': 'test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 1 filtered out;\n'}),
                (names, {'summary': 'test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n'}),
                (names, {'hashes': dict(test_sha256='wrong', candidate_test_sha256='wrong')})):
            with self.assertRaises(AssertionError):
                parse(inventory, **kwargs)

    def test_missing_extra_rename_mode_symlink_gitlink_binary_reject(self):
        for path in p.JOIN_ONCE_CAPS:
            missing = {key: value for key, value in self.good.items() if key != path}
            changes = [missing, missing | {path + '.renamed': self.good[path]}]
            changes += [self.good | {path: entry} for entry in (('100755', *self.good[path][1:]),
                ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', p.JOIN_ONCE_M))]
            changes.append(self.changed(path, b'\0binary\xff'))
            for entries in changes:
                with self.subTest(path=path):
                    self.bad_content(entries)
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))

    def test_individual_and_aggregate_budgets_reject(self):
        self.assertEqual((p.JOIN_ONCE_DELTA_LIMIT, sum(cap[1] for cap in p.JOIN_ONCE_CAPS.values())), (2400, 2485))
        for path, (_, delta) in p.JOIN_ONCE_CAPS.items():
            lines = len(inverse_warning_adapter(path, (c.ROOT / path).read_bytes()).splitlines())
            with patch.dict(p.JOIN_ONCE_CAPS, {path: (lines - 1, delta)}), self.assertRaises(AssertionError):
                self.content(self.pure)
            def oversized(*args, root):
                return f'{delta + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', p.JOIN_ONCE_M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.content(self.pure, oversized)
        def aggregate(*args, root):
            if args[:5] == ('diff', '--numstat', p.JOIN_ONCE_M, self.pure, '--'):
                return f'{p.JOIN_ONCE_CAPS[args[5]][1]}\t0\t{args[5]}\n'.encode()
            return c._git(*args, root=root)
        with self.assertRaisesRegex(AssertionError, 'delta_budget'):
            self.content(self.pure, aggregate)
        for row in (b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', b'1\t0\t' + path.encode() + b'\nextra'):
            def malformed(*args, root):
                return row if args == ('diff', '--numstat', p.JOIN_ONCE_M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError):
                self.content(self.pure, malformed)

    def test_current_adapter_inverses_recover_complete_m_bytes(self):
        self.assertEqual(set(adapters.JOIN_ONCE_FRAGMENTS), set(pt.FRAGMENTS))
        for path, fragments in adapters.JOIN_ONCE_FRAGMENTS.items():
            data = (c.ROOT / path).read_bytes()
            self.assertEqual(adapters.inverse_join_once_adapter(path, data), self.frozen(path))
            for before, _ in fragments:
                for replacement in ('', before * 2):
                    with self.assertRaises(AssertionError):
                        adapters.inverse_join_once_adapter(path, data.replace(before.encode(), replacement.encode(), 1))
            with self.assertRaises(AssertionError):
                adapters.inverse_join_once_adapter(path, data + b'# unrelated\n')

    def test_publication_helper_extraction_preserves_twenty_tests_and_assertions(self):
        current, helper = (c.ROOT / p.TESTS).read_bytes(), inverse_warning_adapter(p.JOIN_ONCE_HELPER, (c.ROOT / p.JOIN_ONCE_HELPER).read_bytes())
        frozen = self.frozen(p.TESTS)
        self.assertEqual(adapters.publication_tests_inverse(current, helper), frozen)
        self.assertEqual(helper.decode().split(adapters.EXTRACT_BEGIN, 1)[1].split(adapters.EXTRACT_END, 1)[0],
                         ''.join(frozen.decode().splitlines(True)[18:85]))
        old, new = at.methods(frozen), at.methods(current)
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual(sum(name.startswith('test_') for name in new), 20)
        restored = at.methods(adapters.publication_tests_inverse(current, helper))
        for name, node in old.items():
            assertions = lambda tree: Counter(ast.dump(call) for call in ast.walk(tree) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
            self.assertEqual(assertions(node), assertions(restored[name]))
        for changed_current, changed_helper in ((current + b'# drift\n', helper), (current, helper.replace(b'assert ', b'# assert ', 1))):
            with self.assertRaises(AssertionError):
                adapters.publication_tests_inverse(changed_current, changed_helper)

    def test_historical_profiles_pins_shapes_and_ownership_bytes_are_immutable(self):
        for path in (*at.PROFILE_DIGESTS, p.authenticated.PROFILE, p.OWNERSHIP_TESTS, p.CONTRACTS, p.CHECKS):
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path))
        current = inverse_warning_adapter(p.PROFILE, (c.ROOT / p.PROFILE).read_bytes())
        self.assertEqual(adapters.publication_profile_inverse(current), self.frozen(p.PROFILE))
        with self.assertRaises(AssertionError):
            adapters.publication_profile_inverse(current + b'# drift\n')
        for ref in (p.desktop.X, p.nginx.F, p.two_hop.F, p.authenticated.M, p.N, p.JOIN_ONCE_M):
            self.assertEqual(self.selected(ref), c._entries(ref, self.repo))
        self.assertEqual(p.PROFILE_ID, 'engineering/issue88-publication-core-composition-v1')

    def test_selected_content_failure_is_terminal_without_fallback(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(p, 'join_once_content', side_effect=error('terminal content')), \
                 patch.object(p, 'publication_content') as old, self.assertRaisesRegex(error, 'terminal content'):
                self.selected(self.pure)
            old.assert_not_called()
            with patch.object(p, 'amendment_content', side_effect=error('terminal historical')), \
                 patch.object(p, 'join_once_content') as new, self.assertRaisesRegex(error, 'terminal historical'):
                self.selected(p.JOIN_ONCE_M)
            new.assert_not_called()

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

    def test_exact_283_plus_20_inventory_loaded_and_executed(self):
        expected = [prefix + '.' + name for prefix, names in c.EXPECTED_GROUPS.items() for name in names.split()]
        added = [prefix + '.' + name for prefix, names in p.JOIN_ONCE_GROUPS.items() for name in names.split()]
        pt.inventory_ids(expected, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        pt.inventory_ids(added, 20, 'ef9d08cd31005ec4a23fb4a3326d1257997815846641ff694ec2bfe7b2f21535')
        pt.inventory_ids([name for name in expected if name not in added])
        loaded = [case.id() for case in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), 'rc_pretag*_tests.py'))]
        self.assertEqual(Counter(loaded), Counter(expected))
        for ids in (expected[:-1], expected + [expected[0]], expected[:-1] + ['unknown']):
            with self.assertRaises(AssertionError):
                pt.inventory_ids(ids, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
        old, new = ast.parse(self.frozen(p.COMPOSITION)), ast.parse((c.ROOT / p.COMPOSITION).read_bytes())
        for name in ('run_inventory', 'InventoryResult', '_flatten', '_git', '_entries', '_profile_fixture'):
            find = lambda tree: ast.dump(next(node for node in tree.body if getattr(node, 'name', '') == name))
            self.assertEqual(find(old), find(new))
        # The unchanged strict runner authenticates actual executed IDs after all 303 finish.

    def test_protected_scope_versions_runtime_and_old452_are_unchanged(self):
        protected = {path for path in self.original if path not in p.JOIN_ONCE_CAPS}
        self.assertTrue(all(self.good[path] == self.original[path] for path in protected))
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in
                ('README.md', 'design.md', 'requirements.md', 'tasks.md',
                 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py',
                 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        for path in held:
            self.assertFalse((c.ROOT / path).exists() or (c.ROOT / path).is_symlink(), path)
        runtime = {path for path in protected if path.startswith('services/local-agent/')}
        self.assertEqual(len(runtime), 45)
        for path in runtime | {p.CONTRACTS, p.CHECKS, 'package.json', 'package-lock.json', 'src-tauri/Cargo.toml',
                              'src-tauri/Cargo.lock', 'src-tauri/tauri.conf.json', 'scripts/rc_release_policy.py',
                              'scripts/rc_release_eligibility.py', '.github/workflows/rc-pretag-evidence.yml'}:
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)
        # Reuse the frozen module inventory and its exact old452 digest without executing it here.
        tree = ast.parse(self.frozen(p.TESTS))
        method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                      and node.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
        modules = ast.literal_eval(method.body[0].value.func.value).split()
        ids = [case.id() for module in modules for case in c._flatten(unittest.defaultTestLoader.loadTestsFromName(module))
               if case.id().split('.', 1)[0] == module]
        pt.inventory_ids(ids, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')


if __name__ == '__main__':
    unittest.main()
