"""Verify a pre-reviewed frozen cumulative source manifest, never generate one."""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import re
import subprocess
from source_provenance_gate import verify as verify_provenance

BASE = '758c60a6e74e624e144f9c19c5f19d04d17f7a13'
MANIFEST = 'docs/releases/reviewed-source-manifest.json'
SHA = re.compile(r'[0-9a-f]{40}')
LIMIT = 8 * 1024 * 1024
LEGACY_BRANCH = 'feat/cloud-gateway-agent-runtime'


def require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(['git', *arguments], cwd=root, timeout=30)


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate manifest key')
        value[key] = item
    return value


def blob(root: Path, revision: str, path: str) -> dict | None:
    return _blob(root, revision, path, None)


def _blob(root, revision, path, reader):
    # Private owner sharing only; public gates accept controls, never a reader.
    raw = (git(root, 'ls-tree', '-z', revision, '--', path) if reader is None
           else reader.tree_entry(revision, path))
    if not raw:
        return None
    entries = raw.rstrip(b'\0').split(b'\0')
    require(len(entries) == 1, 'ambiguous source entry')
    metadata, found = entries[0].split(b'\t', 1)
    mode, kind, sha = metadata.decode('ascii').split()
    require(found.decode('utf-8') == path and kind == 'blob', 'source entry must be a Git blob')
    require(mode in ('100644', '100755', '120000'), 'unsupported source file mode')
    data = git(root, 'cat-file', 'blob', sha) if reader is None else reader.blob_bytes(sha)
    return {'mode': mode, 'blob_sha': sha, 'sha256': hashlib.sha256(data).hexdigest()}


def verify(root: Path, source: str, *, baseline: str = BASE, deadline=None, check_active=None) -> dict:
    # baseline override is for isolated unit fixtures only; CLI has no override.
    require(SHA.fullmatch(source) is not None and SHA.fullmatch(baseline) is not None, 'invalid source identity')
    budget = {} if deadline is None and check_active is None else dict(deadline=deadline, check_active=check_active)
    provenance = verify_provenance(root, source, **budget)
    owner = nullcontext()
    if budget:
        from rc_consumer_fixed_git import Reader
        owner = Reader(root, **budget)
    with owner as reader:
        result = _verify(root, source, baseline, provenance, reader)
    if budget:
        reader.check()
    return result


def _verify(root, source, baseline, provenance, reader):
    if reader is None:
        subprocess.run(['git', 'merge-base', '--is-ancestor', baseline, source], cwd=root, timeout=30, check=True)
    elif not reader.ancestor(baseline, source):
        raise subprocess.CalledProcessError(1, ['git', 'merge-base', '--is-ancestor', baseline, source])
    manifest_blob = _blob(root, source, MANIFEST, reader)
    require(manifest_blob is not None and manifest_blob['mode'] == '100644',
            'BLOCKED: tracked parent-reviewed frozen source manifest is required')
    raw = (git(root, 'cat-file', 'blob', manifest_blob['blob_sha']) if reader is None
           else reader.blob_bytes(manifest_blob['blob_sha']))
    require(0 < len(raw) <= LIMIT, 'invalid manifest size')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite manifest value')))
    require(type(value) is dict and set(value) == {'schema', 'base_commit', 'version', 'review_reference', 'entries'},
            'invalid manifest schema fields')
    require(type(value['schema']) is int and value['schema'] == 1 and value['base_commit'] == baseline,
            'manifest schema or pinned baseline mismatch')
    require(value['version'] == provenance['version'], 'reviewed product version mismatch')
    require(type(value['review_reference']) is str and 1 <= len(value['review_reference']) <= 500,
            'human review reference required; this is not approval proof')
    entries = value['entries']
    require(type(entries) is list and len(entries) <= 10000, 'invalid reviewed entry list')
    actual = {}
    raw = (git(root, 'diff', '--name-status', '--no-renames', '-z', baseline, source) if reader is None
           else reader.changes(baseline, source))
    parts = raw.split(b'\0')
    require(parts[-1] == b'' and (len(parts) - 1) % 2 == 0, 'invalid Git diff framing')
    for offset in range(0, len(parts) - 1, 2):
        status, path = parts[offset].decode('ascii'), parts[offset + 1].decode('utf-8')
        if path == MANIFEST:
            continue
        require(status in ('A', 'M', 'D', 'T'), 'unsupported source status')
        before, after = _blob(root, baseline, path, reader), _blob(root, source, path, reader)
        require(after is None or after['mode'] in ('100644', '100755'), 'candidate symlinks are not permitted')
        actual[path] = {'path': path, 'status': status, 'before': before, 'after': after}
    reviewed = {}
    for entry in entries:
        require(type(entry) is dict and set(entry) == {'path', 'status', 'before', 'after'}, 'invalid entry fields')
        path = entry['path']
        require(type(path) is str and path and path != MANIFEST and not path.startswith('/')
                and all(part not in ('', '.', '..') for part in path.split('/'))
                and not any(ord(c) < 32 for c in path) and '\\' not in path,
                'invalid or excluded reviewed path')
        require(path not in reviewed, 'duplicate reviewed path')
        reviewed[path] = entry
    require(list(reviewed) == sorted(reviewed), 'reviewed entries must be sorted')
    require(reviewed == actual, 'frozen reviewed source differs in paths/status/mode/blob/content')
    return {'passed': True, 'source_sha': source,
            'source_tree': (git(root, 'rev-parse', 'HEAD^{tree}').decode().strip() if reader is None
                            else reader.read('rev-parse', 'HEAD^{tree}')),
            'base_commit': baseline, 'version': provenance['version'], 'entry_count': len(entries),
            'metadata_exclusion': MANIFEST, 'manifest_blob': manifest_blob,
            'review_reference': value['review_reference'], 'publish_approved': False,
            'trust': 'Repository consistency only; external code review and branch protection establish approval'}


def select_route(root: Path, source: str, *, head_ref: str = '', ref: str = '') -> dict:
    """Choose the required validator, never approval or a fallback after failure."""
    require(SHA.fullmatch(source) is not None, 'invalid source identity')
    require(git(root, 'rev-parse', 'HEAD').decode().strip() == source,
            'checkout does not match expected source SHA')
    clean = subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--'], cwd=root, timeout=30)
    require(clean.returncode == 0, 'tracked source differs from the candidate commit')
    # Only the immutable Git tree can select cumulative review. An untracked
    # file cannot opt the old branch out of its strict additive scope guard.
    manifest = blob(root, source, MANIFEST)
    legacy = head_ref == LEGACY_BRANCH if head_ref else ref == 'refs/heads/' + LEGACY_BRANCH
    mode = 'isolated-increment' if legacy and manifest is None else 'reviewed-cumulative'
    return {'scope_mode': mode, 'source_sha': source, 'publish_approved': False,
            'trust': 'Routing only; the selected validator and required CI must still pass'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--expect-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--select-route', action='store_true')
    parser.add_argument('--head-ref', default='')
    parser.add_argument('--ref', default='')
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    require(args.github_output is None or args.select_route, '--github-output requires --select-route')
    value = (select_route(args.root.resolve(), args.expect_sha, head_ref=args.head_ref, ref=args.ref)
             if args.select_route else verify(args.root.resolve(), args.expect_sha))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    if args.github_output is not None:
        with args.github_output.open('a', encoding='utf-8') as output:
            output.write('scope_mode=' + value['scope_mode'] + '\n')
    print(json.dumps(value))


if __name__ == '__main__':
    main()
