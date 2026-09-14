"""Promote only the existing v0.5.0 metadata; preserve binary, tag and evidence bytes."""
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
import time
import zipfile

REPO = 'Eswink/coding-tools-mcp'
SOURCE = '63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076'
TREE = '01b11a1088d82501a1e579801ce6ac774ab5d43a'
BUILD = 34810770540
RELEASE = 388174565
FAILED_JOB = 103873894785
NAME = 'v0.5.0 — 新版桌面控制台 · Windows / Ubuntu'
BRANCH = 'refs/heads/release/stable-v0.5.0'
DOC_BRANCH = 'refs/heads/docs/stable-v0.5.0'
ALLOWED_FILES = {
    'README.md', 'README.en.md', 'docs/releases/stable-v0.5.0.md',
    'docs/specs/ui-refactor-v1/stable-release-plan.md',
    'scripts/stable_release_v050.py', 'scripts/stable_release_v050_tests.py',
    '.github/workflows/stable-release-v050.yml',
}
# Asset IDs, sizes and hashes were read from the existing public Release.
ASSETS = {
    'MCP_0.5.0_x64-setup.exe': (562709950, 5701414, 'ae831f5a4c0b233a344f837cf47516d33dc8522be6fcf2380e30526fff9c1ade'),
    'MCP_0.5.0_amd64.deb': (562709965, 9912422, 'c06757aa380aa0e2a0cdddb5b6a2a97004aeafbc348d4aa660d9d7b3d2c8a20b'),
    'MCP_0.5.0_amd64.AppImage': (562709988, 86841848, '86b95dcd3f3bf8da6b334d937d033e7870858326e969b577a9ebfc4606d24fec'),
    'UI-evidence_v0.5.0.zip': (562710081, 22015863, '7f67cdababf0709a44ee2fb6486160cf2abd74584eb9d255e6a9ef3c002bceaf'),
    'Verification_v0.5.0.md': (562710110, 4136, 'c1972692a6a5ebd2f4b269b1cb47f36c272e599709a0f5ce40d8b6880a26ea8f'),
    'Release-scope_v0.5.0.json': (562710123, 2675, '534aa69724ddc28ae5c2acf00abf5799be5149ac3fb2d93cb7328e1c8310ca55'),
    'SHA256SUMS_v0.5.0.txt': (562710138, 537, '36b210307bdaf77c2813257a24c1bff695435bc862b4b9a5e9f8ba9213d1de7f'),
}
JOBS = {103871493968, 103871522907, 103871522917, 103871522926, 103871522950,
        103871522970, 103871523051, 103871523052, 103871523061, 103871523071,
        103871523121, 103871523136, 103872970658, 103872970669, 103872970707, 103872970714}


def need(value, message):
    if not value:
        raise ValueError(message)


def check_release(release, tag, branch):
    need(release.get('id') == RELEASE and release.get('tag_name') == 'v0.5.0'
         and release.get('target_commitish') == SOURCE and release.get('draft') is False
         and type(release.get('prerelease')) is bool, 'release identity/type differs')
    for ref in (tag, branch):
        need(ref.get('object', {}).get('type') == 'commit' and ref['object'].get('sha') == SOURCE,
             'immutable product ref changed')
    rows = release.get('assets', [])
    need(len(rows) == 7 and {r.get('name') for r in rows} == set(ASSETS), 'asset set differs')
    for row in rows:
        aid, size, digest = ASSETS[row['name']]
        need(row.get('id') == aid and row.get('size') == size and row.get('digest') == 'sha256:' + digest
             and row.get('state') == 'uploaded', 'immutable asset differs: ' + row['name'])


def check_build(run, jobs):
    need(run.get('id') == BUILD and run.get('head_sha') == SOURCE and run.get('run_attempt') == 1
         and run.get('head_branch') == 'release/ui-v0.5.0' and run.get('status') == 'completed'
         and run.get('conclusion') == 'failure', 'original build identity/conclusion changed')
    rows = jobs.get('jobs', [])
    need(jobs.get('total_count') == 17 and len(rows) == 17
         and {r.get('id') for r in rows} == JOBS | {FAILED_JOB}, 'original job set differs')
    for row in rows:
        need(row.get('run_id') == BUILD and row.get('status') == 'completed'
             and row.get('conclusion') == ('failure' if row['id'] == FAILED_JOB else 'success'),
             'original prerequisite failed or history rewritten')


def metadata_client(parent, token, *, permitted, source, notes):
    class MetadataOnly(parent):
        attempted = False

        def request(self, method, path, data=None, allow_missing=False, upload=None):
            if method == 'GET':
                need(data is None and upload is None, 'GET with payload rejected')
            else:
                need(permitted and not self.attempted and method == 'PATCH'
                     and path == f'/releases/{RELEASE}' and upload is None
                     and data == {'name': NAME, 'body': notes, 'prerelease': False, 'make_latest': 'true'},
                     'only one approved metadata PATCH is allowed')
                main = super().request('GET', '/git/ref/heads/main')
                need(main.get('object', {}).get('type') == 'commit'
                     and main['object'].get('sha') == source, 'main moved before promotion')
                self.attempted = True  # A timed-out request may have succeeded. Never retry a write.
            return super().request(method, path, data, allow_missing=allow_missing, upload=upload)
    return MetadataOnly(token)


def unzip_checked(path, destination):
    with zipfile.ZipFile(path) as archive:
        rows = archive.infolist()
        need(len(rows) < 1000 and sum(r.file_size for r in rows) < 80 * 1024 * 1024, 'archive exceeds bounds')
        names = set()
        for row in rows:
            p = Path(row.filename)
            need(not p.is_absolute() and '..' not in p.parts and '\\' not in row.filename
                 and row.filename not in names and not stat.S_ISLNK(row.external_attr >> 16), 'unsafe archive entry')
            names.add(row.filename)
        archive.extractall(destination)


def recompose(original, checkout, delivery, source_export, output):
    need({f.name for f in delivery.iterdir()} == set(ASSETS), 'delivery set differs')
    assets = []
    for name, (_, size, digest) in ASSETS.items():
        p = delivery / name
        need(p.is_file() and not p.is_symlink() and p.stat().st_size == size
             and hashlib.sha256(p.read_bytes()).hexdigest() == digest, 'delivery bytes differ: ' + name)
        assets.append({'name': name, 'path': p, 'size': size, 'digest': 'sha256:' + digest,
                       'label': name, 'content_type': 'application/octet-stream'})
    collected = output / 'collected'
    unzip_checked(delivery / 'UI-evidence_v0.5.0.zip', collected)
    shutil.copytree(source_export, collected / 'exclusive-source')
    for name in list(ASSETS)[:3]:
        folder = 'exclusive-windows-package' if name.endswith('.exe') else 'exclusive-ubuntu-packages'
        shutil.copyfile(delivery / name, collected / folder / name)
    recomposed, summary = original.compose(collected, output / 'recomposed', checkout,
        source=SOURCE, tree=TREE, version='0.5.0', run_id=str(BUILD), ref=original.REF)
    need(summary == original.load(delivery / 'Release-scope_v0.5.0.json'), 'original evidence differs')
    need(len(recomposed) == 7 and {a['name'] for a in recomposed} == set(ASSETS), 'recomposed set differs')
    for a in recomposed:
        need((a['size'], a['digest'][7:]) == ASSETS[a['name']][1:], 'recomposed bytes differ')
    return assets, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('checkout', 'delivery', 'source-export', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--promote', action='store_true')
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    commit = os.environ.get('GITHUB_SHA', '')
    need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REPOSITORY') == REPO
         and os.environ.get('GITHUB_REF') in (BRANCH, DOC_BRANCH), 'approved hosted workflow required')
    need(not args.promote or os.environ.get('GITHUB_REF') == BRANCH, 'promotion branch required')
    for cwd, ref, expected in ((root, 'HEAD', commit), (args.checkout, 'HEAD', SOURCE),
                               (args.checkout, 'HEAD^{tree}', TREE)):
        need(subprocess.check_output(['git', 'rev-parse', ref], cwd=cwd, text=True).strip() == expected,
             'checkout identity differs')
    changed = set(subprocess.check_output(['git', 'diff', '--name-only', '-z', SOURCE, commit], cwd=root).decode().strip('\0').split('\0'))
    need(changed and changed <= ALLOWED_FILES, 'unexpected product/source changes')
    sys.path.insert(0, str(args.checkout.resolve() / 'scripts'))
    import ui_release as original
    notes = (root / 'docs/releases/stable-v0.5.0.md').read_text(encoding='utf-8')
    api = metadata_client(original.transport.GitHub, os.environ.get('GH_TOKEN', ''),
                          permitted=args.promote, source=commit, notes=notes)
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {'completed': False, 'metadata_commit': commit, 'product_source': SOURCE, 'product_tree': TREE,
               'run_id': os.environ['GITHUB_RUN_ID'], 'original_build_run': BUILD,
               'original_build_conclusion': 'failure', 'release_id': RELEASE, 'stage': 'verify',
               'assets_replaced': False, 'tags_moved': False}
    try:
        check_build(api.request('GET', f'/actions/runs/{BUILD}'),
                    api.request('GET', f'/actions/runs/{BUILD}/jobs?per_page=100'))
        def live():
            value = api.request('GET', f'/releases/{RELEASE}')
            check_release(value, api.request('GET', '/git/ref/tags/v0.5.0'),
                          api.request('GET', '/git/ref/heads/release/ui-v0.5.0'))
            return value
        before = live()
        assets, summary = recompose(original, args.checkout.resolve(), args.delivery, args.source_export, args.output)
        receipt['original_evidence'] = summary
        receipt['anonymous_before'] = original.anonymous_downloads(assets, '0.5.0')
        check = live()
        need(check['published_at'] == before['published_at'], 'publication identity changed')
        receipt['stage'] = 'verified'
        if args.promote:
            # Latest must not move away from an already newer full release.
            latest = api.request('GET', '/releases/latest', allow_missing=True)
            if latest and latest.get('id') != RELEASE:
                need(latest.get('tag_name') in ('v0.4.0', 'v0.3.2', 'v0.3.1', 'v0.3.0', 'v0.2.6', 'v0.2.5'),
                     'unexpected existing Latest; review before promotion')
            receipt['stage'] = 'metadata-promotion'
            api.request('PATCH', f'/releases/{RELEASE}',
                        {'name': NAME, 'body': notes, 'prerelease': False, 'make_latest': 'true'})
            # Only read-side visibility is retried, never the PATCH or asset downloads.
            for attempt in range(10):
                final = live()
                latest = api.request('GET', '/releases/latest', allow_missing=True)
                if final['prerelease'] is False and latest and latest.get('id') == RELEASE:
                    break
                time.sleep(2)
            need(final['prerelease'] is False and latest and latest.get('id') == RELEASE
                 and latest.get('draft') is False and latest.get('prerelease') is False
                 and final.get('name') == NAME and final.get('body') == notes, 'stable/Latest readback incomplete')
            receipt['anonymous_after'] = original.anonymous_downloads(assets, '0.5.0')
            final = live()
            need(api.request('GET', '/git/ref/heads/main')['object']['sha'] == commit, 'main moved after promotion')
            receipt.update(prerelease=final['prerelease'], draft=final['draft'], latest=True)
        receipt.update(completed=True, stage='completed', promotion=args.promote,
                       immutable_assets={n: {'id': v[0], 'size': v[1], 'sha256': v[2]} for n, v in ASSETS.items()})
    finally:
        receipt['metadata_patch_attempted'] = api.attempted
        (args.output / 'stable-promotion-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'completed': True, 'promotion': args.promote, 'metadata_patch_attempted': api.attempted}))


if __name__ == '__main__':
    main()
