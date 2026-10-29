"""Run from scripts/: python3 -m unittest rc_pretag_rc080.topology_profile_tests"""
import subprocess
import tempfile
import unittest
from pathlib import Path

import rc_pretag_publication_profile as p
import rc_pretag_rc070_topology_profile as rc070
from rc_pretag_rc080 import topology_profile as rc080

ROOT = Path(__file__).resolve().parents[2]
RC070_M = '3ea09a6fbc0cf637dc9a7d6e8f58b8a39f06d274'


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', *args], cwd=root, timeout=60)


def entries(ref, root=ROOT):
    return {path: tuple(header.split()) for header, path in
            (row.split('\t', 1) for row in git('ls-tree', '-rz', ref, root=root).decode().split('\0') if row)}


def select(ref, root=ROOT):
    return rc080.select(ref, root, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS)


def head_is_descendant():
    try:
        rc080.topology(git('rev-parse', 'HEAD').decode().strip(), ROOT, git, p.R)
        return True
    except AssertionError:
        return False


class Rc080TopologyProfileTests(unittest.TestCase):
    def test_anchor_identity_is_admitted(self):
        self.assertEqual(select(rc080.M), entries(rc080.M))

    def test_0_7_x_and_rc070_refs_fall_through(self):
        for ref in rc080.M_PARENTS + (RC070_M,):
            self.assertIsNone(select(ref), ref)

    def test_wrong_release_anchor_falls_through(self):
        self.assertIsNone(rc080.select(rc080.M, ROOT, git, entries, None, rc080.M, p.R_TREE, p.R_DOCUMENTS))

    def test_independent_of_rc070(self):
        source = (ROOT / rc080.PROFILE).read_text()
        self.assertNotIn('import rc_pretag_rc070', source)
        self.assertNotIn(RC070_M, source)

    @unittest.skipUnless(head_is_descendant(), 'HEAD is not a 0.8.0 descendant')
    def test_head_is_admitted_and_rc070_does_not_admit_it(self):
        self.assertEqual(select('HEAD'), entries('HEAD'))
        self.assertIsNone(rc070.select('HEAD', ROOT, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS))


@unittest.skipUnless(head_is_descendant(), 'HEAD is not a 0.8.0 descendant')
class Rc080NegativeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / 'repo'
        subprocess.check_call(['git', 'clone', '-q', str(ROOT), str(cls.repo)])
        git('checkout', '-q', git('rev-parse', 'HEAD').decode().strip(), root=cls.repo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def commit(self, path, data):
        git('checkout', '-q', '--detach', git('rev-parse', 'HEAD').decode().strip(), root=self.repo)
        (self.repo / path).write_bytes(data)
        git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit', '-qam', 'case', root=self.repo)
        return git('rev-parse', 'HEAD', root=self.repo).decode().strip()

    def admit(self, ref):
        return rc080.select(ref, self.repo, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS)

    def test_frozen_admission_source_is_rejected(self):
        path = 'scripts/rc_pretag_rc070_topology_profile.py'
        ref = self.commit(path, (ROOT / path).read_bytes() + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_frozen'):
            self.admit(ref)

    def test_host_may_only_carry_the_hook(self):
        ref = self.commit(rc080.HOST, (ROOT / rc080.HOST).read_bytes() + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_host_hook'):
            self.admit(ref)

    def test_stale_probe_manifest_is_rejected(self):
        ref = self.commit('README.md', (ROOT / 'README.md').read_bytes() + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080 manifest'):
            self.admit(ref)

    def test_merge_falls_through(self):
        tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
        ref = git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit-tree', tree, '-p', 'HEAD',
                  '-p', rc080.M_PARENTS[0], '-m', 'merge', root=self.repo).decode().strip()
        self.assertIsNone(self.admit(ref))


if __name__ == '__main__':
    unittest.main()
