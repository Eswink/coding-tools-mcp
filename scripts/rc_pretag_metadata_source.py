"""Read-only exact source scope; this does not confer release/security authority.

Staged mode is a prospective index review, not published-source evidence. Git tree
objects are reconstructed in memory; no object, index, reference or file is written.
The sole predecessor exception is one exact pinned historical scope-test blob.
Commit objects are bounded local memory only; identity/message bytes are discarded.
Only inventoried working files are checked. Untracked/ignored tooling is not source
and this result does not claim a generally clean or atomic filesystem snapshot.
"""
from dataclasses import dataclass, field
import hashlib
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

BASE_SHA = '1dfe6b0f3aff7c51e90fcd624b838948e518800c'
BASE_TREE = '0d251466e935e4689f7350d6be56a8caad86f512'
BASE_COUNT = 1628
PARENT_SHA = '229990a2daebac89a796dac2b31c20ab7254a227'
PARENT_TREE = 'ce28e65f86132339d3962166d34efb9b4f968f43'
GUARD_PATH = 'scripts/rc_publication_boundary_tests.py'
GUARD_BLOB = '85627ca59cc6b7d700af30867c1e7aa0c8fb547f'
ADDITIONS = tuple(sorted([
    '.github/workflows/rc-pretag-metadata-checks.yml',
    *('docs/specs/issue-88-pretag-metadata/' + name + '.md'
      for name in ('requirements', 'design', 'tasks')),
    *('scripts/' + name + '.py' for name in (
        'rc_pretag_metadata', 'rc_pretag_metadata_types', 'rc_pretag_metadata_api',
        'rc_pretag_metadata_worker', 'rc_pretag_metadata_fixtures',
        'rc_pretag_metadata_tests', 'rc_pretag_metadata_api_tests',
        'rc_pretag_metadata_boundary_tests', 'rc_pretag_metadata_live',
        'rc_pretag_metadata_live_tests',
        'rc_pretag_metadata_source', 'rc_pretag_metadata_source_tests')),
]))
MAX_ENTRIES, MAX_OUTPUT, MAX_TOTAL_OUTPUT = 4096, 1024 * 1024, 8 * 1024 * 1024
MAX_FILE, MAX_TOTAL_FILES = 4 * 1024 * 1024, 64 * 1024 * 1024
MAX_COMMANDS, COMMAND_SECONDS, TOTAL_SECONDS = 12, 5, 30
SHA = re.compile(r'[0-9a-f]{40}\Z')


class SourceVerificationError(ValueError):
    """Only a fixed diagnostic code is exposed; never Git stderr or file content."""


@dataclass(frozen=True)
class Entry:
    path: str
    mode: str
    oid: str


@dataclass(frozen=True)
class SourceVerification:
    mode: str
    source_sha: str
    source_tree: str
    parent_sha: str
    parent_tree: str
    predecessor_count: int
    unchanged_predecessor_count: int
    guard_path: str
    guard_blob: str
    additions: tuple
    working_bytes: int
    baseline_sha: str
    baseline_tree: str
    source_verified: bool = field(default=True, init=False)
    published_candidate: bool = field(default=False, init=False)
    release_approved: bool = field(default=False, init=False)
    publish_approved: bool = field(default=False, init=False)
    security_approved: bool = field(default=False, init=False)
    snapshot_atomic: bool = field(default=False, init=False)


def require(condition, code):
    if not condition:
        raise SourceVerificationError(code)


def valid_sha(value):
    require(type(value) is str and SHA.fullmatch(value) is not None, 'invalid_sha')
    return value


def valid_path(path):
    require(type(path) is str, 'invalid_path')
    try:
        require(0 < len(path.encode('utf-8')) <= 512, 'invalid_path')
    except UnicodeError:
        raise SourceVerificationError('invalid_path') from None
    require(not any(ord(c) < 32 or ord(c) == 127 for c in path), 'invalid_path')
    parts = path.split('/')
    require(len(parts) <= 32 and all(p not in ('', '.', '..') for p in parts),
            'invalid_path')
    require('\\' not in path and all(p.casefold() != '.git' for p in parts),
            'invalid_path')
    return parts


def inventory(entries):
    require(type(entries) in (tuple, list) and len(entries) <= MAX_ENTRIES,
            'inventory_limit')
    result = {}
    for entry in entries:
        require(type(entry) is Entry, 'invalid_entry')
        valid_path(entry.path)
        require(entry.mode == '100644', 'invalid_mode')
        valid_sha(entry.oid)
        require(entry.path not in result, 'duplicate_path')
        result[entry.path] = entry
    for path in result:
        parts = path.split('/')
        require(all('/'.join(parts[:i]) not in result for i in range(1, len(parts))),
                'path_conflict')
    return result


def object_hash(kind, data):
    return hashlib.sha1(kind + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def tree_hash(entries):
    """Pure canonical SHA1 Git tree calculation, including every path/blob/mode."""
    root = {}
    for entry in inventory(entries).values():
        node = root
        parts = entry.path.split('/')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = entry
    def digest(node):
        rows = []
        for name, value in node.items():
            directory = type(value) is dict
            oid = digest(value) if directory else value.oid
            mode = '40000' if directory else value.mode
            rows.append((name.encode() + (b'/' if directory else b''),
                         mode.encode() + b' ' + name.encode() + b'\0' + bytes.fromhex(oid)))
        return object_hash(b'tree', b''.join(row for _, row in sorted(rows)))
    return digest(root)


def validate_inventory(base_entries, candidate_entries, *, expected_base_tree,
                       expected_candidate_tree, expected_base_count=BASE_COUNT,
                       expected_additions=ADDITIONS):
    """Pure exact validator; fixture-specific expectations do not alter live pins."""
    valid_sha(expected_base_tree)
    valid_sha(expected_candidate_tree)
    base, candidate = inventory(base_entries), inventory(candidate_entries)
    require(type(expected_base_count) is int and len(base) == expected_base_count,
            'base_count_mismatch')
    require(type(expected_additions) is tuple and len(expected_additions) <= 32,
            'invalid_additions')
    for path in expected_additions:
        valid_path(path)
    wanted = set(expected_additions)
    require(len(wanted) == len(expected_additions), 'duplicate_addition')
    require(not wanted.intersection(base), 'addition_exists_in_base')
    require(tree_hash(base_entries) == expected_base_tree, 'base_tree_mismatch')
    require(set(candidate) == set(base) | wanted, 'candidate_paths_mismatch')
    require(GUARD_PATH in base, 'guard_missing_from_base')
    require(candidate[GUARD_PATH] == Entry(GUARD_PATH, '100644', GUARD_BLOB),
            'guard_blob_mismatch')
    require(all(candidate[path] == entry for path, entry in base.items()
                if path != GUARD_PATH),
            'predecessor_changed')
    require(tree_hash(candidate_entries) == expected_candidate_tree,
            'candidate_tree_mismatch')
    return tuple(sorted(wanted))


def parse_inventory(raw, *, index=False):
    require(type(raw) is bytes and len(raw) <= MAX_OUTPUT, 'git_output_limit')
    require(raw.endswith(b'\0') and raw != b'\0', 'invalid_inventory')
    rows = raw[:-1].split(b'\0')
    require(len(rows) <= MAX_ENTRIES, 'inventory_limit')
    result = []
    try:
        for row in rows:
            desc, path = row.split(b'\t', 1)
            a, b, c = desc.decode('ascii').split(' ')
            require(c == '0' if index else b == 'blob', 'invalid_entry_kind')
            result.append(Entry(path.decode('utf-8'), a, b if index else c))
    except (UnicodeError, ValueError) as error:
        if isinstance(error, SourceVerificationError):
            raise
        raise SourceVerificationError('invalid_inventory') from None
    inventory(result)
    return tuple(result)


def parse_commit(raw, expected_sha):
    require(type(raw) is bytes and len(raw) <= 65536, 'invalid_commit')
    require(object_hash(b'commit', raw) == valid_sha(expected_sha), 'commit_hash_mismatch')
    header, separator, _ = raw.partition(b'\n\n')
    require(bool(separator), 'invalid_commit')
    lines = header.split(b'\n')
    require(lines[0].startswith(b'tree '), 'invalid_commit')
    parents = []
    try:
        tree = valid_sha(lines[0][5:].decode('ascii'))
        cursor = 1
        while cursor < len(lines) and lines[cursor].startswith(b'parent '):
            parents.append(valid_sha(lines[cursor][7:].decode('ascii')))
            cursor += 1
    except UnicodeError:
        raise SourceVerificationError('invalid_commit') from None
    require(not any(line.startswith((b'tree ', b'parent ')) for line in lines[cursor:]),
            'invalid_commit_header_order')
    return tree, tuple(parents)


class GitReader:
    """Fixed read-only Git commands with no inherited environment or network."""
    def __init__(self, root):
        self.root = root
        self.deadline = time.monotonic() + TOTAL_SECONDS
        self.commands = self.output = 0

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'source_timeout')
        return remaining

    def read(self, operation, oid=None):
        commands = {'head': ('rev-parse', '--verify', 'HEAD'),
                    'index': ('ls-files', '--stage', '-z'),
                    'commit': ('cat-file', 'commit'),
                    'tree': ('ls-tree', '-r', '-z')}
        require(operation in commands, 'invalid_git_operation')
        args = list(commands[operation])
        if operation in ('commit', 'tree'):
            args.append(valid_sha(oid))
        else:
            require(oid is None, 'invalid_git_operation')
        self.commands += 1
        require(self.commands <= MAX_COMMANDS, 'git_command_limit')
        deadline = time.monotonic() + min(COMMAND_SECONDS, self.remaining())
        argv = ['/usr/bin/git', '--no-optional-locks', '--no-replace-objects',
                '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null',
                '-c', 'protocol.allow=never', '-c', 'core.commitGraph=false', *args]
        env = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'HOME': '/nonexistent',
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
               'GIT_TERMINAL_PROMPT': '0', 'GIT_NO_LAZY_FETCH': '1'}
        process = None
        try:
            process = subprocess.Popen(argv, cwd=self.root, env=env, shell=False,
                close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL)
            data = bytearray()
            os.set_blocking(process.stdout.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, 'git_timeout')
                    for key, _ in selector.select(remaining):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        data.extend(chunk)
                        self.output += len(chunk)
                        require(len(data) <= MAX_OUTPUT and self.output <= MAX_TOTAL_OUTPUT,
                                'git_output_limit')
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'git_timeout')
            require(process.wait(timeout=remaining) == 0, 'git_failed')
            return bytes(data)
        except (OSError, subprocess.SubprocessError):
            raise SourceVerificationError('git_failed') from None
        finally:
            if process is not None:
                try:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=1)
                    process.stdout.close()
                except (OSError, subprocess.SubprocessError):
                    raise SourceVerificationError('git_cleanup_uncertain') from None


def working_bytes(root, entries, budget):
    """Use anchored directory descriptors and O_NOFOLLOW at every component."""
    require(os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'), 'unsupported_platform')
    absolute = os.path.abspath(root)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    total = 0
    try:
        root_fd = os.open('/', directory_flags)
        try:
            for component in Path(absolute).parts[1:]:
                next_fd = os.open(component, directory_flags, dir_fd=root_fd)
                os.close(root_fd)
                root_fd = next_fd
            for entry in entries:
                budget.remaining()
                folder = os.dup(root_fd)
                try:
                    parts = valid_path(entry.path)
                    for component in parts[:-1]:
                        next_fd = os.open(component, directory_flags, dir_fd=folder)
                        os.close(folder)
                        folder = next_fd
                    fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=folder)
                    try:
                        before = os.fstat(fd)
                        require(stat.S_ISREG(before.st_mode), 'nonregular_working_file')
                        require(not before.st_mode & 0o111, 'working_mode_mismatch')
                        require(before.st_size <= MAX_FILE, 'working_file_limit')
                        h = hashlib.sha1(b'blob ' + str(before.st_size).encode() + b'\0')
                        size = 0
                        while True:
                            budget.remaining()
                            chunk = os.read(fd, 65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            total += len(chunk)
                            require(size <= MAX_FILE and total <= MAX_TOTAL_FILES,
                                    'working_file_limit')
                            h.update(chunk)
                        after = os.fstat(fd)
                        identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size,
                                              s.st_mtime_ns, s.st_ctime_ns)
                        current = os.stat(parts[-1], dir_fd=folder, follow_symlinks=False)
                        require(identity(before) == identity(after) == identity(current),
                                'working_file_changed')
                        require(size == before.st_size and h.hexdigest() == entry.oid,
                                'working_bytes_mismatch')
                    finally:
                        os.close(fd)
                finally:
                    os.close(folder)
        finally:
            os.close(root_fd)
    except OSError:
        raise SourceVerificationError('unsafe_working_file') from None
    return total


def verify_source(root, expected_source_sha, *, expected_tree=None, staged=False):
    """Verify the one-step append to pinned 229, itself a sole child of PR97.

    committed: source_sha is the actual one-commit candidate HEAD, whose sole parent
    is 229. staged: expected_source_sha MUST be 229; source_tree is prospective,
    and the report's mode is 'prospective_index', never a published candidate.
    parent_sha/tree identify direct parent 229. baseline_sha/tree and predecessor
    counts describe PR97's 1628 entries (1627 unchanged plus the pinned guard).
    The exact 16 additions are relative to PR97, not new additions to 229.
    An independently expected tree may be supplied; otherwise actual commit/index
    tree is measured. All results are local observations, not publication proof.
    """
    valid_sha(expected_source_sha)
    if expected_tree is not None:
        valid_sha(expected_tree)
    require(type(staged) is bool, 'invalid_mode')
    reader = GitReader(root)
    def head():
        raw = reader.read('head')
        require(len(raw) == 41 and raw.endswith(b'\n'), 'invalid_head')
        try:
            return valid_sha(raw[:-1].decode('ascii'))
        except UnicodeError:
            raise SourceVerificationError('invalid_head') from None
    actual = head()
    require(actual == expected_source_sha, 'source_sha_mismatch')
    base_tree, _ = parse_commit(reader.read('commit', BASE_SHA), BASE_SHA)
    require(base_tree == BASE_TREE, 'base_tree_mismatch')
    base = parse_inventory(reader.read('tree', BASE_TREE))
    parent_tree, parents = parse_commit(reader.read('commit', PARENT_SHA), PARENT_SHA)
    require(parent_tree == PARENT_TREE, 'published_parent_tree_mismatch')
    require(parents == (BASE_SHA,), 'published_parent_lineage_mismatch')
    if staged:
        require(actual == PARENT_SHA, 'staged_head_mismatch')
        candidate = parse_inventory(reader.read('index'), index=True)
        candidate_tree = tree_hash(candidate)
    else:
        candidate_tree, parents = parse_commit(reader.read('commit', actual), actual)
        require(parents == (PARENT_SHA,), 'candidate_parent_mismatch')
        candidate = parse_inventory(reader.read('tree', candidate_tree))
        require(inventory(parse_inventory(reader.read('index'), index=True)) ==
                inventory(candidate), 'index_mismatch')
    if expected_tree is not None:
        require(candidate_tree == expected_tree, 'source_tree_mismatch')
    additions = validate_inventory(base, candidate, expected_base_tree=BASE_TREE,
        expected_candidate_tree=candidate_tree, expected_base_count=BASE_COUNT)
    total = working_bytes(root, candidate, reader)
    require(head() == actual, 'source_changed')
    require(inventory(parse_inventory(reader.read('index'), index=True)) ==
            inventory(candidate), 'index_changed')
    reader.remaining()
    return SourceVerification('prospective_index' if staged else 'committed', actual,
        candidate_tree, PARENT_SHA, PARENT_TREE, len(base), len(base) - 1,
        GUARD_PATH, GUARD_BLOB, additions, total, BASE_SHA, BASE_TREE)
