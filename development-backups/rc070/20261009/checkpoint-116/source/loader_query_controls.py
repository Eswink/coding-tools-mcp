"""Finite data-only controls; this entry never creates a query/process owner.

The holder fixtures below are explicitly Python mock objects with no PID, FD,
Popen, pipe or native authority. Real ELF observations are byte reads only.
"""
import ast
import importlib.util
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
QUERY = HERE / 'loader_query_context.py'
BUILDER = Path('/workspace/work/rc070/startup-native-birth-spec-next/external/rc_native_startup_owner/build_source_owner.py')
BUILDER_SHA = '877d975b2221e24ecf2d86eddd13499c10b70bc8994b1bc0f6d0cea926e78dab'


def load_query_module():
    spec = importlib.util.spec_from_file_location('rc_loader_query_readonly_controls', QUERY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_denied(label, operation, rows):
    try:
        operation()
    except (RuntimeError, ValueError, TypeError, AssertionError) as error:
        rows.append({'case': label, 'result': 'PASS', 'denied_type': type(error).__name__,
                     'scope': 'ordinary_data_only'})
        return
    raise AssertionError('expected_data_denial:' + label)


def run_parser_controls(module, rows):
    expect_denied('arbitrary_dict_not_registered_admission',
                  lambda: module.parse_loader_list(b'', {}), rows)
    target, loader, library = '/ordinary-fixture/outer', '/ordinary-fixture/ld.so', '/ordinary-fixture/libc.so.6'
    state = {'target': target, 'loader': loader,
             'candidate_aliases': {loader: loader, library: library},
             'candidate_info': {target: {'needed': ['libc.so.6']},
                                loader: {'needed': []}, library: {'needed': []}},
             'allowed_paths': frozenset([target, loader, library])}
    raw = (b'\tlinux-vdso.so.1 (0x1234)\n'
           b'\tlibc.so.6 => /ordinary-fixture/libc.so.6 (0x2345)\n'
           b'\t/ordinary-fixture/ld.so (0x3456)\n')
    result = module._parse_listing_data(raw, state)
    assert result['qualifies_native'] is False
    assert set(result['selected_paths']) == {library, loader}
    assert all('0x' not in str(row) for row in result['roles'])
    rows.append({'case': 'pure_factual_parser_fixture_no_registered_admission', 'result': 'PASS',
                 'scope': 'ordinary_data_only_no_actual_loader_output'})
    for label, altered in [
            ('parser_duplicate_dependency', raw + raw.splitlines(keepends=True)[1]),
            ('parser_not_found', raw.replace(b'/ordinary-fixture/libc.so.6 (0x2345)', b'not found')),
            ('parser_unsealed_path', raw.replace(b'/ordinary-fixture/libc.so.6', b'/unsealed/libc.so.6')),
            ('parser_unknown_line', raw + b'unknown callback output\n'),
            ('parser_missing_needed', raw.replace(raw.splitlines(keepends=True)[1], b'')),
            ('parser_missing_loader', raw.replace(raw.splitlines(keepends=True)[2], b'')),
            ('parser_duplicate_vdso', raw + raw.splitlines(keepends=True)[0]),
            ('parser_non_utf8', raw + b'\xff\n')]:
        expect_denied(label, lambda altered=altered: module._parse_listing_data(altered, state), rows)


def run_elf_policy_controls(module, rows):
    # These are pure policy inputs, not ELF files or sealed actual admissions.
    base = {'kind': 3, 'interpreter': None, 'needed': ['libc.so.6'],
            'rpath': [], 'runpath': [], 'dynamic': []}
    module.validate_elf_policy(base)
    rows.append({'case': 'pure_elf_policy_supported_shape', 'result': 'PASS', 'scope': 'ordinary_data_only'})
    for tag, label in [(0x6ffffefc, 'audit'), (0x6ffffefb, 'depaudit'),
                       (0x7fffffff, 'filter'), (0x7ffffffd, 'auxiliary'), (0x6ffffefa, 'config')]:
        changed = dict(base, dynamic=[(tag, 1)])
        expect_denied('candidate_callback_tag_' + label,
                      lambda changed=changed: module.validate_elf_policy(changed), rows)
    for label, changed in [('candidate_ET_REL_not_runtime', dict(base, kind=1)),
                           ('needed_contains_directory', dict(base, needed=['../libc.so.6'])),
                           ('needed_unsupported_token', dict(base, needed=['$LIB.so'])),
                           ('unknown_dynamic_init_flag', dict(base, dynamic=[(0x6ffffffb, 0x20)]))]:
        expect_denied(label, lambda changed=changed: module.validate_elf_policy(changed), rows)
    for label, paths in [('search_empty_component', ['']), ('search_relative', ['relative']),
                         ('search_unknown_token', ['$LIB']), ('search_cwd_token', ['$ORIGIN/$PLATFORM'])]:
        expect_denied(label, lambda paths=paths: module.expand_search_paths(paths, '/ordinary-fixture'), rows)
    builder = module.load_builder_readonly()
    actual = module.read_elf_policy(builder, module.OUTER)
    assert actual['bytes_sha256'] == module.OUTER_SHA and actual['rpath'] == ['$ORIGIN/../lib']
    rows.append({'case': 'actual_fixed_outer_ELF_policy_readonly', 'result': 'PASS',
                 'scope': 'real_ELF_byte_reads_only_no_actual_query',
                 'sha256': actual['bytes_sha256']})


def run_global_policy_controls(module, rows):
    base = {'env': {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'},
            'inherited_unsafe': [], 'secure': False, 'preload_absent': True,
            'capability_absent': True}
    module.check_global_policy(base)
    rows.append({'case': 'pure_exact_environment_policy', 'result': 'PASS', 'scope': 'ordinary_data_only'})
    for label, changed in [
            ('env_EXTRA_LD_PRELOAD_denied', dict(base, env=dict(base['env'], LD_PRELOAD='ordinary-fixture.so'))),
            ('env_changed_PATH_denied', dict(base, env=dict(base['env'], PATH='/tmp:/usr/bin:/bin'))),
            ('inherited_unsafe_context_denied', dict(base, inherited_unsafe=['LD_DEBUG'])),
            ('secure_exec_denied', dict(base, secure=True)),
            ('secure_exec_unknown_denied', dict(base, secure=None)),
            ('preload_file_present_denied', dict(base, preload_absent=False)),
            ('capability_unknown_denied', dict(base, capability_absent=None))]:
        expect_denied(label, lambda changed=changed: module.check_global_policy(changed), rows)


def run_ownership_controls(builder, rows):
    registry, attempts = [], []
    cancel = KeyboardInterrupt('intentional_mock_close_cancel')
    object_only = types.SimpleNamespace(close=lambda: (attempts.append('close'),
                                                       (_ for _ in ()).throw(cancel)))
    holder = builder.new_holder(registry, 'explicit_python_mock_no_native_resource')
    assert registry[0] is holder and holder['object'] is None
    holder['object'], holder['state'], holder['factory_attempted'] = object_only, 'OWNED', True
    errors = builder.close_resource(holder)
    assert errors == [cancel] and errors[0] is cancel
    assert holder['state'] == 'UNKNOWN' and holder['object'] is object_only and registry[0] is holder
    assert builder.close_resource(holder) == [] and attempts == ['close']
    rows.append({'case': 'mock_close_cancel_once_unknown_strong_retention', 'result': 'PASS',
                 'scope': 'ordinary_python_mock_no_fd_no_process'})
    primary = SystemExit(1)
    other_object_only = types.SimpleNamespace(close=lambda: (_ for _ in ()).throw(cancel))
    owned = builder.OwnedFile('/unopened/mock-only', 'rb')
    owned.holder['object'], owned.holder['state'] = other_object_only, 'OWNED'
    owned.holder['factory_attempted'] = True
    try:
        owned.__exit__(type(primary), primary, None)
    except BaseExceptionGroup as group:
        assert len(group.exceptions) == 2
        assert group.exceptions[0] is primary and group.exceptions[1] is cancel
    else:
        raise AssertionError('original_primary_and_close_cancel_not_preserved')
    assert owned.holder['state'] == 'UNKNOWN' and owned.holder['object'] is other_object_only
    assert any(item is owned.holder for item in builder._FILE_HOLDERS)
    rows.append({'case': 'mock_original_systemexit_and_close_keyboardinterrupt_objects',
                 'result': 'PASS', 'scope': 'ordinary_python_mock_no_fd_no_process'})


def run_bootstrap_controls(module, rows):
    original = (module._BUILDER, module._read_bootstrap_bytes)
    executed = []
    had_exec = 'exec' in module.__dict__
    original_exec = module.__dict__.get('exec')
    try:
        module._BUILDER = None
        module._read_bootstrap_bytes = lambda: b'raise AssertionError("unsafe_source_must_not_execute")\n'
        module.exec = lambda *args, **kwargs: executed.append('EXECUTED')
        expect_denied('bootstrap_bad_actual_bytes_SHA_before_any_exec', module.load_builder_readonly, rows)
        assert executed == [] and module._BUILDER is None
    finally:
        module._BUILDER, module._read_bootstrap_bytes = original
        if had_exec:
            module.exec = original_exec
        else:
            del module.exec
    expect_denied('admission_has_no_public_constructor', lambda: module.QueryAdmission(), rows)
    expect_denied('unregistered_exacttype_not_minted_admission',
                  lambda: module.parse_loader_list(b'', object.__new__(module.QueryAdmission)), rows)


def run_failure_fence_controls(module, rows):
    original = (module.verify_after, module.time.monotonic)
    attempts, failures, record = [], [], {}
    primary = SystemExit(1)
    fence_cancel, clock_cancel = KeyboardInterrupt('mock_afterfence_cancel'), SystemExit(9)
    try:
        module.verify_after = lambda unused: (attempts.append('afterfence'),
                                              (_ for _ in ()).throw(fence_cancel))[1]
        module.time.monotonic = lambda: (attempts.append('clock'),
                                         (_ for _ in ()).throw(clock_cancel))[1]
        failures.append(primary)
        module._finish_after_fences(None, record, 0.0, failures)
        assert attempts == ['afterfence', 'clock']
        assert len(failures) == 3
        assert failures[0] is primary and failures[1] is fence_cancel and failures[2] is clock_cancel
        rows.append({'case': 'pure_afterfence_cancel_still_attempts_clock_preserves_all_objects',
                     'result': 'PASS', 'scope': 'mock_observers_no_process_no_admission'})
        module.verify_after = lambda unused: {'ordinary_mock': True, 'qualifies_native': False}
        module.time.monotonic = lambda: 121.0
        failures, record = [], {}
        module._finish_after_fences(None, record, 0.0, failures)
        assert len(failures) == 1 and isinstance(failures[0], RuntimeError)
        assert record['elapsed_seconds'] == 121.0 and 'after_fences' in record
        rows.append({'case': 'pure_total_deadline_late_fences_deny_even_after_mock_success',
                     'result': 'PASS', 'scope': 'mock_observers_no_process_no_admission'})
    finally:
        module.verify_after, module.time.monotonic = original


def run_readonly_controls():
    module = load_query_module()
    builder = module.load_builder_readonly()
    before = builder.snapshot([QUERY, Path(__file__), BUILDER, module.OUTER])
    assert builder.file_identity(BUILDER)['sha256'] == BUILDER_SHA
    tree = ast.parse(builder.read_text_owned(Path(__file__)))
    denied = {'ordinary_job', 'query_loader_context', 'Popen', 'run', 'execv', 'execve',
              'spawn', 'compile_candidate'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else '')
            assert name not in denied, 'data_controls_process_call:' + name
    rows = [{'case': 'control_source_has_no_query_or_process_calls', 'result': 'PASS',
             'scope': 'ordinary_AST_only'}]
    run_parser_controls(module, rows)
    run_elf_policy_controls(module, rows)
    run_global_policy_controls(module, rows)
    run_ownership_controls(builder, rows)
    run_bootstrap_controls(module, rows)
    run_failure_fence_controls(module, rows)
    builder.check_unchanged(before)
    return {'kind': 'loader_query_data_only_controls', 'cases': rows,
            'actual_popen_jobs': 0, 'actual_loader_queries': 0, 'actual_gcc_driver_jobs': 0,
            'actual_root_exec': 0, 'bridge_imports': 0, 'actual_native_birth_controls': 0,
            'qualifies_native': False, 'wholecompiler': 'NOTRUN', 'original_sut': 'NOTRUN',
            'original488_qualification': False,
            'note': 'Mocks deliberately retain UNKNOWN original objects; no actual FD/PID/process.'}


def main():
    print(json.dumps(run_readonly_controls(), sort_keys=True))


if __name__ == '__main__':
    main()
