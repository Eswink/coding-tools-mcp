"""Restore the immutable publisher candidate without carrier contamination."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

BASE = 'c60f9667fa8431e27fabbc497c19b4abfef5b965'
MANIFEST = 'scripts/rc_native_probe_source_manifest.json'
FINGERPRINT_FIELDS = ('github_sha', 'tree', 'file_count', 'index_sha256', 'manifest_sha256')
RUNNER_SHA = 'e7661d77e02f6c0eb00127247ad0045dde9230aeedb1636af278f2c031e0b231'
FIXTURE_SHA = '233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5'
ENV = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
       'GIT_TERMINAL_PROMPT': '0', 'GIT_AUTHOR_NAME': 'RC native source probe',
       'GIT_AUTHOR_EMAIL': 'rc-native-source-probe@invalid', 'GIT_COMMITTER_NAME': 'RC native source probe',
       'GIT_COMMITTER_EMAIL': 'rc-native-source-probe@invalid',
       'GIT_AUTHOR_DATE': '2026-10-09T00:00:00Z', 'GIT_COMMITTER_DATE': '2026-10-09T00:00:00Z'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def read_regular(path):
    """Read only an owned single-link regular file via nofollow directory FDs."""
    path = Path(path).absolute()
    assert path.is_absolute() and '..' not in path.parts
    directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    fd = None
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid()
        assert not before.st_mode & 0o022 and 0 <= before.st_size <= 32*1024*1024
        raw = bytearray()
        while True:
            chunk = os.read(fd, min(1024*1024, before.st_size-len(raw)+1))
            if not chunk:
                break
            raw.extend(chunk)
            assert len(raw) <= before.st_size
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        assert all(getattr(before, key) == getattr(after, key) for key in fields) and len(raw) == before.st_size
        return bytes(raw)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def git(root, *values, data=None):
    return subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                           '-C', str(root), *values], input=data, capture_output=True, check=True,
                          timeout=30, env=ENV).stdout


def checkout_files(root):
    """Every regular file in the working tree, excluding .git."""
    root = Path(root)
    found = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not (Path(dirpath) == root and d == '.git')]
        for name in filenames + [d for d in dirnames if (Path(dirpath)/d).is_symlink()]:
            found.add((Path(dirpath)/name).relative_to(root).as_posix())
    # Build byproducts the repository already ignores (e.g. __pycache__) are not source; everything else counts.
    ignored = set(git(root, 'ls-files', '-z', '--others', '--ignored', '--exclude-standard').decode().split('\0')[:-1])
    return found - ignored


def set_diff(manifest_paths, tracked, files):
    """Bidirectional comparison; empty dict means identical."""
    expected = set(manifest_paths) | {MANIFEST}
    diff = {}
    for label, actual in (('git_index', set(tracked)), ('checkout', set(files))):
        missing, extra = sorted(expected - actual), sorted(actual - expected)
        if missing or extra:
            diff[label] = dict(missing_from_actual=missing, extra_in_actual=extra)
    return diff


def whole_source(root, rows, tree):
    root = Path(root)
    tracked = git(root, 'ls-files', '-z').decode().split('\0')[:-1]
    assert len(tracked) == len(set(tracked))
    diff = set_diff([r['path'] for r in rows], tracked, checkout_files(root))
    assert not diff, 'manifest/checkout file set mismatch: '+json.dumps(diff, sort_keys=True)
    source = {}
    stages = git(root, 'ls-files', '--stage', '-z').decode().split('\0')[:-1]
    actual_stages = {}
    for line in stages:
        header, path = line.split('\t', 1)
        mode, blob, stage = header.split()
        assert stage == '0'
        actual_stages[path] = (mode, blob)
    for row in rows:
        rel = Path(row['path'])
        assert not rel.is_absolute() and '..' not in rel.parts and row['mode'] in ('100644', '100755')
        path = root/rel
        assert all(not q.is_symlink() for q in [path, *path.parents] if q != root.parent)
        info = path.lstat()
        raw = path.read_bytes()
        assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
        mode = {'100644': 0o644, '100755': 0o755}[row['mode']]
        blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        assert (stat.S_IMODE(info.st_mode), len(raw), sha(raw), blob) == (mode, row['bytes'], row['sha256'], row['blob'])
        assert actual_stages[row['path']] == (row['mode'], row['blob'])
        source[row['path']] = dict(size=len(raw), mode=mode, sha256=sha(raw))
    assert git(root, 'write-tree').decode().strip() == tree
    assert git(root, 'status', '--porcelain', '--untracked-files=all').decode() == ''
    return source


def manifest_rows(root):
    """Generator: rows for every tracked file except the manifest itself."""
    root = Path(root)
    rows = []
    for line in git(root, 'ls-files', '--stage', '-z').decode().split('\0')[:-1]:
        header, path = line.split('\t', 1)
        mode, blob, _ = header.split()
        if path == MANIFEST:
            continue
        raw = (root/path).read_bytes()
        rows.append(dict(path=path, mode=mode, blob=blob, bytes=len(raw), sha256=sha(raw)))
    return sorted(rows, key=lambda r: r['path'])


def fingerprint(root, github_sha):
    root = Path(root)
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    assert head == github_sha, 'HEAD %s != GITHUB_SHA %s' % (head, github_sha)
    return dict(github_sha=head, tree=git(root, 'rev-parse', 'HEAD^{tree}').decode().strip(),
                file_count=len(git(root, 'ls-files', '-z').split(b'\0'))-1,
                index_sha256=sha(git(root, 'ls-files', '--stage', '-z')),
                manifest_sha256=sha(git(root, 'show', 'HEAD:'+MANIFEST)))


def verify_runner(path):
    actual = sha(Path(path).read_bytes())
    if actual != RUNNER_SHA:
        raise AssertionError('runner sha mismatch: expected %s actual %s' % (RUNNER_SHA, actual))
    return actual


def evaluate(counts, fingerprints, head):
    """Valid only if both QUALIFIED, fingerprints identical field by field, and equal to PR head."""
    problems = []
    for name in ('necessary85', 'original300'):
        if counts.get(name) != 'QUALIFIED':
            problems.append('%s not QUALIFIED: %s' % (name, counts.get(name)))
    a, b = fingerprints.get('necessary85'), fingerprints.get('original300')
    if a is None or b is None:
        problems.append('missing fingerprint')
    else:
        for key in FINGERPRINT_FIELDS:
            if a.get(key) != b.get(key):
                problems.append('fingerprint %s differs: %s != %s' % (key, a.get(key), b.get(key)))
        if a.get('github_sha') != head:
            problems.append('fingerprint github_sha %s != head %s' % (a.get('github_sha'), head))
    return dict(valid=not problems, problems=problems)


def restore(management, output, github_sha):
    management, output = Path(management).resolve(), Path(output).resolve()
    assert not output.exists() and output != management and management not in output.parents
    output.mkdir()
    head = git(management, 'rev-parse', 'HEAD').decode().strip()
    assert head == github_sha, 'management HEAD %s != GITHUB_SHA %s' % (head, github_sha)
    ancestor = subprocess.run(['/usr/bin/git', '-C', str(management), 'merge-base', '--is-ancestor', BASE, head],
                              capture_output=True, timeout=30, env=ENV)
    assert ancestor.returncode == 0, 'base %s is not an ancestor of %s' % (BASE, head)
    root = output/'pure-sut'
    subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-hardlinks',
                    '--no-checkout', '--', str(management), str(root)], capture_output=True, check=True,
                   timeout=120, env=ENV)
    git(root, 'checkout', '--detach', github_sha)
    raw_manifest = git(root, 'show', 'HEAD:'+MANIFEST)
    manifest = json.loads(raw_manifest)
    tree = git(root, 'rev-parse', 'HEAD^{tree}').decode().strip()
    source = whole_source(root, manifest['rows'], tree)
    fp = fingerprint(root, github_sha)
    context = dict(root=str(root), base=BASE, private_commit=head, tree=tree, count=fp['file_count'],
                   rows=manifest['rows'], source=source, index_sha256=fp['index_sha256'],
                   source_manifest_sha256=fp['manifest_sha256'], fingerprint=fp,
                   evidence_subject='layer commit '+head+' (not frozen b9cfb8a0)',
                   frozen02='UNQUALIFIED', current_CI85='NOT_RUN', current_CI300='NOT_RUN')
    write(output/'SOURCE-RESTORATION.json', context)
    return context
