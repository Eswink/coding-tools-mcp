"""Unit tests for the #148 retarget layer: fingerprint, set comparison, runner SHA, ancestry."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import rc_native_probe_restore as R  # noqa: E402
import rc_native_probe_manifest as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def run(cwd, *args):
    return subprocess.run(['/usr/bin/git', '-C', str(cwd), *args], check=True, capture_output=True, env=R.ENV).stdout.decode().strip()


class SetDiff(unittest.TestCase):
    def test_identical(self):
        self.assertEqual(R.set_diff(['a', 'b'], ['a', 'b', R.MANIFEST], ['a', 'b', R.MANIFEST]), {})

    def test_extra_and_missing_both_sides(self):
        diff = R.set_diff(['a', 'gone'], ['a', R.MANIFEST, 'new'], ['a', R.MANIFEST, 'stray'])
        self.assertEqual(diff['git_index'], dict(missing_from_actual=['gone'], extra_in_actual=['new']))
        self.assertEqual(diff['checkout'], dict(missing_from_actual=['gone'], extra_in_actual=['stray']))


class Runner(unittest.TestCase):
    def test_real_runner_matches(self):
        self.assertEqual(R.verify_runner(ROOT/'scripts/rc_native_probe_original_runner.py'), R.RUNNER_SHA)

    def test_one_byte_flip_fails_with_both_shas(self):
        raw = bytearray((ROOT/'scripts/rc_native_probe_original_runner.py').read_bytes())
        raw[100] ^= 0x01
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'runner.py'
            path.write_bytes(bytes(raw))
            with self.assertRaises(AssertionError) as caught:
                R.verify_runner(path)
        message = str(caught.exception)
        self.assertIn('expected '+R.RUNNER_SHA, message)
        self.assertIn('actual '+R.sha(bytes(raw)), message)


class WorkflowPolicy(unittest.TestCase):
    def test_committed_workflow_passes(self):
        import rc_native_probe_checks as C
        self.assertTrue(C.native_job_python_ok((ROOT/'.github/workflows/rc-native-recovery-probe.yml').read_text()))

    def test_setup_python_inside_native_job_fails(self):
        import rc_native_probe_checks as C
        text = (ROOT/'.github/workflows/rc-native-recovery-probe.yml').read_text()
        native, hermetic = text.split('\n  hermetic-probe-sets:\n', 1)
        bad = native.replace('    steps:\n', '    steps:\n      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n', 1) + '\n  hermetic-probe-sets:\n' + hermetic
        self.assertNotEqual(bad, text)
        self.assertFalse(C.native_job_python_ok(bad))

    def test_setup_python_allowed_in_both_hermetic_jobs(self):
        import rc_native_probe_checks as C
        text = (ROOT/'.github/workflows/rc-native-recovery-probe.yml').read_text()
        native, rest = text.split('\n  hermetic-probe-sets:\n', 1)
        probe_sets, executor = rest.split('\n  hermetic-executor:\n', 1)
        self.assertNotIn('setup-python', native)
        for job in (probe_sets, executor):
            self.assertIn('actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065', job)
            self.assertIn("python-version: '3.12'", job)
        self.assertTrue(C.native_job_python_ok(text))

    def test_setup_python_without_hermetic_split_fails(self):
        import rc_native_probe_checks as C
        self.assertFalse(C.native_job_python_ok('jobs:\n  publisher-native:\n    steps:\n      - uses: actions/setup-python@x\n'))


class Evaluate(unittest.TestCase):
    FP = dict(github_sha='h'*40, tree='t'*40, file_count=3, index_sha256='i'*64, manifest_sha256='m'*64)

    def test_valid(self):
        q = dict(necessary85='QUALIFIED', original300='QUALIFIED')
        self.assertTrue(R.evaluate(q, dict(necessary85=dict(self.FP), original300=dict(self.FP)), 'h'*40)['valid'])

    def test_each_field_mismatch_invalid(self):
        q = dict(necessary85='QUALIFIED', original300='QUALIFIED')
        for key in R.FINGERPRINT_FIELDS:
            other = dict(self.FP, **{key: 'x'})
            verdict = R.evaluate(q, dict(necessary85=dict(self.FP), original300=other), 'h'*40)
            self.assertFalse(verdict['valid'], key)
            self.assertTrue(any(key in p for p in verdict['problems']))

    def test_not_qualified_or_wrong_head(self):
        fps = dict(necessary85=dict(self.FP), original300=dict(self.FP))
        self.assertFalse(R.evaluate(dict(necessary85='QUALIFIED', original300='FAIL_UNKNOWN'), fps, 'h'*40)['valid'])
        self.assertFalse(R.evaluate(dict(necessary85='QUALIFIED', original300='QUALIFIED'), fps, 'z'*40)['valid'])
        self.assertFalse(R.evaluate(dict(necessary85='QUALIFIED', original300='NOT_RUN'), {'necessary85': self.FP}, 'h'*40)['valid'])


class RestoreInRepo(unittest.TestCase):
    """Simulated GITHUB_SHA checkout: a throwaway repo whose root commit stands in for the base."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.repo = self.dir/'repo'
        self.repo.mkdir()
        run(self.repo, 'init', '-q')
        (self.repo/'a.txt').write_text('a\n')
        run(self.repo, 'add', '.')
        run(self.repo, 'commit', '-qm', 'base')
        self.base = run(self.repo, 'rev-parse', 'HEAD')
        (self.repo/'scripts').mkdir()
        (self.repo/'b.txt').write_text('b\n')
        run(self.repo, 'add', '.')
        (self.repo/R.MANIFEST).write_bytes(M.render(self.repo))
        run(self.repo, 'add', '.')
        run(self.repo, 'commit', '-qm', 'layer')
        self.head = run(self.repo, 'rev-parse', 'HEAD')
        self.old_base, R.BASE = R.BASE, self.base

    def tearDown(self):
        R.BASE = self.old_base
        shutil.rmtree(self.dir)

    def test_restore_fingerprint(self):
        ctx = R.restore(self.repo, self.dir/'out', self.head)
        fp = ctx['fingerprint']
        self.assertEqual(fp['github_sha'], self.head)
        self.assertEqual(fp['tree'], run(self.repo, 'rev-parse', 'HEAD^{tree}'))
        self.assertEqual(fp['file_count'], 3)
        self.assertEqual(R.fingerprint(ctx['root'], self.head), fp)

    def test_wrong_github_sha_rejected(self):
        with self.assertRaises(AssertionError):
            R.restore(self.repo, self.dir/'out', self.base)

    def test_base_not_ancestor_rejected(self):
        run(self.repo, 'checkout', '-q', '--orphan', 'other')
        run(self.repo, 'commit', '-qm', 'orphan')
        R.BASE = run(self.repo, 'rev-parse', 'HEAD')
        run(self.repo, 'checkout', '-q', self.head)
        with self.assertRaises(AssertionError) as caught:
            R.restore(self.repo, self.dir/'out', self.head)
        self.assertIn('not an ancestor', str(caught.exception))

    def test_untracked_extra_file_reports_diff(self):
        ctx = R.restore(self.repo, self.dir/'out', self.head)
        (Path(ctx['root'])/'stray.txt').write_text('x')
        with self.assertRaises(AssertionError) as caught:
            R.whole_source(ctx['root'], ctx['rows'], ctx['tree'])
        self.assertIn('stray.txt', str(caught.exception))

    def test_ignored_byproduct_not_counted(self):
        ctx = R.restore(self.repo, self.dir/'out', self.head)
        self.assertNotIn('cache/x.pyc', R.checkout_files(self.repo))
        (Path(ctx['root'])/'.git/info/exclude').write_text('*.pyc\n')
        (Path(ctx['root'])/'x.pyc').write_bytes(b'0')
        self.assertNotIn('x.pyc', R.checkout_files(ctx['root']))

    def test_manifest_missing_row_reports_diff(self):
        ctx = R.restore(self.repo, self.dir/'out', self.head)
        rows = [r for r in ctx['rows'] if r['path'] != 'b.txt']
        with self.assertRaises(AssertionError) as caught:
            R.whole_source(ctx['root'], rows, ctx['tree'])
        self.assertIn('b.txt', str(caught.exception))



class ExcludesSelfObservation(unittest.TestCase):
    """excludes_self: MANIFEST stays out of source observation (receipt/context), keep 1882."""

    def test_committed_manifest_excludes_self(self):
        import json
        manifest = json.loads((ROOT/R.MANIFEST).read_text())
        self.assertEqual(manifest['excludes_self'], R.MANIFEST)
        self.assertEqual(manifest['entries'], len(manifest['rows']))
        self.assertNotIn(R.MANIFEST, [r['path'] for r in manifest['rows']])

    def test_runner_source_filter_excludes_manifest(self):
        raw = (ROOT/'scripts/rc_native_probe_original_runner.py').read_text()
        self.assertIn("p != 'scripts/rc_native_probe_source_manifest.json'", raw)
        # Negative: dropping the exclusion must not match the pinned runner.
        mutated = raw.replace(" and p != 'scripts/rc_native_probe_source_manifest.json'", '')
        self.assertNotEqual(R.sha(mutated.encode()), R.RUNNER_SHA)

    def test_restore_source_dict_excludes_manifest(self):
        # Lightweight: rows/source from current tree via manifest_rows + whole_source contract
        rows = R.manifest_rows(ROOT)
        self.assertNotIn(R.MANIFEST, [r['path'] for r in rows])
        self.assertEqual(len(rows), 1882)

if __name__ == '__main__':
    unittest.main()
