#!/usr/bin/env python3
"""Data-only desktop compiler-input/DEB evidence contract; never release approval."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

import exact_build_audit as exact

need = exact.need
TARGET = 'x86_64-unknown-linux-gnu'
BINARY = 'coding-tools-mcp-desktop'
REPOSITORY = 'Eswink/coding-tools-mcp'
WORKFLOW = 'issue85-desktop-glib-deb.yml'
MAX_JSON = 64 * 1024**2
MAX_BINARY = 256 * 1024**2
FLAGS = dict(engineering_only=True, installed_desktop_bytes_verified=False,
             security_approved=False, release_approved=False, publish_approved=False,
             raw_zero_claim=False)
SOURCE_INPUTS = (
    'package.json', 'package-lock.json', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock',
    'src-tauri/tauri.conf.json', 'src-tauri/Ubuntu桌面v1.json', 'src-tauri/build.rs',
    'services/cloud-agent/Cargo.toml', 'services/local-agent/Cargo.toml',
    'scripts/AppImage入口配置v3.py', 'scripts/AppImage启动入口v3.sh',
    'scripts/verify_glib_backport.py', 'scripts/exact_build_audit.py', 'scripts/rc_version_gate.py',
    'scripts/desktop_glib_build_evidence.py', 'scripts/desktop_glib_build_contract.py',
    'scripts/desktop_glib_deb.py', 'scripts/desktop_glib_link.py',
    'scripts/desktop_glib_probes.py',
    '.github/workflows/' + WORKFLOW)

FILES = {'upstream.crate', 'advisory-clone.stdout', 'advisory-clone.stderr',
    'source-audit.stdout', 'source-audit.stderr', 'source-audit/metadata.json',
    'source-audit/product-raw-audit.json', 'source-audit/product-raw-audit.stderr',
    'source-audit/upstream-identity-raw-audit.json', 'source-audit/upstream-identity-raw-audit.stderr',
    'source-audit/summary.json', 'metadata.json', 'metadata.stderr', 'selected-tree.txt',
    'selected-tree.stderr', 'runner-config.json', 'runner-start.json', 'build.jsonl',
    'build.stderr', 'cargo-exit.json', 'desktop.elf', 'glib.rlib', 'compiler-copies.json',
    'tauri.stdout', 'tauri.stderr', 'desktop.deb'}


def __getattr__(name):
    if name != 'glib': raise AttributeError(name)
    import verify_glib_backport
    return verify_glib_backport


def clean_git_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null',
               GIT_CONFIG_NOSYSTEM='1', GIT_NO_REPLACE_OBJECTS='1', GIT_OPTIONAL_LOCKS='0')
    return env


def git(root, *args):
    p = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
                        *args], cwd=root, env=clean_git_environment(), capture_output=True,
                       timeout=30, check=False)
    need(p.returncode == 0, 'git_source_identity_failed')
    return p.stdout.decode().strip()


@contextlib.contextmanager
def parent_descriptor(path):
    path = Path(path).absolute()
    need(path.name and all(p not in ('.', '..') for p in path.parts), 'unsafe_file_path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, path.name
    finally:
        os.close(fd)


def file_identity(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)


@contextlib.contextmanager
def regular_descriptor(path, limit=MAX_JSON, *, single_link=True):
    with parent_descriptor(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit,
             'invalid_regular_file')
        need(not single_link or before.st_nlink == 1, 'evidence_hardlink')
        yield fd, before
        need(file_identity(before) == file_identity(os.fstat(fd)), 'file_changed_during_read')
    finally:
        os.close(fd)


def read_regular(path, limit=MAX_JSON, *, single_link=True):
    with regular_descriptor(path, limit, single_link=single_link) as (fd, before):
        chunks, size = [], 0
        while chunk := os.read(fd, min(1024**2, limit + 1 - size)):
            size += len(chunk)
            need(size <= limit, 'file_resource_limit')
            chunks.append(chunk)
        need(size == before.st_size, 'file_read_size_changed')
        return b''.join(chunks)


def file_record(path, limit=MAX_BINARY, *, single_link=True):
    with regular_descriptor(path, limit, single_link=single_link) as (fd, before):
        h, size = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024**2):
            size += len(chunk)
            need(size <= limit, 'file_resource_limit')
            h.update(chunk)
        need(size == before.st_size, 'file_read_size_changed')
        return {'sha256': h.hexdigest(), 'size': size}



def stable_file(path, root, limit=MAX_BINARY, allow_hardlinks=False):
    path, root = Path(path).absolute(), Path(root).absolute()
    need(path.is_relative_to(root) and path != root, 'file_outside_owned_root')
    with regular_descriptor(path, limit, single_link=not allow_hardlinks) as (fd, before):
        need(before.st_uid == os.getuid(), 'wrong_file_owner')
        if before.st_nlink > 1:
            aliases = 0
            for base, dirs, files in os.walk(root, followlinks=False):
                need(all(not (Path(base) / d).is_symlink() for d in dirs), 'linked_target_directory')
                for name in files:
                    item = (Path(base) / name).stat(follow_symlinks=False)
                    if (item.st_dev, item.st_ino) == (before.st_dev, before.st_ino): aliases += 1
            need(aliases == before.st_nlink, 'hardlink_alias_outside_target')
        h, size = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024**2):
            size += len(chunk)
            need(size <= limit, 'file_resource_limit')
            h.update(chunk)
        need(size == before.st_size, 'file_read_size_changed')
        return {'sha256': h.hexdigest(), 'size': size}

def copy_regular(source, destination, limit=MAX_BINARY):
    with regular_descriptor(source, limit, single_link=False) as (src, before):
        with parent_descriptor(destination) as (parent, name):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            copied = os.fstat(fd)
            need((before.st_dev, before.st_ino) != (copied.st_dev, copied.st_ino), 'copy_aliases_target')
            size = 0
            while chunk := os.read(src, 1024**2):
                size += len(chunk)
                need(size <= limit, 'copy_resource_limit')
                view = memoryview(chunk)
                while view:
                    written = os.write(fd, view)
                    need(written > 0, 'copy_write_failed')
                    view = view[written:]
            os.fsync(fd)
            need(size == before.st_size and os.fstat(fd).st_nlink == 1, 'copy_identity_changed')
        finally:
            os.close(fd)
    return file_record(destination, limit)


def decode(data, limit=MAX_JSON):
    need(isinstance(data, bytes) and len(data) <= limit, 'json_resource_limit')
    # Bound nesting before json.loads recurses, respecting escaped string syntax.
    depth, quoted, escaped = 0, False, False
    for c in data:
        if quoted:
            if escaped: escaped = False
            elif c == 92: escaped = True
            elif c == 34: quoted = False
        elif c == 34: quoted = True
        elif c in (91, 123):
            depth += 1
            need(depth <= 64, 'json_nesting_limit')
        elif c in (93, 125): depth -= 1
    return exact.decode(data)


def write_json(path, value):
    data = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n').encode()
    need(len(data) <= MAX_JSON, 'json_resource_limit')
    with parent_descriptor(path) as (parent, name):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


exclusive_json = write_json


def source_identity(root, sha):
    from rc_version_gate import project_versions
    need(re.fullmatch('[0-9a-f]{40}', sha or ''), 'invalid_source_sha')
    need(git(root, 'rev-parse', 'HEAD') == sha, 'wrong_source_sha')
    need(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'unclean_source')
    need(not (root / '.git/objects/info/alternates').exists(), 'source_object_alternates')
    version, _ = project_versions(root)
    inputs = {p: file_record(root / p, MAX_JSON) for p in SOURCE_INPUTS}
    lock = decode(read_regular(root / 'package-lock.json'))
    need(lock['packages']['node_modules/@tauri-apps/cli']['version'] == '2.11.4' and
         lock['packages']['node_modules/@tauri-apps/cli-linux-x64-gnu']['version'] == '2.11.4',
         'wrong_locked_tauri_cli')
    return dict(source_sha=sha, source_tree=git(root, 'rev-parse', 'HEAD^{tree}'),
                version=version, target=TARGET, source_inputs=inputs)


def producer_identity(sha, run_id, attempt, workflow_ref):
    need(re.fullmatch('[0-9a-f]{40}', sha or ''), 'invalid_producer_source')
    need(all(type(x) is str and re.fullmatch('[1-9][0-9]*', x) for x in (run_id, attempt)),
         'invalid_producer_run')
    prefix = REPOSITORY + '/.github/workflows/' + WORKFLOW + '@refs/heads/'
    need(type(workflow_ref) is str and workflow_ref.startswith(prefix) and
         re.fullmatch(r'ci/issue85-desktop-glib-deb-[A-Za-z0-9._-]+', workflow_ref[len(prefix):]),
         'invalid_producer_workflow')
    return dict(provider='github-actions', repository=REPOSITORY, source_sha=sha,
                workflow_sha=sha, run_id=run_id, run_attempt=attempt, workflow_ref=workflow_ref,
                job='build', runner_os='Linux', platform={'id': 'ubuntu', 'version_id': '22.04'})


def cargo_arguments():
    return ['build', '--locked', '--message-format=json', '--bins', '--features',
            'tauri/custom-protocol', '--release', '--target', TARGET]


def verify_compiler_events(metadata, selected_text, build_bytes, source_root, target_dir):
    import verify_glib_backport as glib
    by_id, by_display, _ = exact.package_maps(metadata, {'package': metadata['packages']})
    selected = exact.tree_packages(selected_text, by_display)
    root = metadata.get('resolve', {}).get('root')
    need(root in selected and by_id[root]['name'] == BINARY, 'wrong_product_root')
    glibs = [p for p in by_id if by_id[p]['name'] == 'glib']
    need(len(glibs) == 1 and glibs[0] in selected and by_id[glibs[0]].get('source') is None,
         'wrong_selected_glib')
    gid = glibs[0]
    need(by_id[gid]['manifest_path'] == source_root + '/' + glib.VENDOR + '/Cargo.toml',
         'wrong_glib_manifest')
    nodes = {n['id']: n for n in metadata['resolve']['nodes']}
    seen, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid in seen: continue
        seen.add(pid)
        todo += [d['pkg'] for d in nodes[pid]['deps']
                 if any(k.get('kind') is None for k in d.get('dep_kinds', []))]
    need(gid in seen, 'glib_not_normal_product_dependency')
    needed = {(pid, exact.unit(t)): t for pid in selected for t in by_id[pid]['targets']
              if not set(t['kind']) & {'test', 'example', 'bench'} and
              ('bin' not in t['kind'] or pid == root)}
    features, units, important, finished = {}, set(), {}, False
    build_scripts = {'artifacts': [], 'executed': []}
    for line in build_bytes.splitlines():
        need(line and len(line) <= 4 * 1024**2 and not finished, 'invalid_or_late_build_event')
        event = decode(line, 4 * 1024**2)
        need(type(event) is dict, 'invalid_build_event')
        reason = event.get('reason')
        if reason == 'build-finished':
            need(event.get('success') is True, 'failed_build_finished')
            finished = True
        elif reason == 'compiler-artifact':
            pid, target = event.get('package_id'), event.get('target', {})
            unit = (pid, exact.unit(target))
            need(unit in needed, 'unmapped_compiler_unit')
            need(event.get('manifest_path') == by_id[pid]['manifest_path'] and
                 target.get('src_path') == needed[unit]['src_path'], 'compiler_source_mismatch')
            need(event.get('profile', {}).get('test') is False and event.get('fresh') is False,
                 'test_or_stale_compiler_unit')
            fs = event.get('features')
            need(type(fs) is list and all(type(f) is str for f in fs) and len(fs) == len(set(fs)),
                 'invalid_compiler_features')
            features.setdefault(pid, set()).update(fs)
            units.add(unit)
            if target['kind'] == ['custom-build']: build_scripts['artifacts'].append(event)
            key = 'glib' if pid == gid and target['kind'] == ['lib'] else (
                'root' if pid == root and target['kind'] == ['bin'] else None)
            if key:
                need(key not in important, 'duplicate_required_compiler_unit')
                profile = event['profile']
                need(profile.get('opt_level') == '3' and profile.get('debug_assertions') is False and
                     type(profile.get('debuginfo')) is int and profile['debuginfo'] == 0,
                     'wrong_required_release_profile')
                names = event.get('filenames', [])
                need(names and all(type(n) is str and n.startswith(target_dir + '/' + TARGET + '/release/')
                                   and '..' not in Path(n).parts for n in names), 'unsafe_compiler_output')
                if key == 'root':
                    need(event.get('executable') == target_dir + '/' + TARGET + '/release/' + BINARY
                         and event['executable'] in names, 'wrong_root_executable')
                else:
                    need(len([n for n in names if n.endswith('.rlib')]) == 1, 'missing_glib_rlib')
                important[key] = event
        elif reason == 'compiler-message':
            need(event.get('package_id') in selected and event.get('message', {}).get('level') != 'error',
                 'compiler_error_or_unknown_package')
        elif reason == 'build-script-executed':
            need(event.get('package_id') in selected, 'unknown_build_script')
            build_scripts['executed'].append(event)
        else: need(False, 'unknown_compiler_event')
    need(finished and units == set(needed) and features == selected and set(important) == {'glib', 'root'},
         'incomplete_compiler_evidence')
    return dict(**important, build_scripts=build_scripts)


def evidence_inventory(directory):
    result, total = {}, 0
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            need(not (Path(base) / name).is_symlink(), 'linked_evidence_directory')
        for name in files:
            path = Path(base) / name
            relative = path.relative_to(directory).as_posix()
            if relative == 'envelope.json': continue
            need(len(relative.encode()) <= 1024, 'evidence_path_limit')
            record = file_record(path)
            total += record['size']
            need(len(result) < 8300 and total <= 1024**3, 'evidence_resource_limit')
            result[relative] = record
    return result


def verify_paired_source(root, directory, envelope):
    import tomllib
    import verify_glib_backport as glib
    source = glib.verify_source(root, directory / 'upstream.crate')
    manifests = glib.verify_configuration(root, {})
    lock = tomllib.loads(read_regular(root / 'src-tauri/Cargo.lock').decode())
    metadata = decode(read_regular(directory / 'metadata.json'))
    glib.verify_metadata(Path(envelope['source_root']), metadata, lock, manifests)
    folder = directory / 'source-audit'
    summary = decode(read_regular(folder / 'summary.json'))
    product = decode(read_regular(folder / 'product-raw-audit.json'))
    original = decode(read_regular(folder / 'upstream-identity-raw-audit.json'))
    upstream_lock = tomllib.loads(read_regular(root / glib.PROVENANCE / 'upstream-identity.Cargo.lock').decode())
    paired = glib.verify_audits(product, original, lock, upstream_lock)
    need(summary.get('audit_version') == 'cargo-audit 0.22.2', 'wrong_audit_tool')
    for name, report in (('product', product), ('upstream-identity', original)):
        record = summary['audit_commands'][name]
        command = record.get('command', [])
        relative = 'src-tauri/Cargo.lock' if name == 'product' else glib.PROVENANCE + '/upstream-identity.Cargo.lock'
        need(command == [envelope['audit_binary'], 'audit', '--no-fetch', '--db', envelope['audit_db'],
                         '--file', relative, '--json'], 'wrong_paired_audit_command')
        need(type(record['exit']) is int and record['exit'] == (1 if report['vulnerabilities']['found'] else 0),
             'wrong_paired_audit_exit')
        need(record['report_sha256'] == file_record(folder / (name + '-raw-audit.json'))['sha256'],
             'changed_paired_audit')
    need(summary['provenance_sha256'] == source['provenance_sha256'] and
         summary['product_lock_sha256'] == file_record(root / 'src-tauri/Cargo.lock')['sha256'],
         'changed_source_audit_identity')
    need(summary['advisory_database'] == envelope['advisory_database'] and
         summary['audit_binary_sha256'] == envelope['tools']['audit']['sha256'], 'changed_advisory_snapshot')
    count = glib.verify_metadata(Path(envelope['source_root']),
        decode(read_regular(folder / 'metadata.json')), lock, manifests)
    expected_summary = dict(**source, **paired, metadata_package_count=count,
        product_lock_sha256=file_record(root / 'src-tauri/Cargo.lock')['sha256'], source_backport_verified=True,
        audit_commands=summary['audit_commands'], advisory_database=envelope['advisory_database'],
        audit_version='cargo-audit 0.22.2', audit_binary_sha256=envelope['tools']['audit']['sha256'])
    need(json.dumps(summary, sort_keys=True) == json.dumps(expected_summary, sort_keys=True) and
         json.dumps(decode(read_regular(directory / 'source-audit.stdout')), sort_keys=True) ==
         json.dumps(summary, sort_keys=True), 'contradictory_source_audit_receipt')
    return {**source, **paired}


def verify_runner_receipts(directory, e, events, root_record, glib_record, profile=None):
    source, target, evidence = (e[k] for k in ('source_root', 'target_dir', 'evidence_root'))
    paths = [Path(p) for p in (source, target, evidence)]
    need(all(p.is_absolute() and '..' not in p.parts and len(str(p).encode()) <= 1024 for p in paths)
         and not any(a.is_relative_to(b) for i, a in enumerate(paths) for j, b in enumerate(paths) if i != j),
         'invalid_producer_directory_relationship')
    config = dict(source_sha=e['source_sha'], source_root=source, target_dir=target,
        evidence_root=evidence, evidence_dir=evidence + '/traces', real_cargo=e['tools']['cargo']['path'],
        real_cargo_sha256=e['tools']['cargo']['sha256'], real_rustc=e['tools']['rustc']['path'],
        real_rustc_sha256=e['tools']['rustc']['sha256'])
    if profile is not None:
        need(profile == 'linux-engineering-packages-v1', 'unknown_runner_profile')
        config['profile'] = profile
    receipts = {'runner-config.json': config,
        'runner-start.json': {'arguments': cargo_arguments(), 'cwd': source + '/src-tauri'},
        'cargo-exit.json': {'exit': 0},
        'compiler-copies.json': {'events': events, 'copies': {'desktop': root_record, 'glib': glib_record}}}
    for name, value in receipts.items():
        need(json.dumps(decode(read_regular(directory / name)), sort_keys=True) ==
             json.dumps(value, sort_keys=True), 'contradictory_runner_receipt:' + name)
    audit_command = [e['tools']['python']['path'], 'scripts/verify_glib_backport.py', '--root', source,
        '--archive', evidence + '/upstream.crate', '--audit-bin', e['audit_binary'], '--audit-db', e['audit_db'],
        '--output', evidence + '/source-audit']
    need(json.dumps(e.get('commands'), sort_keys=True) ==
         json.dumps({'source-audit': {'argv': audit_command, 'exit': 0}}, sort_keys=True),
         'contradictory_source_audit_command')


def verify(root, directory, sha, expected_producer, trusted_digest):
    from desktop_glib_deb import verify_deb
    from desktop_glib_link import verify_link_trace
    source = source_identity(root, sha)
    need(re.fullmatch('[0-9a-f]{64}', trusted_digest or ''), 'missing_trusted_envelope_digest')
    data = read_regular(directory / 'envelope.json')
    need(exact.digest(data) == trusted_digest, 'wrong_trusted_envelope_digest')
    e = decode(data)
    need(type(e.get('schema')) is int and e['schema'] == 1 and
         all(e.get(k) == v for k, v in source.items()), 'wrong_envelope_source')
    need(e.get('producer') == expected_producer == producer_identity(
        sha, expected_producer['run_id'], expected_producer['run_attempt'], expected_producer['workflow_ref']),
        'wrong_envelope_producer')
    need(all(e.get(k) is v for k, v in FLAGS.items()), 'wrong_scope_flags')
    need(e.get('files') == evidence_inventory(directory), 'changed_evidence_inventory')
    need(set(e['files']) - {n for n in e['files'] if re.fullmatch(r'traces/rustc-[0-9a-f]{32}\.json', n)}
         == FILES, 'unexpected_evidence_files')
    need(type(e.get('cargo_exit')) is int and e['cargo_exit'] == 0 and
         type(e.get('tauri_exit')) is int and e['tauri_exit'] == 0, 'failed_product_build')
    need(e.get('cargo_arguments') == cargo_arguments(), 'wrong_product_build_command')
    for tool in ('cargo', 'rustc'):
        item = e.get('tools', {}).get(tool, {})
        need(re.match(tool + r' 1\.98\.1(?: |$)', item.get('version', '')) and
             re.fullmatch('[0-9a-f]{64}', item.get('sha256', '')), 'wrong_product_toolchain')
    need(e.get('tools', {}).get('tauri', {}).get('version') == 'tauri-cli 2.11.4' and
         e.get('tools', {}).get('python', {}).get('version', '').startswith('Python 3.12.'), 'wrong_tauri_or_python')
    runner = e['source_root'] + '/scripts/desktop_glib_build_evidence.py'
    expected_tauri = ['npm', 'run', 'tauri', '--', 'build', '--config', 'src-tauri/Ubuntu桌面v1.json',
        '--bundles', 'deb', '--target', TARGET, '--runner', runner, '--', '--locked', '--message-format=json']
    need(e.get('tauri_command') == expected_tauri, 'wrong_tauri_command')
    cargo = e['tools']['cargo']['path']
    need(e.get('metadata_command') == [cargo, 'metadata', '--locked', '--format-version', '1',
        '--manifest-path', 'src-tauri/Cargo.toml', '--features', 'tauri/custom-protocol'], 'wrong_metadata_command')
    need(e.get('selected_tree_command') == [cargo, 'tree', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
        '--prefix', 'none', '--format', '{p}\t{f}', '--target', TARGET, '--edges', 'normal,build',
        '--features', 'tauri/custom-protocol'], 'wrong_selected_tree_command')
    env = e.get('build_environment', {})
    fixed = dict(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', CARGO_TERM_COLOR='never',
        CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='2', CARGO_PROFILE_RELEASE_DEBUG='0',
        CARGO_TARGET_DIR=e['target_dir'], TZ='UTC', RUSTC=e['tools']['rustc']['path'], RUSTC_WRAPPER=runner)
    need(type(env) is dict and all(env.get(k) == v for k, v in fixed.items()) and
         set(env) <= set(fixed) | {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR',
                                   'RUSTUP_HOME', 'CARGO_HOME'}, 'unreviewed_build_environment')
    snapshot = e.get('advisory_database', {})
    need(snapshot.get('clean') is True and snapshot.get('origin') == 'https://github.com/RustSec/advisory-db.git',
         'untrusted_advisory_database')
    for key, length in (('commit', 40), ('tree', 40), ('contents_sha256', 64)):
        need(re.fullmatch('[0-9a-f]{' + str(length) + '}', str(snapshot.get(key))), 'bad_advisory_identity')
    acquisition = e.get('advisory_acquisition', {})
    need(acquisition.get('method') == 'fresh_official_clone' and type(acquisition.get('exit')) is int and
         acquisition['exit'] == 0 and type(acquisition.get('started_ns')) is int and
         type(acquisition.get('finished_ns')) is int and 0 < acquisition['started_ns'] <= acquisition['finished_ns'],
         'wrong_advisory_acquisition')
    paired, lineage, package = verify_compiler_payload(root, directory, sha, source, e)
    return dict(**source, **FLAGS, producer=expected_producer, envelope_sha256=trusted_digest,
        desktop_compiler_input_to_deb_binding_verified=True, compiler_input_provenance=lineage,
        deb=package, paired_source=paired,
        limitations=['native linker consumption and retained GLib code unproven',
                     'installed/native/system-library/security/release acceptance unproven'])


def verify_compiler_payload(root, directory, sha, source, e, profile=None):
    import tomllib
    from desktop_glib_deb import verify_deb
    from desktop_glib_link import verify_link_trace
    paired = verify_paired_source(root, directory, e)
    metadata = decode(read_regular(directory / 'metadata.json'))
    events = verify_compiler_events(metadata,
        read_regular(directory / 'selected-tree.txt').decode(), read_regular(directory / 'build.jsonl'),
        e['source_root'], e['target_dir'])
    root_record = file_record(directory / 'desktop.elf')
    glib_record = file_record(directory / 'glib.rlib', 128 * 1024**2)
    verify_runner_receipts(directory, e, events, root_record, glib_record, profile)
    trace_paths = sorted((directory / 'traces').glob('*.json'))
    traces = [decode(read_regular(p, 4 * 1024**2)) for p in trace_paths]
    need(all(p.name == 'rustc-' + str(t.get('id')) + '.json' for p, t in zip(trace_paths, traces)),
         'trace_filename_identity_mismatch')
    need(0 < len(traces) <= 8192 and sum(e['files']['traces/' + p.name]['size']
         for p in (directory / 'traces').glob('*.json')) <= MAX_JSON, 'trace_resource_limit')
    local_sources, tracked = {}, set(git(root, 'ls-files').splitlines())
    for trace in traces:
        path = (trace.get('source') or {}).get('path', '')
        prefix = e['source_root'] + '/'
        if path.startswith(prefix):
            relative = path[len(prefix):]
            need('..' not in Path(relative).parts and relative in tracked,
                 'untracked_local_compilation_source')
            local_sources[path] = file_record(root / relative)['sha256']
    glib_source, root_source = (events[k]['target']['src_path'] for k in ('glib', 'root'))
    glib_rlib = next(n for n in events['glib']['filenames'] if n.endswith('.rlib'))
    lineage = verify_link_trace(traces, dict(source_sha=sha, source_root=e['source_root'],
        target_dir=e['target_dir'], real_rustc=e['tools']['rustc']['path'],
        real_rustc_sha256=e['tools']['rustc']['sha256'], glib_source=glib_source,
        glib_source_sha256=local_sources[glib_source], glib_rlib={'path': glib_rlib, **glib_record},
        root_source=root_source, root_source_sha256=local_sources[root_source],
        root_executable={'path': events['root']['executable'], **root_record},
        local_source_hashes=local_sources, probe_context={**events['build_scripts'], 'packages': metadata['packages'],
            'lock_packages': tomllib.loads(read_regular(root / 'src-tauri/Cargo.lock').decode())['package']}))
    package = verify_deb(read_regular(directory / 'desktop.elf', MAX_BINARY),
                         read_regular(directory / 'desktop.deb', MAX_BINARY), source['version'])
    return paired, lineage, package
