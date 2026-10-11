#!/usr/bin/env python3
"""Schema-2 manifest controls: regeneration, layer tree, no-downgrade. Needs the fixed backup objects locally."""
import copy, json, subprocess, sys, tempfile, unittest
from pathlib import Path
sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import windows_foundation_source_guard as guard
import gen_windows_foundation_source_manifest as gen

REPO = SCRIPTS.parent
MANIFEST = SCRIPTS / 'windows_foundation_source_manifest.json'


def git(*a, repo=REPO, data=None):
    return subprocess.run(['git', '-C', str(repo), *a], input=data, capture_output=True, check=True).stdout


class ManifestV2Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.head = git('rev-parse', 'HEAD').decode().strip()
        cls.tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
        cls.v1_bytes = git('cat-file', 'blob', guard.V1_MANIFEST_BLOB)
        cls.tmp = tempfile.TemporaryDirectory(prefix='manifest-v2-')
        cls.v1 = Path(cls.tmp.name) / 'v1.json'; cls.v1.write_bytes(cls.v1_bytes)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def write(self, value):
        p = Path(self.tmp.name) / 'm.json'; p.write_text(json.dumps(value), encoding='utf-8'); return p

    def test_committed_manifest_is_schema2_and_loads(self):
        m = guard.load_manifest(MANIFEST, repo=REPO, commit=self.head)
        self.assertEqual(m['schema'], 2)

    def test_regeneration_at_head_is_byte_identical(self):
        self.assertEqual(gen.generate(REPO, self.tree).encode('utf-8'), MANIFEST.read_bytes())

    def test_regeneration_twice_converges(self):
        self.assertEqual(gen.generate(REPO, self.tree), gen.generate(REPO, self.tree))

    def test_frozen_19bb2920_v1_reproduction_is_byte_identical(self):
        self.assertEqual(gen.generate(REPO, guard.TARGET, schema=1).encode('utf-8'), self.v1_bytes)

    def test_verify_layer_passes_on_head(self):
        r = guard.verify_layer(REPO, guard.load_manifest(MANIFEST, repo=REPO, commit=self.head))
        self.assertEqual(r['layer_tree'], self.tree)

    def test_tree_excluding_matches_documented_algorithm(self):
        with tempfile.TemporaryDirectory() as t:
            import os
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(t) / 'i'))
            run = lambda *a: subprocess.run(['git', '-C', str(REPO), *a], env=env, capture_output=True, check=True).stdout
            run('read-tree', self.tree); run('update-index', '--force-remove', '--', guard.MANIFEST_PATH)
            self.assertEqual(guard.tree_excluding(REPO, self.tree), run('write-tree').decode().strip())

    def test_excluded_manifest_change_does_not_move_layer_tree(self):
        blob = git('hash-object', '-w', '--stdin', data=b'{}\n').decode().strip()
        with tempfile.TemporaryDirectory() as t:
            import os
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(t) / 'i'))
            run = lambda *a: subprocess.run(['git', '-C', str(REPO), *a], env=env, capture_output=True, check=True).stdout
            run('read-tree', self.tree)
            run('update-index', '--cacheinfo', '100644,' + blob + ',' + guard.MANIFEST_PATH)
            other = run('write-tree').decode().strip()
        self.assertNotEqual(other, self.tree)
        self.assertEqual(guard.tree_excluding(REPO, other), guard.tree_excluding(REPO, self.tree))

    def test_non_excluded_change_fails_verify_layer(self):
        m = guard.load_manifest(MANIFEST, repo=REPO, commit=self.head)
        bad = copy.deepcopy(m); bad['layer_source'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'layer source rows differ'):
            guard.verify_layer(REPO, bad)
        bad = copy.deepcopy(m); bad['target_tree_excluding_manifest'] = '0' * 40
        with self.assertRaisesRegex(ValueError, 'layer tree excluding manifest differs'):
            guard.verify_layer(REPO, bad)

    def test_v1_manifest_on_this_layer_commit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'schema 2 required'):
            guard.load_manifest(self.v1, repo=REPO, commit=self.head)

    def test_v1_manifest_without_commit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'schema 2 required'):
            guard.load_manifest(self.v1)

    def test_v1_manifest_on_frozen_historical_commit_is_admitted(self):
        self.assertEqual(guard.load_manifest(self.v1, repo=REPO, commit=guard.V1_FROZEN_LAST)['schema'], 1)

    def test_v1_admission_requires_v1_blob_at_that_commit(self):
        self.assertFalse(guard.manifest_commit_is_v1_frozen(REPO, guard.BASE))
        self.assertFalse(guard.manifest_commit_is_v1_frozen(REPO, self.head))

    def test_v1_admission_is_ancestry_not_timestamp(self):
        # A v1-manifest commit backdated to 2020 but NOT an ancestor of 313c3a16 must be rejected.
        import os
        with tempfile.TemporaryDirectory() as t:
            clone = Path(t) / 'c'
            git('clone', '-q', '--shared', '--no-checkout', str(REPO), str(clone))
            env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_INDEX_FILE=str(Path(t) / 'i'), GIT_AUTHOR_DATE='2020-01-01T00:00:00Z',
                       GIT_COMMITTER_DATE='2020-01-01T00:00:00Z', GIT_AUTHOR_NAME='x', GIT_AUTHOR_EMAIL='x@example.invalid',
                       GIT_COMMITTER_NAME='x', GIT_COMMITTER_EMAIL='x@example.invalid')
            run = lambda *a: subprocess.run(['git', '-C', str(clone), *a], env=env, capture_output=True, check=True).stdout
            run('read-tree', self.head)
            run('update-index', '--cacheinfo', '100644,' + guard.V1_MANIFEST_BLOB + ',' + guard.MANIFEST_PATH)
            tree = run('write-tree').decode().strip()
            for parents in ([], ['-p', self.head]):
                commit = run('commit-tree', tree, *parents, '-m', 'backdated v1').decode().strip()
                self.assertEqual(run('rev-parse', commit + ':' + guard.MANIFEST_PATH).decode().strip(), guard.V1_MANIFEST_BLOB)
                self.assertFalse(guard.manifest_commit_is_v1_frozen(clone, commit))
                with self.assertRaisesRegex(ValueError, 'schema 2 required'):
                    guard.load_manifest(self.v1, repo=clone, commit=commit)
            self.assertTrue(guard.manifest_commit_is_v1_frozen(clone, guard.V1_FROZEN_LAST))

    def test_unknown_or_bool_schema_rejected(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        for value in (3, True, '2', None):
            bad = dict(m, schema=value)
            with self.assertRaisesRegex(ValueError, 'unsupported manifest schema'):
                guard.load_manifest(self.write(bad))

    def test_schema2_structure_denials(self):
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
        cases = [
            (dict(m, excluded_paths=[]), 'excluded paths differ'),
            (dict(m, target_tree_excluding_manifest='x'), 'layer tree malformed'),
            (dict(m, target_tree_excluding_manifest_files=1), 'rows/count differ'),
            (dict(m, layer_source=list(reversed(m['layer_source']))), 'not byte-sorted'),
            (dict(m, layer_source=m['layer_source'] + [dict(m['layer_source'][-1], path=guard.MANIFEST_PATH)],
                  target_tree_excluding_manifest_files=len(m['layer_source']) + 1), 'not byte-sorted|excluded path'),
        ]
        for value, msg in cases:
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError, msg):
                guard.load_manifest(self.write(value))

    def test_cli_verify_layer_receipt(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, str(SCRIPTS / 'windows_foundation_source_guard.py'), 'verify-layer',
                                '--manifest', str(MANIFEST), '--manager', str(REPO), '--receipt', str(Path(t) / 'r.json')],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
            self.assertTrue(json.loads((Path(t) / 'r.json').read_text())['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
