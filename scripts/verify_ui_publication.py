"""Read-only closure for the already-public v0.5.0; never publish or change a ref."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

SOURCE = '63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076'
TREE = '01b11a1088d82501a1e579801ce6ac774ab5d43a'
BUILD_RUN = 34810770540
RELEASE = 388174565
PUBLISH_JOB = 103873894785
VERSION = '0.5.0'
ASSETS = {
    'MCP_0.5.0_x64-setup.exe': (5701414, 'ae831f5a4c0b233a344f837cf47516d33dc8522be6fcf2380e30526fff9c1ade'),
    'MCP_0.5.0_amd64.deb': (9912422, 'c06757aa380aa0e2a0cdddb5b6a2a97004aeafbc348d4aa660d9d7b3d2c8a20b'),
    'MCP_0.5.0_amd64.AppImage': (86841848, '86b95dcd3f3bf8da6b334d937d033e7870858326e969b577a9ebfc4606d24fec'),
    'UI-evidence_v0.5.0.zip': (22015863, '7f67cdababf0709a44ee2fb6486160cf2abd74584eb9d255e6a9ef3c002bceaf'),
    'Verification_v0.5.0.md': (4136, 'c1972692a6a5ebd2f4b269b1cb47f36c272e599709a0f5ce40d8b6880a26ea8f'),
    'Release-scope_v0.5.0.json': (2675, '534aa69724ddc28ae5c2acf00abf5799be5149ac3fb2d93cb7328e1c8310ca55'),
    'SHA256SUMS_v0.5.0.txt': (537, '36b210307bdaf77c2813257a24c1bff695435bc862b4b9a5e9f8ba9213d1de7f'),
}
JOBS = {
    103871493968, 103871522907, 103871522917, 103871522926, 103871522950,
    103871522970, 103871523051, 103871523052, 103871523061, 103871523071,
    103871523121, 103871523136, 103872970658, 103872970669, 103872970707, 103872970714,
}


def need(value, message):
    if not value: raise ValueError(message)


def assert_build(run, jobs):
    need(run.get('id') == BUILD_RUN and run.get('head_sha') == SOURCE and run.get('run_attempt') == 1
         and run.get('head_branch') == 'release/ui-v0.5.0' and run.get('status') == 'completed'
         and run.get('conclusion') == 'failure', 'original build identity/conclusion changed')
    rows = jobs.get('jobs', [])
    need(jobs.get('total_count') == 17 and len(rows) == 17
         and {r.get('id') for r in rows} == JOBS | {PUBLISH_JOB}, 'exact original jobs required')
    for row in rows:
        expected = 'failure' if row['id'] == PUBLISH_JOB else 'success'
        need(row.get('run_id') == BUILD_RUN and row.get('status') == 'completed'
             and row.get('conclusion') == expected, 'original prerequisite failed or identity differs')


def assert_release(release, tag, main, branch):
    need(release.get('id') == RELEASE and release.get('tag_name') == 'v0.5.0'
         and release.get('target_commitish') == SOURCE and release.get('draft') is False
         and release.get('prerelease') is True, 'not the existing public prerelease')
    for ref in (tag, main, branch):
        need(ref.get('object', {}).get('type') == 'commit' and ref['object'].get('sha') == SOURCE,
             'tag/main/release source mismatch')
    rows = release.get('assets', [])
    need(len(rows) == len(ASSETS) and {r.get('name') for r in rows} == set(ASSETS), 'asset set mismatch')
    for row in rows:
        size, digest = ASSETS[row['name']]
        need(row.get('state') == 'uploaded' and row.get('size') == size and row.get('digest') == 'sha256:' + digest,
             'public asset bytes differ: ' + row['name'])


def read_only_client(parent, token):
    class ReadOnly(parent):
        def request(self, method, path, data=None, allow_missing=False, upload=None):
            need(method == 'GET' and data is None and upload is None, 'release recovery forbids mutations')
            return super().request(method, path, allow_missing=allow_missing)
    return ReadOnly(token)


def unzip_checked(path, destination):
    with zipfile.ZipFile(path) as archive:
        rows = archive.infolist()
        need(len(rows) < 1000 and sum(r.file_size for r in rows) < 80 * 1024 * 1024, 'archive exceeds bounds')
        names = set()
        for row in rows:
            parts = Path(row.filename)
            need(not parts.is_absolute() and '..' not in parts.parts and '\\' not in row.filename
                 and row.filename not in names and not stat.S_ISLNK(row.external_attr >> 16), 'unsafe archive entry')
            names.add(row.filename)
        archive.extractall(destination)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('checkout', 'delivery', 'source-export', 'output'): p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(); a.checkout = a.checkout.resolve()
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == 'Eswink/coding-tools-mcp'
         and os.environ.get('GITHUB_REF') == 'refs/heads/verify/ui-v0.5.0', 'explicit verification workflow required')
    for name, expected in [('HEAD', SOURCE), ('HEAD^{tree}', TREE)]:
        actual = subprocess.check_output(['git', 'rev-parse', name], cwd=a.checkout, text=True).strip()
        need(actual == expected, 'checked out source mismatch')
    sys.path.insert(0, str(a.checkout / 'scripts'))
    import ui_release as original
    api = read_only_client(original.transport.GitHub, os.environ.get('GH_TOKEN', ''))
    assert_build(api.request('GET', f'/actions/runs/{BUILD_RUN}'),
                 api.request('GET', f'/actions/runs/{BUILD_RUN}/jobs?per_page=100'))
    def live():
        release = api.request('GET', '/releases/' + str(RELEASE))
        assert_release(release, api.request('GET', '/git/ref/tags/v0.5.0'),
            api.request('GET', '/git/ref/heads/main'), api.request('GET', '/git/ref/heads/release/ui-v0.5.0'))
        return release
    live()
    need({f.name for f in a.delivery.iterdir()} == set(ASSETS), 'original delivery set mismatch')
    assets = []
    for name, (size, digest) in ASSETS.items():
        path = a.delivery / name
        need(path.is_file() and not path.is_symlink() and path.stat().st_size == size
             and hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'original delivery corrupted')
        assets.append({'name': name, 'path': path, 'size': size, 'digest': 'sha256:' + digest,
                       'label': name, 'content_type': 'application/octet-stream'})
    a.output.mkdir(parents=True, exist_ok=False)
    collected = a.output / 'collected'
    unzip_checked(a.delivery / 'UI-evidence_v0.5.0.zip', collected)
    shutil.copytree(a.source_export, collected / 'exclusive-source')
    for name in list(ASSETS)[:3]:
        folder = 'exclusive-windows-package' if name.endswith('.exe') else 'exclusive-ubuntu-packages'
        shutil.copyfile(a.delivery / name, collected / folder / name)
    # Full original gates, no monkeypatch or weakened verifier; output is local only.
    recomposed, summary = original.compose(collected, a.output / 'recomposed', a.checkout,
        source=SOURCE, tree=TREE, version=VERSION, run_id=str(BUILD_RUN), ref=original.REF)
    need(summary == original.load(a.delivery / 'Release-scope_v0.5.0.json'), 'recomputed proof summary differs')
    for item in recomposed:
        need((item['size'], item['digest'][7:]) == ASSETS[item['name']], 'recomposed artifact differs')
    checks = original.anonymous_downloads(assets, VERSION)
    final = live()
    receipt = {'publication_verified': True, 'verification_read_only': True,
        'verification_run_id': os.environ['GITHUB_RUN_ID'], 'verification_source': os.environ['GITHUB_SHA'],
        'original_build_run': BUILD_RUN, 'original_build_conclusion': 'failure',
        'original_failed_job': PUBLISH_JOB, 'original_failure_phase': 'post-publication tag GET returned HTTP404',
        'all_16_build_source_native_jobs_passed': True, 'release_id': RELEASE, 'source_sha': SOURCE,
        'source_tree': TREE, 'version': VERSION, 'prerelease': True, 'published_at': final['published_at'],
        'mutations_performed': 0, 'assets': checks, 'recomputed_evidence': summary}
    (a.output / 'publication-recovery-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'publication_verified': True, 'release_id': RELEASE, 'assets': len(checks),
                      'mutations_performed': 0, 'original_run_preserved_as_failure': True}))

if __name__ == '__main__': main()
