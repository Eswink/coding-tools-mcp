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
SIDE = 'd6a450882cf5ae9be27068d8de8912c3747a56a9'


def git(*args, root=ROOT):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', *args], cwd=root, timeout=60)


def entries(ref, root=ROOT):
    return {path: tuple(header.split()) for header, path in
            (row.split('\t', 1) for row in git('ls-tree', '-rz', ref, root=root).decode().split('\0') if row)}


def select(ref, root=ROOT):
    return rc080.select(ref, root, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS)


def is_ancestor(ancestor, ref, root=ROOT):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, ref], cwd=root).returncode == 0


def required_budget(ref, root=ROOT):
    """Smallest budget at which topology(ref) admits; None when not admitted even at DEPTH_LIMIT."""
    def ok(budget):
        try:
            rc080.topology(ref, root, git, p.R, budget)
            return True
        except AssertionError:
            return False
    if not ok(rc080.DEPTH_LIMIT):
        return None
    low, high = 0, rc080.DEPTH_LIMIT
    while low < high:
        mid = (low + high) // 2
        low, high = (low, mid) if ok(mid) else (mid + 1, high)
    return low


HEADROOM_WARN = 16


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

    def test_main_merge_of_develop_is_admitted(self):
        self.assertEqual(git('show', '-s', '--format=%P', MAIN_MERGE).decode().split(), [rc080.M, SIDE])
        self.assertEqual(rc080.topology(MAIN_MERGE, ROOT, git, p.R), 1)
        self.assertEqual(select(MAIN_MERGE), entries(MAIN_MERGE))
        self.assertIsNone(rc070.select(MAIN_MERGE, ROOT, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS))

    def test_head_is_admitted_when_m_is_an_ancestor(self):
        """The only HEAD-dependent test: never skips. M ancestor of HEAD => must be admitted."""
        head = git('rev-parse', 'HEAD').decode().strip()
        if is_ancestor(rc080.M, head):
            self.assertEqual(select(head), entries(head), 'rc080 must admit HEAD (M is an ancestor)')
            self.assertIsNone(rc070.select(head, ROOT, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS))
        else:
            self.assertIsNone(select(head))

    def test_head_depth_headroom_is_at_least_16(self):
        head = git('rev-parse', 'HEAD').decode().strip()
        # A1 C5: never a silent pass. A HEAD that does not descend from M has no
        # rc080 depth to measure, so the headroom check fails instead of returning.
        self.assertTrue(is_ancestor(rc080.M, head),
                        'rc080 M %s is not an ancestor of HEAD %s; depth headroom unmeasurable' % (rc080.M, head))
        need = required_budget(head)
        self.assertIsNotNone(need, 'HEAD not admitted within DEPTH_LIMIT %d' % rc080.DEPTH_LIMIT)
        self.assertGreaterEqual(rc080.DEPTH_LIMIT - need, HEADROOM_WARN,
                                'rc080 depth headroom %d < %d (need %d of %d)'
                                % (rc080.DEPTH_LIMIT - need, HEADROOM_WARN, need, rc080.DEPTH_LIMIT))


class Rc080NegativeCases(unittest.TestCase):
    """Built on the fixed fixture MAIN_MERGE (dffc3c6b), never on HEAD."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / 'repo'
        subprocess.check_call(['git', 'clone', '-q', '--no-checkout', str(ROOT), str(cls.repo)])
        git('checkout', '-q', '--detach', MAIN_MERGE, root=cls.repo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def commit(self, path, data):
        git('checkout', '-q', '--detach', MAIN_MERGE, root=self.repo)
        (self.repo / path).write_bytes(data)
        git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit', '-qam', 'case', root=self.repo)
        return git('rev-parse', 'HEAD', root=self.repo).decode().strip()

    def fixture(self, path):
        return git('show', '%s:%s' % (MAIN_MERGE, path), root=self.repo)

    def admit(self, ref):
        return rc080.select(ref, self.repo, git, entries, None, p.R, p.R_TREE, p.R_DOCUMENTS)

    def merge(self, *parents, tree=None):
        tree = git('rev-parse', (tree or parents[-1]) + '^{tree}', root=self.repo).decode().strip()
        args = [arg for parent in parents for arg in ('-p', parent)]
        return git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit-tree', tree, *args, '-m', 'merge',
                   root=self.repo).decode().strip()

    def test_fixture_itself_is_admitted(self):
        self.assertEqual(self.admit(MAIN_MERGE), entries(MAIN_MERGE, self.repo))

    def test_frozen_admission_source_is_rejected(self):
        path = 'scripts/rc_pretag_rc070_topology_profile.py'
        ref = self.commit(path, self.fixture(path) + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_frozen'):
            self.admit(ref)

    def test_host_may_only_carry_the_hook(self):
        ref = self.commit(rc080.HOST, self.fixture(rc080.HOST) + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_host_hook'):
            self.admit(ref)

    def test_stale_probe_manifest_is_rejected(self):
        ref = self.commit('README.md', self.fixture('README.md') + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080 manifest'):
            self.admit(ref)

    def test_merge_falls_through(self):
        self.assertIsNone(self.admit(self.merge(MAIN_MERGE, rc080.M_PARENTS[0], tree=MAIN_MERGE)))

    def test_merge_of_admitted_descendant_is_admitted(self):
        ref = self.merge(rc080.M, MAIN_MERGE)
        self.assertEqual(rc080.topology(ref, self.repo, git, p.R), 1)
        self.assertEqual(self.admit(ref), entries(MAIN_MERGE, self.repo))

    def test_linear_descendant_of_merge_is_admitted_by_topology(self):
        child = self.merge(self.merge(rc080.M, MAIN_MERGE))
        self.assertEqual(rc080.topology(child, self.repo, git, p.R), 2)

    def test_octopus_merge_falls_through(self):
        self.assertIsNone(self.admit(self.merge(rc080.M, MAIN_MERGE, SIDE)))

    def test_merge_does_not_bypass_second_parent_content(self):
        path = 'scripts/rc_pretag_rc070_topology_profile.py'
        bad = self.commit(path, self.fixture(path) + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080_frozen'):
            self.admit(self.merge(rc080.M, bad, tree=bad))

    def test_merge_with_own_changes_is_content_checked(self):
        edited = self.commit('README.md', self.fixture('README.md') + b'\n')
        with self.assertRaisesRegex(AssertionError, 'rc080 manifest'):
            self.admit(self.merge(rc080.M, MAIN_MERGE, tree=edited))

    def test_unknown_parent_falls_through(self):
        tree = git('rev-parse', MAIN_MERGE + '^{tree}', root=self.repo).decode().strip()
        for parent in ('0a18f3bcf562e32a1fd29477491a84a1bf0e6d0c', '86b5310000000000000000000000000000000000'):
            raw = ('tree %s\nparent %s\nauthor t <t@invalid> 0 +0000\ncommitter t <t@invalid> 0 +0000\n\ncase\n'
                   % (tree, parent)).encode()
            ref = subprocess.run(['git', 'hash-object', '-t', 'commit', '-w', '--literally', '--stdin'], cwd=self.repo,
                                 input=raw, capture_output=True, check=True).stdout.decode().strip()
            self.assertIsNone(self.admit(ref), parent)


class Rc080DepthBudgetTests(unittest.TestCase):
    """Boundary on synthetic commit-tree chains rooted at M; independent of HEAD depth."""

    @classmethod
    def setUpClass(cls):
        cls.limit = rc080.DEPTH_LIMIT
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / 'repo'
        subprocess.check_call(['git', 'clone', '-q', '--shared', '--no-checkout', str(ROOT), str(cls.repo)])
        cls.tree = git('rev-parse', rc080.M + '^{tree}', root=cls.repo).decode().strip()
        cls.chain = cls.build(rc080.M, cls.limit + 4, 'chain')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def build(cls, base, count, label):
        refs = [base]
        for index in range(1, count + 1):
            refs.append(cls.commit_tree('%s %d' % (label, index), refs[-1]))
        return refs

    @classmethod
    def commit_tree(cls, message, *parents):
        args = [arg for parent in parents for arg in ('-p', parent)]
        return git('-c', 'user.name=t', '-c', 'user.email=t@invalid', 'commit-tree', cls.tree, *args, '-m', message,
                   root=cls.repo).decode().strip()

    def depth(self, ref):
        return rc080.topology(ref, self.repo, git, p.R)

    def test_depth_limit_is_128(self):
        self.assertEqual(rc080.DEPTH_LIMIT, 128)

    def test_depth_equal_to_limit_is_admitted(self):
        self.assertEqual(self.depth(self.chain[self.limit]), self.limit)

    def test_depth_limit_plus_one_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'rc080_not_descendant'):
            self.depth(self.chain[self.limit + 1])
        self.assertIsNone(rc080.select(self.chain[self.limit + 1], self.repo, git, entries, None, p.R, p.R_TREE,
                                       p.R_DOCUMENTS))

    def test_depth_beyond_limit_is_rejected(self):
        for ref in self.chain[self.limit + 2:]:
            with self.assertRaisesRegex(AssertionError, 'rc080_not_descendant'):
                self.depth(ref)

    def test_second_parent_shares_the_budget(self):
        self.assertEqual(self.depth(self.commit_tree('merge', rc080.M, self.chain[self.limit - 1])), 1)
        with self.assertRaisesRegex(AssertionError, 'rc080_not_descendant'):
            self.depth(self.commit_tree('merge', rc080.M, self.chain[self.limit]))

    def test_main_merge_required_budget_formula(self):
        # dffc3c6b: distance 0 to itself -> needs 0 + 1 + 13 = 14
        self.assertEqual(required_budget(MAIN_MERGE, self.repo), 14)

if __name__ == '__main__':
    unittest.main()
