"""Engineering compiler/package replay with external source, attempt and digest authority."""
from __future__ import annotations
import argparse
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tarfile

import desktop_glib_build_contract as c
import desktop_glib_deb as deb
from AppImage入口配置v3 import setup_python_library, setup_python_omitted

PROFILE = 'linux-engineering-packages-v1'
WORKFLOW = 'linux-rc-packages.yml'
EXTRA_SOURCE = ('scripts/linux_package_provenance.py', 'scripts/linux_package_provenance_contract.py',
    'scripts/appimage_relro_tool.py', 'scripts/appimage_relro_guard.py', 'scripts/appimage_relro_contract.py',
    'scripts/appimage_tools.py', 'scripts/rc_packages.py', 'scripts/linux_runtime_provenance.py',
    '.github/workflows/' + WORKFLOW)
SCOPE = dict(all_bundled_dsos_relro_preserved=False, full_dependency_closure_verified=False,
    native_linker_consumption_verified=False, retained_glib_code_verified=False,
    independent_all_query_attempts_verified=False, security_approved=False,
    release_approved=False, publish_approved=False)
EXTRA_FILES = {'appimage-tools-prepared.json', 'appimage-tools-before.json', 'appimage-tools-after.json',
    'appimage-entry.json', 'appdir-entry.json', 'appimage-desktop.elf', 'final.deb',
    'final-deb-parser.json', 'package-manifest.json', 'provenance-inputs.json'}
GUARD_FILES = {'config.json', 'parser-tool.json', 'original-patchelf', 'compiler-binding.json',
               'lock', 'state.json', 'operations.jsonl', 'final.json'}


def capture_setup_python_loader(environment, *, omission=False):
    def omitted(record):
        return dict(schema='setup-python-omission-v1', input=record, original_ld_library_path=record['library_path'] if record else None,
            child_ld_library_path=None, loading_authorized=False)
    if 'LD_LIBRARY_PATH' not in environment:
        return omitted(None) if omission else None
    version = '.'.join(map(str, sys.version_info[:3]))
    installation = '/opt/hostedtoolcache/Python/' + version + '/x64'
    executable = Path(sys.executable).resolve(strict=True)
    c.need(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12) and
        str(executable) == installation + '/bin/python3.12' and sys.prefix == installation and
        environment.get('pythonLocation', installation) == installation, 'unrecognized_setup_python_installation')
    library = Path(installation) / 'lib'
    c.need(environment['LD_LIBRARY_PATH'] == str(library), 'unrecognized_setup_python_loader_path')
    def identity(info):
        return (*c.file_identity(info), info.st_mode, info.st_uid)
    with c.parent_descriptor(library / '.loader-evidence') as (fd, _):
        before = os.fstat(fd)
        c.need(before.st_uid in (0, os.geteuid()), 'unowned_setup_python_library')
        exe_before = executable.stat(follow_symlinks=False)
        record = dict(schema='setup-python-loader-v1', version=version,
            executable=dict(path=str(executable), **c.file_record(executable, 32 * 1024**2)),
            library_path=str(library), library_directory=dict(device=before.st_dev, inode=before.st_ino,
                mode=before.st_mode, uid=before.st_uid))
        try:
            setup_python_omitted(omitted(record)) if omission else setup_python_library(record)
        except ValueError:
            diagnostic = dict(requested_python=str(sys.executable)[:1024], resolved_python=str(executable)[:1024],
                python_version=version[:32], python_prefix=str(sys.prefix)[:1024],
                python_sha256=record['executable']['sha256'], python_size=record['executable']['size'],
                library_path=str(library)[:1024], library_mode=before.st_mode, library_uid=before.st_uid,
                library_gid=before.st_gid, library_device=before.st_dev, library_inode=before.st_ino)
            try:
                print('SETUP_PYTHON_LOADER_REJECTION:' + json.dumps(diagnostic, sort_keys=True), file=sys.stderr, flush=True)
            except (OSError, ValueError):
                pass
            raise
        with c.parent_descriptor(library / '.loader-evidence') as (named_fd, _):
            c.need(identity(before) == identity(os.fstat(fd)) == identity(os.fstat(named_fd)) ==
                identity(library.stat(follow_symlinks=False)) and
                identity(exe_before) == identity(executable.stat(follow_symlinks=False)), 'changed_setup_python_identity')
    return omitted(record) if omission else record


def producer_identity(sha, run_id, attempt, workflow_ref):
    c.need(re.fullmatch('[0-9a-f]{40}', sha or ''), 'invalid_producer_source')
    c.need(all(type(v) is str and re.fullmatch('[1-9][0-9]*', v) for v in (run_id, attempt)),
           'invalid_producer_run')
    prefix = c.REPOSITORY + '/.github/workflows/' + WORKFLOW + '@refs/heads/'
    c.need(type(workflow_ref) is str and workflow_ref.startswith(prefix) and re.fullmatch(
        r'(?:fix/linux-startup-platform|ci/preliminary-packages-[A-Za-z0-9._-]+)', workflow_ref[len(prefix):]),
        'invalid_producer_workflow')
    return dict(provider='github-actions', repository=c.REPOSITORY, source_sha=sha, workflow_sha=sha,
        run_id=run_id, run_attempt=attempt, workflow_ref=workflow_ref, job='build', runner_os='Linux',
        platform={'id': 'ubuntu', 'version_id': '22.04'})


def source_identity(root, sha):
    return {**c.source_identity(root, sha), 'engineering_source_inputs':
            {name: c.file_record(root / name, c.MAX_JSON) for name in EXTRA_SOURCE}}


def tauri_command(root):
    return ['npm', 'run', 'tauri', '--', '--verbose', 'build', '--config', 'src-tauri/Ubuntu桌面v1.json',
        '--bundles', 'deb,appimage', '--target', c.TARGET, '--runner',
        str(Path(root) / 'scripts/desktop_glib_build_evidence.py'), '--', '--locked', '--message-format=json']


def check_bundle_directory(bundle, target):
    c.need(target.is_absolute() and '..' not in target.parts and
           bundle == target / c.TARGET / 'release/bundle', 'wrong_authenticated_bundle_directory')
    with c.parent_descriptor(bundle / 'sentinel'):
        pass


def read_json(path):
    return c.decode(c.read_regular(path))


def verify_header(e, source, expected_producer, expected_profile):
    c.need(expected_profile == PROFILE and e.get('profile') == expected_profile, 'wrong_expected_profile')
    c.need(e.get('schema') == 'linux-package-provenance-v1' and
           all(e.get(k) == v for k, v in source.items()), 'wrong_envelope_source')
    c.need(e.get('producer') == expected_producer == producer_identity(source['source_sha'],
        expected_producer['run_id'], expected_producer['run_attempt'], expected_producer['workflow_ref']),
        'wrong_envelope_producer')
    c.need(all(e.get(k) is v for k, v in {**c.FLAGS, **SCOPE}.items()), 'wrong_scope_flags')
    c.need(all(type(e.get(k)) is int and e[k] == 0 for k in ('cargo_exit', 'tauri_exit')),
           'failed_product_build')
    paths = [e[key] for key in ('source_root', 'target_dir', 'evidence_root', 'originals_dir', 'packages_root')]
    c.need(all(type(value) is str and Path(value).is_absolute() and str(Path(value)) == value and
        '..' not in Path(value).parts and len(value.encode()) <= 1024 for value in paths) and not any(
        Path(a).is_relative_to(Path(b)) for i, a in enumerate(paths) for j, b in enumerate(paths) if i != j),
        'invalid_engineering_directory_relationship')
    c.need(e.get('cargo_arguments') == c.cargo_arguments() and
           e.get('tauri_command') == tauri_command(e['source_root']), 'wrong_engineering_build_command')
    c.need('python_loader' in e and e['python_loader'] is None and
        setup_python_omitted(e['python_loader_omission']), 'missing_setup_python_omission')
    original_python = e['python_loader_omission']['input']
    if original_python is not None:
        c.need(original_python['executable'] == {key: e['tools']['python'][key] for key in ('path', 'sha256', 'size')} and
            e['tools']['python']['version'] == 'Python ' + original_python['version'], 'setup_python_compiler_identity_mismatch')
    runner = e['source_root'] + '/scripts/desktop_glib_build_evidence.py'
    fixed = dict(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', CARGO_TERM_COLOR='never',
        CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='2', CARGO_PROFILE_RELEASE_DEBUG='0',
        CARGO_TARGET_DIR=e['target_dir'], TZ='UTC', RUSTC=e['tools']['rustc']['path'], RUSTC_WRAPPER=runner,
        APPIMAGE_EXTRACT_AND_RUN='1', LDAI_RUNTIME_FILE=e['originals_dir'] + '/runtime-x86_64',
        PATCHELF=e['source_root'] + '/scripts/appimage_relro_guard.py',
        APPIMAGE_RELRO_CONFIG=e['evidence_root'] + '/appimage-relro/config.json',
        APPIMAGE_RELRO_CONFIG_SHA256=e['files']['appimage-relro/config.json']['sha256'])
    env = e.get('build_environment', {})
    c.need(type(env) is dict and all(env.get(k) == v for k, v in fixed.items()) and
        set(env) <= set(fixed) | {'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TMPDIR',
                                 'RUSTUP_HOME', 'CARGO_HOME'}, 'unreviewed_build_environment')
    for tool in ('cargo', 'rustc'):
        c.need(re.match(tool + r' 1\.98\.1(?: |$)', e['tools'][tool]['version']) and
               re.fullmatch('[0-9a-f]{64}', e['tools'][tool]['sha256']), 'wrong_product_toolchain')
    c.need(e['tools']['tauri']['version'] == 'tauri-cli 2.11.4' and
           e['tools']['python']['version'].startswith('Python 3.12.'), 'wrong_tauri_or_python')
    cargo = e['tools']['cargo']['path']
    c.need(e.get('metadata_command') == [cargo, 'metadata', '--locked', '--format-version', '1',
        '--manifest-path', 'src-tauri/Cargo.toml', '--features', 'tauri/custom-protocol'], 'wrong_metadata_command')
    c.need(e.get('selected_tree_command') == [cargo, 'tree', '--locked', '--manifest-path', 'src-tauri/Cargo.toml',
        '--prefix', 'none', '--format', '{p}\t{f}', '--target', c.TARGET, '--edges', 'normal,build',
        '--features', 'tauri/custom-protocol'], 'wrong_selected_tree_command')
    snapshot, acquisition = e['advisory_database'], e['advisory_acquisition']
    c.need(snapshot.get('clean') is True and snapshot.get('origin') == 'https://github.com/RustSec/advisory-db.git',
           'untrusted_advisory_database')
    for key, length in (('commit', 40), ('tree', 40), ('contents_sha256', 64)):
        c.need(re.fullmatch('[0-9a-f]{' + str(length) + '}', str(snapshot.get(key))), 'bad_advisory_identity')
    c.need(acquisition.get('method') == 'fresh_official_clone' and type(acquisition.get('exit')) is int and
        acquisition['exit'] == 0 and type(acquisition.get('started_ns')) is int and
        type(acquisition.get('finished_ns')) is int and 0 < acquisition['started_ns'] <= acquisition['finished_ns'],
        'wrong_advisory_acquisition')


def verify_inventory(directory, files):
    from appimage_relro_contract import PROTECTED
    c.need(files == c.evidence_inventory(directory), 'changed_evidence_inventory')
    for name in files:
        c.need(c.stable_file(directory / name, directory) == files[name], 'unowned_or_changed_evidence')
    expected = c.FILES | EXTRA_FILES | {'appimage-relro/' + n for n in GUARD_FILES}
    expected |= {prefix + '/' + n for prefix in ('appdir-members', 'appimage-members') for n in PROTECTED}
    actual = {n for n in files if not re.fullmatch(r'traces/rustc-[0-9a-f]{32}\.json', n)}
    c.need(actual == expected, 'unexpected_engineering_evidence_files')


def verify_tool_checks(directory, e):
    import appimage_tools as tools
    for phase, filename in (('prepare', 'prepared'), ('before', 'before'), ('after', 'after')):
        value = read_json(directory / ('appimage-tools-' + filename + '.json'))
        c.need(value.get('schema') == 'pinned-appimage-tools-v1' and value.get('phase') == phase and
            value.get('pins') == list(tools.TOOLS) and value.get('source_sha') == e['source_sha'] and
            value.get('source_tree') == e['source_tree'] and value.get('source_root') == e['source_root'] and
            value.get('target_directory') == e['target_dir'] and value.get('passed') is True and
            value.get('runtime_file') == e['originals_dir'] + '/runtime-x86_64', 'wrong_pinned_tool_receipt')
        originals, cache = {}, {}
        for tool in tools.TOOLS:
            originals[tool['name']] = dict(path=e['originals_dir'] + '/' + tool['name'],
                size=tool['size'], sha256=tool['sha256'], mode='0o444')
            if tool['cache_name']:
                cache[tool['cache_name']] = dict(path=e['target_dir'] + '/.tauri/' + tool['cache_name'],
                    size=tool['size'], sha256=tools.NORMALIZED_SHA256 if tool['name'] == 'linuxdeploy-x86_64.AppImage'
                    else tool['sha256'], mode='0o755')
        if phase == 'after':
            cache['AppRun-x86_64'] = dict(path=e['target_dir'] + '/.tauri/AppRun-x86_64',
                size=tools.LAUNCHER_SIZE, sha256=tools.LAUNCHER_SHA256, mode='0o755')
        c.need(value.get('originals') == originals and value.get('cache') == cache and
            all(value.get(key) is False for key in ('security_approved', 'release_approved', 'publish_approved')),
            'changed_original_tool_or_cache_pin')


def verify_package_identity(manifest, inputs, e):
    import rc_packages
    c.need(inputs.get('schema') == 'linux-provenance-inputs-v1' and inputs.get('profile') == PROFILE and
        inputs.get('source_sha') == e['source_sha'] and inputs.get('source_tree') == e['source_tree'] and
        inputs.get('producer') == e['producer'] and inputs.get('version') == e['version'] and
        all(inputs.get(k) is v for k, v in SCOPE.items()), 'wrong_package_provenance_context')
    c.need(manifest.get('source_sha') == e['source_sha'] and manifest.get('source_tree') == e['source_tree'] and
        manifest.get('version') == e['version'] and manifest.get('run_id') == e['producer']['run_id'] and
        manifest.get('build_kind') == 'release-candidate' and manifest.get('passed') is True and
        set(manifest.get('packages', {})) == {'deb', 'appimage'} and manifest['packages'] == inputs['packages'],
        'wrong_package_manifest')
    for kind, item in manifest['packages'].items():
        suffix = '.deb' if kind == 'deb' else '.AppImage'
        expected_version = rc_packages.debian_version(e['version']) if kind == 'deb' else e['version']
        c.need(item['artifact']['name'] == f"MCP_{e['version']}_amd64{suffix}" and
            item['package_version'] == expected_version and item['architecture'] == 'amd64' and
            item['package_id'] == ('coding-tools-mcp' if kind == 'deb' else None), 'wrong_package_identity')
        c.need(re.fullmatch('[0-9a-f]{64}', item['artifact']['sha256']) and
            type(item['artifact']['size']) is int and 0 < item['artifact']['size'] <= c.MAX_BINARY and
            re.fullmatch('[0-9a-f]{64}', item['payload_sha256']), 'wrong_package_record')


def parser_limits():
    try:
        import resource
    except ImportError as exc:
        raise RuntimeError('Linux DEB parser resource limits are unavailable on this platform') from exc
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (deb.MAX_TAR, deb.MAX_TAR))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))


def final_payload_members(raw):
    files, dirs, seen, total = {}, set(), set(), 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive:
            c.need(len(seen) < deb.MAX_ENTRIES and not member.pax_headers, 'final_tar_entry_limit_or_extension')
            name = member.name[2:] if member.name.startswith('./') else member.name
            if name in ('', '.'):
                c.need(member.isdir() and member.size == 0 and member.mode in (0o700, 0o755) and member.uid == member.gid == 0 and
                    not dirs and not files and name not in seen, 'invalid_final_tar_root')
                seen.add(name)
                continue
            c.need(len(name.encode()) <= deb.MAX_PATH and not name.startswith('/') and
                all(part not in ('', '.', '..') for part in name.split('/')) and
                '\\' not in name and all(ord(ch) >= 32 and ord(ch) != 127 for ch in name) and name not in seen,
                'unsafe_or_duplicate_final_tar_path')
            seen.add(name)
            c.need(member.uid == member.gid == 0 and (member.isfile() or member.isdir()) and
                member.mode == (0o755 if member.isdir() or name == deb.BINARY else 0o644), 'unsafe_final_tar_member')
            total += member.size
            c.need(0 <= member.size <= c.MAX_BINARY and total <= deb.MAX_TAR, 'final_tar_payload_limit')
            if member.isdir():
                c.need(member.size == 0, 'nonempty_final_tar_directory'); dirs.add(name)
            else:
                with archive.extractfile(member) as stream: body = stream.read(member.size + 1)
                c.need(len(body) == member.size, 'truncated_final_tar_payload'); files[name] = body
    c.need(set(files) == deb.DATA_FILES and dirs <= deb.DATA_DIRS, 'unexpected_final_deb_members')
    return files, dirs, len(seen)


def final_deb_payload(path, version):
    """A fixed system archive reader; never load code or commands from evidence."""
    parser = Path('/usr/bin/dpkg-deb')
    parser_record = c.file_record(parser, single_link=False)
    with c.regular_descriptor(path, c.MAX_BINARY) as (fd, info), tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        descriptor = '/proc/self/fd/' + str(fd)
        command = [str(parser), '--fsys-tarfile', descriptor]
        result = subprocess.run(command, pass_fds=(fd,), stdout=output, stderr=errors,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'}, timeout=45,
            preexec_fn=parser_limits, check=False)
        errors.seek(0)
        c.need(result.returncode == 0 and len(errors.read(65537)) <= 65536, 'final_deb_parser_failed')
        output.seek(0)
        raw = output.read(deb.MAX_TAR + 1)
        c.need(len(raw) <= deb.MAX_TAR, 'final_deb_parser_overflow')
        files, dirs, count = final_payload_members(raw)
        c.need(set(files) == deb.DATA_FILES and dirs <= deb.DATA_DIRS, 'unexpected_final_deb_members')
        os.lseek(fd, 0, os.SEEK_SET)
        output.seek(0); output.truncate(); errors.seek(0); errors.truncate()
        result = subprocess.run([str(parser), '--field', descriptor, 'Package', 'Version', 'Architecture'],
            pass_fds=(fd,), stdout=output, stderr=errors, env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'},
            preexec_fn=parser_limits, timeout=30, check=False)
        expected = f'Package: coding-tools-mcp\nVersion: {version}\nArchitecture: amd64\n'.encode()
        output.seek(0); errors.seek(0)
        c.need(result.returncode == 0 and output.read(65537) == expected and len(errors.read(65537)) <= 65536,
               'wrong_final_deb_control_identity')
        c.need(c.file_identity(path.stat(follow_symlinks=False)) == c.file_identity(info), 'final_deb_path_changed')
    c.need(parser_record == c.file_record(parser, single_link=False), 'final_deb_parser_changed')
    return files, dict(parser=str(parser), **parser_record, mode='fixed-data-reader',
        archive=c.file_record(path), version=version, members=count)


def package_bindings(directory, version):
    import rc_packages
    raw = c.read_regular(directory / 'desktop.deb', c.MAX_BINARY)
    pre = c.read_regular(directory / 'desktop.elf', c.MAX_BINARY)
    raw_proof = deb.verify_deb(pre, raw, version)
    archive = deb.ar_members(raw)
    raw_files, _, _ = deb.tar_members(deb.gunzip(archive['data.tar.gz'], deb.MAX_TAR))
    final_files, parser = final_deb_payload(directory / 'final.deb', rc_packages.debian_version(version))
    c.need(raw_files == final_files, 'repacked_deb_payload_changed')
    prior = read_json(directory / 'final-deb-parser.json')
    c.need(prior.get('parser') == '/usr/bin/dpkg-deb' and re.fullmatch('[0-9a-f]{64}', prior.get('sha256', '')) and
        all(prior.get(k) == parser[k] for k in ('archive', 'version', 'members', 'mode')), 'final_deb_parser_receipt_changed')
    payload = dict(sha256=hashlib.sha256(final_files[deb.BINARY]).hexdigest(), size=len(final_files[deb.BINARY]))
    return dict(prebundle=c.file_record(directory / 'desktop.elf'),
        raw_deb={**c.file_record(directory / 'desktop.deb'), 'payload_sha256': payload['sha256']},
        final_deb={**c.file_record(directory / 'final.deb'), 'payload_sha256': payload['sha256']}), raw_proof


def guard_replay(directory, e, references):
    import appimage_relro_contract as guard
    names = {p.name for p in (directory / 'appimage-relro').iterdir()}
    c.need(names in (GUARD_FILES, GUARD_FILES - {'final.json'}), 'failed_or_unexpected_guard_state')
    config = read_json(directory / 'appimage-relro/config.json')
    c.need(config['profile'] == PROFILE and config['source_sha'] == e['source_sha'] and
        config['source_tree'] == e['source_tree'] and config['producer'] == e['producer'] and
        config['source_root'] == e['source_root'] and config['target_root'] == e['target_dir'] and
        config['evidence_root'] == e['evidence_root'] and
        config['guard_sha256'] == e['engineering_source_inputs']['scripts/appimage_relro_guard.py']['sha256'] and
        config['python_path'] == e['tools']['python']['path'] and config['python_sha256'] == e['tools']['python']['sha256'] and
        config['python_version'] == e['tools']['python']['version'], 'wrong_guard_context')
    compiler = read_json(directory / 'compiler-copies.json')
    compiler.update(compiled=c.read_regular(directory / 'desktop.elf', c.MAX_BINARY),
        compiler_copies_bytes=c.read_regular(directory / 'compiler-copies.json'),
        build_jsonl_bytes=c.read_regular(directory / 'build.jsonl'),
        relro_evidence={name: c.read_regular(directory / 'appimage-relro' / name)
                        for name in GUARD_FILES if name != 'final.json' or (directory / 'appimage-relro/final.json').exists()})
    records = []
    for name in ('appdir', 'appimage'):
        items = read_json(directory / (name + '-entry.json'))['members']
        records.append({path: {**item, **({'data': c.read_regular(directory / (name + '-members') / path,
            c.MAX_BINARY)} if path in guard.PROTECTED else {})} for path, item in items.items()})
    image = read_json(directory / 'package-manifest.json')['packages']['appimage']['artifact']
    image = {key: image[key] for key in ('sha256', 'size')}
    return guard.verify_final(config, compiler, *records, image,
        {name: c.read_regular(directory / ('tauri.' + name)) for name in ('stdout', 'stderr')}, references)


def verify_packages(directory, e):
    references, raw_proof = package_bindings(directory, e['version'])
    manifest = read_json(directory / 'package-manifest.json')
    inputs = read_json(directory / 'provenance-inputs.json')
    verify_package_identity(manifest, inputs, e)
    c.need(inputs['package_references'] == references, 'changed_deb_package_references')
    c.need({k: manifest['packages']['deb']['artifact'][k] for k in ('sha256', 'size')} ==
        c.file_record(directory / 'final.deb'), 'wrong_final_deb_archive')
    entry = read_json(directory / 'appimage-entry.json')
    paths = sorted(name for name, record in entry['members'].items() if record['kind'] == 'file')
    c.need(len(paths) == 179 and hashlib.sha256('\n'.join(paths).encode()).hexdigest() ==
        '218ae8dcbd7bc243de2034770d63978f90be13a3f2cd91b205ede77d0b11a259', 'changed_dependency_path_inventory')
    c.need(entry['source_sha'] == e['source_sha'] and entry['passed'] is True and
        entry['appimage_sha256'] == manifest['packages']['appimage']['artifact']['sha256'] and
        entry['members'] == inputs['members'], 'wrong_final_appimage_inventory')
    final = guard_replay(directory, e, references)
    c.need(read_json(directory / 'appimage-relro/final.json') == final and
        inputs['guard_final'] == c.file_record(directory / 'appimage-relro/final.json') and
        e['package_manifest'] == c.file_record(directory / 'package-manifest.json') and
        e['provenance_inputs'] == c.file_record(directory / 'provenance-inputs.json'), 'changed_final_guard_or_package_binding')
    return inputs, final, raw_proof


def verify(root, directory, sha, expected_producer, trusted_digest, expected_profile):
    c.need(re.fullmatch('[0-9a-f]{64}', trusted_digest or ''), 'missing_trusted_envelope_digest')
    data = c.read_regular(directory / 'envelope.json')
    c.need(hashlib.sha256(data).hexdigest() == trusted_digest, 'wrong_trusted_envelope_digest')
    e = c.decode(data)
    source = source_identity(root, sha)
    verify_header(e, source, expected_producer, expected_profile)
    verify_inventory(directory, e['files'])
    metadata = read_json(directory / 'metadata.json')
    c.need(metadata.get('target_directory') == e['target_dir'], 'metadata_target_directory_mismatch')
    verify_tool_checks(directory, e)
    paired, lineage, raw = c.verify_compiler_payload(root, directory, sha, source, e, PROFILE)
    inputs, guard, _ = verify_packages(directory, e)
    return dict(schema='linux-package-proof-v1', profile=PROFILE, **source, **{**c.FLAGS, **SCOPE},
        producer=expected_producer, envelope_sha256=trusted_digest,
        desktop_compiler_input_to_deb_binding_verified=True, compiler_input_provenance=lineage,
        paired_source=paired, raw_deb=raw, packages=inputs['packages'], guard=guard,
        limitations=['sampled runtime mappings are a separate gate', 'query attempts before wrapper entry may be unobserved'])


def installed_binding(directory, source, expected_producer, digest, profile, artifact_id, artifact_digest, kind, os_name):
    c.need(profile == PROFILE and kind in ('deb', 'appimage') and os_name in ('ubuntu-22.04', 'ubuntu-24.04'),
           'wrong_installed_profile')
    c.need(re.fullmatch('[1-9][0-9]*', artifact_id or '') and
        re.fullmatch('(?:sha256:)?[0-9a-f]{64}', artifact_digest or ''), 'invalid_artifact_identity')
    data = c.read_regular(directory / 'compiler-envelope.json')
    c.need(re.fullmatch('[0-9a-f]{64}', digest or '') and hashlib.sha256(data).hexdigest() == digest,
           'wrong_trusted_envelope_digest')
    e = c.decode(data)
    c.need(e['profile'] == profile and e['source_sha'] == source and e['producer'] == expected_producer,
           'wrong_installed_source_or_attempt')
    inputs = read_json(directory / 'provenance-inputs.json')
    c.need(c.file_record(directory / 'provenance-inputs.json') == e['provenance_inputs'] and
        inputs['source_sha'] == source and inputs['producer'] == expected_producer and
        inputs['profile'] == profile and inputs['source_tree'] == e['source_tree'], 'changed_runtime_inputs')
    manifest = read_json(directory / 'exclusive-package.json')
    c.need(c.file_record(directory / 'exclusive-package.json') == e['package_manifest'] and
           manifest['packages'] == inputs['packages'], 'changed_installed_manifest')
    verify_package_identity(manifest, inputs, e)
    entry = inputs['packages'][kind]['artifact']
    c.need(Path(entry['name']).name == entry['name'] and c.file_record(directory / entry['name']) ==
        {key: entry[key] for key in ('sha256', 'size')}, 'changed_installed_package')
    members = inputs['members'] if kind == 'appimage' else {deb.BINARY: dict(kind='file',
        sha256=inputs['package_references']['final_deb']['payload_sha256'],
        size=inputs['package_references']['prebundle']['size'])}
    return dict(schema='linux-installed-binding-v1', profile=profile, source_sha=source, source_tree=e['source_tree'],
        run_id=expected_producer['run_id'], run_attempt=expected_producer['run_attempt'],
        workflow=expected_producer['workflow_ref'], os=os_name, kind=kind,
        package={key: entry[key] for key in ('sha256', 'size')}, envelope_sha256=digest,
        artifact_id=artifact_id, artifact_digest=artifact_digest, python_loader=None,
        python_loader_omission=capture_setup_python_loader(os.environ, omission=True),
        members=[dict(path=path, **record) for path, record in sorted(members.items()) if record['kind'] == 'file'],
        main_member=deb.BINARY)


def main():
    if sys.argv[1:2] == ['project-harness-input']:
        from linux_package_provenance import project_harness_input
        return project_harness_input(sys.argv[2:])
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['installed'])
    for key in ('directory', 'output'):
        p.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'expected-profile', 'producer-run-id', 'producer-run-attempt', 'producer-workflow-ref',
                'expected-envelope-sha256', 'artifact-id', 'artifact-digest', 'kind', 'os'):
        p.add_argument('--' + key, required=True)
    a = p.parse_args()
    result = installed_binding(a.directory, a.source, producer_identity(a.source, a.producer_run_id,
        a.producer_run_attempt, a.producer_workflow_ref), a.expected_envelope_sha256, a.expected_profile,
        a.artifact_id, a.artifact_digest, a.kind, a.os)
    c.write_json(a.output, result)


if __name__ == '__main__':
    main()
