"""New read-only baseline755 audit AST; never launches owner or writes run files."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys

BASE = Path('/workspace/work/rc070/full755-exact-mode/work/full755-prepare')
OUT = Path('/workspace/work/rc070/full755-preflight-exact-original03')
SEAL_SHA = 'bf2fd07c3a73d43d7cbf3fec88f139a35c87bc649e6fba2fef57ba6f168b817d'
PACKET_SHA = '50438a5b16df7f56edd295e75a3896892f908696e0aa503c9e729b9bedc17f0e'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return json.loads(path.read_bytes())


def file_row(path):
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    raw = path.read_bytes()
    assert len(raw) == info.st_size
    return {'bytes': len(raw), 'sha256': sha(raw)}


def expected_events(record, group):
    rows = []
    if group == 'pretag':
        rows.append({'entry': record['entry'], 'full_loaded_ids': record['full_loaded_ids']})
    rows.append({'entry': record['entry'], 'loaded_ids': record['raw_loaded_ids']})
    assert record['raw_executed_ids'] == record['raw_success_ids']
    for value in record['raw_executed_ids']:
        rows.extend(({'entry': record['entry'], 'start': value},
                     {'entry': record['entry'], 'success': value}))
    rows.append({'result': record})
    return rows


def verify_saved_events(raw, records, group, encode):
    assert type(raw) is bytes and raw.endswith(b'\n') and len(raw) <= 1024**2
    rows = [row for record in records for row in expected_events(record, group)]
    assert raw == b''.join(encode(row) for row in rows)
    return {'bytes': len(raw), 'sha256': sha(raw), 'events': len(rows),
            'starts': sum('start' in row for row in rows),
            'successes': sum('success' in row for row in rows),
            'results': sum('result' in row for row in rows), 'exact_original_encoder': True}


def consumer_hex_print(entry, raw):
    # Exact original owner print(json.dumps(dict(...))) default serialization.
    return (json.dumps(dict(entry=entry, raw_events_hex=raw.hex(),
                            bytes=len(raw), sha256=sha(raw))) + '\n').encode()


def verify_consumer_hex_print(stdout, entry, raw):
    assert stdout.count(consumer_hex_print(entry, raw)) == 1


def pool_rows(root):
    rows = {}
    for path in sorted((root / '.git/objects').rglob('*')):
        if path.is_file():
            info = path.lstat()
            assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            rows[str(path.relative_to(root / '.git/objects'))] = {
                **file_row(path), 'mode': oct(stat.S_IMODE(info.st_mode))}
    return rows


def validate_root_wrapper_exit(actual_exit):
    if type(actual_exit) is not int:
        raise TypeError('root actual wrapper exit must be explicitly supplied integer tool provenance')
    if actual_exit != 0:
        raise ValueError('root actual wrapper process did not exit zero')
    return actual_exit


def audit_full755(audit_dir, root_wrapper_actual_exit):
    validate_root_wrapper_exit(root_wrapper_actual_exit)
    audit_dir = Path(audit_dir)
    assert audit_dir.is_absolute() and audit_dir.resolve() == audit_dir
    assert audit_dir != OUT and OUT not in audit_dir.parents and audit_dir not in OUT.parents
    # Importing exact original modules defines functions; no main/owner/worker is called.
    packet_raw = (OUT / 'EXECUTION-PREFLIGHT-MANIFEST.json').read_bytes()
    assert sha(packet_raw) == PACKET_SHA
    packet = json.loads(packet_raw)
    owner = load('readonly_original_owner', BASE / 'original/owner-original.py')
    assert sha((BASE / 'original/owner-original.py').read_bytes()) == '8fe7478874c3817858dbb2eabed515dbeb78f268393577a66ba0408ee44922ff'
    external = load('readonly_full755_external', BASE / 'full755_external.py')
    original = external.configure_original(packet)
    root = Path(packet['root'])
    owned = OUT / 'owned-owner'
    outer = read(OUT / 'OUTER-RECEIPT.json')
    physical = read(OUT / 'PHYSICAL-FULL755-OUTER-RECEIPT.json')
    aggregate = read(owned / 'aggregate.json')
    assert outer['passed'] is True and outer['actual_owner_exit'] == 0
    assert not outer['errors'] and not outer['signals'] and not outer['deadline_exceeded']
    assert outer['aggregate_error'] is None and outer['original_inventory'] == 755
    assert outer['original_wall_budget_seconds'] == 1200 and outer['public_qualification'] is False and outer['matrix4149'] == 0
    assert aggregate['passed'] is True and aggregate['actual_success'] == 755
    assert aggregate['production_ready'] is False and not aggregate['errors'] and not aggregate['cancelled']
    assert aggregate['outcomes'] == {'pretag': 0, 'consumer': 0}
    assert external.natural_original_family(OUT) is True
    assert physical['delegate_exit_after_natural_gate'] == 0 and not physical['fence_failures']
    assert physical['natural_original_family_admitted'] is True
    assert physical['physical_before_after_equal'] is True and physical['extra_runtime_before_after_equal'] is True
    assert physical['public_RC_CI_install_credit'] is False
    streams, group_rows, ids = {}, {}, {}
    stdout = (OUT / 'OWNER-STDOUT.raw.log').read_bytes()
    for group in owner.EXPECTED:
        receipt = read(owned / (group + '-receipt.json'))
        assert receipt == aggregate['group_receipts'][group]
        assert owner.valid(group, receipt)
        workers = [record['process'] for record in receipt['records']]
        assert len({worker['pid'] for worker in workers}) == (3 if group == 'pretag' else 15)
        assert len({worker['parent'] for worker in workers}) == 1
        assert all(worker['parent'] == worker['pgrp'] != worker['pid'] for worker in workers)
        individual = []
        for record in receipt['records']:
            entry = record['entry']
            prefix = entry if group == 'pretag' else 'consumer-' + entry
            item = read(owned / (prefix + '-receipt.json'))
            assert owner.valid(group, item, entry) and item['records'] == [record]
            raw = (owned / (prefix + '-named-events.jsonl')).read_bytes()
            streams[prefix] = verify_saved_events(raw, [record], group, owner.encode)
            individual.append(raw)
            if group == 'consumer':
                verify_consumer_hex_print(stdout, entry, raw)
        raw = (owned / (group + '-named-events.jsonl')).read_bytes()
        merged = verify_saved_events(raw, receipt['records'], group, owner.encode)
        assert raw == b''.join(individual)
        merged['exact_actual_ordered_concat'] = True
        assert stdout.count(('[' + group + ' named-events] ').encode() + raw + b'\n') == 1
        group_log = owned / (group + '-stdout.log')
        group_rows[group] = {'merged': merged, 'stdout': file_row(group_log),
                             'loaded': len(receipt['loaded_ids']),
                             'executed': len(receipt['executed_ids']),
                             'success': len(receipt['success_ids'])}
        assert group_rows[group]['stdout']['bytes'] <= 2 * 1024**2
        assert not (owned / (group + '-stdout-overflow.json')).exists()
    for field in ['loaded_ids', 'executed_ids', 'success_ids']:
        values = [value for receipt in aggregate['group_receipts'].values() for value in receipt[field]]
        assert len(values) == len(set(values)) == 755
        ids[field] = {'count': len(values), 'sha256': sha('\n'.join(sorted(values)).encode())}
    assert ids == outer['actual_named_inventory']
    assert outer['raw_stdout'] == original.file(OUT / 'OWNER-STDOUT.raw.log')
    assert outer['inner_aggregate'] == original.file(owned / 'aggregate.json')
    assert stdout.endswith(owner.encode(aggregate))
    before = read(OUT / 'source-before.json')
    assert read(OUT / 'source-after.json') == before == original.source()
    assert aggregate['source_before'] == aggregate['source_after'] == read(owned / 'source-before.json') == read(owned / 'source-after.json')
    assert aggregate['source_before']['head'] == before['head']
    assert len(before['source']) == 1849 and before['tree'] == 'b227335c6503c8b9d2575802522758a308684be8'
    runtime = read(OUT / 'runtime-before.json')
    assert runtime == read(OUT / 'runtime-after.json') == {k: original.file(v['path']) for k, v in runtime.items()}
    extra = read(OUT / 'extra-runtime-before.json')
    assert extra == read(OUT / 'extra-runtime-after.json') == {k: external.full_identity(v['path']) for k, v in extra.items()}
    modes = external.load('readonly_actual_modes', BASE / 'original/physical_modes.py')
    current_modes = modes.require_exact_posix_modes(root, {p: v['mode'] for p, v in before['source'].items()})
    assert current_modes == read(OUT / 'physical-source-before.json') == physical['physical_after']
    refs = (OUT / 'public-heads-tags-before.txt').read_bytes()
    assert refs == (OUT / 'public-heads-tags-after.txt').read_bytes() == original.git('for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/remotes', 'refs/tags')
    native_before = read(OUT / 'native-dependencies-before.json')
    assert native_before == read(OUT / 'native-dependencies-after.json')
    proof = audit_dir / 'CURRENT-NATIVE-PROOF.json'
    subprocess.run([packet['python'], '-B', str(BASE / 'original/verify-native-dependencies03.py'),
                    str(root), str(BASE / 'contracts755-recovery-work'), str(proof), 'candidate-b227'],
                   check=True, timeout=35, capture_output=True)
    assert read(proof) == native_before
    pool = read(OUT / 'native-object-pool-before-after.json')
    assert pool['before'] == pool['after'] == pool_rows(root)
    seal_path = BASE / 'FINAL-SOURCE-SEAL03.json'
    assert sha(seal_path.read_bytes()) == SEAL_SHA
    seal = read(seal_path)
    # Exact seal shape is read explicitly below; source rows remain no-rewrite.
    source_rows = seal['source_files']
    for row in source_rows:
        path = Path(row['path'])
        assert file_row(path) == {'bytes': row['bytes'], 'sha256': row['sha256']}
    assert len(source_rows) == 14
    return {'scope': 'Independent exact original baseline engineering755 only',
            'root_actual_wrapper_exit_required': 0, 'root_actual_wrapper_exit': root_wrapper_actual_exit,
            'root_actual_exit_input_boundary': 'Caller supplies actual root tool exit; auditor does not derive this input from OUTER or other receipts',
            'audit_success': True, '755_ids': ids, 'groups': group_rows, 'individual_streams': streams,
            'original_outer': file_row(OUT / 'OUTER-RECEIPT.json'),
            'physical_outer': file_row(OUT / 'PHYSICAL-FULL755-OUTER-RECEIPT.json'),
            'raw_stdout': file_row(OUT / 'OWNER-STDOUT.raw.log'), 'aggregate': file_row(owned / 'aggregate.json'),
            'natural_family': True, 'physical1849_before_after_current_equal': True,
            'source_runtime_refs_native_before_after_current_equal': True,
            'runtime_file_count': len(extra), 'source_seal_count': len(source_rows),
            'native_roots': native_before['required_unique_commit_roots'],
            'native_declarations': native_before['declaration_count'],
            'per_entry_kernel_limit': outer['per_entry_exit_evidence'],
            'outer_seconds': outer['seconds'], 'old755_recovery03': 'FAIL retained; cause unresolved',
            'observation_limit': 'No write/flush/FD hooks in this original baseline; exact saved-byte joins only',
            'RC_CI_install_publisher_credit': 0}


def main():
    assert len(sys.argv) == 3
    actual_exit = json.loads(sys.argv[2])
    validate_root_wrapper_exit(actual_exit)
    directory = Path(sys.argv[1])
    assert not directory.exists()
    directory.mkdir(mode=0o700)
    report = audit_full755(directory, actual_exit)
    with (directory / 'ACTUAL-RAW-JOIN-AUDIT.json').open('x') as stream:
        stream.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'audit_success': report['audit_success'], '755_ids': report['755_ids'],
                      'report_sha256': sha((directory / 'ACTUAL-RAW-JOIN-AUDIT.json').read_bytes())}))


if __name__ == '__main__':
    main()
