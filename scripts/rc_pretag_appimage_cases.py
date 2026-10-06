"""Exact AppImage admission proofs; hermetic fixtures are not native build evidence."""
import ast
from collections import Counter
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import rc_pretag_composition_tests as c
import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p
import rc_pretag_publication_adapters as adapters
import rc_pretag_publication_tests as pt
import rc_pretag_appimage_profile as a

HELPER_CLASS = 'appimage_tools_tests.AppImageToolsTests'
HELPER_DIGEST = 'a69845799bf8c310a3dbd05221ef8d366c92b54e8331815219c44554d682f62d'
WARNING_CLASS = 'rc_pretag_snapshot_warning_cases.SnapshotWarningCompositionTests'
WARNING_DIGEST = '94cd89ce8d62e001f8ec0e256dd031462cdbf8c34ed8edb06dd7189b52c42e75'
WORKFLOW_PIN = ('330804dd3f7dab3ea6911f4ac8ad7757c62fb22b', '737e1daada388d708732349ef3d3b66f11615d10260f8136a69ed81373f4c8de')
# These exact insertions are frozen with the amended workflow before source admission.
WORKFLOW_FRAGMENTS = (
    ('          ref: ${{ github.sha }}\n          fetch-depth: 0\n          persist-credentials: false\n', '          ref: ${{ github.sha }}\n          persist-credentials: false\n'),
    ('          # BEGIN PINNED APPIMAGE CASES\n          python -B scripts/appimage_tools_tests.py\n          python -B scripts/rc_pretag_appimage_cases.py\n          python -B scripts/rc_pretag_snapshot_warning_cases.py\n          # END PINNED APPIMAGE CASES\n', ''),
    ('          # BEGIN PINNED APPIMAGE PREPARATION\n          target_directory=$(cargo metadata --offline --no-deps --format-version 1 --manifest-path src-tauri/Cargo.toml | python -c \'import json,sys; print(json.load(sys.stdin)["target_directory"])\')\n          export LDAI_RUNTIME_FILE="$RUNNER_TEMP/appimage-originals/runtime-x86_64"\n          python -B scripts/appimage_tools.py prepare --root "$GITHUB_WORKSPACE" --target-directory "$target_directory" \\\n            --directory "$RUNNER_TEMP/appimage-originals" --source "$GITHUB_SHA" --output evidence/appimage-tools-prepared.json\n          python -B scripts/appimage_tools.py verify --root "$GITHUB_WORKSPACE" --target-directory "$target_directory" \\\n            --directory "$RUNNER_TEMP/appimage-originals" --source "$GITHUB_SHA" --phase before --output evidence/appimage-tools-before.json\n          # END PINNED APPIMAGE PREPARATION\n', ''),
    ('          # BEGIN PINNED APPIMAGE POSTCHECK\n          python -B scripts/appimage_tools.py verify --root "$GITHUB_WORKSPACE" --target-directory "$target_directory" \\\n            --directory "$RUNNER_TEMP/appimage-originals" --source "$GITHUB_SHA" --phase after --output evidence/appimage-tools-after.json\n          # END PINNED APPIMAGE POSTCHECK\n', ''),
)


def workflow_inverse(data):
    text = data.decode()
    for before, after in WORKFLOW_FRAGMENTS:
        text = c._replace_once(text, before, after)
    restored = text.encode()
    assert o.pin(restored) == WORKFLOW_PIN, 'complete M workflow inverse'
    assert (len(restored), len(restored.splitlines())) == (11020, 218)
    return restored


def ids(name):
    return [test.id() for test in c._flatten(unittest.defaultTestLoader.loadTestsFromName(name))]


def old_inventory():
    strict = [case.id() for case in c._flatten(unittest.defaultTestLoader.discover(str(c.ROOT / 'scripts'), 'rc_pretag*_tests.py'))]
    pt.inventory_ids(strict, 303, '0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125')
    method = next(node for node in ast.walk(ast.parse((c.ROOT / p.TESTS).read_bytes())) if isinstance(node, ast.FunctionDef)
                  and node.name == 'test_protected_source_versions_gates_workflows_and_old_452_are_unchanged')
    modules = ast.literal_eval(method.body[0].value.func.value).split()
    consumer = [name for module in modules for name in ids(module) if name.split('.', 1)[0] == module]
    pt.inventory_ids(consumer, 452, 'd01db4e6cd605c6636423e27c8c0409e90aba217cc0e6930474f59a24b57f372')
    warning = ids(WARNING_CLASS)
    pt.inventory_ids(warning, 20, WARNING_DIGEST)
    combined = strict + consumer + warning
    assert len(combined) == len(set(combined)) == 775
    return combined


def execution_valid(loaded, result):
    pt.inventory_ids(loaded, 20, a.DIGEST)
    assert Counter(loaded) == Counter(a.CLASS + '.' + name for name in a.NAMES)
    executed = getattr(result, 'executed_ids', [])
    pt.inventory_ids(executed, 20, a.DIGEST)
    return (result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
            and Counter(executed) == Counter(loaded) and result.testsRun == len(set(executed)) == 20)


class AppImageCompositionTests(unittest.TestCase):
    def setUp(self):
        from rc_pretag_linux_package_inverse import normalize
        self.repo, _, self.commit, self.blob = self.enterContext(c._profile_fixture())
        self.original = c._entries(a.M, self.repo)
        self.good = self.original | {path: ('100644', 'blob', self.blob(normalize(path, (c.ROOT / path).read_bytes()))) for path in a.CAPS}
        self.pure = self.commit([a.M], self.good)
        self.feature = self.commit([a.M, self.pure], self.good)
        self.overlay = self.good | c.RELEASE_DOCS
        self.release = self.commit([p.R, self.feature], self.overlay)
        self._baseline_select, self._baseline_cache = p.selected_profile, None
        self._baseline_args = (self.repo, c._git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, dict(c.RELEASE_DOCS))

    def frozen(self, path):
        return c._git('show', a.M + ':' + path, root=self.repo)

    def selected(self, ref, git=c._git):
        return p.selected_profile(ref, self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def verified_baseline(self, ref, root, git, entries, historical, release, release_tree, documents, **kwargs):
        arguments = (root, git, entries, historical, release, release_tree, documents)
        callbacks_match = all(actual is expected for actual, expected in zip(arguments[1:4], self._baseline_args[1:4]))
        if ref != a.M or kwargs or not callbacks_match or arguments != self._baseline_args:
            return self._baseline_select(ref, *arguments, **kwargs)
        if self._baseline_cache is None:
            self._baseline_cache = dict(self._baseline_select(ref, *arguments))
        return dict(self._baseline_cache)

    def content(self, ref, git=c._git):
        with patch.object(p, 'selected_profile', side_effect=self.verified_baseline):
            return a.content(ref, self.repo, git, c._entries, c._feature_profile, c.RELEASE, c.RELEASE_TREE, c.RELEASE_DOCS)

    def changed(self, path, data):
        return self.good | {path: ('100644', 'blob', self.blob(data))}

    def bad_content(self, entries, parents=None):
        ref = self.commit([a.M] if parents is None else parents, entries)
        a.topology(ref, self.repo, c._git, p.R)
        with self.assertRaises(AssertionError):
            self.selected(ref)  # Altered candidates always revalidate the full immutable history.

    def rejects(self, parents):
        ref = self.commit(parents, self.good)
        with self.assertRaises(o.TopologyError):
            a.topology(ref, self.repo, c._git, p.R)
        with patch.object(a, 'content') as content, self.assertRaises(o.TopologyError):
            self.selected(ref)
        content.assert_not_called()

    def test_exact_m_anchor_tree_parents_and_fresh_history(self):
        self.assertEqual((a.M, a.M_TREE, a.M_PARENTS), ('feeaf299df6c3729285c91511ece18e9984a2503',
            '81abcfdbe1bea9ab3a0baae252d4ad86db8b15c5', ('6edd4e6137a6947319183b3ac8801bfa608ac722', '851f3374871f6303b37ec7c7055936e6d74ecc1c')))
        self.assertEqual(self.selected(a.M), self.original)
        with patch.object(p, 'warning_content', wraps=p.warning_content) as historical:
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(self.selected(self.pure), self.good)
            self.assertEqual(historical.call_count, 2)
            self.bad_content(self.changed(a.HELPER, (c.ROOT / a.HELPER).read_bytes() + b'\n'))
            self.assertEqual(historical.call_count, 3)
        with patch.object(p, 'warning_content', side_effect=AssertionError('fresh history')), self.assertRaisesRegex(AssertionError, 'fresh history'):
            self.selected(self.pure)
        for command, replacement, error in ((('show', '-s', '--format=%P', a.M), b'\n', o.TopologyError),
                (('rev-parse', a.M + '^{tree}'), b'0' * 40 + b'\n', AssertionError)):
            def wrong(*args, root):
                return replacement if args == command else c._git(*args, root=root)
            with self.assertRaises(error):
                self.selected(self.pure, wrong)
        self.assertEqual(self.content(self.pure), self.good)
        copy = self.verified_baseline(a.M, *self._baseline_args); copy.clear()
        self.assertEqual(self.verified_baseline(a.M, *self._baseline_args), self.original)
        with patch.object(self, '_baseline_select', side_effect=AssertionError('delegated')):
            for ref, replacements, kwargs in (('HEAD', {}, {}), (a.M, {0: Path('/wrong')}, {}),
                    (a.M, {1: lambda: None}, {}), (a.M, {2: lambda: None}, {}), (a.M, {3: lambda: None}, {}),
                    (a.M, {6: {}}, {}), (a.M, {}, {'profile': p.PROFILE_ID})):
                arguments = list(self._baseline_args)
                for index, value in replacements.items(): arguments[index] = value
                with self.assertRaisesRegex(AssertionError, 'delegated'):
                    self.verified_baseline(ref, *arguments, **kwargs)
            with patch.dict(c.RELEASE_DOCS, {'extra': ('100644', 'blob', 'wrong')}), self.assertRaisesRegex(AssertionError, 'delegated'):
                self.verified_baseline(a.M, *self._baseline_args[:-1], c.RELEASE_DOCS)

    def test_candidate_exact_eleven_paths_and_pins(self):
        from rc_pretag_linux_package_inverse import normalize
        self.assertEqual(self.selected(self.pure), self.good)
        self.assertEqual((len(self.original), len(self.good), len(a.CAPS)), (1698, 1705, 11))
        self.assertEqual({path for path in self.good if self.good[path] != self.original.get(path)}, a.CAPS.keys())
        self.assertEqual(a.SOURCE_PINS.keys(), a.CAPS.keys() - {a.PROFILE})
        self.assertEqual(len(a.CAPS.keys() - self.original.keys()), 7)
        for path, row in a.SOURCE_PINS.items():
            data = normalize(path, (c.ROOT / path).read_bytes())
            self.assertEqual(row, ('100644', *o.pin(data), len(data), len(data.splitlines())))
            self.bad_content(self.changed(path, data + b'\n'))

    def test_ordered_feature_merge_requires_entire_candidate_tree(self):
        self.assertEqual(self.selected(self.feature), self.good)
        self.assertEqual(a.topology(self.feature, self.repo, c._git, p.R), ('nonrelease', self.feature, self.pure))
        for entries in (self.original, self.changed(a.HELPER, b'changed\n'), self.overlay):
            self.bad_content(entries, [a.M, self.pure])

    def test_release_overlay_requires_exact_four_r_documents(self):
        self.assertEqual(self.selected(self.release), self.overlay)
        self.assertEqual((len(c.RELEASE_DOCS), p.R_DOCUMENTS), (4, c.RELEASE_DOCS))
        for path in c.RELEASE_DOCS:
            for entries in (self.overlay | {path: self.good[path]}, {k: v for k, v in self.overlay.items() if k != path},
                            self.overlay | {path: ('100755', *self.overlay[path][1:])}):
                self.bad_content(entries, [p.R, self.feature])
        self.bad_content(self.overlay | {'extra.md': ('100644', 'blob', self.blob(b'extra'))}, [p.R, self.feature])

    def test_missing_reversed_extra_duplicate_nested_parents_reject(self):
        for parents in ([], [self.pure], [self.pure, a.M], [a.M, self.pure, p.R], [a.M, a.M], [a.M, self.feature],
                        [p.R], [p.R, self.pure], [self.feature, p.R], [p.R, self.feature, self.pure], [p.R, self.release]):
            with self.subTest(parents=parents): self.rejects(parents)

    def test_unknown_same_tree_anchors_and_correction_chains_reject(self):
        impostor = self.commit([], self.original)
        correction = self.commit([self.pure], self.good)
        for parents in ([impostor], [impostor, self.pure], [correction], [a.M, correction],
                        ['0a18f3bcf562e32a1fd29477491a84a1bf0e6d0c'], ['86b5310000000000000000000000000000000000']):
            self.rejects(parents)
        with self.assertRaises(o.TopologyError): a.topology(self.pure, self.repo, c._git, impostor)

    def test_source_pins_sizes_modes_and_five_tools_are_exact(self):
        row = a.SOURCE_PINS[a.HELPER]
        for index, value in enumerate(('100755', '0' * 40, '0' * 64, row[3] + 1, row[4] + 1)):
            changed = list(row); changed[index] = value
            with patch.dict(a.SOURCE_PINS, {a.HELPER: tuple(changed)}), self.assertRaises(AssertionError): self.content(self.pure)
        for pins in ({k: v for k, v in a.SOURCE_PINS.items() if k != a.HELPER}, a.SOURCE_PINS | {'extra': row}):
            with patch.dict(a.SOURCE_PINS, pins, clear=True), self.assertRaises(AssertionError): self.content(self.pure)
        tree = ast.parse((c.ROOT / a.HELPER).read_bytes())
        constants = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                     and node.targets[0].id in {'TOOLS', 'NORMALIZED_SHA256', 'LAUNCHER', 'LAUNCHER_SIZE', 'LAUNCHER_SHA256'}}
        tools = constants['TOOLS']
        expected = (
            ('linuxdeploy-x86_64.AppImage', 13264064, 'e762bea85c8eb0d4b3508d46e5c1f037f717d0f9303ae3b4aafc8b04991fa1ef', 'https://github.com/tauri-apps/binary-releases/releases/download/linuxdeploy/linuxdeploy-x86_64.AppImage', 182515537, None, 'linuxdeploy-x86_64.AppImage'),
            ('linuxdeploy-plugin-appimage-x86_64.AppImage', 16488952, '49d6a17160675a6bd1781699aae6bdf7692d98552e02a3671d2183d10547842e', 'https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage', 602435573, None, 'linuxdeploy-plugin-appimage.AppImage'),
            ('runtime-x86_64', 944632, '156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074', 'https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64', 596078161, None, None),
            ('linuxdeploy-plugin-gtk.sh', 14622, '7804c9eef13e59bf2783aad9882ef9db8f3f3f9e8d631874b1d348d550a3693f', 'https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gtk/dda522bce37387f1b853d9095713bfaa924c8423/linuxdeploy-plugin-gtk.sh', None, 'dda522bce37387f1b853d9095713bfaa924c8423', 'linuxdeploy-plugin-gtk.sh'),
            ('linuxdeploy-plugin-gstreamer.sh', 4857, 'c107b49d84edbffc6ab226ed1007e0626a4f7aa2c3a36b7782bef62351d49e94', 'https://raw.githubusercontent.com/tauri-apps/linuxdeploy-plugin-gstreamer/2a2e67491c32995a3f279ad0ecbe77abd512b42a/linuxdeploy-plugin-gstreamer.sh', None, '2a2e67491c32995a3f279ad0ecbe77abd512b42a', 'linuxdeploy-plugin-gstreamer.sh'),
)
        self.assertEqual(tuple(tuple(row.get(key) for key in ('name', 'size', 'sha256', 'url', 'asset_id', 'commit', 'cache_name')) for row in tools), expected)
        self.assertEqual(sum(row['size'] for row in tools), 30717127)
        self.assertEqual([row['provenance'] for row in tools], ['first-observed; upstream API digest null',
            'upstream API SHA256', 'upstream API SHA256', 'observed immutable-commit bytes', 'observed immutable-commit bytes'])
        self.assertEqual(constants['NORMALIZED_SHA256'], '20eebde3c18ae2e44279bd624fc72482503aece216d5d77f10932235342f71c1')
        self.assertEqual((constants['LAUNCHER'], constants['LAUNCHER_SIZE'], constants['LAUNCHER_SHA256']),
            ('scripts/AppImage启动入口v3.sh', 1319, '726a50e47cdbc011f6eef6bcf655e1e2eec236f6750cadaff170a8f74c202c2c'))

    def test_helper_test_inventory_is_twenty_unique_ids(self):
        helper = ids(HELPER_CLASS)
        pt.inventory_ids(helper, 20, HELPER_DIGEST)
        self.assertEqual(len(helper), len(set(helper)))
        for invalid in (helper[:-1], helper + helper[:1], helper[:-1] + ['unknown']):
            with self.assertRaises(AssertionError): pt.inventory_ids(invalid, 20, HELPER_DIGEST)

    def test_workflow_inverse_preserves_all_original_gates_and_jobs(self):
        from rc_pretag_linux_package_inverse import normalize
        current = normalize(a.WORKFLOW, (c.ROOT / a.WORKFLOW).read_bytes())
        self.assertEqual(workflow_inverse(current), self.frozen(a.WORKFLOW))
        for before, _ in WORKFLOW_FRAGMENTS:
            for replacement in ('', before * 2):
                with self.assertRaises(AssertionError): workflow_inverse(current.replace(before.encode(), replacement.encode(), 1))
        for altered in (current + b'# drift\n', current.replace(b'contents: read', b'contents: write'),
                        current.replace(b'--no-fail-fast', b''), current.replace(b'ubuntu-24.04', b'ubuntu-22.04')):
            with self.assertRaises(AssertionError): workflow_inverse(altered)

    def test_workflow_runs_pinned_preparation_and_pre_post_checks(self):
        from rc_pretag_linux_package_inverse import normalize
        current = normalize(a.WORKFLOW, (c.ROOT / a.WORKFLOW).read_bytes()).decode()
        self.assertEqual(current.count('fetch-depth: 0'), 1)
        self.assertLess(current.index('fetch-depth: 0'), current.index('  installed:'))
        for command in ('python -B scripts/appimage_tools_tests.py', 'python -B scripts/rc_pretag_appimage_cases.py',
                        'python -B scripts/rc_pretag_snapshot_warning_cases.py'):
            self.assertEqual(current.count(command), 1)
            self.assertLess(current.index(command), current.index('id: regression'))
        package = current[current.index('        id: package_build'):current.index('        id: package_upload')]
        prepare = package.index('scripts/appimage_tools.py prepare')
        before = package.index('--phase before')
        build = package.index('npm run tauri -- build --config src-tauri/Ubuntu桌面v1.json --bundles deb,appimage -- --locked')
        after = package.index('--phase after')
        verify = package.index('scripts/AppImage入口配置v3.py --verify')
        self.assertTrue(prepare < before < build < after < verify)
        self.assertIn('export LDAI_RUNTIME_FILE=', package)
        self.assertIn("if: always() && steps.prerequisites.outcome == 'success'", package)
        self.assertEqual(current.split('  installed:', 1)[1], self.frozen(a.WORKFLOW).decode().split('  installed:', 1)[1])

    def test_missing_extra_rename_symlink_gitlink_binary_reject(self):
        for path in a.CAPS:
            missing = {key: value for key, value in self.good.items() if key != path}
            changes = [missing, missing | {path + '.renamed': self.good[path]}]
            changes += [self.good | {path: entry} for entry in (('100755', *self.good[path][1:]),
                ('120000', 'blob', self.blob(b'target')), ('160000', 'commit', a.M))]
            for entries in (*changes, self.changed(path, b'\0binary\xff')):
                with self.subTest(path=path): self.bad_content(entries)
        self.bad_content(self.changed('unreviewed-extra.py', b'extra\n'))

    def test_individual_and_aggregate_budgets_reject(self):
        from rc_pretag_linux_package_inverse import normalize
        self.assertEqual((a.DELTA_LIMIT, sum(cap[1] for cap in a.CAPS.values())), (2200, 2272))
        for path, (_, delta) in a.CAPS.items():
            lines = len(normalize(path, (c.ROOT / path).read_bytes()).splitlines())
            with patch.dict(a.CAPS, {path: (lines - 1, delta)}), self.assertRaises(AssertionError): self.content(self.pure)
            def oversized(*args, root):
                return f'{delta + 1}\t0\t{path}\n'.encode() if args == ('diff', '--numstat', a.M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.content(self.pure, oversized)
        def aggregate(*args, root):
            if args[:5] == ('diff', '--numstat', a.M, self.pure, '--'):
                return f'{a.CAPS[args[5]][1]}\t0\t{args[5]}\n'.encode()
            return c._git(*args, root=root)
        with self.assertRaisesRegex(AssertionError, 'appimage_delta_budget'): self.content(self.pure, aggregate)
        for row in (b'', b'-\t-\t' + path.encode(), b'1\t0', b'1\t0\twrong', b'1\t0\t' + path.encode() + b'\nextra'):
            def malformed(*args, root):
                return row if args == ('diff', '--numstat', a.M, self.pure, '--', path) else c._git(*args, root=root)
            with self.assertRaises(AssertionError): self.content(self.pure, malformed)

    def test_current_inverses_recover_complete_m_guards(self):
        from rc_pretag_linux_package_inverse import normalize
        self.assertEqual(a.BASE_PINS.keys(), {p.PROFILE, p.JOIN_ONCE_HELPER, a.WARNING})
        for path in a.BASE_PINS:
            current = normalize(path, (c.ROOT / path).read_bytes())
            frozen = self.frozen(path)
            self.assertEqual(a.inverse_appimage_adapter(path, current), frozen)
            self.assertEqual(a.inverse_appimage_adapter(path, frozen), frozen)
            self.assertEqual(o.pin(frozen), a.BASE_PINS[path])
        self.assertEqual(adapters.inverse_warning_adapter(p.PROFILE, normalize(p.PROFILE, (c.ROOT / p.PROFILE).read_bytes())),
                         c._git('show', p.WARNING_B + ':' + p.PROFILE, root=self.repo))
        self.assertEqual((c.ROOT / p.JOIN_ONCE_TESTS).read_bytes(), self.frozen(p.JOIN_ONCE_TESTS))

    def test_adapter_fragments_missing_duplicate_outside_edits_reject(self):
        from rc_pretag_linux_package_inverse import normalize
        for path, fragments in a.FRAGMENTS.items():
            current = normalize(path, (c.ROOT / path).read_bytes())
            for before, _ in fragments:
                for replacement in ('', before * 2):
                    changed = current.replace(before.encode(), replacement.encode(), 1)
                    if o.pin(changed) == a.BASE_PINS[path]:  # Exact M is an explicitly valid input.
                        self.assertEqual(a.inverse_appimage_adapter(path, changed), self.frozen(path))
                        changed += b'# incomplete adoption outside M\n'
                    with self.assertRaises(AssertionError): a.inverse_appimage_adapter(path, changed)
            for changed in (current + b'# outside\n', current.replace(b'assert ', b'# assert ', 1), b'\xff'):
                with self.assertRaises(AssertionError): a.inverse_appimage_adapter(path, changed)
        self.assertEqual(a.inverse_appimage_adapter('unknown', b'unchanged'), b'unchanged')

    def test_historical_profiles_pins_and_all_775_assertions_preserved(self):
        inventory = old_inventory()
        modules = {name.split('.', 1)[0] for name in inventory}
        for module in modules:
            path = 'scripts/' + module + '.py'
            current, frozen = (c.ROOT / path).read_bytes(), self.frozen(path)
            self.assertEqual(a.inverse_appimage_adapter(path, current), frozen, path)
            methods = lambda data: {node.name: node for node in ast.walk(ast.parse(data)) if isinstance(node, ast.FunctionDef)}
            old, new = methods(frozen), methods(current)
            self.assertEqual(old.keys(), new.keys(), path)
            assertions = lambda node: Counter(ast.dump(call) for call in ast.walk(node) if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute) and call.func.attr.startswith('assert'))
            for name in old: self.assertEqual(assertions(old[name]), assertions(new[name]), path + ':' + name)
        for path in ('scripts/rc_pretag_ownership_profile.py', 'scripts/rc_pretag_desktop_profile.py',
                     'scripts/rc_pretag_nginx_profile.py', 'scripts/rc_pretag_two_hop_profile.py', p.authenticated.PROFILE):
            self.assertEqual((c.ROOT / path).read_bytes(), self.frozen(path), path)
        self.assertEqual(p.PROFILE_ID, 'engineering/issue88-publication-core-composition-v1')

    def test_selected_content_failure_is_terminal_without_fallback(self):
        for error in (AssertionError, o.TopologyError):
            with patch.object(a, 'content', side_effect=error('terminal AppImage')), patch.object(p, 'warning_content') as old, \
                 self.assertRaisesRegex(error, 'terminal AppImage'): self.selected(self.pure)
            old.assert_not_called()
            with patch.object(p, 'warning_content', side_effect=error('terminal historical')), patch.object(a, 'content') as new, \
                 self.assertRaisesRegex(error, 'terminal historical'): self.selected(a.M)
            new.assert_not_called()
            with patch.object(a, 'content', return_value=self.good), patch.object(o, 'release_content', side_effect=error('terminal release')), \
                 patch.object(p, 'warning_content') as old, self.assertRaisesRegex(error, 'terminal release'): self.selected(self.release)
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
        with patch.dict(os.environ, hostile): self.assertEqual(self.selected('moving', moving), self.good)
        self.assertEqual(sum(any('moving' in arg for arg in args) for args in calls), 1)

    def test_old775_plus_new40_ids_are_exact_disjoint(self):
        old, helper, guard = old_inventory(), ids(HELPER_CLASS), ids(a.CLASS)
        pt.inventory_ids(helper, 20, HELPER_DIGEST)
        pt.inventory_ids(guard, 20, a.DIGEST)
        self.assertEqual(Counter(guard), Counter(a.CLASS + '.' + name for name in a.NAMES))
        self.assertEqual((len(old + helper + guard), len(set(old + helper + guard))), (815, 815))
        self.assertFalse(Path(a.CASES).match('rc_pretag*_tests.py'))

    def test_new_inventory_execution_rejects_skips_missing_duplicate_unknown(self):
        loaded = ids(a.CLASS)
        good = dict(executed_ids=loaded, testsRun=20, skipped=[], expectedFailures=[], unexpectedSuccesses=[], wasSuccessful=lambda: True)
        self.assertTrue(execution_valid(loaded, SimpleNamespace(**good)))
        for field, value in (('skipped', [('id', 'reason')]), ('expectedFailures', [('id', 'failure')]),
                             ('unexpectedSuccesses', ['id']), ('testsRun', 19), ('wasSuccessful', lambda: False)):
            self.assertFalse(execution_valid(loaded, SimpleNamespace(**(good | {field: value}))))
        for invalid in (loaded[:-1], loaded + loaded[:1], loaded[:-1] + ['unknown']):
            with self.assertRaises(AssertionError): execution_valid(invalid, SimpleNamespace(**good))
            with self.assertRaises(AssertionError): execution_valid(loaded, SimpleNamespace(**(good | {'executed_ids': invalid})))

    def test_protected_runtime_held_versions_and_release_scope_unchanged(self):
        from rc_pretag_linux_package_inverse import normalize
        self.assertTrue(all(self.good[path] == value for path, value in self.original.items() if path not in a.CAPS))
        held = {'docs/specs/rc-source-assembly-engineering/' + name for name in ('README.md', 'design.md', 'requirements.md',
                'tasks.md', 'subspecs/focused-validation/spec.md', 'subspecs/source-evidence/spec.md')}
        held |= {'scripts/rc_source_assembly.py', 'scripts/rc_source_assembly_dispatch_tests.py',
                 'scripts/rc_source_assembly_tests.py', 'tests/delivery/test_linux_lifecycle_wiring.py'}
        self.assertEqual(len(held), 10)
        self.assertFalse(held & self.good.keys())
        for path in held: self.assertFalse((c.ROOT / path).exists() or (c.ROOT / path).is_symlink(), path)
        for path in ('package.json', 'package-lock.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock', 'src-tauri/tauri.conf.json',
                     p.CHECKS, p.CONTRACTS, '.github/workflows/rc-pretag-evidence.yml', '.github/workflows/final-rc-packages.yml',
                     'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py', 'scripts/AppImage启动入口v3.sh',
                     'scripts/AppImage入口配置v3.py', 'services/local-agent/src/process.rs', 'src-tauri/src/workspace_snapshots/filesystem.rs'):
            self.assertEqual(normalize(path, (c.ROOT / path).read_bytes()), self.frozen(path), path)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName(a.CLASS)
    loaded = [test.id() for test in c._flatten(suite)]
    pt.inventory_ids(loaded, 20, a.DIGEST)
    assert Counter(loaded) == Counter(a.CLASS + '.' + name for name in a.NAMES)
    result = unittest.TextTestRunner(verbosity=2, resultclass=c.InventoryResult).run(suite)
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=getattr(result, 'executed_ids', []), loaded=len(loaded), executed=result.testsRun)))
    return 0 if execution_valid(loaded, result) else 1


if __name__ == '__main__':
    raise SystemExit(main())
