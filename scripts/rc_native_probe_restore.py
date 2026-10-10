"""Restore the immutable publisher candidate without carrier contamination."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

BACKUP = 'dab238dc34d5a59f471aff935c728c1ed809cc78'
PARENT = '13cd343d942b7a68912d42a8f9235c02ed647764'
FINITE11 = '733a1d5bd53ae0f3b2c3fe44463ac20566c6c47f'
TREE = 'b9cfb8a0b58f8e0863c764e50cf3d38920eefeae'
FAMILY = 'development-backups/rc070/20261009/'
FULL52 = FAMILY+'checkpoint-01/publisher-historical-finite11/source.patch'
ONLY8 = FAMILY+'checkpoint-02/publisher-frozen02-source-only/source.patch'
WHOLE = FAMILY+'checkpoint-02/publisher-frozen02-source-only/SOURCE-TREE.json'
PAYLOADS = ((FULL52, 402164, 'b0636194b0b5b51430242f1bdfbb72a59940ec46b09240ff4b9e9a6734b5ff35'),
            (ONLY8, 44498, 'e0ee17cff76799f96dd0aa0af2043495076594ddb96fefd134458fc5288e1128'),
            (WHOLE, 492335, 'da3719558d66e0556c8c70125461a5b66a96c427192fca7405c373e77daa6b5d'))
RUNNER_SHA = 'ecfd57ec3d5d8e669076f86a56f869ce65b82d6a5fd7382e04dd3f4505343c0c'
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


def whole_source(root, rows):
    root = Path(root)
    tracked = git(root, 'ls-files', '-z').decode().split('\0')[:-1]
    assert len(rows) == len(tracked) == 1878 and len(set(tracked)) == 1878
    assert set(tracked) == {r['path'] for r in rows}
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
    assert git(root, 'write-tree').decode().strip() == TREE
    assert git(root, 'status', '--porcelain', '--untracked-files=all').decode() == ''
    return source


def restore(management, output):
    management, output = Path(management).resolve(), Path(output).resolve()
    assert not output.exists() and output != management and management not in output.parents
    output.mkdir()
    raw_payloads = {}
    for path, size, digest in PAYLOADS:
        raw = git(management, 'show', BACKUP+':'+path)
        assert len(raw) == size and sha(raw) == digest
        raw_payloads[path] = raw
    manifest = json.loads(raw_payloads[WHOLE])
    assert manifest['tree'] == TREE and manifest['entries'] == len(manifest['rows']) == 1878
    root = output/'pure-sut'
    subprocess.run(['/usr/bin/git', '-c', 'core.hooksPath=/dev/null', 'clone', '--no-hardlinks',
                    '--no-checkout', '--', str(management), str(root)], capture_output=True, check=True,
                   timeout=30, env=ENV)
    git(root, 'checkout', '--detach', PARENT)
    git(root, 'apply', '--check', '--index', '-', data=raw_payloads[FULL52])
    git(root, 'apply', '--index', '-', data=raw_payloads[FULL52])
    assert git(root, 'write-tree').decode().strip() == FINITE11
    assert len(git(root, 'ls-files', '-z').split(b'\0'))-1 == 1877
    git(root, 'apply', '--check', '--index', '-', data=raw_payloads[ONLY8])
    git(root, 'apply', '--index', '-', data=raw_payloads[ONLY8])
    assert git(root, 'write-tree').decode().strip() == TREE
    private = git(root, 'commit-tree', TREE, '-p', PARENT, data=b'Sealed native source probe; not a release candidate grant\n').decode().strip()
    git(root, 'reset', '--hard', private)
    assert git(root, 'rev-list', '--parents', '-n', '1', private).decode().split() == [private, PARENT]
    source = whole_source(root, manifest['rows'])
    index = sha(git(root, 'ls-files', '--stage', '-z'))
    assert index == 'eb1c0600b9314ac74702a228e852b245f6c57284cc6bed1f9a54014ae7ed945c'
    context = dict(root=str(root), backup=BACKUP, parent=PARENT, private_commit=private, tree=TREE,
                   count=1878, rows=manifest['rows'], source=source, index_sha256=index,
                   source_manifest_sha256=sha(raw_payloads[WHOLE]),
                   payloads=[dict(path=p, bytes=n, sha256=s) for p,n,s in PAYLOADS],
                   qualification=False, historical_local85='FAILED_50_named_PASS_35_non_success',
                   current_CI85='NOT_RUN', current_CI300='NOT_RUN')
    write(output/'SOURCE-RESTORATION.json', context)
    return context
