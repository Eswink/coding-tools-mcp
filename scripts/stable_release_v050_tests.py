"""Offline negative contracts for the bounded stable promotion and both READMEs."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
import zipfile
import stable_release_v050 as s

ROOT = Path(__file__).resolve().parents[1]


def release():
    return {'id': s.RELEASE, 'tag_name': 'v0.5.0', 'target_commitish': s.SOURCE,
            'draft': False, 'prerelease': True,
            'assets': [{'name': n, 'id': v[0], 'size': v[1], 'digest': 'sha256:' + v[2], 'state': 'uploaded'}
                       for n, v in s.ASSETS.items()]}


def ref(sha=s.SOURCE):
    return {'object': {'type': 'commit', 'sha': sha}}


def build():
    return {'id': s.BUILD, 'head_sha': s.SOURCE, 'head_branch': 'release/ui-v0.5.0',
            'run_attempt': 1, 'status': 'completed', 'conclusion': 'failure'}


def jobs():
    return {'total_count': 17, 'jobs': [{'id': x, 'run_id': s.BUILD, 'status': 'completed',
        'conclusion': 'failure' if x == s.FAILED_JOB else 'success'} for x in s.JOBS | {s.FAILED_JOB}]}


class Fake:
    def __init__(self, token):
        self.calls = []
        self.main = ref('a' * 40)
        self.fail_patch = False

    def request(self, method, path, data=None, allow_missing=False, upload=None):
        self.calls.append((method, path, data))
        if method == 'PATCH' and self.fail_patch:
            raise OSError('simulated ambiguous transport failure')
        return self.main


def client(permitted=True):
    return s.metadata_client(Fake, '', permitted=permitted, source='a' * 40, notes='approved notes')


def patch(api, **changes):
    data = {'name': s.NAME, 'body': 'approved notes', 'prerelease': False, 'make_latest': 'true', **changes}
    return api.request('PATCH', f'/releases/{s.RELEASE}', data)


class PromotionTests(unittest.TestCase):
    def test_existing_prerelease_and_stable_keep_identity(self):
        value = release()
        for channel in (True, False):
            value['prerelease'] = channel
            s.check_release(value, ref(), ref())

    def test_wrong_release_or_source_rejected(self):
        for key, value in [('id', 1), ('tag_name', 'v0.5.1'), ('target_commitish', '0' * 40), ('draft', True), ('prerelease', None)]:
            item = release(); item[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                s.check_release(item, ref(), ref())

    def test_tag_move_rejected(self):
        with self.assertRaises(ValueError): s.check_release(release(), ref('b' * 40), ref())

    def test_release_branch_move_rejected(self):
        with self.assertRaises(ValueError): s.check_release(release(), ref(), ref('b' * 40))

    def test_replaced_asset_id_rejected(self):
        item = release(); item['assets'][0]['id'] += 1
        with self.assertRaises(ValueError): s.check_release(item, ref(), ref())

    def test_size_digest_and_state_changes_rejected(self):
        for key, value in [('size', 1), ('digest', 'sha256:' + '0' * 64), ('state', 'new')]:
            item = release(); item['assets'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): s.check_release(item, ref(), ref())

    def test_missing_duplicate_and_extra_assets_rejected(self):
        for change in ('missing', 'duplicate', 'extra'):
            item = release()
            if change == 'missing': item['assets'].pop()
            elif change == 'duplicate': item['assets'][0] = copy.deepcopy(item['assets'][1])
            else: item['assets'].append(copy.deepcopy(item['assets'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError): s.check_release(item, ref(), ref())

    def test_original_publication_failure_preserved(self): s.check_build(build(), jobs())

    def test_original_run_not_rewritten_as_success(self):
        item = build(); item['conclusion'] = 'success'
        with self.assertRaises(ValueError): s.check_build(item, jobs())

    def test_failed_prerequisite_rejected(self):
        item = jobs(); next(x for x in item['jobs'] if x['id'] != s.FAILED_JOB)['conclusion'] = 'failure'
        with self.assertRaises(ValueError): s.check_build(build(), item)

    def test_partial_job_list_rejected(self):
        item = jobs(); item['jobs'].pop()
        with self.assertRaises(ValueError): s.check_build(build(), item)

    def test_wrong_run_and_retried_build_rejected(self):
        for key, value in [('run_attempt', 2), ('head_sha', '0' * 40), ('id', 1)]:
            item = build(); item[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): s.check_build(item, jobs())

    def test_verifier_is_read_only(self):
        api = client(False); api.request('GET', '/releases/latest')
        with self.assertRaises(ValueError): patch(api)
        self.assertEqual(len(api.calls), 1)

    def test_exact_patch_and_main_check(self):
        api = client(); patch(api)
        self.assertEqual([x[0] for x in api.calls], ['GET', 'PATCH'])
        self.assertTrue(api.attempted)

    def test_second_patch_rejected(self):
        api = client(); patch(api)
        with self.assertRaises(ValueError): patch(api)
        self.assertEqual(len(api.calls), 2)

    def test_main_race_prevents_patch(self):
        api = client(); api.main = ref('b' * 40)
        with self.assertRaises(ValueError): patch(api)
        self.assertEqual([x[0] for x in api.calls], ['GET'])

    def test_failed_patch_not_blindly_retried(self):
        api = client(); api.fail_patch = True
        with self.assertRaises(OSError): patch(api)
        with self.assertRaises(ValueError): patch(api)
        self.assertTrue(api.attempted)
        self.assertEqual(len(api.calls), 2)

    def test_no_upload_delete_or_ref_writes(self):
        for method, path in [('POST', '/releases'), ('DELETE', f'/releases/{s.RELEASE}'),
                             ('PATCH', '/git/refs/tags/v0.5.0'), ('PATCH', '/releases/1')]:
            api = client()
            with self.subTest(method=method, path=path), self.assertRaises(ValueError): api.request(method, path, {})
            self.assertEqual(api.calls, [])

    def test_patch_cannot_change_tag_target_draft_or_notes(self):
        for changes in ({'tag_name': 'v9.0.0'}, {'target_commitish': 'main'}, {'draft': False}, {'body': 'unexpected'}):
            api = client()
            with self.subTest(changes=changes), self.assertRaises(ValueError): patch(api, **changes)
            self.assertEqual(api.calls, [])

    def test_get_cannot_carry_credentials_payload(self):
        api = client()
        with self.assertRaises(ValueError): api.request('GET', '/releases', data={})
        self.assertEqual(api.calls, [])

    def test_archive_traversal_and_symlink_rejected(self):
        for name in ('../escape', '/absolute', 'a\\b', 'link'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'evidence.zip'
                with zipfile.ZipFile(path, 'w') as z:
                    info = zipfile.ZipInfo(name)
                    if name == 'link': info.external_attr = 0o120777 << 16
                    z.writestr(info, 'safe synthetic bytes')
                with self.subTest(name=name), self.assertRaises(ValueError): s.unzip_checked(path, Path(tmp) / 'out')

    def test_safe_archive_extracts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.zip'
            with zipfile.ZipFile(path, 'w') as z: z.writestr('result.json', '{}')
            out = Path(tmp) / 'out'; s.unzip_checked(path, out)
            self.assertEqual((out / 'result.json').read_text(), '{}')

    def test_readme_downloads_belong_to_fork(self):
        for name in ('README.md', 'README.en.md'):
            text = (ROOT / name).read_text(encoding='utf-8')
            urls = re.findall(r'https://github\.com/[^\s)"<>]+', text)
            self.assertIn('https://github.com/Eswink/coding-tools-mcp/releases/latest', urls)
            self.assertFalse(any('mybolide/' in url and '/releases' in url for url in urls))
            downloads = [url.split('/')[-1] for url in urls if '/releases/download/' in url]
            self.assertTrue(set(downloads) <= set(s.ASSETS))
            self.assertTrue(set(list(s.ASSETS)[:3]) <= set(downloads))

    def test_relative_document_links_exist(self):
        for name in ('README.md', 'README.en.md', 'docs/releases/stable-v0.5.0.md'):
            path = ROOT / name; text = path.read_text(encoding='utf-8')
            targets = re.findall(r'\]\(([^)]+)\)|(?:href|src)="([^"]+)"', text)
            for pair in targets:
                target = next(t for t in pair if t).split('#')[0]
                if target and '://' not in target:
                    with self.subTest(file=name, target=target): self.assertTrue((path.parent / target).exists())

    def test_documents_include_actual_approval_and_refresh(self):
        for name in ('README.md', 'README.en.md'):
            text = (ROOT / name).read_text(encoding='utf-8')
            for token in ('auth_status', 'request_chat_authorization', 'EXCLUSIVE_CHAT_LOCKED', 'draining',
                          'mcp offline_access', 'history_session_checkpoint', '90', '480', '720', '1440',
                          'src-tauri/src/update/mod.rs', 'node scripts/前端完整回归v4.mjs'):
                with self.subTest(file=name, token=token): self.assertIn(token, text)

    def test_document_version_and_real_defaults(self):
        self.assertEqual(json.loads((ROOT / 'package.json').read_text())['version'], '0.5.0')
        policy = (ROOT / 'src-tauri/src/auth/session_policy.rs').read_text()
        for token in ('access_token_ttl_seconds: 3600', 'refresh_session_ttl_seconds: 30 * 86400',
                      'chat_lease_ttl_seconds: 86400', 'chat_idle_timeout_seconds: 0'):
            self.assertIn(token, policy)

    def test_workflow_separates_read_only_and_metadata_write(self):
        text = (ROOT / '.github/workflows/stable-release-v050.yml').read_text()
        verify, promote = text.split('  promote:')
        self.assertNotIn('contents: write', verify)
        self.assertIn('needs: verify', promote)
        self.assertIn('contents: write', promote)
        self.assertIn('--promote', promote)
        self.assertNotIn('pull_request_target', text)
        self.assertNotIn('secrets: inherit', text)
        self.assertNotIn('continue-on-error', text)

    def test_allowlist_excludes_product_and_original_publishers(self):
        self.assertEqual(len(s.ALLOWED_FILES), 7)
        self.assertFalse(any(x.startswith(('src/', 'src-tauri/')) for x in s.ALLOWED_FILES))
        self.assertNotIn('.github/workflows/ui-release.yml', s.ALLOWED_FILES)


if __name__ == '__main__':
    unittest.main(verbosity=2)
