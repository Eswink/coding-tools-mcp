"""The single engineering Tauri build, reusing the historical compiler collector."""
from __future__ import annotations
import contextlib
import hashlib
import importlib
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time

import desktop_glib_build_contract as c
import desktop_glib_build_evidence as old
import linux_package_provenance_contract as contract
import verify_glib_backport as glib


@contextlib.contextmanager
def environment(values):
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(values)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def engineering_environment(root, target, original):
    for key, value in original.items():
        c.need(not key.startswith(('APPIMAGE_RELRO_', 'LD_', 'DYLD_', 'LDAI_', 'LINUXDEPLOY_',
            'APPIMAGE_', 'TAURI_')) or key == 'APPIMAGE_EXTRACT_AND_RUN' and value == '1',
            'inherited_engineering_override:' + key)
        c.need(key not in ('PATCHELF', 'PATCHELF_DEBUG', 'NO_STRIP', 'DEPLOY_GSTREAMER',
            'OUTPUT', 'APPDIR', 'DISABLE_COPYRIGHT_FILES_DEPLOYMENT'), 'inherited_engineering_override:' + key)
    return old.build_environment(root, target, original)


def owned_directories(root, output, target, originals, packages):
    paths = (root, output, target, originals, packages)
    c.need(all(p.is_absolute() and '..' not in p.parts for p in paths), 'invalid_engineering_path')
    c.need(not any(a.is_relative_to(b) for i, a in enumerate(paths) for j, b in enumerate(paths) if i != j),
           'overlapping_engineering_directories')
    for path in paths[1:]:
        with c.parent_descriptor(path) as (fd, _):
            c.need(os.fstat(fd).st_uid == os.geteuid(), 'wrong_engineering_parent_owner')
        c.need(not os.path.lexists(path), 'engineering_directory_must_be_fresh')
    old.new_directory(output)
    old.new_directory(target)
    old.new_directory(output / 'traces')


def check_restored_target(target, output):
    original = target / c.TARGET / 'release' / c.BINARY
    c.need(c.stable_file(original, target, c.MAX_BINARY, allow_hardlinks=True) ==
           c.file_record(output / 'desktop.elf'), 'tauri_did_not_restore_prebundle_elf')


def collect(root, output, target, sha, archive, audit_binary, audit_db, originals, packages, profile):
    import appimage_tools
    import appimage_relro_tool
    import rc_packages
    entry = importlib.import_module('AppImage入口配置v3')
    c.need(profile == contract.PROFILE, 'wrong_expected_profile')
    source = contract.source_identity(root, sha)
    env = engineering_environment(root, target, os.environ)
    c.need(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_SHA') == sha and
        os.environ.get('GITHUB_WORKFLOW_SHA') == sha and os.environ.get('GITHUB_JOB') == 'build' and
        os.environ.get('GITHUB_REPOSITORY') == c.REPOSITORY, 'trusted_github_producer_required')
    producer = contract.producer_identity(sha, os.environ.get('GITHUB_RUN_ID'),
        os.environ.get('GITHUB_RUN_ATTEMPT'), os.environ.get('GITHUB_WORKFLOW_REF'))
    release = platform.freedesktop_os_release()
    c.need(release.get('ID') == 'ubuntu' and release.get('VERSION_ID') == '22.04' and
        platform.machine() == 'x86_64' and platform.system() == 'Linux', 'wrong_producer_platform')
    owned_directories(root, output, target, originals, packages)
    tools = old.tool_identities(root, env, audit_binary)
    c.need(Path(shutil.which('python3', path=env['PATH']) or '').resolve() == Path(tools['python']['path']),
           'guard_python_not_collector_python')
    c.copy_regular(archive, output / 'upstream.crate', 1024**2)
    c.need(c.file_record(output / 'upstream.crate')['sha256'] == glib.ARCHIVE_SHA, 'wrong_official_glib_archive')
    c.need(not audit_db.exists(), 'advisory_snapshot_must_be_fresh')
    started = time.time_ns()
    code = old.capture(['git', 'clone', '--depth', '1', 'https://github.com/RustSec/advisory-db.git', str(audit_db)],
        root, env, output / 'advisory-clone.stdout', output / 'advisory-clone.stderr', timeout=300)
    c.need(code == 0, 'advisory_clone_failed')
    database = old.advisory_identity(audit_db)
    acquisition = dict(method='fresh_official_clone', started_ns=started, finished_ns=time.time_ns(), exit=code)
    audit_command = [tools['python']['path'], 'scripts/verify_glib_backport.py', '--root', str(root),
        '--archive', str(output / 'upstream.crate'), '--audit-bin', str(audit_binary),
        '--audit-db', str(audit_db), '--output', str(output / 'source-audit')]
    code = old.capture(audit_command, root, env, output / 'source-audit.stdout', output / 'source-audit.stderr', timeout=600)
    c.need(code == 0, 'failed_source-audit')
    commands = {'source-audit': dict(argv=audit_command, exit=code)}
    meta = [tools['cargo']['path'], 'metadata', '--locked', '--format-version', '1', '--manifest-path',
            'src-tauri/Cargo.toml', '--features', 'tauri/custom-protocol']
    tree = [tools['cargo']['path'], 'tree', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
        '--prefix', 'none', '--format', '{p}\t{f}', '--target', c.TARGET, '--edges', 'normal,build',
        '--features', 'tauri/custom-protocol']
    for command, name, error in ((meta, 'metadata', 'metadata_capture_failed'), (tree, 'selected-tree', 'selected_tree_capture_failed')):
        suffix = '.json' if name == 'metadata' else '.txt'
        c.need(old.capture(command, root, env, output / (name + suffix), output / (name + '.stderr'), timeout=600) == 0, error)
    env.update(APPIMAGE_EXTRACT_AND_RUN='1', LDAI_RUNTIME_FILE=str(originals / 'runtime-x86_64'))
    with environment(env):
        appimage_tools.prepare(root, target, originals, sha, output / 'appimage-tools-prepared.json')
        guard = appimage_relro_tool.prepare_session(dict(**source, source_root=str(root), producer=producer,
            profile=profile), target, output, {'originals_dir': str(originals)}, tools['python'])
        appimage_tools.verify(root, target, originals, sha, 'before', output / 'appimage-tools-before.json')
    guard_path = output / 'appimage-relro/config.json'
    env.update(PATCHELF=str(root / 'scripts/appimage_relro_guard.py'), APPIMAGE_RELRO_CONFIG=str(guard_path),
               APPIMAGE_RELRO_CONFIG_SHA256=c.file_record(guard_path)['sha256'])
    config = dict(source_sha=sha, source_root=str(root), target_dir=str(target), profile=profile,
        evidence_root=str(output), evidence_dir=str(output / 'traces'),
        real_cargo=tools['cargo']['path'], real_cargo_sha256=tools['cargo']['sha256'],
        real_rustc=tools['rustc']['path'], real_rustc_sha256=tools['rustc']['sha256'])
    config_path = output / 'runner-config.json'
    c.write_json(config_path, config)
    runner = root / 'scripts/desktop_glib_build_evidence.py'
    env.update({old.CONFIG_ENV: str(config_path), old.CONFIG_ENV + '_SHA256': c.file_record(config_path)['sha256'],
                'RUSTC': tools['rustc']['path'], 'RUSTC_WRAPPER': str(runner)})
    build = contract.tauri_command(root)
    code = old.capture(build, root, env, output / 'tauri.stdout', output / 'tauri.stderr', forward=True)
    c.need(code == 0, 'tauri_product_build_failed')
    cargo_exit = contract.read_json(output / 'cargo-exit.json')['exit']
    c.need(type(cargo_exit) is int and cargo_exit == 0, 'cargo_product_build_failed')
    from appimage_relro_guard import seal_session
    seal_session(guard)
    check_restored_target(target, output)
    bundle = target / c.TARGET / 'release/bundle'
    contract.check_bundle_directory(bundle, target)
    raw_debs, images = list((bundle / 'deb').glob('*.deb')), list((bundle / 'appimage').glob('*.AppImage'))
    c.need(len(raw_debs) == len(images) == 1, 'expected_one_fresh_package_per_kind')
    c.copy_regular(raw_debs[0], output / 'desktop.deb')
    with environment(env):
        appimage_tools.verify(root, target, originals, sha, 'after', output / 'appimage-tools-after.json')
        entry.verify(root, images[0], output / 'appimage-entry.json', sha, output)
        members = entry.elf_inventory(bundle / 'appimage/Coding Tools MCP.AppDir', output / 'appdir-members')
        c.write_json(output / 'appdir-entry.json', {'members': members})
    with environment(dict(env, GITHUB_SHA=sha, GITHUB_RUN_ID=producer['run_id'])):
        manifest = rc_packages.prepare(root, packages, sha, bundle)
    c.copy_regular(packages / 'exclusive-package.json', output / 'package-manifest.json')
    c.copy_regular(packages / manifest['packages']['deb']['artifact']['name'], output / 'final.deb')
    _, parser = contract.final_deb_payload(output / 'final.deb', rc_packages.debian_version(source['version']))
    c.write_json(output / 'final-deb-parser.json', parser)
    references, _ = contract.package_bindings(output, source['version'])
    envelope = dict(schema='linux-package-provenance-v1', profile=profile, **source,
        **{**c.FLAGS, **contract.SCOPE}, producer=producer, source_root=str(root), target_dir=str(target),
        evidence_root=str(output), originals_dir=str(originals), packages_root=str(packages),
        cargo_exit=cargo_exit, tauri_exit=code, cargo_arguments=c.cargo_arguments(), tauri_command=build,
        metadata_command=meta, selected_tree_command=tree, tools=tools,
        build_environment={k: v for k, v in env.items() if not k.startswith('DESKTOP_GLIB_')},
        commands=commands, audit_binary=str(audit_binary), audit_db=str(audit_db),
        advisory_database=database, advisory_acquisition=acquisition)
    final = contract.guard_replay(output, envelope, references)
    c.write_json(output / 'appimage-relro/final.json', final)
    inputs = dict(schema='linux-provenance-inputs-v1', profile=profile, source_sha=sha,
        source_tree=source['source_tree'], version=source['version'], producer=producer,
        packages=manifest['packages'], package_references=references,
        members=contract.read_json(output / 'appimage-entry.json')['members'],
        guard_final=c.file_record(output / 'appimage-relro/final.json'), **contract.SCOPE)
    c.write_json(packages / 'provenance-inputs.json', inputs)
    c.copy_regular(packages / 'provenance-inputs.json', output / 'provenance-inputs.json')
    c.need(contract.source_identity(root, sha) == source and old.advisory_identity(audit_db) == database,
           'source_or_database_changed')
    glib.verify_configuration(root, env)
    glib.verify_source(root, output / 'upstream.crate')
    envelope.update(package_manifest=c.file_record(output / 'package-manifest.json'),
        provenance_inputs=c.file_record(output / 'provenance-inputs.json'), files=c.evidence_inventory(output))
    c.write_json(output / 'envelope.json', envelope)
    digest = c.file_record(output / 'envelope.json')['sha256']
    proof = contract.verify(root, output, sha, producer, digest, profile)
    c.copy_regular(output / 'envelope.json', packages / 'compiler-envelope.json')
    return proof


def dispatch(args):
    c.need(args.expected_profile == contract.PROFILE, 'explicit_engineering_profile_required')
    if args.mode == 'collect-linux':
        c.need(all((args.target_directory, args.archive, args.audit_bin, args.audit_db,
            args.originals_directory, args.packages_directory)), 'missing_engineering_collect_input')
        return collect(args.root.absolute(), args.directory.absolute(), args.target_directory.absolute(),
            args.source, args.archive.absolute(), args.audit_bin.resolve(strict=True), args.audit_db.absolute(),
            args.originals_directory.absolute(), args.packages_directory.absolute(), args.expected_profile)
    producer = contract.producer_identity(args.source, args.producer_run_id,
        args.producer_run_attempt, args.producer_workflow_ref)
    c.need(re.fullmatch('[1-9][0-9]*', args.artifact_id or '') and
        re.fullmatch('(?:sha256:)?[0-9a-f]{64}', args.artifact_digest or ''), 'missing_expected_evidence_artifact')
    result = contract.verify(args.root.absolute(), args.directory.absolute(), args.source,
        producer, args.expected_envelope_sha256, args.expected_profile)
    result['artifact_reference'] = dict(id=args.artifact_id, digest=args.artifact_digest,
        run_id=producer['run_id'], run_attempt=producer['run_attempt'])
    return result
