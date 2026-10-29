"""Linux-runnable contract tests for the v23 exact-manifest standard-user acceptance.

Kept inside scripts/windows_standard_v23/ (not top-level) so v22's frozen,
non-recursive scripts/*.py inventory and its 300 cap are unaffected.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
ROOT = SCRIPTS.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))

import source_manifest_v23 as inv  # noqa: E402

spec = importlib.util.spec_from_file_location('windows_standard_v23', HERE / 'Windows标准用户验收v23.py')
v23 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v23)

V22 = SCRIPTS / 'Windows标准用户验收v22.py'
V22_SHA256 = 'af72940615f494ded1dcbbd26bf9994b1adb97104ce144e90dc50d26653c7f9d'
V27_SHA256 = '16365a5bf83576366065d84526c2b70154016c3274a18e1dba12053a0656db8e'


def tree(base: Path, top: int, sub=('extra_v23.py',)) -> Path:
    scripts = base / 'scripts'
    (scripts / inv.SUBDIR / '__pycache__').mkdir(parents=True)
    for index in range(top):
        (scripts / f'm{index:04d}.py').write_text(f'# {index}\n', encoding='utf-8')
    (scripts / 'notes.txt').write_text('ignored', encoding='utf-8')
    (scripts / 'nested').mkdir()
    (scripts / 'nested' / 'deep.py').write_text('# ignored (non-recursive)\n', encoding='utf-8')
    for name in sub:
        (scripts / inv.SUBDIR / name).write_text('# sub\n', encoding='utf-8')
    (scripts / inv.SUBDIR / 'readme.txt').write_text('ignored', encoding='utf-8')
    (scripts / inv.SUBDIR / '__pycache__' / 'x.py').write_text('', encoding='utf-8')
    (base / 'package.json').write_text('{"name":"t"}', encoding='utf-8')
    names = list(inv.collect(scripts)) + [f'scripts/{inv.SUBDIR}/{inv.MANIFEST_NAME}']
    (scripts / inv.SUBDIR / inv.MANIFEST_NAME).write_text(json.dumps(inv.build(names), ensure_ascii=False), encoding='utf-8')
    return scripts


class ManifestShape(unittest.TestCase):
    def setUp(self):
        self.good = inv.build(['package.json', 'scripts/a.py', f'scripts/{inv.SUBDIR}/{inv.MANIFEST_NAME}'])

    def test_roundtrip_and_digest_is_order_canonical(self):
        inv.validate(self.good)
        self.assertEqual(self.good['names_sha256'], inv.names_digest(sorted(self.good['entries'])))
        self.assertEqual(self.good['count'], 3)

    def test_tampering_fails_closed(self):
        cases = {
            'count': lambda d: d.update(count=d['count'] + 1),
            'bool count': lambda d: d.update(count=True) if d['count'] == 1 else d.update(count=float(d['count'])),
            'digest': lambda d: d.update(names_sha256='0' * 64),
            'unsorted': lambda d: d['entries'].reverse(),
            'duplicate': lambda d: d['entries'].insert(1, d['entries'][1]),
            'extra key': lambda d: d.update(cap=300),
            'schema': lambda d: d.update(schema='v22'),
            'nested': lambda d: d['entries'].insert(2, 'scripts/nested/deep.py'),
            'parent': lambda d: d['entries'].insert(2, 'scripts/../x.py'),
            'backslash': lambda d: d['entries'].insert(2, 'scripts/a\\b.py'),
            'drive': lambda d: d['entries'].insert(2, 'scripts/c:x.py'),
            'no package': lambda d: d['entries'].remove('package.json'),
            'no self': lambda d: d['entries'].remove(f'scripts/{inv.SUBDIR}/{inv.MANIFEST_NAME}'),
        }
        for label, mutate in cases.items():
            data = json.loads(json.dumps(self.good)); mutate(data)
            with self.subTest(label), self.assertRaises(ValueError):
                inv.validate(data)


class CopyAndVerify(unittest.TestCase):
    def test_more_than_300_sources_are_accepted_exactly(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw); scripts = tree(base / 'repo', 420)
            fixture = base / 'fixture'
            hashes = v23.copy_sources(fixture, scripts)
            self.assertGreater(len(hashes), 300)
            self.assertNotIn('scripts/nested/deep.py', hashes)
            self.assertNotIn('scripts/notes.txt', hashes)
            self.assertIn(f'scripts/{inv.SUBDIR}/extra_v23.py', hashes)
            v23.verify_sources(fixture / 'source', hashes)

    def test_extra_or_missing_source_is_rejected_before_copy(self):
        for action in ('extra-top', 'extra-sub', 'missing'):
            with self.subTest(action), tempfile.TemporaryDirectory() as raw:
                base = Path(raw); scripts = tree(base / 'repo', 5)
                if action == 'extra-top': (scripts / 'late.py').write_text('', encoding='utf-8')
                elif action == 'extra-sub': (scripts / inv.SUBDIR / 'late.json').write_text('{}', encoding='utf-8')
                else: (scripts / 'm0003.py').unlink()
                with self.assertRaisesRegex(ValueError, 'differs from the v23 manifest'):
                    v23.copy_sources(base / 'fixture', scripts)
                self.assertFalse((base / 'fixture' / 'source').exists())

    def test_symlinked_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw); scripts = tree(base / 'repo', 3)
            (scripts / 'm0001.py').unlink(); (scripts / 'm0001.py').symlink_to(scripts / 'm0000.py')
            with self.assertRaises(ValueError):
                v23.copy_sources(base / 'fixture', scripts)

    def test_child_side_detects_changed_extra_or_missing_entries(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw); scripts = tree(base / 'repo', 4)
            source = base / 'fixture' / 'source'
            hashes = v23.copy_sources(base / 'fixture', scripts)
            (source / 'scripts' / 'm0002.py').write_text('# changed\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'test source changed'):
                v23.verify_sources(source, hashes)
            (source / 'scripts' / 'm0002.py').write_text('# 2\n', encoding='utf-8')
            v23.verify_sources(source, hashes)
            for mutate in (lambda h: h.pop('scripts/m0001.py'), lambda h: h.update({'scripts/zz.py': '0' * 64})):
                changed = dict(hashes); mutate(changed)
                with self.assertRaises(ValueError):
                    v23.verify_sources(source, changed)
            with self.assertRaises(ValueError):
                v23.verify_sources(source, list(hashes))


class RepositoryContract(unittest.TestCase):
    def test_checked_in_manifest_matches_git_and_filesystem(self):
        manifest = inv.load(HERE / inv.MANIFEST_NAME)
        if (ROOT / '.git').exists():
            inv.require_exact(manifest, inv.git_names(ROOT))
        inv.require_exact(manifest, inv.collect(SCRIPTS))

    def test_v22_and_v27_remain_byte_identical_and_v23_is_outside_their_glob(self):
        self.assertEqual(hashlib.sha256(V22.read_bytes()).hexdigest(), V22_SHA256)
        self.assertEqual(hashlib.sha256((SCRIPTS / '标准宿主引导v27.py').read_bytes()).hexdigest(), V27_SHA256)
        top = sorted(p.name for p in SCRIPTS.glob('*.py'))
        self.assertFalse([n for n in top if 'v23' in n and 'Windows标准用户验收' in n])
        self.assertNotIn('标准宿主引导v28.py', top)

    def test_bootstrap_v28_targets_v23_with_its_own_marker(self):
        text = (HERE / '标准宿主引导v28.py').read_text(encoding='utf-8')
        self.assertIn("'.standard-account-fixture-v23'", text)
        self.assertIn("'windows_standard_v23' / 'Windows标准用户验收v23.py'", text)
        self.assertNotIn('v22', text)
        self.assertEqual(v23.FIXTURE_MARKER, '.standard-account-fixture-v23')
        self.assertEqual(v23.BOOTSTRAP, '标准宿主引导v28.py')

    def test_v23_preserves_v22_security_gates(self):
        source = (HERE / 'Windows标准用户验收v23.py').read_text(encoding='utf-8')
        for text in ("script_name(args.get('scenario', 'legacy'))", "'scenario':args.scenario",
                     "verify_sources(root / 'source', data['source_hashes'])", 'use_normal_user_process',
                     'owned_account(name, sid, marker, actual)', "if password.encode() in raw",
                     'CreateProcessWithLogonW', 'verify_sources(root / \'source\', hashes)'):
            self.assertIn(text, source)
        self.assertNotIn('<= 300', source.replace('``1 <= len(inventory) <= 300``', ''))

    def test_account_identity_is_v23_scoped(self):
        self.assertTrue(v23.NAME.fullmatch('ctmcpv23_0123456789'))
        self.assertFalse(v23.NAME.fullmatch('ctmcpv22_0123456789'))
        with self.assertRaises(RuntimeError):
            sid = 'S-1-5-21-1-2-3-1001'
            v23.owned_account('ctmcpv23_0123456789', sid, 'coding-tools-native-v22:x', ('ctmcpv23_0123456789', sid, 'coding-tools-native-v22:x'))

    def test_evidence_name_matches_release_consumer(self):
        consumer = (SCRIPTS / 'exclusive_release.py').read_text(encoding='utf-8')
        self.assertIn(f"folder / '{v23.EVIDENCE}'", consumer)

    def test_cli_check_passes(self):
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
        for command in ('check', 'git-check') if (ROOT / '.git').exists() else ('check',):
            result = subprocess.run([sys.executable, '-B', str(HERE / 'source_manifest_v23.py'), command, '--root', str(ROOT)],
                                    capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(json.loads(result.stdout)['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
