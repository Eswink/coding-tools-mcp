"""Root-only engineering build. Requires a separately reviewed sealed packet.

No command runs on import. This adapter conveys no native family or release
authorization. The existing product version and PostgreSQL features remain.
"""
from pathlib import Path
import hashlib
import json
import math
import os
import signal
import stat
import subprocess
import sys
import time
import types

D = Path('/workspace/work/rc070/rsa-gateway-build-owned05')
P = D / 'BUILD-STARTUP-PACKET05.private.json'
RETAINED = []


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    def floating(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('nonfinite_json_number')
        return result
    return json.loads(Path(path).read_bytes().decode('utf-8'),
                      object_pairs_hook=pairs, parse_float=floating,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


def check_row(row):
    path = Path(row['path'])
    before = path.lstat()
    for field, key in [('st_dev', 'dev'), ('st_ino', 'inode'),
                       ('st_nlink', 'nlink'), ('st_mtime_ns', 'mtimeNs'),
                       ('st_ctime_ns', 'ctimeNs')]:
        if getattr(before, field) != row[key]:
            raise RuntimeError('physical_input_changed:' + str(path))
    if stat.S_IMODE(before.st_mode) != int(row['mode'], 8):
        raise RuntimeError('input_mode_changed:' + str(path))
    if row['kind'] == 'symlink':
        if not stat.S_ISLNK(before.st_mode) or os.readlink(path) != row['linkTarget']:
            raise RuntimeError('literal_alias_changed:' + str(path))
        if str(path.resolve(strict=True)) != row['resolved']:
            raise RuntimeError('alias_resolution_changed:' + str(path))
    elif row['kind'] == 'regular':
        if not stat.S_ISREG(before.st_mode) or before.st_size != row['bytes']:
            raise RuntimeError('regular_input_changed:' + str(path))
        if digest(path) != row['sha256']:
            raise RuntimeError('input_bytes_changed:' + str(path))
    elif row['kind'] == 'directory':
        if not stat.S_ISDIR(before.st_mode):
            raise RuntimeError('directory_role_changed:' + str(path))
    else:
        raise ValueError('unsupported_input_kind')
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if tuple(getattr(before, k) for k in fields) != tuple(getattr(after, k) for k in fields):
        raise RuntimeError('input_changed_during_read:' + str(path))


def verify_build_lease(packet):
    """Verify every sealed input and each declared complete namespace.

    All independent rows are attempted; original cancellation objects remain
    in the raised group. This proves listed inputs, not observed syscalls.
    """
    failures = []
    for name, expected in packet['executorSourceLeases'].items():
        try:
            if digest(name) != expected['sha256'] or Path(name).stat().st_size != expected['bytes']:
                raise RuntimeError('executor_source_changed')
        except BaseException as error:
            failures.append(error)
    lease_path = Path(packet['inputLeaseFile'])
    if digest(lease_path) != packet['inputLeaseSHA256']:
        raise RuntimeError('immutable_input_lease_changed')
    lease = read_json(lease_path)
    for row in lease['rows'] + lease.get('directoryRoles', []):
        try:
            check_row(row)
        except BaseException as error:
            failures.append(error)
    for namespace in lease['namespaces']:
        try:
            root = Path(namespace['root'])
            actual = set()
            for parent, dirs, files in os.walk(root, followlinks=False):
                if Path(parent) == root:
                    excluded = ['.git'] if namespace.get('excludeRootGitOnly') else []
                    dirs[:] = [x for x in dirs if x not in excluded]
                for name in list(dirs):
                    p = Path(parent) / name
                    if p.is_symlink():
                        actual.add(p.relative_to(root).as_posix())
                        dirs.remove(name)
                for name in files:
                    if Path(parent) == root and name == '.git' and namespace.get('excludeRootGitOnly'):
                        continue
                    actual.add((Path(parent) / name).relative_to(root).as_posix())
            if actual != set(namespace['relativePaths']):
                raise RuntimeError('declared_input_namespace_changed:' + str(root))
        except BaseException as error:
            failures.append(error)
    for path in lease['configAbsences']:
        try:
            if os.path.lexists(path):
                raise RuntimeError('config_absence_changed:' + path)
        except BaseException as error:
            failures.append(error)
    for ref in packet['nativeRefs']:
        try:
            value = subprocess.check_output(['/usr/bin/git', 'rev-parse', ref['ref']],
                       cwd=ref['cwd'], timeout=2).decode('ascii').strip()
            if value != ref['expected']:
                raise RuntimeError('native_source_ref_changed')
        except BaseException as error:
            failures.append(error)
    if failures:
        RETAINED.extend(failures)
        if len(failures) == 1:
            raise failures[0]
        raise BaseExceptionGroup('independent_input_fence_failures', failures)
    return {'rows': len(lease['rows']), 'namespaces': len(lease['namespaces']),
            'listedInputsUnchanged': True, 'observedSyscallClosure': False}


def verify_native_build(packet, capture):
    """Consume complete original Cargo JSON and bind all four real binaries."""
    raw = Path(packet['outputDirectory']) / 'stdout.raw'
    stderr = Path(packet['outputDirectory']) / 'stderr.raw'
    for name, path in [('stdout', raw), ('stderr', stderr)]:
        row = capture['streams'][name]
        if path.stat().st_size != row['bytes_written'] or digest(path) != row['sha256'] or row['eof'] is not True:
            raise RuntimeError('original_stream_identity_changed')
    events = []
    def unique_pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('duplicate_original_cargo_json_key')
            result[key] = value
        return result
    for line in raw.read_bytes().decode('utf-8').splitlines():
        if not line:
            raise ValueError('empty_cargo_json_line')
        value = json.loads(line, object_pairs_hook=unique_pairs,
                           parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
        if not isinstance(value, dict) or value.get('reason') not in {
                'compiler-artifact', 'compiler-message', 'build-script-executed', 'build-finished'}:
            raise ValueError('unexpected_original_cargo_event')
        events.append(value)
    final = [x for x in events if x['reason'] == 'build-finished']
    if len(final) != 1 or final[0].get('success') is not True or events[-1] is not final[0]:
        raise RuntimeError('whole_package_build_not_finished_successfully')
    artifacts = [x for x in events if x['reason'] == 'compiler-artifact']
    bins = {}
    for name in packet['expectedBins']:
        matches = [x for x in artifacts if x.get('manifest_path') == packet['manifest']
                   and x.get('target', {}).get('kind') == ['bin'] and x['target']['name'] == name]
        if len(matches) != 1:
            raise RuntimeError('exact_original_bin_artifact_missing_or_duplicated:' + name)
        path = Path(packet['targetDirectory']) / packet['triple'] / 'release' / name
        if matches[0].get('executable') != str(path):
            raise RuntimeError('bin_not_from_exact_new_target_directory')
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or not st.st_mode & 0o111:
            raise RuntimeError('bin_not_regular_actual_executable')
        with path.open('rb') as stream:
            header = stream.read(20)
        if len(header) != 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 62:
            raise RuntimeError('bin_not_actual_x86_64_ELF')
        bins[name] = {'bytes': st.st_size, 'sha256': digest(path), 'mode': f'{stat.S_IMODE(st.st_mode):04o}'}
    patched = {}
    for name in ['sqlx', 'sqlx-macros-core']:
        manifest = str(Path(packet['cwd']) / 'vendor' / name / 'Cargo.toml')
        matches = [x for x in artifacts if x.get('manifest_path') == manifest]
        if not matches:
            raise RuntimeError('owned_patched_package_not_really_compiled:' + name)
        features = set().union(*(set(x.get('features', [])) for x in matches))
        if not {'postgres', 'migrate', 'macros', 'uuid'} <= features or {'mysql', 'all-databases'} & features:
            raise RuntimeError('original_postgres_macro_migrate_features_not_preserved')
        patched[name] = sorted(features)
    return {'completeOriginalJSONEvents': len(events), 'original4Bins': bins,
            'actualPatchedCompileFeatures': patched,
            'wholeEngineeringPackageBuild': True, 'finalRCQualified': False}


def main():
    started = time.monotonic()
    def deadline_signal(signum, frame):
        raise TimeoutError('outer_fixed_deadline_signal_requires_owned_cleanup')
    signal.signal(signal.SIGTERM, deadline_signal)
    packet = read_json(P)
    if packet['seconds'] != 480 or packet['maxBytes'] != 2097152:
        raise ValueError('original_fixed_compiler_budget_required')
    marker = D / 'ROOT-ONCE-BUILD-START05.private.json'
    if marker.exists() or Path(packet['targetDirectory']).exists() or os.listdir(packet['outputDirectory']):
        raise RuntimeError('distinct_once_slot_target_and_logs_not_fresh')
    verify_build_lease(packet)
    with marker.open('x') as stream:
        json.dump({'startMonotonic': started, 'packetSHA256': digest(P),
                   'scope': 'ENGINEERING_BUILD_ONLY_NO_NATIVE_FAMILY_OR_RELEASE'}, stream)
    marker.chmod(0o600)
    capture = proof = None
    failures = []
    try:
        data = Path(packet['collectorSource']).read_bytes()
        if hashlib.sha256(data).hexdigest() != packet['executorSourceLeases'][packet['collectorSource']]['sha256']:
            raise RuntimeError('collector_source_changed_before_import')
        module = types.ModuleType('root_sealed_compiler_collector04')
        module.__file__ = packet['collectorSource']
        exec(compile(data, packet['collectorSource'], 'exec'), module.__dict__)
        remaining = 480 - (time.monotonic() - started)
        capture = module.collect_build_streams(packet['argv'], packet['cwd'], packet['environment'],
                 packet['cargoSHA256'], packet['outputDirectory'],
                 lambda: verify_build_lease(packet), lambda: verify_build_lease(packet),
                 seconds=remaining, byte_limit=packet['maxBytes'])
        proof = verify_native_build(packet, capture)
    except BaseException as error:
        failures.append(error)
    finally:
        try:
            verify_build_lease(packet)
        except BaseException as error:
            failures.append(error)
        try:
            if time.monotonic() - started >= 480:
                raise TimeoutError('whole_build_and_artifact_checks_deadline_exhausted')
        except BaseException as error:
            failures.append(error)
    RETAINED.extend(failures)
    result = {'scope': 'ACTUAL_WHOLE_GATEWAY_ENGINEERING_BUILD_ONLY',
              'proof': proof, 'elapsedBeforeWriter': time.monotonic() - started,
              'actualChildExit': capture.get('observed_returncode') if capture else None,
              'failureTypes': [type(x).__name__ for x in failures],
              'sourceAndListedRuntimeInputsAfter': not failures,
              'nativeFamilyClosure': False, 'install': 'NOTRUN', 'RCQualified': False,
              'independentTerminalReview': 'PENDING', 'rawPrivateCustody': True}
    p = D / 'ACTUAL-ROOT-BUILD-RECEIPT05.private.json'
    with p.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    p.chmod(0o600)
    elapsed = time.monotonic() - started
    print(json.dumps({'scope': result['scope'], 'actualPostWriterElapsedSeconds': elapsed,
                      'failures': result['failureTypes'], 'bins': list(proof['original4Bins']) if proof else [],
                      'RCQualified': False}))
    if elapsed >= 480:
        failures.append(TimeoutError('actual_postwriter_build_deadline_exhausted'))
    if failures:
        if len(failures) == 1:
            raise failures[0]
        raise BaseExceptionGroup('original_build_and_independent_final_failures', failures)


if __name__ == '__main__':
    main()
