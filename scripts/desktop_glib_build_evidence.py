#!/usr/bin/env python3
"""Nonpublishing real Tauri compiler-input and DEB byte evidence."""
from __future__ import annotations
import argparse
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

import desktop_glib_build_contract as c
import verify_glib_backport as glib

CONFIG_ENV = 'DESKTOP_GLIB_CONFIG'
MAX_LOG = 64 * 1024**2


def new_directory(path):
    with c.parent_descriptor(path) as (parent, name):
        os.mkdir(name, 0o700, dir_fd=parent)


def build_environment(root, target, original):
    forbidden = ('RUSTC', 'RUSTDOC', 'RUSTFLAGS', 'RUSTDOCFLAGS', 'RUSTC_WRAPPER',
                 'RUSTC_WORKSPACE_WRAPPER', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS',
                 'CARGO_TARGET_DIR', 'CARGO_BUILD_TARGET_DIR', 'CARGO_BUILD_BUILD_DIR',
                 'CARGO_BUILD_TARGET', 'MAKEFLAGS', 'MFLAGS', 'CARGO_MAKEFLAGS', 'RUSTC_BOOTSTRAP')
    for key in original:
        c.need(key not in forbidden and not key.startswith(('CARGO_PROFILE_', 'CARGO_TARGET_',
            'CARGO_BUILD_RUST', 'CARGO_SOURCE_', 'CARGO_REGISTR', 'CARGO_PATCH_', 'CARGO_REPLACE_',
            'CARGO_ALIAS_', 'CARGO_CONFIG', 'DESKTOP_GLIB_')), 'inherited_build_override:' + key)
    keep = ('PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR', 'RUSTUP_HOME', 'CARGO_HOME')
    env = {k: original[k] for k in keep if k in original}
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', CARGO_TERM_COLOR='never',
               CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='2', CARGO_PROFILE_RELEASE_DEBUG='0',
               CARGO_TARGET_DIR=str(target), TZ='UTC')
    glib.verify_configuration(root, env)
    return env


def child_environment(env):
    safe = {k: v for k, v in env.items() if not k.startswith('GIT_')}
    safe.update({k: v for k, v in c.clean_git_environment().items() if k.startswith('GIT_')})
    return safe


def command_output(args, root, env, timeout=60):
    p = subprocess.run(args, cwd=root, env=child_environment(env), capture_output=True, timeout=timeout, check=False)
    c.need(p.returncode == 0 and len(p.stdout) <= MAX_LOG and len(p.stderr) <= MAX_LOG,
           'tool_identity_command_failed')
    return p.stdout.decode().strip()


def capture(args, root, env, stdout_path, stderr_path, timeout=3600, forward=False, pass_fds=()):
    failures = []
    streams = []
    for path in (stdout_path, stderr_path):
        with c.parent_descriptor(path) as (parent, name):
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        streams.append(os.fdopen(fd, 'wb'))
    p = None
    try:
        p = subprocess.Popen(args, cwd=root, env=child_environment(env), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             pass_fds=pass_fds)
        def drain(source, destination, display):
            size = 0
            try:
                while chunk := source.read1(65536):
                    size += len(chunk)
                    c.need(size <= MAX_LOG, 'compiler_stream_limit')
                    destination.write(chunk)
                    if forward:
                        display.write(chunk)
                        display.flush()
                destination.flush()
                os.fsync(destination.fileno())
            except BaseException as exc:
                failures.append(str(exc))
                p.kill()
            finally:
                source.close()
        threads = [threading.Thread(target=drain, args=triple, daemon=True) for triple in (
            (p.stdout, streams[0], sys.stdout.buffer), (p.stderr, streams[1], sys.stderr.buffer))]
        for thread in threads: thread.start()
        try:
            code = p.wait(timeout=timeout)
        except BaseException:
            p.kill()
            p.wait()
            raise
        finally:
            for thread in threads: thread.join(timeout=30)
        c.need(not failures and all(not t.is_alive() for t in threads), 'incomplete_compiler_capture')
        return code
    finally:
        if p is not None and p.poll() is None:
            p.kill()
            p.wait()
        for stream in streams: stream.close()


def load_runner_config():
    path = Path(os.environ.get(CONFIG_ENV, ''))
    raw = c.read_regular(path)
    c.need(hashlib.sha256(raw).hexdigest() == os.environ.get(CONFIG_ENV + '_SHA256'), 'runner_config_changed')
    config = c.decode(raw)
    c.need(os.environ.get('CARGO_TARGET_DIR') == config['target_dir'], 'wrong_runner_target')
    return config


def cargo_runner(arguments):
    from desktop_glib_link import jobserver_fds
    config = load_runner_config()
    c.need(Path.cwd() == Path(config['source_root']) / 'src-tauri', 'wrong_runner_directory')
    c.need(arguments == c.cargo_arguments(), 'unexpected_tauri_cargo_arguments')
    evidence, root = Path(config['evidence_root']), Path(config['source_root'])
    c.write_json(evidence / 'runner-start.json', {'arguments': arguments, 'cwd': str(Path.cwd())})
    c.need(c.file_record(config['real_cargo'], single_link=False)['sha256'] == config['real_cargo_sha256'],
           'cargo_executable_changed')
    code = capture([config['real_cargo'], *arguments], Path.cwd(), dict(os.environ),
                   evidence / 'build.jsonl', evidence / 'build.stderr', forward=True,
                   pass_fds=jobserver_fds(os.environ))
    c.write_json(evidence / 'cargo-exit.json', {'exit': code})
    if code:
        return code
    events = c.verify_compiler_events(c.decode(c.read_regular(evidence / 'metadata.json')),
        c.read_regular(evidence / 'selected-tree.txt').decode(), c.read_regular(evidence / 'build.jsonl'),
        config['source_root'], config['target_dir'])
    binary = Path(events['root']['executable'])
    rlib = Path(next(n for n in events['glib']['filenames'] if n.endswith('.rlib')))
    for path in (binary, rlib):
        c.stable_file(path, Path(config['target_dir']), c.MAX_BINARY, allow_hardlinks=True)
    copies = {'desktop': c.copy_regular(binary, evidence / 'desktop.elf'),
              'glib': c.copy_regular(rlib, evidence / 'glib.rlib', 128 * 1024**2)}
    c.write_json(evidence / 'compiler-copies.json', {'events': events, 'copies': copies})
    if config.get('profile') == 'linux-engineering-packages-v1':
        from appimage_relro_tool import bind_compiler
        bind_compiler(evidence / 'appimage-relro/config.json', {'events': events, 'copies': copies})
    return 0


def tool_identities(root, env, audit_binary):
    tools = {}
    for tool in ('rustc', 'cargo'):
        path = Path(command_output(['rustup', 'which', '--toolchain', '1.98.1', tool], root, env)).resolve(strict=True)
        version = command_output([str(path), '--version'], root, env)
        c.need(re.match(tool + r' 1\.98\.1(?: |$)', version), 'wrong_real_toolchain')
        c.need(path.name == tool and path.name != 'rustup', 'rustup_shim_not_toolchain')
        tools[tool] = {'path': str(path), 'version': version, **c.file_record(path, single_link=False)}
    env['PATH'] = str(Path(tools['cargo']['path']).parent) + os.pathsep + env['PATH']
    python = Path(sys.executable).resolve(strict=True)
    c.need(sys.version_info[:2] == (3, 12), 'python312_required')
    tools['python'] = {'path': str(python), 'version': platform.python_version(), **c.file_record(python, single_link=False)}
    tools['python']['version'] = 'Python ' + tools['python']['version']
    version = command_output(['npm', 'exec', '--no', '--', 'tauri', '--version'], root, env)
    c.need(version == 'tauri-cli 2.11.4', 'wrong_actual_tauri_cli')
    natives = list((root / 'node_modules/@tauri-apps/cli-linux-x64-gnu').glob('*.node'))
    c.need(len(natives) == 1, 'missing_tauri_native_cli')
    tools['tauri'] = {'version': version, **c.file_record(natives[0], single_link=False)}
    tools['audit'] = {'path': str(audit_binary), 'version': command_output([str(audit_binary), '--version'], root, env),
                      **c.file_record(audit_binary, single_link=False)}
    c.need(tools['audit']['version'] == 'cargo-audit 0.22.2', 'wrong_audit_binary')
    return tools


def advisory_identity(path):
    c.need(not c.git(path, 'status', '--porcelain', '--untracked-files=all'), 'dirty_advisory_database')
    origin = c.git(path, 'remote', 'get-url', 'origin')
    c.need(origin == 'https://github.com/RustSec/advisory-db.git', 'wrong_advisory_origin')
    files = sorted(c.git(path, 'ls-files').splitlines())
    h = hashlib.sha256()
    for name in files:
        c.need('..' not in Path(name).parts and not Path(name).is_absolute(), 'unsafe_advisory_path')
        h.update(name.encode() + b'\0' + c.file_record(path / name, c.MAX_JSON)['sha256'].encode() + b'\n')
    return {'commit': c.git(path, 'rev-parse', 'HEAD'), 'tree': c.git(path, 'rev-parse', 'HEAD^{tree}'),
            'contents_sha256': h.hexdigest(), 'origin': origin, 'clean': True, 'file_count': len(files)}


def collect(root, output, target, sha, archive, audit_binary, audit_db):
    source = c.source_identity(root, sha)
    c.need(not output.is_relative_to(root) and not target.is_relative_to(root) and output != target,
           'build_evidence_must_be_external')
    c.need(not output.is_relative_to(target) and not target.is_relative_to(output), 'overlapping_build_directories')
    env = build_environment(root, target, os.environ)
    new_directory(output)
    new_directory(target)
    new_directory(output / 'traces')
    c.need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_SHA') == sha and
           os.environ.get('GITHUB_WORKFLOW_SHA') == sha and os.environ.get('GITHUB_JOB') == 'build' and
           os.environ.get('GITHUB_REPOSITORY') == c.REPOSITORY, 'trusted_github_producer_required')
    producer = c.producer_identity(sha, os.environ.get('GITHUB_RUN_ID'),
                                  os.environ.get('GITHUB_RUN_ATTEMPT'), os.environ.get('GITHUB_WORKFLOW_REF'))
    os_release = platform.freedesktop_os_release()
    c.need(os_release.get('ID') == 'ubuntu' and os_release.get('VERSION_ID') == '22.04' and
           platform.machine() == 'x86_64' and platform.system() == 'Linux', 'wrong_producer_platform')
    tools = tool_identities(root, env, audit_binary)
    c.copy_regular(archive, output / 'upstream.crate', 1024**2)
    c.need(c.file_record(output / 'upstream.crate')['sha256'] == glib.ARCHIVE_SHA, 'wrong_official_glib_archive')
    c.need(not audit_db.exists(), 'advisory_snapshot_must_be_fresh')
    started = time.time_ns()
    clone_env = {**env, **{k: v for k, v in c.clean_git_environment().items() if k.startswith('GIT_')}}
    code = capture(['git', 'clone', '--depth', '1', 'https://github.com/RustSec/advisory-db.git', str(audit_db)],
                   root, clone_env, output / 'advisory-clone.stdout', output / 'advisory-clone.stderr', timeout=300)
    c.need(code == 0, 'advisory_clone_failed')
    database = advisory_identity(audit_db)
    acquisition = {'method': 'fresh_official_clone', 'started_ns': started, 'finished_ns': time.time_ns(), 'exit': code}
    commands = {}
    def step(name, args, timeout=600):
        commands[name] = {'argv': args, 'exit': capture(args, root, env, output / (name + '.stdout'),
                                                       output / (name + '.stderr'), timeout=timeout)}
        c.need(commands[name]['exit'] == 0, 'failed_' + name)
    step('source-audit', [str(Path(sys.executable).resolve()), 'scripts/verify_glib_backport.py',
        '--root', str(root), '--archive', str(output / 'upstream.crate'), '--audit-bin', str(audit_binary),
        '--audit-db', str(audit_db), '--output', str(output / 'source-audit')])
    meta = [tools['cargo']['path'], 'metadata', '--locked', '--format-version', '1', '--manifest-path',
            'src-tauri/Cargo.toml', '--features', 'tauri/custom-protocol']
    c.need(capture(meta, root, env, output / 'metadata.json', output / 'metadata.stderr', timeout=600) == 0,
           'metadata_capture_failed')
    tree = [tools['cargo']['path'], 'tree', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
            '--prefix', 'none', '--format', '{p}\t{f}', '--target', c.TARGET,
            '--edges', 'normal,build', '--features', 'tauri/custom-protocol']
    c.need(capture(tree, root, env, output / 'selected-tree.txt', output / 'selected-tree.stderr', timeout=600) == 0,
           'selected_tree_capture_failed')
    config = dict(source_sha=sha, source_root=str(root), target_dir=str(target),
        evidence_root=str(output), evidence_dir=str(output / 'traces'),
        real_cargo=tools['cargo']['path'], real_cargo_sha256=tools['cargo']['sha256'],
        real_rustc=tools['rustc']['path'], real_rustc_sha256=tools['rustc']['sha256'])
    config_path = output / 'runner-config.json'
    c.write_json(config_path, config)
    runner = root / 'scripts/desktop_glib_build_evidence.py'
    env.update({CONFIG_ENV: str(config_path), CONFIG_ENV + '_SHA256': c.file_record(config_path)['sha256'],
                'RUSTC': tools['rustc']['path'], 'RUSTC_WRAPPER': str(runner)})
    build = ['npm', 'run', 'tauri', '--', 'build', '--config', 'src-tauri/Ubuntu桌面v1.json',
             '--bundles', 'deb', '--target', c.TARGET, '--runner', str(runner),
             '--', '--locked', '--message-format=json']
    code = capture(build, root, env, output / 'tauri.stdout', output / 'tauri.stderr', forward=True)
    c.need(code == 0, 'tauri_product_build_failed')
    cargo_exit = c.decode(c.read_regular(output / 'cargo-exit.json'))['exit']
    c.need(type(cargo_exit) is int and cargo_exit == 0, 'cargo_product_build_failed')
    original = target / c.TARGET / 'release' / c.BINARY
    c.need(c.stable_file(original, target, c.MAX_BINARY, allow_hardlinks=True) ==
           c.file_record(output / 'desktop.elf'), 'tauri_did_not_restore_prebundle_elf')
    packages = list((target / c.TARGET / 'release/bundle/deb').glob('*.deb'))
    c.need(len(packages) == 1, 'expected_one_fresh_deb')
    c.copy_regular(packages[0], output / 'desktop.deb')
    c.need(c.source_identity(root, sha) == source and advisory_identity(audit_db) == database,
           'source_or_database_changed')
    glib.verify_configuration(root, env)
    glib.verify_source(root, output / 'upstream.crate')
    envelope = dict(schema=1, **source, **c.FLAGS, producer=producer, source_root=str(root),
        target_dir=str(target), evidence_root=str(output), cargo_exit=cargo_exit, tauri_exit=code, cargo_arguments=c.cargo_arguments(),
        tauri_command=build, metadata_command=meta, selected_tree_command=tree, tools=tools,
        build_environment={k: v for k, v in env.items() if not k.startswith('DESKTOP_GLIB_')},
        commands=commands, audit_binary=str(audit_binary), audit_db=str(audit_db),
        advisory_database=database, advisory_acquisition=acquisition, files=c.evidence_inventory(output))
    c.write_json(output / 'envelope.json', envelope)
    digest = c.file_record(output / 'envelope.json')['sha256']
    return c.verify(root, output, sha, producer, digest)


def main():
    from desktop_glib_link import capture_rustc, propagate_exit
    if CONFIG_ENV in os.environ:
        if sys.argv[1:2] == ['build']:
            return propagate_exit(cargo_runner(sys.argv[1:]))
        config = load_runner_config()
        c.need(sys.argv[1:2] == [config['real_rustc']], 'unexpected_wrapper_entry')
        return propagate_exit(capture_rustc(sys.argv[1:], config))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['collect', 'verify', 'collect-linux', 'verify-linux'])
    for name in ('root', 'directory'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--target-directory', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--audit-bin', type=Path)
    parser.add_argument('--audit-db', type=Path)
    parser.add_argument('--expected-envelope-sha256')
    parser.add_argument('--expected-profile')
    parser.add_argument('--artifact-id')
    parser.add_argument('--artifact-digest')
    parser.add_argument('--packages-directory', type=Path)
    parser.add_argument('--originals-directory', type=Path)
    parser.add_argument('--producer-run-id')
    parser.add_argument('--producer-run-attempt')
    parser.add_argument('--producer-workflow-ref')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, directory = args.root.absolute(), args.directory.absolute()
    if args.mode.endswith('-linux'):
        from linux_package_provenance import dispatch
        result = dispatch(args)
    elif args.mode == 'collect':
        c.need(all((args.target_directory, args.archive, args.audit_bin, args.audit_db)), 'missing_collect_input')
        result = collect(root, directory, args.target_directory.absolute(), args.source,
                         args.archive.absolute(), args.audit_bin.resolve(strict=True), args.audit_db.absolute())
    else:
        producer = c.producer_identity(args.source, args.producer_run_id,
                                      args.producer_run_attempt, args.producer_workflow_ref)
        result = c.verify(root, directory, args.source, producer, args.expected_envelope_sha256)
    c.need(not args.output.absolute().is_relative_to(directory), 'result_must_be_outside_evidence')
    c.write_json(args.output.absolute(), result)
    print(__import__('json').dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
