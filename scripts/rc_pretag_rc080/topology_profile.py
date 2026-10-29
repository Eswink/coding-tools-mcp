"""Dedicated 0.8.0 topology admission anchored on main 9531007c (A0 merge, PR #172).

Independent of the rc070 anchor 3ea09a6f and of every 0.7.x admission pin: this
module imports neither and admits only linear single-parent descendants of M.
Frozen admission sources must stay byte-identical to M; the issue86 host may
differ from M only by the exact HOOK dispatch block. The probe manifest must be
M's manifest with exactly the changed rows recomputed (F -> M -> cascade); the
reviewed-source row may lag one cascade. Self-bytes are bound by the reviewed
source manifest, not by this module.
"""
import hashlib
import json
import subprocess

import rc_pretag_ownership_profile as o
import rc_pretag_publication_profile as p

M = '9531007c5a687407a362bee91cf18d751123c2f3'
M_TREE = 'bc3ae3ec571e043dbace17c2f6e7e72426e65913'
M_PARENTS = ('4e7e6bc0593dd5553236d46054c5e06549f89a1f', '357518a5e8b6b2f4dd2d6ab52c85b8c68bfa0c57')
M_RAW = (1189, '12ea9222b954f15ae7746b832661ddbff1b53f0100a5f0a5013b7f05c67f7873')
PACKAGE = 'scripts/rc_pretag_rc080/'
PROFILE = PACKAGE + 'topology_profile.py'
HOST = 'scripts/rc_pretag_issue86_root_identity_profile.py'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
REVIEWED = 'docs/releases/reviewed-source-manifest.json'
FROZEN_PREFIX = 'scripts/rc_pretag_'
ANCHOR = (b'    selected = rc070.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
          b'    if selected is not None:\n'
          b'        return selected\n')
HOOK = (b'    import rc_pretag_rc080.topology_profile as rc080\n'
        b'    selected = rc080.select(ref, root, git, entries, historical, release, release_tree, documents)\n'
        b'    if selected is not None:\n'
        b'        return selected\n')
MODES = (('100644', 'blob'), ('100755', 'blob'))
PROFILE_CAP = 200
DEPTH_LIMIT = 64
DELTA_PATHS = 600
DELTA_LINES = 40000


def topology(ref, root, git, release):
    """Admit M and linear descendants of M within DEPTH_LIMIT; merges fall through."""
    if release != p.R:
        raise o.TopologyError('rc080_release_anchor')
    if ref == M:
        return 0
    try:
        rows = git('rev-list', '--first-parent', '--parents', '--max-count=%d' % (DEPTH_LIMIT + 1), ref,
                   root=root).decode().split('\n')
    except subprocess.CalledProcessError as error:
        raise o.TopologyError('missing_parent') from error
    for depth, row in enumerate(line.split() for line in rows if line):
        if row[0] == M:
            return depth
        if len(row) != 2:
            raise o.TopologyError('rc080_candidate_parents')
    raise o.TopologyError('rc080_not_descendant')


def _blob(actual, path, root, git):
    return git('cat-file', 'blob', actual[path][2], root=root)


def _row(path, entry, raw):
    return dict(path=path, mode=entry[0], blob=entry[2], bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def _render(schema, rows):
    rows = sorted(rows.values(), key=lambda row: row['path'])
    return (json.dumps(dict(schema=schema, excludes_self=MANIFEST, entries=len(rows), rows=rows),
                       indent=1, sort_keys=True) + '\n').encode()


def _manifest_ok(previous, actual, changed, reviewed_rows, root, git):
    """M manifest with exactly the changed rows recomputed; REVIEWED may lag one cascade."""
    table = json.loads(previous)
    assert table['schema'] == 'rc-native-probe-source-manifest/v1' and table['excludes_self'] == MANIFEST
    rows = {row['path']: row for row in table['rows']}
    assert len(rows) == table['entries'] == len(table['rows']), 'rc080 manifest rows'
    for path in sorted(changed - {MANIFEST, REVIEWED}):
        if path in actual:
            rows[path] = _row(path, actual[path], _blob(actual, path, root, git))
        else:
            rows.pop(path, None)
    candidates = [rows.get(REVIEWED)] + list(reviewed_rows)
    data = _blob(actual, MANIFEST, root, git)
    return any(data == _render(table['schema'], dict(rows, **{REVIEWED: row})) for row in candidates if row)


def content(ref, root, git, entries):
    assert tuple(o._parents(M, root, git)) == M_PARENTS, 'rc080 M parents'
    assert git('rev-parse', M + '^{tree}', root=root).decode().strip() == M_TREE, 'rc080 M tree'
    raw = git('cat-file', 'commit', M, root=root)
    assert (len(raw), hashlib.sha256(raw).hexdigest()) == M_RAW, 'rc080 M raw'
    baseline = entries(M, root)
    if ref == M:
        return baseline
    actual = entries(ref, root)
    changed = {path for path in baseline.keys() | actual.keys() if baseline.get(path) != actual.get(path)}
    assert len(changed) <= DELTA_PATHS, 'rc080_delta_paths'
    assert all(actual[path][:2] in MODES for path in changed if path in actual), 'rc080_mode'
    frozen = sorted(path for path in changed if path.startswith(FROZEN_PREFIX)
                    and not path.startswith(PACKAGE) and path != HOST)
    assert not frozen, ('rc080_frozen', frozen)
    assert PROFILE in actual and HOST in actual and MANIFEST in actual and REVIEWED in actual, 'rc080_paths'
    assert len(_blob(actual, PROFILE, root, git).splitlines()) <= PROFILE_CAP, 'rc080_profile_cap'
    host = _blob(baseline, HOST, root, git)
    assert host.count(ANCHOR) == 1 and HOOK not in host, 'rc080_host_anchor'
    assert _blob(actual, HOST, root, git) == host.replace(ANCHOR, ANCHOR + HOOK), 'rc080_host_hook'
    lines = 0
    for row in git('diff', '--numstat', '--no-renames', M, ref, root=root).splitlines():
        added, deleted = row.split(b'\t')[:2]
        lines += 0 if added == b'-' else int(added) + int(deleted)
    assert lines <= DELTA_LINES, 'rc080_delta_lines'
    parent = o._parents(ref, root, git)[0]
    reviewed = {actual[REVIEWED], entries(parent, root)[REVIEWED]}
    reviewed_rows = [_row(REVIEWED, entry, git('cat-file', 'blob', entry[2], root=root)) for entry in sorted(reviewed)]
    previous = _blob(baseline, MANIFEST, root, git)
    assert _manifest_ok(previous, actual, changed, reviewed_rows, root, git), 'rc080 manifest'
    return actual


def select(ref, root, git, entries, historical, release, release_tree, documents):
    """Only topology mismatch delegates; selected content errors escape."""
    ref = o._commit(ref, root, git)
    try:
        topology(ref, root, git, release)
    except o.TopologyError:
        return None
    assert (release, release_tree, documents) == (p.R, p.R_TREE, p.R_DOCUMENTS), 'rc080_release'
    return content(ref, root, git, entries)
