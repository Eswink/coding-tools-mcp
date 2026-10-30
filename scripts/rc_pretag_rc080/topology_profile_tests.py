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
MAIN_MERGE = 'dffc3c6b65c3f390256f4346cd77f917dbf3d0e4'  # PR #174: 9531007c + d6a45088


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
    def test_main_merge_of_develop_is_admitted(self):
        self.assertEqual(git('show', '-s', '--format=%P', MAIN_MERGE).decode().split(),
                         [rc080.M, 'd6a450882cf5ae9be27068d8de8912c3747a56a9'])
        self.assertEqual(rc080.topology(MAIN_MERGE, ROOT, git, p.R), 1)
        self.assertEqual(select(MAIN_MERGE), entries(MAIN_MERGE))
        self.assertIsNone(rc070.select(MAIN_MERGE, ROOT, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS))

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

    def merge(self, *parents, tree=None):
        # default to the last parent's tree, never the clone's moving HEAD (other cases commit on it)
        tree = git('rev-parse', (tree or parents[-1]) + '^{tree}', root=self.repo).decode().strip()
        args = [arg for parent in parents for arg in ('-p', parent)]
        return git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit-tree', tree, *args, '-m', 'merge',
                   root=self.repo).decode().strip()

    def test_merge_of_admitted_descendant_is_admitted(self):
        head = git('rev-parse', 'HEAD').decode().strip()
        ref = self.merge(rc080.M, head)
        self.assertEqual(rc080.topology(ref, self.repo, git, p.R), 1)
        self.assertEqual(self.admit(ref), entries(head))

    def test_linear_descendant_of_merge_is_admitted_by_topology(self):
        head = git('rev-parse', 'HEAD').decode().strip()
        child = self.merge(self.merge(rc080.M, head))
        self.assertEqual(rc080.topology(child, self.repo, git, p.R), 2)

    def test_octopus_merge_falls_through(self):
        head = git('rev-parse', 'HEAD').decode().strip()
        self.assertIsNone(self.admit(self.merge(rc080.M, head, head + '^')))

    def test_merge_does_not_bypass_second_parent_content(self):
        path = 'scripts/rc_pretag_rc070_topology_profile.py'
        bad = self.commit(path, (ROOT / path).read_bytes() + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_frozen'):
            self.admit(self.merge(rc080.M, bad, tree=bad))

    def test_merge_with_own_changes_is_content_checked(self):
        head = git('rev-parse', 'HEAD').decode().strip()
        edited = self.commit('README.md', (ROOT / 'README.md').read_bytes() + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080 manifest'):
            self.admit(self.merge(rc080.M, head, tree=edited))

    def test_unknown_parent_falls_through(self):
        tree = git('rev-parse', 'HEAD^{tree}').decode().strip()
        for parent in ('0a18f3bcf562e32a1fd29477491a84a1bf0e6d0c', '86b5310000000000000000000000000000000000'):
            raw = ('tree %s\nparent %s\nauthor t <t@invalid> 0 +0000\ncommitter t <t@invalid> 0 +0000\n\ncase\n'
                   % (tree, parent)).encode()
            ref = subprocess.run(['git', 'hash-object', '-t', 'commit', '-w', '--literally', '--stdin'], cwd=self.repo,
                                 input=raw, capture_output=True, check=True).stdout.decode().strip()
            self.assertIsNone(self.admit(ref), parent)


if __name__ == '__main__':
    unittest.main()
