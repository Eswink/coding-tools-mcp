"""Strict J composition and frozen named fixture inventory; never a release gate."""
import ast
from contextlib import contextmanager
import shutil
import tempfile
from unittest.mock import patch
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import unittest
from rc_consumer_io import read_bytes
import rc_pretag_ownership_profile as ownership
import rc_pretag_desktop_profile as desktop
import rc_pretag_nginx_profile as nginx
import rc_pretag_two_hop_profile as two_hop
import rc_pretag_authenticated_two_hop_profile as authenticated_two_hop
import rc_pretag_publication_profile as publication
from verify_glib_backport import ARCHIVE_SHA
from rc_pretag_collect_fixtures import owned_git_scope, git_environment

ROOT = Path(__file__).resolve().parents[1]
BASE = '1694fe8c771e57c72c89ca096693b03404c24b84'
BASE_TREE = '8fa2331a170e265b1c5dfbb45180113aefeed6b0'
ORIGIN = '70aa9e3644fc50861992717c6c879d8c7261539f'
RELEASE = 'e2e011f7f2a3a1df838bbd588106205b999db610'
RELEASE_TREE = 'c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3'
RELEASE_DOCS = dict(zip(('docs/releases/' + name for name in
    ('next-rc-ledger.md', 'next-rc-notes.md', 'source-acceptance-audit.md', 'verification-v0.6.0-rc.4.md')),
    (('100644', 'blob', blob) for blob in ('f44a9b8abf0dac1e35cea0e23b36750b297d0704',
     'c5cffd2d3dba5ce70f4dbe41167cf9f699c807d3', '7dd36643c0931fd5c8b6e2c2de8152b2f4c0366c',
     'de0f6f90e184bb41af7bb714ad425e51f0a9d819'))))
ADOPTED = {
    'scripts/rc_pretag_types.py': ('2b937d1be26274e8862d35849262385384b63b43', 'd79e667808b305f89bae92d5e3df6766d05f3f77380b75098b6dd0f1a65b19d6'),
    'scripts/rc_pretag_evidence.py': ('a366e08bbad9f2635136dca8c92ad785b7a7e972', 'aded3cfebe8dfc44b17035213721b245d0bcb85c0c55ef06853a1fbf97de0056'),
    'scripts/rc_release_policy.py': ('58b8aa42255c440ee5bdbe46fe67965e5acb1724', 'f63705d96312f1d1b4dd31394ad6c4d450748ce7a65fbb3c90c6b676d0755c9f'),
    'scripts/rc_release_eligibility.py': ('d9e5023678b43b740baa6fcaf406ac1210a2c3d5', '82085f17e982efdadbe736e2fd35e114ce03f43e866f1ef4892bd61f94a6349c'),
    'scripts/rc_pretag_fixtures.py': ('be1d5fd9dd1dcf099fa0cddf118a34421f42d104', '8487aded0a9a5335a744fa38b22e5b3f64399fadd1849d653f3b9e34430fbac8'),
    'scripts/rc_pretag_identity_tests.py': ('48500a3d6a3ba5a6e874dc91700cc21840d6e0b6', '2395ff0ae309a9f4468d66ec69d08f8b42955146b0810eb95fa779f0db952cd8'),
    'scripts/rc_pretag_policy_tests.py': ('004133bd73c7ebfa243d79ba42a4565e7b945cd5', 'b78d9f65a1256b8ff819f0b2a7832302e835f429cb8d4c0bac9b1a3728a4c5b0'),
    '.github/workflows/rc-pretag-contract-checks.yml': ('445daa1c6a8f81aab7393e527a04af1819c31851', '287fde1aa2641d4d7ee40060d4116365af7aa8b8ee38ed9140cba576f3532db9'),
}
NARROW = {
    'scripts/rc_consumer_snapshot.py': ('f33981f53405cc1b1624b1468d0a4ca89cd51a29', '30b7d314ffacb6a3961a5c935c75cffb44d0674acd491c3759cdf84c19fa2b99'),
    'scripts/rc_artifact_consumer.py': ('7a68b8d36e685186c5303e4654edf0a3183b1b5d', 'c169efb3645587562e682b5bcfbaee8acfa9d4bf01ac4941f3f9fe0c7ac36b7b'),
}
BUDGET = dict(zip(('scripts/rc_pretag_' + suffix + '.py' for suffix in
    ('admission', 'collect', 'collection_result', 'collect_fixtures', 'admission_tests', 'collection_tests', 'composition_tests')),
    (280, 200, 195, 300, 450, 430, 470)))
LIVE, CHECKS = ('.github/workflows/rc-pretag-evidence' + suffix + '.yml' for suffix in ('', '-checks'))
BUDGET.update({LIVE: 100, CHECKS: 120})
BUDGET.update({'docs/specs/issue88-pretag-adopter/' + name + '.md': 100 for name in ('requirements', 'design', 'tasks')})
ALLOWED = set(ADOPTED) | set(NARROW) | set(BUDGET)
# These pins must change meaningfully with reviewed execution-envelope changes.
LIVE_PIN = ('9dd8100fd6611358efaacaf98b573ee250de65f2', 'a58f14ba9c278b240362eee53d25a3894cff45c022477a693927f673c1032370')
CHECKS_PIN = ('dec0de32a339b88ab1f5a39ddaf226d75dacfbe1', 'fce45846190ee075ddba4b6198956711472ce85626f5b7c8480f1139800c9352')
PURE_VALIDATION = (
    '    _inputs(expectations)\n',
    "    need(source == expectations['source_sha'], 'candidate_source_mismatch')\n",
    "    need(gate.positive(expected_repository_id), 'repository_identity_mismatch')\n",
)
SNAPSHOT_EXTRA = (
    "    return _select_source_runs_for_identity(api, candidate['source_sha'],\n"
    "                                            candidate['consumer']['repository_id'], expectations)\n\n\n"
    'def _select_source_runs_for_identity(api, source, expected_repository_id, expectations):\n'
    '    # Deliberate duplicate pure checks: direct pretag callers cannot bypass inputs.\n' + ''.join(PURE_VALIDATION))
BYTE_BODY = (
    '    path = transport.download_artifact_zip(api, metadata, download, opener=opener)\n'
    '    snapshot.revalidate_download(api, selection, metadata)\n'
    '    archive.extract_bounded_zip(path, bundle, [name for name, _, _ in payloads(producer.version)])\n'
    '    archive.verify_checksum_inventory(bundle)\n'
    "    archive.extract_bounded_cloud_tar(bundle.path / 'cloud-linux-amd64.tar.gz', cloud)\n"
    "    content = contracts.verify_consumed_bundle(root, bundle.path, cloud.path, producer, selection['integration'])\n"
    '    download.files(); bundle.files(); cloud.files()\n')
BYTE_HELPER = ('def _verify_bundle_bytes(root, api, selection, metadata, producer, download, bundle, cloud, *, opener=None):\n'
               + BYTE_BODY + '    return content\n\n\n')
BYTE_CALL = ('                content = _verify_bundle_bytes(root, api, selection, metadata, producer,\n'
             '                                               download, bundle, cloud, opener=opener)\n')


def _git(*args, root=ROOT, env=None):
    assert args[0] in {'rev-parse', 'rev-list', 'ls-tree', 'ls-files', 'diff', 'show', 'cat-file'}
    root = Path(root).resolve(); gitdir = root / '.git'
    assert gitdir.is_dir() and not gitdir.is_symlink()
    assert not (gitdir / 'commondir').exists() and not (gitdir / 'objects/info/alternates').exists()
    extra = ('--no-ext-diff', '--no-textconv') if args[0] in {'diff', 'show'} else ()
    return subprocess.check_output(['git', '--git-dir=' + str(gitdir), '--work-tree=' + str(root),
        '-c', 'core.quotepath=false', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
        args[0], *extra, *args[1:]], cwd=root, env=git_environment(env), timeout=30)


def _entries(ref, root=ROOT):
    return {path: tuple(header.split()) for header, path in
            (row.split('\t', 1) for row in _git('ls-tree', '-rz', ref, root=root).decode().split('\0') if row)}


def _index_entries(raw):
    result = {}
    for row in raw.decode().split('\0'):
        if not row: continue
        header, path = row.split('\t', 1)
        mode, blob, stage = header.split()
        assert stage == '0' and path not in result
        result[path] = (mode, 'blob', blob)
    return result


def _feature_profile(ref, root=ROOT):
    assert _git('rev-parse', BASE + '^{tree}', root=root).decode().strip() == BASE_TREE
    assert BASE in _git('rev-list', '--first-parent', ref, root=root).decode().splitlines()
    original, actual = _entries(BASE, root), _entries(ref, root)
    assert original.keys() <= actual.keys() and actual.keys() - original.keys() <= ALLOWED
    assert all(actual[path] == entry for path, entry in original.items() if path not in NARROW)
    assert ALLOWED <= actual.keys() and all(value[:2] == ('100644', 'blob') for value in actual.values())
    data = {path: _git('cat-file', 'blob', actual[path][2], root=root) for path in ALLOWED}
    for path, pin in {**ADOPTED, LIVE: LIVE_PIN, CHECKS: CHECKS_PIN}.items():
        assert (_blob(data[path]), hashlib.sha256(data[path]).hexdigest()) == pin
    for path, reconstruct in zip(NARROW, (_reconstruct_snapshot, _reconstruct_consumer)):
        original_data = _git('cat-file', 'blob', original[path][2], root=root)
        assert (_blob(original_data), hashlib.sha256(original_data).hexdigest()) == NARROW[path]
        assert reconstruct(data[path].decode()).encode() == original_data
    assert all(len(data[path].splitlines()) <= cap for path, cap in BUDGET.items())
    narrow = [sum(map(int, _git('diff', '--numstat', BASE, ref, '--', path, root=root).split()[:2])) for path in NARROW]
    assert all(count <= 35 for count in narrow)
    assert sum(len(data[path].splitlines()) for path in BUDGET) + 1436 + sum(narrow) <= 3966
    assert sum(len(data['scripts/rc_pretag_' + name + '.py'].splitlines()) for name in
               ('admission', 'collect', 'collection_result')) <= 640
    return actual


def _selected_profile(ref='HEAD', root=ROOT):
    parents = _git('show', '-s', '--format=%P', ref, root=root).decode().split()
    if parents and parents[0] == RELEASE:
        assert len(parents) == 2
        expected = _feature_profile(parents[1], root)
        assert _git('rev-parse', RELEASE + '^{tree}', root=root).decode().strip() == RELEASE_TREE
        assert all(_entries(RELEASE, root)[path] == entry for path, entry in RELEASE_DOCS.items())
        expected.update(RELEASE_DOCS)
        assert _entries(ref, root) == expected
        return expected
    return _feature_profile(ref, root)


@contextmanager
def _profile_fixture():
    candidate = ownership.M  # Original J/adopter tests retain their exact historical M tree.
    temp = tempfile.TemporaryDirectory()
    with temp:
        repo = Path(temp.name) / 'source'; repo.mkdir()
        def write(*args, data=None):
            with owned_git_scope(temp):
                return subprocess.check_output(['git', '-c', 'user.name=Fixture', '-c',
                    'user.email=fixture@example.invalid', *args], cwd=repo,
                    env=git_environment(), input=data, timeout=30).decode().strip()
        write('init', '-q')
        shutil.copytree(ROOT / '.git/objects', repo / '.git/objects', dirs_exist_ok=True)
        def commit(parents, entries):
            write('read-tree', '--empty')
            write('update-index', '-z', '--index-info', data=''.join(
                f'{mode} {blob}\t{path}\0' for path, (mode, kind, blob) in sorted(entries.items())).encode())
            # Literal headers preserve duplicate parents for isolated grammar negatives.
            body = ('tree ' + write('write-tree') + '\n' + ''.join('parent ' + p + '\n' for p in parents)
                    + 'author Fixture <fixture@example.invalid> 1 +0000\n'
                    + 'committer Fixture <fixture@example.invalid> 1 +0000\n\nOwned composition fixture\n')
            return write('hash-object', '-t', 'commit', '-w', '--stdin', data=body.encode())
        yield repo, candidate, commit, lambda data: write('hash-object', '-w', '--stdin', data=data)



def _blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def _replace_once(text, before, after):
    if text.count(before) != 1:
        raise AssertionError('reviewed extraction text missing or duplicated')
    return text.replace(before, after, 1)


def _reconstruct_snapshot(text):
    text = _replace_once(text, SNAPSHOT_EXTRA, '')
    text = _replace_once(text, '_repository(repository, expected_repository_id)',
                         "_repository(repository, candidate['consumer']['repository_id'])")
    return _replace_once(text, '    observed = _ObservedAPI(api, repository_id)\n    result',
                         "    observed = _ObservedAPI(api, repository_id)\n    source = candidate['source_sha']\n    result")


def _reconstruct_consumer(text):
    text = _replace_once(text, BYTE_HELPER, '')
    return _replace_once(text, BYTE_CALL, ''.join('            ' + line for line in BYTE_BODY.splitlines(True)))


class CompositionTests(unittest.TestCase):
    def test_exact_tracked_tree_modes_and_scope(self):
        expected = publication.selected_profile(
            'HEAD', ROOT, _git, _entries, _feature_profile, RELEASE, RELEASE_TREE, RELEASE_DOCS)
        index = _index_entries(_git('ls-files', '--stage', '-z'))
        self.assertEqual(index, expected)
        self.assertEqual(len(ALLOWED), 22)
        for path, (mode, kind, blob) in expected.items():
            with self.subTest(path=path):
                actual = ROOT / path
                self.assertTrue(stat.S_ISREG(actual.lstat().st_mode))
                self.assertEqual(actual.stat().st_mode & 0o111, int(mode, 8) & 0o111)
                self.assertEqual(_blob(actual.read_bytes()), blob)

    def test_adopted_contracts_are_byte_identical(self):
        for path, (blob, sha256) in ADOPTED.items():
            data = (ROOT / path).read_bytes()
            self.assertEqual((_blob(data), hashlib.sha256(data).hexdigest()), (blob, sha256), path)
        self.assertEqual(sum(len((ROOT / path).read_bytes().splitlines()) for path in ADOPTED), 1436)

    def test_snapshot_inverse_reconstructs_pinned_j(self):
        path = 'scripts/rc_consumer_snapshot.py'
        original = _git('show', BASE + ':' + path)
        self.assertEqual((_blob(original), hashlib.sha256(original).hexdigest()), NARROW[path])
        self.assertEqual(_reconstruct_snapshot((ROOT / path).read_bytes().decode('utf-8')).encode(), original)

    def test_consumer_inverse_reconstructs_pinned_j(self):
        path = 'scripts/rc_artifact_consumer.py'
        original = _git('show', BASE + ':' + path)
        self.assertEqual((_blob(original), hashlib.sha256(original).hexdigest()), NARROW[path])
        self.assertEqual(_reconstruct_consumer((ROOT / path).read_bytes().decode('utf-8')).encode(), original)

    def test_extraction_mutations_do_not_reconstruct_j(self):
        text = (ROOT / 'scripts/rc_consumer_snapshot.py').read_bytes().decode('utf-8')
        for statement in PURE_VALIDATION:
            with self.assertRaises(AssertionError):
                _reconstruct_snapshot(_replace_once(text, SNAPSHOT_EXTRA, SNAPSHOT_EXTRA.replace(statement, '')))
        text = (ROOT / 'scripts/rc_artifact_consumer.py').read_bytes().decode('utf-8')
        for statement in BYTE_BODY.splitlines(True):
            with self.assertRaises(AssertionError):
                _reconstruct_consumer(_replace_once(text, BYTE_HELPER, BYTE_HELPER.replace(statement, '')))

    def test_original_transport_asts_and_supervisor(self):
        tree = ast.parse((ROOT / 'scripts/rc_consumer_transport_tests.py').read_bytes().decode('utf-8'))
        klass = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'TransportTests')
        methods = [node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')]
        self.assertEqual(len(methods), 12)
        digest = hashlib.sha256('\n'.join(ast.dump(node, include_attributes=False) for node in methods).encode()).hexdigest()
        self.assertEqual(digest, '9a204c5631142c9b2298b3eeaabdeba1e9148b19398984e736c96305a4e744e2')
        self.assertEqual(_blob((ROOT / 'scripts/rc_consumer_transport_supervisor_tests.py').read_bytes()),
                         'e45608f7ae523c25ea5d12cd4d24cbd56a3f1c12')

    def test_finite_review_budgets(self):
        frozen = {path: _git('show', ownership.M + ':' + path) for path in BUDGET}
        for path, cap in BUDGET.items():
            self.assertLessEqual(len(frozen[path].splitlines()), cap, path)
        self.assertLessEqual(sum(len(frozen['scripts/rc_pretag_' + name + '.py'].splitlines())
                                 for name in ('admission', 'collect', 'collection_result')), 640)
        narrow_count = 0
        for path in NARROW:
            added, removed, _ = _git('diff', '--numstat', BASE, ownership.M, '--', path).decode().split()
            self.assertLessEqual(int(added) + int(removed), 35, path)
            narrow_count += int(added) + int(removed)
        self.assertLessEqual(sum(len(frozen[p].splitlines()) for p in BUDGET) + 1436 + narrow_count, 3966)

    def test_live_workflow_exact_execution_envelope(self):
        data = (ROOT / LIVE).read_bytes()
        self.assertEqual((_blob(data), hashlib.sha256(data).hexdigest()), LIVE_PIN)
        text = data.decode()
        for required in ('branches:\n      - release/rc-pretag-*', 'timeout-minutes: 15', 'persist-credentials: false',
                         'ref: ${{ github.sha }}', 'fetch-depth: 0', "python-version: '3.12'",
                         'permissions:\n  contents: read\n  actions: read', 'GH_TOKEN: ${{ github.token }}', 'python -B -I -S scripts/rc_pretag_collect.py',
                         "if: ${{ success() && !cancelled() && steps.collect.outcome == 'success' }}",
                         'path: ${{ steps.collect.outputs.receipt_path }}', 'if-no-files-found: error', 'retention-days: 7',
                         'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
                         'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065',
                         'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',
                         'runs-on: ubuntu-24.04', 'name: Collect pre-tag FINAL evidence (release remains blocked)'):
            self.assertIn(required, text)
        for forbidden in ('workflow_dispatch:', 'pull_request:', 'pull_request_target:', 'continue-on-error:', 'always()',
                          'write', 'download-artifact', 'environment:', 'secrets.', 'gh ', 'curl ', '|| true'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('GH_TOKEN:'), 1)

    def test_fixture_workflow_triggers_and_no_duplicate_regressions(self):
        data = _git('show', ownership.M + ':' + CHECKS)
        self.assertEqual((_blob(data), hashlib.sha256(data).hexdigest()), CHECKS_PIN)
        current = (ROOT / CHECKS).read_bytes()
        self.assertEqual(ownership.pin(current), ownership.NEW_PINS[CHECKS])
        self.assertIn("'" + ownership.BRANCH + "'", current.decode())
        for path in ownership.FILTERS:
            self.assertEqual(current.decode().count("'" + path + "'"), 2, path)
        text = data.decode()
        self.assertIn("branches: ['feat/rc-final-artifact-consumer-pretag-1694fe8c', 'feat/rc-final-artifact-consumer-128']", text)
        self.assertEqual(text.count('branches:'), 1)
        self.assertIn('pull_request:', text)
        for path in ('scripts/rc_pretag*', 'scripts/rc_release_policy.py', 'scripts/rc_release_eligibility.py',
                     'scripts/rc_consumer_snapshot.py', 'scripts/rc_artifact_consumer.py',
                     'docs/specs/issue88-pretag-adopter/**', '.github/workflows/rc-pretag-contract-checks.yml', LIVE, CHECKS):
            self.assertEqual(text.count("'" + path + "'"), 2, path)
        self.assertIn('python -B scripts/rc_pretag_composition_tests.py', text)
        for forbidden in ('rc_consumer_test_runner', 'release_tag_gate_tests', 'workflow_dispatch:', 'GH_TOKEN',
                          'secrets.', 'github.token', 'download-artifact', 'upload-artifact', 'rc_pretag_collect.py',
                          'gh ', 'always()', 'continue-on-error:'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(text.count('timeout-minutes: 15'), 1)
        preserved = (ROOT / '.github/workflows/rc-artifact-consumer-checks.yml').read_bytes().decode('utf-8')
        self.assertEqual(preserved.count("'scripts/rc_*'"), 2)
        self.assertIn("'feat/rc-final-artifact-consumer-*'", preserved)

    def test_pure_and_exact_pr89_profiles_accept(self):
        with _profile_fixture() as (repo, candidate, commit, blob):
            original = _feature_profile(candidate, repo)
            merged = commit([BASE, candidate], original)
            self.assertEqual(_selected_profile(merged, repo), original)
            synthetic = commit([RELEASE, merged], original | RELEASE_DOCS)
            self.assertEqual(_selected_profile(synthetic, repo), original | RELEASE_DOCS)

    def test_synthetic_parent_shape_rejects_unknown_reversed_extra_nested(self):
        with _profile_fixture() as (repo, candidate, commit, blob):
            entries = _feature_profile(candidate, repo) | RELEASE_DOCS
            synthetic = commit([RELEASE, candidate], entries)
            for parents in ([], [candidate], [candidate, RELEASE], [BASE, candidate],
                            [RELEASE, candidate, BASE], [RELEASE, synthetic]):
                with self.subTest(parents=parents), self.assertRaises(AssertionError):
                    _selected_profile(commit(parents, entries), repo)

    def test_candidate_requires_j_first_parent_and_pure_profile(self):
        with _profile_fixture() as (repo, candidate, commit, blob):
            entries = _feature_profile(candidate, repo)
            invalid = commit([RELEASE, candidate], entries)
            with self.assertRaises(AssertionError):
                _selected_profile(commit([RELEASE, invalid], entries | RELEASE_DOCS), repo)

    def test_synthetic_overlay_rejects_doc_mode_path_and_deletion_mutations(self):
        with _profile_fixture() as (repo, candidate, commit, blob):
            expected = _feature_profile(candidate, repo) | RELEASE_DOCS
            bad = blob(b'Unreviewed documentation mutation\n')
            for path in [*RELEASE_DOCS, 'scripts/rc_consumer_io.py', 'unreviewed-extra.txt']:
                for change in (None, ('100644', 'blob', bad), ('100755', 'blob', bad)):
                    mutated = dict(expected)
                    if change is None: mutated.pop(path, None)
                    else: mutated[path] = change
                    if mutated == expected: continue
                    with self.subTest(path=path, change=change), self.assertRaises(AssertionError):
                        _selected_profile(commit([RELEASE, candidate], mutated), repo)

    def test_pure_profile_preserves_exact_j_source_and_docs(self):
        with _profile_fixture() as (repo, candidate, commit, blob):
            original = _feature_profile(candidate, repo)
            for path in [*RELEASE_DOCS, 'scripts/rc_consumer_io.py']:
                mutated = dict(original); mutated[path] = ('100644', 'blob', blob(b'Changed protected source\n'))
                with self.subTest(path=path), self.assertRaises(AssertionError):
                    _feature_profile(commit([candidate], mutated), repo)

        clean = b'100644 ' + b'a' * 40 + b' 0\tfixture\0'
        self.assertEqual(_index_entries(clean), {'fixture': ('100644', 'blob', 'a' * 40)})
        for raw in (clean.replace(b' 0\t', b' 1\t'), clean + clean,
                    clean.replace(b' 0\t', b' 2\t') + clean.replace(b' 0\t', b' 3\t')):
            with self.subTest(index=raw), self.assertRaises(AssertionError): _index_entries(raw)

    def test_source_reader_rejects_ambient_git_redirection(self):
        expected = _git('rev-parse', 'HEAD')
        with tempfile.TemporaryDirectory() as raw:
            hostile = dict(GIT_DIR=raw, GIT_WORK_TREE=raw, GIT_INDEX_FILE=raw + '/index',
                GIT_COMMON_DIR=raw, GIT_OBJECT_DIRECTORY=raw, GIT_ALTERNATE_OBJECT_DIRECTORIES=raw,
                GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.worktree', GIT_CONFIG_VALUE_0=raw)
            with patch.dict(os.environ, hostile):
                self.assertEqual(_git('rev-parse', 'HEAD'), expected)
                self.assertEqual(_git('rev-parse', 'HEAD', env=hostile), expected)
            self.assertEqual(list(Path(raw).iterdir()), [])
            with self.assertRaises(AssertionError): _git('init')

    def test_no_new_publication_or_alternate_validator(self):
        forbidden = {'make_asset_plan', 'write_sanitized_provenance', 'PlanCommit', 'verify_consumed_bundle',
                     'download_artifact_zip', 'extract_bounded_zip', 'extract_bounded_cloud_tar',
                     'post', 'put', 'patch', 'delete', 'urlopen', 'Popen', 'system', 'create_release', 'dispatch'}
        for suffix in ('admission', 'collect', 'collection_result'):
            tree = ast.parse((ROOT / ('scripts/rc_pretag_' + suffix + '.py')).read_bytes().decode('utf-8'))
            calls = {getattr(node.func, 'id', getattr(node.func, 'attr', '')) for node in ast.walk(tree) if isinstance(node, ast.Call)}
            self.assertFalse(calls & forbidden, (suffix, calls & forbidden))


# Reviewed frozen IDs: original118 + six composition + six fixture-Git isolation.
EXPECTED_GROUPS = {
    'rc_pretag_ownership_tests.FixtureMetadataTests': (
        'test_metadata_snapshot_and_disappearance_boundaries test_metadata_links_and_owned_identity_remain_rejected '
        'test_automatic_maintenance_controls_are_fixed_child_only'),
    'rc_pretag_ownership_tests.OwnershipCompositionTests': (
        'test_exact_m_ownership_overlay_accepts_only_reviewed_delta test_ownership_io_drift_and_reverted_handoff_reject '
        'test_proof_bodies_live_pins_and_fixture_identity_reject_drift test_overlay_modes_paths_deletions_and_extra_sources_reject '
        'test_original_adopter_and_ownership_budgets_are_separate test_pure_candidate_chain_anchors_at_m_with_fixed_limit '
        'test_exact_fix_merge_has_m_then_pure_candidate test_exact_release_overlay_has_r_then_validated_nonrelease '
        'test_invalid_pure_topologies_reject_with_valid_trees test_invalid_fix_merges_reject_with_valid_trees '
        'test_invalid_release_overlays_reject_with_valid_trees '),
    'rc_pretag_ownership_tests.OwnershipFailureBoundaryTests': (
        'test_actual_directory_fault_blocks_collection_observation test_actual_handoff_walk_fault_preserves_uncertainty '
        'test_actual_constructor_fault_blocks_collect_and_emit '),
    'rc_pretag_admission_tests.AdmissionTests': ('test_absent_tag_still_rejected_by_unchanged_posttag_consumer test_active_job_requires_exact_unique_identity_attempt_and_status test_actual_ref_requires_exact_version_and_alphanumeric_nonce test_all_invocation_environment_fields_are_mandatory '
        'test_all_six_version_slots_reject_independently test_annotated_and_foreign_local_tags_reject_without_repair test_current_and_exact_attempt_runs_must_be_live_and_matching test_discovery_values_cannot_replace_strict_fixed_selection '
        'test_environment_identity_types_and_event_are_not_coerced test_existing_lightweight_tag_passes_posttag_and_blocks_pretag test_final_source_fence_rechecks_after_artifact_metadata test_fixed_admission_and_final_branch_change_reject_freshness '
        'test_frozen_own_run_and_attempt_are_not_replaced_during_fence test_gateway_alignment_rejects_committed_wrong_version test_head_mismatch_rejects_before_live_reads test_j_supported_integration_branch_can_differ_from_final '
        'test_known_remote_tag_collision_and_malformed_200_reject test_known_visibility_error_close_failure_is_terminal test_local_tag_command_failure_cannot_be_missing test_manifest_schema_and_version_are_real_gate_checks '
        'test_missing_reviewed_manifest_is_not_generated test_non403404_and_untyped_tag_failures_are_terminal test_own_updated_at_is_not_frozen_like_completed_producer test_real_clean_six_slot_reviewed_source_without_tag '
        'test_repository_ref_commit_tree_and_workflow_live_identity test_runtime_is_exact_linux_cpython312 test_shared_selector_direct_inputs_reject_before_network test_tag_cancellation_cannot_become_unknown_visibility '
        'test_tracked_untracked_and_ignored_source_reject_before_api test_typed_403_404_remain_unknown_only_after_close test_unreviewed_commit_is_not_covered_by_frozen_manifest test_visibility_change_cannot_promote_unknown_to_absence '
        'test_workflow_missing_or_symlink_is_not_committed_regular_identity '),
    'rc_pretag_collection_tests.CollectionTests': ('test_all_payload_descriptors_close_before_result_factory test_corrupt_actual_zip_stops_before_parser test_post_content_fences_reject_mutation_without_reselection test_real_current_pipeline_yields_only_bounded_blocked_observation '
        'test_shared_pipeline_failure_edges_stop_in_exact_order '),
    'rc_pretag_collection_tests.FailureTests': ('test_closed_failure_schema_and_sticky_cleanup_uncertainty test_exact_success_and_failure_caps_include_newline test_interrupt_timeout_and_unknown_codes_never_claim_cleanup test_saved_receipt_plan_or_success_dictionary_cannot_be_encoded '),
    'rc_pretag_collection_tests.OutputLifecycleTests': ('test_anchored_handoff_rejects_symlink_hardlink_outside_missing test_cleanup_uncertainty_survives_later_close_and_report_errors test_cli_failures_and_cancellation_emit_only_sanitized_nonzero test_cli_token_popped_before_every_git_and_child_and_released '
        'test_freeform_fields_never_cross_allowlist test_handoff_write_flush_fsync_close_failure_is_terminal test_mutated_raw_and_non_record_output_are_rejected test_numeric_boolean_nonfinite_and_content_authority_rejected '
        'test_private_single_file_closed_before_handoff test_report_exclusive_nofollow_and_owner_reject test_report_mode_hardlink_inode_and_root_replacement_reject test_report_write_flush_fsync_close_readback_and_root_close_fail '
        'test_handoff_consumes_close_authority_once_and_bounds_full_line '),
    'rc_pretag_composition_tests.CompositionTests': ('test_adopted_contracts_are_byte_identical test_consumer_inverse_reconstructs_pinned_j test_exact_tracked_tree_modes_and_scope test_extraction_mutations_do_not_reconstruct_j '
        'test_finite_review_budgets test_fixture_workflow_triggers_and_no_duplicate_regressions test_live_workflow_exact_execution_envelope test_no_new_publication_or_alternate_validator '
        'test_original_transport_asts_and_supervisor test_snapshot_inverse_reconstructs_pinned_j '
        'test_pure_and_exact_pr89_profiles_accept test_synthetic_parent_shape_rejects_unknown_reversed_extra_nested '
        'test_candidate_requires_j_first_parent_and_pure_profile test_synthetic_overlay_rejects_doc_mode_path_and_deletion_mutations '
        'test_pure_profile_preserves_exact_j_source_and_docs test_source_reader_rejects_ambient_git_redirection '),
    'rc_pretag_admission_tests.FixtureGitIsolationTests': ('test_fixture_git_environment_inherited_explicit_and_empty '
        'test_fixture_git_launch_surfaces_use_owned_cwd test_fixture_git_sentinel_repository_unchanged '
        'test_fixture_git_context_escapes_reject_before_launch test_fixture_git_lifetime_nested_roots_and_restoration '
        'test_fixture_git_preserves_credential_and_non_git_observers '),
    'rc_pretag_identity_tests.PreTagIdentityTests': ('test_all_invocation_integer_fields_reject_boolean_float_string test_artifact_source_current_attempt_job_and_outer_digest_binding test_bounded_json_bytes_depth_arrays_strings test_candidate_and_empty_full_receipts_roundtrip '
        'test_candidate_does_not_accept_tag_objects_or_bypass_modes test_candidate_invocation_source_tree_version_binding test_clean_six_versions_gateway_and_manifest_fields test_consumer_and_integration_attempt3_remain_supported '
        'test_consumer_push_is_not_dispatch test_every_candidate_field_required_no_extra_keys test_every_selected_job_source_attempt_id_and_time_binding test_exact_four_payload_inventory_and_no_paths '
        'test_final_attempt1_and_push_candidate_only test_immutable_nested_records test_json_duplicate_keys_nonfinite_and_malformed_utf8 test_missing_spoofed_or_foreign_workflow_identity '
        'test_nested_unknown_fields_and_non_integer_schema test_only_canonical_numbered_rc_versions test_pretag_branch_binds_version_nonce_and_actual_shape test_raw_audit_findings_retained_and_counts_strict '
        'test_receipt_cannot_claim_collection_success_or_finalization test_receipt_selected_source_and_role_bound test_remote_absence_needs_observed_visibility_but_stays_unverified test_selected_runs_current_attempt_newest_job_inventory '
        'test_sha_tree_canonical_lowercase_and_length test_source_exact_repository_and_numeric_types test_structural_original_text_and_false_flags_preserved '),
    'rc_pretag_identity_tests.PreTagReviewIdentityTests': ('test_actual_integration_pr_ref_and_event_shapes_are_bound test_overlong_json_integer_has_fixed_error_without_raw_parser_text '),
    'rc_pretag_policy_tests.PreTagPolicyTests': ('test_all_passing_caller_claims_never_authenticate_or_approve test_complete_ledger_mapping_including_later_and_deferred test_copied_fixed_inventories_match_unchanged_producer_contracts test_draft_visibility_and_review_do_not_follow_scope_label '
        'test_each_failed_unknown_and_skipped_row_blocks test_each_gate_missing_permission_or_visibility_blocks test_each_required_row_missing_blocks_explicitly test_empty_inventory_blocks_every_required_row '
        'test_every_gate_wrong_source_and_tree_fails test_fixture_workflow_least_privilege_fixed_actions_and_no_live_collector test_no_forged_eligibility_approval_status_or_inventory test_policy_rows_have_full_permission_identity_freshness_map '
        'test_pretag_invocation_and_selected_source_binding test_review_freeform_approval_string_is_not_a_receipt test_run_current_attempt_binding_and_positive_consumer_attempt3 test_runtime_contract_modules_have_no_io_or_execution_entrypoint '
        'test_stale_review_head_or_postmerge_new_sha_fails test_unknown_gate_and_duplicate_row_rejected '),
    'rc_pretag_policy_tests.PreTagRefinementTests': ('test_rc_zero_matches_existing_canonical_version_contract test_stale_review_source_cannot_hide_behind_matching_invocation test_tag_absence_map_names_exact_read_and_explicit_blocked_receipt '),
    'rc_pretag_policy_tests.PreTagReviewCorrectionTests': ('test_hosted_floor_matches_all_current_reviewed_fixtures test_issue88_is_explicit_later_scope_without_circular_pretag_run test_negative_and_pending_review_claims_retain_explicit_outcomes '),
}


assert not (EXPECTED_GROUPS.keys() & desktop.EXPECTED_GROUPS.keys())
EXPECTED_GROUPS.update(desktop.EXPECTED_GROUPS)
assert not (EXPECTED_GROUPS.keys() & nginx.EXPECTED_GROUPS.keys())
EXPECTED_GROUPS.update(nginx.EXPECTED_GROUPS)
assert not (EXPECTED_GROUPS.keys() & two_hop.EXPECTED_GROUPS.keys())
EXPECTED_GROUPS.update(two_hop.EXPECTED_GROUPS)
assert not (EXPECTED_GROUPS.keys() & authenticated_two_hop.EXPECTED_GROUPS.keys())
EXPECTED_GROUPS.update(authenticated_two_hop.EXPECTED_GROUPS)
assert not (EXPECTED_GROUPS.keys() & publication.EXPECTED_GROUPS.keys())
EXPECTED_GROUPS.update(publication.EXPECTED_GROUPS)


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


class InventoryResult(unittest.TextTestResult):
    def startTest(self, test):
        if not hasattr(self, 'executed_ids'):
            self.executed_ids = []
        self.executed_ids.append(test.id())
        super().startTest(test)


def run_inventory():
    filename = os.environ.get('RC_CONSUMER_TEST_GLIB_ARCHIVE', '')
    if not filename or hashlib.sha256(read_bytes(Path(filename), 1024**2)).hexdigest() != ARCHIVE_SHA:
        print('required checksum-pinned official source fixture unavailable')
        return 1
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'scripts'), pattern='rc_pretag*_tests.py')
    loaded = [test.id() for test in _flatten(suite)]
    expected = [prefix + '.' + name for prefix, names in EXPECTED_GROUPS.items() for name in names.split()]
    if Counter(loaded) != Counter(expected) or len(set(loaded)) != len(loaded):
        print(json.dumps(dict(error='frozen_inventory_mismatch', missing=sorted(set(expected) - set(loaded)),
                              unexpected=sorted(set(loaded) - set(expected)))))
        return 1
    result = unittest.TextTestRunner(verbosity=2, resultclass=InventoryResult).run(suite)
    executed = getattr(result, 'executed_ids', [])
    print(json.dumps(dict(loaded_ids=loaded, executed_ids=executed, loaded=len(loaded), executed=result.testsRun)))
    return 0 if (result.wasSuccessful() and not result.skipped and not result.expectedFailures and not result.unexpectedSuccesses
                 and Counter(executed) == Counter(loaded) and result.testsRun == len(loaded)) else 1


if __name__ == '__main__':
    raise SystemExit(run_inventory())
