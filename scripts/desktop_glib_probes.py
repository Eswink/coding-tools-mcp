#!/usr/bin/env python3
"""Finite locked build probes: diagnostic observations, never compiler ancestry."""
from __future__ import annotations
import os
from pathlib import Path
import re

from exact_build_audit import need
from desktop_glib_link import TARGET, MAX_BINARY, canonical, hash_record

REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'
# Official archive checksum, then official build.rs hash (autocfg: src/lib.rs).
PINS = {
    ('anyhow', '1.0.103'): ('2a4385e2e34eb35d6b3efe798b9eb88096925d87726c0798709bf56d9ed84af3', '89d1baedcff59822ed692d3a33f131c211a213bdec33c83f68b54110d9c64223'),
    ('async-io', '2.6.0'): ('456b8a8feb6f42d237746d4b3e9a178494627745c3c56c6ea55d92ba50d026fc', '114f314a71b008f860a7f6564971c914206e7a1e2252e9fe7ff675d2f75220b3'),
    ('autocfg', '1.5.1'): ('f2032f911046de80f0a198e0901378627c33f59ea0ac00e363d481118bd70a53', '772630d0e09d06f343fd72284c8330eacde87d2a4ee22f70af62a0e2119fbf05'),
    ('indexmap', '1.9.3'): ('bd070e393353796e801d209ad339e89596eb4c8d430d18ede6a1cced8fafbd99', '558b4d0b9e9b3a44f7e1a2b69f7a7567ea721cd45cb54f4e458e850bf702f35c'),
    ('memoffset', '0.9.1'): ('488016bfae457b036d996092f6cb448677611ce4449e970ceaf42695203f218a', '0ddaae191a4091fe1318177d12244ff0dbabc17a18f25a54059f4badc9a20876'),
    ('num-traits', '0.2.19'): ('071dfc062690e90b734c0b2273ce72ad0ffa95f0c74596bc250dcfd960262841', 'd3969209fc1c9d201c66ed11820d0b328600d75b3971f8ceebeab04900bc0587'),
    ('proc-macro2', '1.0.106'): ('8fd00f0bb2e90d81d1044c2b32617f68fcb9fa3bb7640c23e9c748e53fb30934', 'baeb20b52f6b536be8657a566591a507bb2e34a45cf8baa42b135510a0c3c729'),
    ('rustix', '1.1.4'): ('b6fe4565b9518b83ef4f91bb47ce29620ca828bd32cb7e408f0062e9930ba190', '74cb32e64aa6fe99c2496a425b016e22f4e43c438a8237966b8acae04a98eaf9'),
    ('thiserror', '1.0.69'): ('b6aaf5339b578ea85b50e080feb250a3e8ae8cfcdff9a461c9ec2904bc923f52', '275d0ddbb22d5f015fba360f51a48da10b6309410efe8c6ca678412b1e8c9288'),
    ('thiserror', '2.0.18'): ('4288b5bcbc7920c07a1149a35cf9590a2aa808e0bc1eafaade0b80947865fbc4', '18bf4b4af0f507c7fdfe4dbfc98b5ac3d6a5ef924f46ee56125fd8b22fd61b4c')}
FILE_PROBES = {
    ('proc-macro2', '1.0.106', 'src/probe/proc_macro_span.rs'): (1217, '53853f0c70170c9695294b8867821664d9b8f1c901957b003003a3c26987abbe'),
    ('proc-macro2', '1.0.106', 'src/probe/proc_macro_span_file.rs'): (370, 'e7fb4cf8852d9d589bfa3321d8d5cdc8cccb45606ec816a6b8a08f73e416b9ce'),
    ('proc-macro2', '1.0.106', 'src/probe/proc_macro_span_location.rs'): (408, 'e022386204b6e042b3c55a6c809923849a2f915199bcbf3be72d0b7c8ffa7f83'),
    ('anyhow', '1.0.103', 'src/nightly.rs'): (1563, '1c0aeadfcdbe22f8f807b185dec1a7448c378bddb37689714944b60473b58049'),
    ('thiserror', '1.0.69', 'build/probe.rs'): (832, '2e2198c1aa004aabf8b36cc34e057b4dfce56d23401fe0a7582d8480225817f7'),
    ('thiserror', '2.0.18', 'build/probe.rs'): (844, '8df55471d6b75623d423b17ebbf493335ee66140d1ddd232c88db3e59f61298c')}
AUTOCFG_CALLERS = {'async-io', 'indexmap', 'memoffset', 'num-traits'}


def classify_probe(args, cwd, target_dir, environment):
    """Return a finite descriptor only for an exact reviewed ordered invocation."""
    name, version = (environment.get(k) for k in ('CARGO_PKG_NAME', 'CARGO_PKG_VERSION'))
    if (name, version) not in PINS or name == 'autocfg':
        return None
    out, source, family = environment.get('OUT_DIR', ''), None, None
    for package, revision, relative in FILE_PROBES:
        if (package, revision) != (name, version):
            continue
        prefix = ['--cfg=procmacro2_build_probe'] if name == 'proc-macro2' else (
                 ['--cfg=anyhow_build_probe'] if name == 'anyhow' else [])
        expected = prefix + ['--edition=' + ('2021' if name == 'proc-macro2' else '2018'),
            '--crate-name=' + name.replace('-', '_'), '--crate-type=lib', '--cap-lints=allow',
            '--emit=dep-info,metadata', '--out-dir', out + '/probe', relative, '--target', TARGET]
        if args == expected:
            family, source = name, canonical(relative, cwd)
    if name == 'rustix' and args == ['--crate-type=rlib', '--emit=metadata', '--target', TARGET,
                                    '-o', out + '/rustix_test_can_compile', '-']:
        family = 'rustix'
    if name in AUTOCFG_CALLERS and len(args) == 9 and args[:1] == ['--crate-name']:
        match = re.fullmatch(r'autocfg_[0-9a-f]{16}_(0|[1-9][0-9]{0,6})', args[1])
        if match and int(match.group(1)) <= 1048575 and args[2:] == [
                '--crate-type=lib', '--out-dir', out, '--emit=llvm-ir', '--target', TARGET, '-']:
            family = 'autocfg'
    if family is None:
        return None
    need(cwd == canonical(cwd) == environment.get('CARGO_MANIFEST_DIR'), 'wrong_probe_manifest_directory')
    need(environment.get('PROFILE') == 'release' and environment.get('HOST') == TARGET and
         environment.get('TARGET') == TARGET, 'wrong_probe_environment')
    pattern = re.escape(target_dir) + r'/(?:' + TARGET + r'/)?release/build/' + re.escape(name) + r'-[0-9a-f]{16}/out'
    need(out == canonical(out) and re.fullmatch(pattern, out), 'wrong_probe_output_directory')
    return dict(family=family, package_name=name, package_version=version, manifest_dir=cwd,
                source=source, target=TARGET, out_dir=out, stdin='unobserved' if source is None else None)


def capture_probe_parent(target_dir, out_dir, previous=None):
    """Observe only the direct build-script executable; never inspect stdin/cmdline."""
    from desktop_glib_build_contract import parent_descriptor, stable_file
    with parent_descriptor(Path(out_dir) / 'unused') as (fd, _):
        need(os.fstat(fd).st_uid == os.getuid(), 'wrong_probe_directory_owner')
    pid = os.getppid()
    path = os.readlink('/proc/' + str(pid) + '/exe')
    package = Path(out_dir).parent.name.rsplit('-', 1)[0]
    pattern = re.escape(target_dir + '/release/build/' + package) + r'-[0-9a-f]{16}/build-script-build'
    need(path == canonical(path) and re.fullmatch(pattern, path), 'wrong_probe_parent_path')
    identity = stable_file(path, target_dir, MAX_BINARY, allow_hardlinks=True)
    need(pid == os.getppid() and path == os.readlink('/proc/' + str(pid) + '/exe'), 'probe_parent_changed')
    if previous is None:
        return dict(pid=pid, path=path, before=identity, after=None)
    need(previous['pid'] == pid and previous['path'] == path and previous['before'] == identity,
         'probe_parent_changed')
    return dict(previous, after=identity)


def package_identity(context, name, version):
    """Bind observed registry identities to the lock from the trusted checkout."""
    pin = PINS[(name, version)]
    packages = [p for p in context['packages'] if (p.get('name'), p.get('version')) == (name, version)]
    locked = [p for p in context['lock_packages'] if (p.get('name'), p.get('version')) == (name, version)]
    need(len(packages) == len(locked) == 1 and packages[0].get('source') == REGISTRY and
         locked[0].get('source') == REGISTRY and locked[0].get('checksum') == pin[0], 'untrusted_probe_package')
    package = packages[0]
    need(package.get('id') == REGISTRY + '#' + name + '@' + version, 'wrong_probe_package_id')
    return package


def verify_probe_trace(record, expected, units, owners):
    """Pure replay: compare authenticated observations without producer-path access."""
    context = expected.get('probe_context', {})
    need(set(context) == {'packages', 'lock_packages', 'artifacts', 'executed'} and
         all(isinstance(v, list) and len(v) <= 8192 for v in context.values()), 'missing_probe_context')
    unit = classify_probe(record['argv'][1:], record['cwd'], expected['target_dir'], record['environment'])
    need(unit is not None and unit == record['unit'] and record['role'] == 'probe' and
         type(record['returncode']) is int and record['returncode'] in (0, 1) and
         record['error'] is None and record['outputs'] == record['externs'] == [], 'invalid_diagnostic_probe')
    name, version = unit['package_name'], unit['package_version']
    package = package_identity(context, name, version)
    manifest = unit['manifest_dir'] + '/Cargo.toml'
    need(package.get('manifest_path') == manifest, 'wrong_probe_package_manifest')
    targets = [t for t in package['targets'] if t.get('kind') == ['custom-build']]
    need(len(targets) == 1 and targets[0].get('crate_types') == ['bin'] and
         targets[0].get('name') == 'build-script-build' and
         targets[0].get('src_path') == unit['manifest_dir'] + '/build.rs', 'wrong_probe_build_source')
    parent = record.get('parent')
    need(isinstance(parent, dict) and set(parent) == {'pid', 'path', 'before', 'after'} and
         type(parent['pid']) is int and 1 <= parent['pid'] < 2**31, 'missing_probe_parent')
    for field in ('before', 'after'):
        hash_record(parent[field])
    need(parent['before'] == parent['after'], 'probe_parent_mutated')
    path = parent['path']
    pattern = re.escape(expected['target_dir'] + '/release/build/' + name) + r'-[0-9a-f]{16}/build-script-build'
    need(path == canonical(path) and re.fullmatch(pattern, path), 'wrong_probe_parent_path')
    artifacts = [a for a in context['artifacts'] if a.get('filenames') == [path]]
    need(len(artifacts) == 1, 'missing_or_duplicate_probe_parent_artifact')
    artifact = artifacts[0]
    need(artifact.get('reason') == 'compiler-artifact' and artifact.get('package_id') == package['id'] and
         artifact.get('manifest_path') == manifest and artifact.get('fresh') is False and
         artifact.get('profile', {}).get('test') is False and artifact.get('target') == targets[0],
         'wrong_probe_parent_artifact')
    executions = [e for e in context['executed'] if e.get('package_id') == package['id'] and
                  e.get('out_dir') == unit['out_dir']]
    need(len(executions) == 1 and executions[0].get('reason') == 'build-script-executed', 'missing_probe_execution')
    candidates = []
    for owner, output in owners.values():
        rec = units[owner]
        if output['kind'] == 'link' and rec['role'] == 'host' and rec['unit']['crate_name'] == 'build_script_build' and (
                Path(output['path']).parent == Path(path).parent and
                {k: output[k] for k in ('sha256', 'size')} == parent['before']):
            candidates.append(rec)
    need(len(candidates) == 1, 'missing_or_duplicate_probe_parent_owner')
    compiled = candidates[0]
    need(type(compiled['finished_ns']) is int and type(record['started_ns']) is int and
         0 <= compiled['finished_ns'] <= record['started_ns'] < 2**63, 'probe_parent_not_completed')
    need(type(compiled['returncode']) is int and compiled['returncode'] == 0 and compiled['error'] is None and
         compiled['unit']['crate_types'] == ['bin'] and 'link' in compiled['unit']['emits'] and
         compiled['source']['path'] == targets[0]['src_path'] and
         compiled['source']['before'] == compiled['source']['after'] and
         compiled['source']['before']['sha256'] == PINS[(name, version)][1], 'untrusted_probe_parent_source')
    need(all(compiled['environment'].get(k) == v for k, v in {
        'CARGO_PKG_NAME': name, 'CARGO_PKG_VERSION': version, 'CARGO_MANIFEST_DIR': unit['manifest_dir']}.items()),
        'wrong_probe_parent_package')
    source = record['source']
    if unit['source'] is None:
        need(source is None, 'stdin_probe_has_invented_hash')
    else:
        relative = str(Path(unit['source']).relative_to(unit['manifest_dir']))
        size, digest = FILE_PROBES[(name, version, relative)]
        need(isinstance(source, dict) and set(source) == {'path', 'before', 'after'} and
             source['path'] == unit['source'], 'wrong_probe_source')
        for field in ('before', 'after'):
            hash_record(source[field])
            need(source[field] == {'sha256': digest, 'size': size}, 'untrusted_probe_source')
    if unit['family'] == 'autocfg':
        auto = package_identity(context, 'autocfg', '1.5.1')
        inputs = [e for e in compiled['externs'] if e['name'] == 'autocfg']
        need(len(inputs) == 1 and inputs[0]['path'] in owners, 'missing_autocfg_input_owner')
        ident, output = owners[inputs[0]['path']]
        provider = units[ident]
        need(provider['role'] == 'host' and type(provider['returncode']) is int and
             provider['returncode'] == 0 and provider['error'] is None and
             set(provider['unit']['crate_types']) <= {'lib', 'rlib'} and 'link' in provider['unit']['emits'] and
             provider['unit']['crate_name'] == 'autocfg' and
             provider['source']['path'] == str(Path(auto['manifest_path']).parent / 'src/lib.rs') and
             provider['source']['before'] == provider['source']['after'] and
             provider['source']['before']['sha256'] == PINS[('autocfg', '1.5.1')][1] and
             inputs[0]['before'] == inputs[0]['after'] == {k: output[k] for k in ('sha256', 'size')},
             'wrong_autocfg_input_owner')
        need(all(provider['environment'].get(k) == v for k, v in {
            'CARGO_PKG_NAME': 'autocfg', 'CARGO_PKG_VERSION': '1.5.1',
            'CARGO_MANIFEST_DIR': str(Path(auto['manifest_path']).parent)}.items()), 'wrong_autocfg_package')
