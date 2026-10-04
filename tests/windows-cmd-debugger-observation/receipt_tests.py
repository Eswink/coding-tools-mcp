"""Pure receipt fixtures and strict version tests; no Windows calls or artifact authentication."""
import json
import pathlib
import runpy
import sys
import types
import unittest

HERE = pathlib.Path(__file__).parent
CONTRACT = runpy.run_path(str(HERE / 'receipt_contract.py'))
(CONTEXT_ERRORS, COUNTERS, ENUMS_V2, ENUMS_V3, FLAGS, NUMERIC, NUMERIC_V2,
 NUMERIC_V3, PREFIX, check_receipt) = (CONTRACT[name] for name in (
    'CONTEXT_ERRORS', 'COUNTERS', 'ENUMS_V2', 'ENUMS_V3', 'FLAGS', 'NUMERIC',
    'NUMERIC_V2', 'NUMERIC_V3', 'PREFIX', 'check_receipt'))
NUMERIC_V4, ENUMS_V4 = (CONTRACT[name] for name in ('NUMERIC_V4', 'ENUMS_V4'))


def fixture(result='matched_open_failed'):
    n = dict.fromkeys(NUMERIC, -1)
    n.update(dict.fromkeys(FLAGS | set(COUNTERS), 0))
    n.update(pid=41, main_tid=51, creation_filetime=12345, attach_attempted=1, attach_succeeded=1,
             attach_break_seen=1, entries_ready_before_resume=1, event_count=5, thread_peak=1, module_peak=2,
             entry_hits=1, read_bytes=4096, write_attempts=6, matched_tid=51, pair_complete=1,
             desired_access=0x80120089, object_attributes=0x40, share_access=7, file_attributes=0x80,
             create_disposition=1, open_options=0x60, ntstatus_u32=0xc0000022, exit_event_seen=1,
             exit_event_continued=1, process_signaled=1, terminal_exit_u32=1, elapsed_ms=10)
    i = dict(protocol='own-child-open-v1', result=result, error='none', error_api='none', cleanup='exit_confirmed', open_api='NtCreateFile')
    if result == 'matched_open_succeeded':
        n.update(ntstatus_u32=0, object_identity_matched=1)
    if result == 'observed_pending':
        n.update(ntstatus_u32=0x103, pair_complete=0, abort_terminate_attempted=1, abort_terminate_error=0, active_patches_at_exit=1)
        i['error'] = 'pending_io'
    return {'Numbers': {PREFIX + k: v for k, v in n.items()}, 'Identities': {PREFIX + k: v for k, v in i.items()}}


def encoded(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()


class ContextReceiptContracts(unittest.TestCase):
    def value(self, error='none', mask=0, api='none', native_error=0):
        value = fixture(); n, i = value['Numbers'], value['Identities']
        n.update({PREFIX + 'context_mismatch_mask': mask, PREFIX + 'native_error': native_error})
        i.update({PREFIX + 'protocol': 'own-child-open-v2', PREFIX + 'error': error, PREFIX + 'error_api': api})
        if error != 'none':
            n[PREFIX + 'pair_complete'] = 0
        return value

    def test_versions_have_separate_exact_schemas(self):
        self.assertEqual((len(NUMERIC), len(NUMERIC_V2), len(ENUMS_V2)), (35, 36, 6))
        self.assertEqual(check_receipt(encoded(self.value())), 'matched_open_failed')
        legacy = fixture(); legacy['Numbers'][PREFIX + 'pair_complete'] = 0
        legacy['Identities'].update({PREFIX + 'error': 'context_failed', PREFIX + 'error_api': 'GetThreadContext'})
        self.assertEqual(check_receipt(encoded(legacy)), 'incomplete')
        variants = [fixture(), self.value()]
        variants[0]['Numbers'][PREFIX + 'context_mismatch_mask'] = 0
        del variants[1]['Numbers'][PREFIX + 'context_mismatch_mask']
        for error in CONTEXT_ERRORS:
            value = fixture(); value['Identities'][PREFIX + 'error'] = error; variants.append(value)
        for value in variants:
            with self.assertRaises(ValueError):
                check_receipt(encoded(value))

    def test_v2_all_fields_are_required_and_strictly_typed(self):
        for section, keys in (('Numbers', NUMERIC_V2), ('Identities', ENUMS_V2)):
            for key in keys:
                for bad in (None, True, False, [], {}, 1.0, 'unknown', -(2**63), 2**64):
                    value = self.value(); value[section][PREFIX + key] = bad
                    with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                        check_receipt(encoded(value))
                value = self.value(); del value[section][PREFIX + key]
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
            value = self.value(); value[section][PREFIX + 'unknown'] = 0
            with self.assertRaises(ValueError):
                check_receipt(encoded(value))
        good = encoded(self.value())
        token = b'"cmd_debug_context_mismatch_mask":0'
        for raw in (good.replace(token, token + b',' + token), good.replace(token, token[:-1] + b'NaN')):
            with self.assertRaises(ValueError):
                check_receipt(raw)

    def test_v2_reason_mask_and_native_error_matrix(self):
        for reason in sorted(CONTEXT_ERRORS | {'context_failed', 'native_failed'}):
            for mask in (-2, -1, 0, 1, 8, 0x100001, 0x1fffff, 0x200000):
                for api in ('none', 'GetThreadContext', 'SetThreadContext'):
                    for error in (0, 5, 0xffffffff):
                        for paired in (0, 1):
                            valid = ((reason == 'context_get_failed' and mask == -1 and api == 'GetThreadContext') or
                                     (reason == 'context_roundtrip_unavailable' and mask == -1 and api == 'none' and error == 0) or
                                     (reason == 'context_roundtrip_mismatch' and 0 < mask <= 0x1fffff and api == 'none' and error == 0) or
                                     (reason not in CONTEXT_ERRORS and mask in (-1, 0)))
                            valid = valid and (reason not in CONTEXT_ERRORS or paired == 0)
                            valid = valid and (reason != 'context_failed' or api != 'SetThreadContext' or (mask == -1 and paired == 0))
                            value = self.value(reason, mask, api, error)
                            value['Numbers'][PREFIX + 'pair_complete'] = paired
                            with self.subTest(reason=reason, mask=mask, api=api, native_error=error, paired=paired):
                                if valid:
                                    self.assertEqual(check_receipt(encoded(value)), 'matched_open_failed' if paired else 'incomplete')
                                else:
                                    with self.assertRaises(ValueError):
                                        check_receipt(encoded(value))
        for mask in (-1, 1, 0x1fffff):
            with self.subTest(success_mask=mask), self.assertRaises(ValueError):
                check_receipt(encoded(self.value(mask=mask)))


class EflagsReceiptContracts(unittest.TestCase):
    def value(self, error='none', fields=0, flags=0, api='none', native_error=0):
        value = fixture()
        value['Numbers'].update({PREFIX + 'context_mismatch_mask': fields,
                                 PREFIX + 'eflags_difference_mask': flags,
                                 PREFIX + 'native_error': native_error})
        value['Identities'].update({PREFIX + 'protocol': 'own-child-open-v3',
                                    PREFIX + 'error': error, PREFIX + 'error_api': api})
        if error != 'none':
            value['Numbers'][PREFIX + 'pair_complete'] = 0
        return value

    def test_v3_exact_separate_version_schemas(self):
        self.assertEqual((len(NUMERIC_V3), len(ENUMS_V3)), (37, 6))
        self.assertEqual(NUMERIC_V3, NUMERIC_V2 + ['eflags_difference_mask'])
        self.assertEqual(ENUMS_V3['error'], ENUMS_V2['error'])
        self.assertEqual(check_receipt(encoded(self.value())), 'matched_open_failed')
        for version in (1, 2):
            value = fixture() if version == 1 else ContextReceiptContracts().value()
            value['Numbers'][PREFIX + 'eflags_difference_mask'] = 0
            with self.subTest(extra_in_version=version), self.assertRaises(ValueError):
                check_receipt(encoded(value))
            del value['Numbers'][PREFIX + 'eflags_difference_mask']
            value['Identities'][PREFIX + 'protocol'] = 'own-child-open-v3'
            with self.subTest(missing_from_version=version), self.assertRaises(ValueError):
                check_receipt(encoded(value))
            value = self.value()
            value['Identities'][PREFIX + 'protocol'] = 'own-child-open-v' + str(version)
            with self.subTest(v3_fields_as_version=version), self.assertRaises(ValueError):
                check_receipt(encoded(value))

    def test_v3_required_fields_types_and_extra_fields(self):
        for section, keys in (('Numbers', NUMERIC_V3), ('Identities', ENUMS_V3)):
            for key in keys:
                for bad in (None, True, False, [], {}, 1.0, 'unknown', -(2**63), 2**64):
                    value = self.value()
                    value[section][PREFIX + key] = bad
                    with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                        check_receipt(encoded(value))
                value = self.value()
                del value[section][PREFIX + key]
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for section in ('Numbers', 'Identities', None):
            for key in ('unknown', 'eflags_requested', 'eflags_actual', 'direction', 'context'):
                value = self.value()
                destination = value if section is None else value[section]
                destination[PREFIX + key] = 0
                with self.subTest(section=section, extra=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))

    def test_v3_all_32_bits_zero_and_combinations(self):
        self.assertEqual(check_receipt(encoded(self.value())), 'matched_open_failed')
        flags_masks = [1 << bit for bit in range(32)] + [0x101, 0x100100, 0x80000100, 0xffffffff]
        for flags in flags_masks:
            for fields in (8, 9, 0x100008, 0x1fffff):
                value = self.value('context_roundtrip_mismatch', fields, flags)
                with self.subTest(fields=fields, flags=flags):
                    self.assertEqual(check_receipt(encoded(value)), 'incomplete')
        for fields in [1 << bit for bit in range(21) if bit != 3] + [3, 0x100001, 0x1ffff7]:
            value = self.value('context_roundtrip_mismatch', fields, 0)
            with self.subTest(non_eflags_fields=fields):
                self.assertEqual(check_receipt(encoded(value)), 'incomplete')

    def test_v3_negative_high_bit_and_overflow_masks(self):
        for flags in (-2, -0x80000000, -(2**63), 0x100000000, 2**63, 2**64):
            value = self.value('context_roundtrip_mismatch', 8, flags)
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                check_receipt(encoded(value))
        for fields in (-2, -(2**63), 0x200000, 0xffffffff, 2**63):
            value = self.value('context_roundtrip_mismatch', fields, 0x80000000)
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                check_receipt(encoded(value))

    def test_v3_reason_api_pair_and_diagnostic_matrix(self):
        for reason in sorted(CONTEXT_ERRORS | {'context_failed', 'native_failed', 'none'}):
            for fields in (-1, 0, 1, 8, 9, 0x100001, 0x1fffff):
                for flags in (-1, 0, 1, 0x100, 0x10000, 0x80000000, 0xffffffff):
                    for api in ('none', 'GetThreadContext', 'SetThreadContext'):
                        for native_error in (0, 5, 0xffffffff):
                            for paired in (0, 1):
                                valid = ((reason == 'context_get_failed' and fields == -1 and api == 'GetThreadContext') or
                                         (reason == 'context_roundtrip_unavailable' and fields == -1 and api == 'none' and native_error == 0) or
                                         (reason == 'context_roundtrip_mismatch' and fields > 0 and api == 'none' and native_error == 0) or
                                         (reason not in CONTEXT_ERRORS and fields in (-1, 0)))
                                valid = valid and (reason not in CONTEXT_ERRORS or paired == 0)
                                valid = valid and (reason != 'context_failed' or api != 'SetThreadContext' or (fields == -1 and paired == 0))
                                valid = valid and (reason != 'none' or (fields == 0 and paired == 1 and api == 'none' and native_error == 0))
                                valid = valid and ((fields == -1 and flags == -1) or
                                                   (fields >= 0 and flags >= 0 and bool(fields & 8) == bool(flags)))
                                value = self.value(reason, fields, flags, api, native_error)
                                value['Numbers'][PREFIX + 'pair_complete'] = paired
                                with self.subTest(reason=reason, fields=fields, flags=flags, api=api,
                                                  native_error=native_error, paired=paired):
                                    if valid:
                                        expected = 'matched_open_failed' if paired else 'incomplete'
                                        self.assertEqual(check_receipt(encoded(value)), expected)
                                    else:
                                        with self.assertRaises(ValueError):
                                            check_receipt(encoded(value))

    def test_v3_duplicate_and_strict_json(self):
        value = self.value()
        good = encoded(value)
        for entries in value.values():
            for key, item in entries.items():
                token = json.dumps(key).encode() + b':' + encoded(item)
                with self.subTest(duplicate=key), self.assertRaises(ValueError):
                    check_receipt(good.replace(token, token + b',' + token, 1))
        token = b'"cmd_debug_eflags_difference_mask":0'
        for bad in (b'NaN', b'Infinity', b'-Infinity', b'0.0', b'true', b'false', b'null', b'"0"', b'9' * 21):
            with self.subTest(raw=bad), self.assertRaises(ValueError):
                check_receipt(good.replace(token, token[:-1] + bad))
        for bad in (b'', b'\xef\xbb\xbf' + good, good + b'\xff', good + b'{}', b' ' * 16385):
            with self.subTest(raw=bad[:20]), self.assertRaises(ValueError):
                check_receipt(bad)

    def test_exact_sibling_loading_ignores_module_cache(self):
        names = ('receipt_contract', 'receipt_tests')
        original = {name: sys.modules.get(name) for name in names}
        path_before = list(sys.path)
        try:
            for name in names:
                sys.modules[name] = types.ModuleType(name)
            loaded = runpy.run_path(str(HERE / 'audit.py'), run_name='sibling_path_probe')
            for name, filename in (('check_receipt', 'receipt_contract.py'),
                                   ('fixture', 'receipt_tests.py'), ('encoded', 'receipt_tests.py')):
                actual = pathlib.Path(loaded[name].__globals__['__file__']).resolve()
                self.assertEqual(actual, (HERE / filename).resolve())
            self.assertEqual(loaded['check_receipt'](encoded(self.value())), 'matched_open_failed')
            for name in ('ContextReceiptContracts', 'EflagsReceiptContracts'):
                self.assertEqual(loaded[name].__module__, 'sibling_path_probe')
            module = types.ModuleType('sibling_path_probe')
            module.__dict__.update(loaded)
            suite = unittest.defaultTestLoader.loadTestsFromModule(module)
            tests = [test for group in suite for test in group]
            ids = [test.id() for test in tests]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(sum('.ContextReceiptContracts.' in item for item in ids), 3)
            self.assertTrue(all(item.startswith('sibling_path_probe.') for item in ids))
            self.assertEqual(sys.path, path_before)
        finally:
            for name in names:
                if original[name] is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original[name]


class ArchitecturalReceiptContracts(unittest.TestCase):
    def value(self, error='none', fields=0, flags=0, api='none', native_error=0):
        value = EflagsReceiptContracts().value(error, fields, flags, api, native_error)
        value['Identities'][PREFIX + 'protocol'] = 'own-child-open-v4'
        return value

    def test_v4_exact_separate_schemas_and_legacy_bit1(self):
        self.assertEqual((len(NUMERIC_V4), len(ENUMS_V4)), (37, 6))
        self.assertEqual(NUMERIC_V4, NUMERIC_V3)
        self.assertIsNot(NUMERIC_V4, NUMERIC_V3)
        self.assertEqual(ENUMS_V4['error'], ENUMS_V3['error'])
        self.assertEqual(ENUMS_V4['protocol'], {'own-child-open-v4'})
        for version in (1, 2, 3, 4, 5):
            for error in ('none', 'context_roundtrip_mismatch'):
                value = self.value(error, 8, 2)
                value['Identities'][PREFIX + 'protocol'] = 'own-child-open-v' + str(version)
                with self.subTest(version=version, error=error):
                    if (version, error) in ((3, 'context_roundtrip_mismatch'), (4, 'none')):
                        expected = 'incomplete' if version == 3 else 'matched_open_failed'
                        self.assertEqual(check_receipt(encoded(value)), expected)
                    else:
                        with self.assertRaises(ValueError):
                            check_receipt(encoded(value))
        for value in (fixture(), ContextReceiptContracts().value()):
            value['Identities'][PREFIX + 'protocol'] = 'own-child-open-v4'
            with self.assertRaises(ValueError):
                check_receipt(encoded(value))

    def test_v4_required_fields_types_and_extra_fields(self):
        for section, keys in (('Numbers', NUMERIC_V4), ('Identities', ENUMS_V4)):
            for key in keys:
                for bad in (None, True, False, [], {}, 1.0, 'unknown', -(2**63), 2**64):
                    value = self.value(fields=8, flags=2)
                    value[section][PREFIX + key] = bad
                    with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                        check_receipt(encoded(value))
                value = self.value()
                del value[section][PREFIX + key]
                with self.subTest(missing=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for section in ('Numbers', 'Identities', None):
            for key in ('unknown', 'eflags_requested', 'eflags_actual', 'direction', 'context'):
                value = self.value()
                destination = value if section is None else value[section]
                destination[PREFIX + key] = 0
                with self.subTest(section=section, extra=key), self.assertRaises(ValueError):
                    check_receipt(encoded(value))

    def test_v4_admissible_pairs_keep_all_success_prerequisites(self):
        bad_numbers = dict(pair_complete=0, matched_tid=-1, attach_break_seen=0, entry_hits=0,
                           ntstatus_u32=-1, desired_access=-1, object_identity_matched=1,
                           exit_event_seen=0, exit_event_continued=0, process_signaled=0,
                           terminal_exit_u32=23, active_patches_at_exit=1, owned_suspends_at_exit=1,
                           abort_terminate_attempted=1, native_error=5, elapsed_ms=-1)
        bad_identities = dict(cleanup='retained_fatal', error_api='GetThreadContext',
                             open_api='none', result='debugger_perturbed')
        for fields, flags in ((0, 0), (8, 2)):
            value = self.value(fields=fields, flags=flags)
            self.assertEqual(check_receipt(encoded(value)), 'matched_open_failed')
            value['Numbers'].update({PREFIX + 'ntstatus_u32': 0, PREFIX + 'object_identity_matched': 1})
            value['Identities'][PREFIX + 'result'] = 'matched_open_succeeded'
            self.assertEqual(check_receipt(encoded(value)), 'matched_open_succeeded')
            for section, changes in (('Numbers', bad_numbers), ('Identities', bad_identities)):
                for key, bad in changes.items():
                    value = self.value(fields=fields, flags=flags)
                    value[section][PREFIX + key] = bad
                    with self.subTest(fields=fields, key=key), self.assertRaises(ValueError):
                        check_receipt(encoded(value))
            with self.assertRaises(ValueError):
                check_receipt(encoded(self.value('context_roundtrip_mismatch', fields, flags)))

    def test_v4_every_other_eflags_bit_and_field_combination(self):
        differences = [(8, mask) for bit in range(32) if bit != 1
                       for mask in (1 << bit, (1 << bit) | 2)]
        differences += [(8, mask) for mask in (0x101, 0x100100, 0x80000102, 0xffffffff)]
        differences += [(mask, 0) for mask in [1 << bit for bit in range(21) if bit != 3]]
        differences += [((1 << bit) | 8, 2) for bit in range(21) if bit != 3]
        differences += [(0x1ffff7, 0), (0x1fffff, 2), (0x1fffff, 0xffffffff)]
        for fields, flags in differences:
            with self.subTest(fields=fields, flags=flags):
                mismatch = self.value('context_roundtrip_mismatch', fields, flags)
                self.assertEqual(check_receipt(encoded(mismatch)), 'incomplete')
                for error in ('none', 'internal_exception'):
                    with self.assertRaises(ValueError):
                        check_receipt(encoded(self.value(error, fields, flags)))

    def test_v4_range_availability_and_raw_consistency(self):
        for fields, flags in ((-2, -1), (-1, -2), (0x200000, 2), (0xffffffff, 2),
                              (8, -0x80000000), (8, 0x100000000), (8, 2**63),
                              (-1, 0), (0, -1), (-1, 2), (8, -1), (8, 0),
                              (0, 2), (1, 2), (9, 0), (0x1ffff7, 0xffffffff)):
            for error in ('none', 'context_roundtrip_mismatch', 'internal_exception'):
                value = self.value(error, fields, flags)
                with self.subTest(fields=fields, flags=flags, error=error), self.assertRaises(ValueError):
                    check_receipt(encoded(value))
        for flags in (1, 0x7fffffff, 0x80000000, 0x80000002, 0xfffffffe, 0xffffffff):
            value = self.value('context_roundtrip_mismatch', 0x1fffff, flags)
            self.assertEqual(check_receipt(encoded(value)), 'incomplete')

    def test_v4_reason_api_pair_and_diagnostic_matrix(self):
        reasons = CONTEXT_ERRORS | {'context_failed', 'native_failed', 'internal_exception', 'none'}
        for reason in sorted(reasons):
            for fields in (-1, 0, 1, 8, 9, 0x100001, 0x1fffff):
                for flags in (-1, 0, 1, 2, 3, 0x100, 0x10000, 0x80000000, 0xffffffff):
                    for api in ('none', 'GetThreadContext', 'SetThreadContext'):
                        for native_error in (0, 5, 0xffffffff):
                            for paired in (0, 1):
                                unavailable = fields == flags == -1
                                completed = fields >= 0 and flags >= 0 and bool(fields & 8) == bool(flags)
                                admissible = (fields, flags) in ((0, 0), (8, 2))
                                if reason == 'context_get_failed':
                                    valid = unavailable and api == 'GetThreadContext' and paired == 0
                                elif reason == 'context_roundtrip_unavailable':
                                    valid = unavailable and api == 'none' and native_error == paired == 0
                                elif reason == 'context_roundtrip_mismatch':
                                    valid = completed and not admissible and api == 'none' and native_error == paired == 0
                                elif reason == 'context_failed' and api == 'SetThreadContext':
                                    valid = unavailable and paired == 0
                                elif reason == 'none':
                                    valid = admissible and paired == 1 and api == 'none' and native_error == 0
                                else:
                                    valid = unavailable or admissible
                                value = self.value(reason, fields, flags, api, native_error)
                                value['Numbers'][PREFIX + 'pair_complete'] = paired
                                with self.subTest(reason=reason, fields=fields, flags=flags, api=api,
                                                  native_error=native_error, paired=paired):
                                    if valid:
                                        expected = 'matched_open_failed' if paired else 'incomplete'
                                        self.assertEqual(check_receipt(encoded(value)), expected)
                                    else:
                                        with self.assertRaises(ValueError):
                                            check_receipt(encoded(value))

    def test_v4_later_errors_cannot_hide_a_first_disallowed_mismatch(self):
        for error in sorted(ENUMS_V4['error'] - CONTEXT_ERRORS - {'none'}):
            for fields, flags in ((-1, -1), (0, 0), (8, 2), (1, 0), (8, 1), (9, 2), (8, 0x102)):
                value = self.value(error, fields, flags)
                with self.subTest(error=error, fields=fields, flags=flags):
                    if (fields, flags) in ((-1, -1), (0, 0), (8, 2)):
                        self.assertEqual(check_receipt(encoded(value)), 'incomplete')
                    else:
                        with self.assertRaises(ValueError):
                            check_receipt(encoded(value))

    def test_v4_duplicate_and_strict_json(self):
        value = self.value(fields=8, flags=2)
        good = encoded(value)
        for entries in value.values():
            for key, item in entries.items():
                token = json.dumps(key).encode() + b':' + encoded(item)
                with self.subTest(duplicate=key), self.assertRaises(ValueError):
                    check_receipt(good.replace(token, token + b',' + token, 1))
        token = b'"cmd_debug_eflags_difference_mask":2'
        for bad in (b'NaN', b'Infinity', b'-Infinity', b'2.0', b'true', b'false', b'null', b'"2"', b'9' * 21):
            with self.subTest(raw=bad), self.assertRaises(ValueError):
                check_receipt(good.replace(token, token[:-1] + bad))
        for bad in (b'', b'\xef\xbb\xbf' + good, good + b'\xff', good + b'{}', b' ' * 16385):
            with self.subTest(raw=bad[:20]), self.assertRaises(ValueError):
                check_receipt(bad)

    def test_v4_exact_sibling_export_and_unique_inventory(self):
        loaded = runpy.run_path(str(HERE / 'audit.py'), run_name='v4_sibling_probe')
        module = types.ModuleType('v4_sibling_probe')
        module.__dict__.update(loaded)
        suite = unittest.defaultTestLoader.loadTestsFromModule(module)
        ids = [test.id() for group in suite for test in group]
        self.assertEqual(len(ids), len(set(ids)))
        exported = loaded['ArchitecturalReceiptContracts']
        self.assertEqual(exported.__module__, 'v4_sibling_probe')
        methods = [method for name, method in vars(exported).items() if name.startswith('test_')]
        self.assertEqual(sum('.ArchitecturalReceiptContracts.' in name for name in ids), len(methods))
        self.assertTrue(all(method.__module__ == 'v4_sibling_probe' for method in methods))
        self.assertTrue(all(name.startswith('v4_sibling_probe.') for name in ids))
