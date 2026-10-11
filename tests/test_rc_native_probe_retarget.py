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


if __name__ == '__main__':
    unittest.main()
