"""Synthetic negative controls; production input/tool pins are not replaced by fixtures."""
import copy
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import appimage_relro_contract as c
import desktop_glib_deb as deb
import desktop_glib_deb_tests as marker_fixture
from exact_build_audit import EvidenceError


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def elf():
    data = bytearray(marker_fixture.elf())
    struct.pack_into('<H', data, 56, 6)
    headers = ((2, 6, 8448, 0x402100, 0x402100, 48, 48, 8),
               (0x6474e552, 4, 8192, 0x402000, 0x402000, 4096, 4096, 1),
               (0x6474e551, 6, 0, 0, 0, 0, 0, 16))
    for i, row in enumerate(headers, 3): struct.pack_into('<IIQQQQQQ', data, 64 + i * 56, *row)
    struct.pack_into('<qQqQqQ', data, 8448, 0x6ffffffb, 0x8000001, 30, 8, 0, 0)
    return bytes(data)


def fixture_config():
    source, target, evidence = '/work/source', '/work/target', '/work/evidence/compiler'
    sha = 'a' * 40
    producer = dict(provider='github-actions', repository='Eswink/coding-tools-mcp', source_sha=sha,
        workflow_sha=sha, run_id='123', run_attempt='2', job='build', runner_os='Linux',
        platform={'id': 'ubuntu', 'version_id': '22.04'}, workflow_ref=
        'Eswink/coding-tools-mcp/.github/workflows/linux-rc-packages.yml@refs/heads/ci/preliminary-packages-test')
    return dict(schema='appimage-relro-config-v1', profile=c.PROFILE, source_sha=sha, source_tree='b' * 40,
        producer=producer, source_root=source, target_root=target, evidence_root=evidence,
        appdir_root=target + '/' + c.base.TARGET + '/release/bundle/appimage/Coding Tools MCP.AppDir',
        compiler_binding_path=evidence + '/appimage-relro/compiler-binding.json', desktop_elf_path=evidence + '/desktop.elf',
        original_patchelf_path=evidence + '/appimage-relro/original-patchelf', original_patchelf_size=c.TOOL_SIZE,
        original_patchelf_sha256=c.TOOL_SHA256, guard_path=source + '/scripts/appimage_relro_guard.py',
        guard_sha256='c' * 64, guard_mode=0o755, python_path='/usr/bin/python3.10', python_sha256='d' * 64,
        python_version='Python 3.10.12', protected=copy.deepcopy(c.PROTECTED), caps=copy.deepcopy(c.CAPS))


def observation(target, data, mode=0o644, inode=10):
    return dict(target=target, **c.byte_record(data), mode=mode, uid=os.geteuid(), device=1,
                inode=inode, nlink=1, mtime_ns=100, ctime_ns=100)


class RelroContractTests(unittest.TestCase):
    def setUp(self):
        self.compiled = elf()
        self.app = self.compiled.replace(deb.UNK, c.APP)
        self.synthetic_tool = b'SYNTHETIC TEST BACKEND; NEVER EXECUTED'
        table = copy.deepcopy(c.PROTECTED)
        for path, item in table.items():
            if path != c.MAIN: item.update(c.byte_record(self.compiled))
        self.patches = [patch.object(c, 'PROTECTED', table), patch.object(c, 'TOOL_SIZE', len(self.synthetic_tool)),
                        patch.object(c, 'TOOL_SHA256', c.digest(self.synthetic_tool))]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        self.config = fixture_config()
        executable = self.config['target_root'] + '/' + c.base.TARGET + '/release/' + c.base.BINARY
        root_event = dict(reason='compiler-artifact', executable=executable)
        events, copies = {'root': root_event}, {'desktop': c.byte_record(self.compiled)}
        self.records = dict(events=events, copies=copies, compiled=self.compiled,
            compiler_copies_bytes=encoded(dict(events=events, copies=copies)),
            build_jsonl_bytes=encoded(root_event) + encoded(dict(reason='build-finished', success=True)))
        self.binding = dict(schema='appimage-relro-compiler-v1', **{k: self.config[k] for k in
            ('profile', 'source_sha', 'source_tree', 'producer', 'target_root')}, prebundle=copies['desktop'],
            compiler_copies_sha256=c.digest(self.records['compiler_copies_bytes']),
            build_jsonl_sha256=c.digest(self.records['build_jsonl_bytes']), event_executable=executable)
        self.evidence = {'config.json': encoded(self.config), 'compiler-binding.json': encoded(self.binding),
            'original-patchelf': self.synthetic_tool, 'parser-tool.json': b'{}\n', 'lock': b''}
        self.records['relro_evidence'] = self.evidence
        self.rows, self.inventory, lines = [], {}, []
        for i, (path, expected) in enumerate(c.PROTECTED.items(), 1):
            data = self.app if path == c.MAIN else self.compiled
            absolute = self.config['appdir_root'] + '/' + path
            record = observation(path, data, expected['mode'], i)
            self.inventory[path] = dict(data=data, **c.byte_record(data), mode=expected['mode'], kind='file', nlink=1)
            self.rows.extend([dict(schema='appimage-relro-operation-v1', event='begin', sequence=i,
                config_sha256=c.digest(self.evidence['config.json']), compiler_binding_sha256=c.digest(self.evidence['compiler-binding.json']),
                pid=42, start_time='123', argv=['--set-rpath', expected['rpath'], absolute], cwd='/work/source',
                operation='set-rpath', target=path, decision='preserve', before=record, original_tool=None, monotonic_ns=i * 10),
                dict(schema='appimage-relro-operation-v1', event='end', sequence=i,
                config_sha256=c.digest(self.evidence['config.json']), result='preserved', exit=0, after=record,
                stdout=None, stderr=None, error=None, monotonic_ns=i * 10 + 1)])
            lines.append('Setting rpath in ELF file ' + absolute + ' to ' + expected['rpath'])
        self.logs = dict(stdout=('\n'.join(lines) + '\n').encode(), stderr=b'')
        self.refresh()
        self.refs = dict(prebundle=c.byte_record(self.compiled), raw_deb=dict(size=500, sha256='e' * 64,
            payload_sha256=c.digest(self.compiled.replace(deb.UNK, deb.DEB))), final_deb=dict(size=501,
            sha256='f' * 64, payload_sha256=c.digest(self.compiled.replace(deb.UNK, deb.DEB))))

    def refresh(self):
        self.journal = b''.join(encoded(row) for row in self.rows)
        self.evidence['operations.jsonl'] = self.journal
        self.evidence['state.json'] = encoded(dict(schema='appimage-relro-state-v1',
            config_sha256=c.digest(self.evidence['config.json']), phase='sealed', next_sequence=len(self.rows) // 2 + 1,
            completed_calls=len(self.rows) // 2, total_hashed_bytes=1024**2, journal_bytes=len(self.journal)))

    def reject(self, fun, *args):
        with self.assertRaises((EvidenceError, OSError, UnicodeError)): fun(*args)

    def final(self, appdir=None, image=None):
        # The tool suite independently exercises actual staging/probe receipt validation.
        with patch('appimage_relro_tool.verify_tool_receipt', return_value={
                'original': {'target': self.config['original_patchelf_path']}}):
            return c.verify_final(self.config, self.records, self.inventory if appdir is None else appdir,
                self.inventory if image is None else image, dict(size=1000, sha256='1' * 64), self.logs, self.refs)

    def add_query(self, exit_code=0):
        begin, end = copy.deepcopy(self.rows[-2:]); sequence = len(self.rows) // 2 + 1
        path = '/usr/lib/x86_64-linux-gnu/libordinary.so.0'
        record = observation(path, self.compiled)
        begin.update(sequence=sequence, argv=['--print-rpath', path], operation='query', target=path,
            decision='delegate', before=record, monotonic_ns=sequence * 10,
            original_tool=observation(self.config['original_patchelf_path'], self.synthetic_tool, 0o500))
        end.update(sequence=sequence, result='delegated', exit=exit_code, after=record,
            stdout=c.byte_record(b''), stderr=c.byte_record(b''), monotonic_ns=sequence * 10 + 1)
        self.rows.extend([begin, end]); self.refresh()

    def test_unique_app_marker_is_exact_and_reuses_old_deb_controls(self):
        with patch.object(deb, 'verify_marker_transform', wraps=deb.verify_marker_transform) as old:
            self.assertEqual(c.verify_app_marker(self.compiled, self.app)['payload_sha256'], c.digest(self.app))
            self.assertEqual(old.call_count, 1)
        writable = marker_fixture.ph(self.compiled, 1, flags=6)
        self.reject(c.verify_app_marker, writable, writable.replace(deb.UNK, c.APP))

    def test_marker_duplicate_wrong_target_and_nonmarker_mutation_reject(self):
        for payload in (self.compiled, self.compiled.replace(deb.UNK, deb.DEB), self.app + c.APP,
                        marker_fixture.replace(self.app, 6000, b'BAD')):
            self.reject(c.verify_app_marker, self.compiled, payload)
        duplicate = marker_fixture.replace(self.compiled, 5000, deb.UNK)
        self.reject(c.verify_app_marker, duplicate, duplicate.replace(deb.UNK, c.APP))

    def test_effective_relro_covers_entire_dynamic_table(self):
        result = c.dynamic_relro(self.compiled)
        self.assertEqual(result['effective_relro'], {'start': 0x402000, 'end': 0x403000})
        self.assertEqual(result['dynamic']['memsz'], 48)
        null_value = marker_fixture.replace(self.compiled, 8488, struct.pack('<Q', 123))
        self.assertEqual(c.dynamic_relro(null_value), result)
        short = marker_fixture.ph(self.compiled, 4, filesz=0x120, memsz=0x120)
        self.reject(c.dynamic_relro, short)

    def test_relro_page_tail_overflow_and_writable_alias_reject(self):
        for data in (marker_fixture.ph(self.compiled, 4, memsz=0x130, filesz=0x130),
                     marker_fixture.ph(self.compiled, 4, vaddr=(1 << 64) - 5), self.compiled[:8500],
                     marker_fixture.ph(self.compiled, 1, offset=8192, vaddr=0x501000, paddr=0x501000, flags=6)):
            self.reject(c.dynamic_relro, data)
        page_alias = marker_fixture.ph(self.compiled, 1, offset=8500, vaddr=0x501134, paddr=0x501134,
                                       filesz=100, memsz=100, align=1, flags=6)
        self.reject(c.dynamic_relro, page_alias)

    def test_rpath_bind_now_nx_and_main_pie_contract_rejects_drift(self):
        for data in (marker_fixture.replace(self.compiled, 8448, struct.pack('<qQ', 29, 0)),
                     marker_fixture.replace(self.compiled, 8448, struct.pack('<qQqQ', 1, 0, 1, 0)),
                     marker_fixture.ph(self.compiled, 5, flags=7)):
            self.reject(c.dynamic_relro, data)
        no_pie = marker_fixture.replace(self.compiled, 8456, struct.pack('<Q', 1))
        self.assertFalse(c.dynamic_relro(no_pie)['pie'])
        self.reject(c.protected_bytes, c.MAIN, no_pie.replace(deb.UNK, c.APP), no_pie)

    def test_exact_nine_destination_inventory_and_alias_identity_required(self):
        result = self.final()
        self.assertEqual(result['protected_count'], 9)
        self.assertEqual(len(result['appdir']), 9)
        self.assertTrue(result['protected_bytes_preserved'])
        self.assertFalse(result['independent_all_query_attempts_verified'])
        self.assertEqual(set(c.PROTECTED), {c.MAIN, 'usr/lib/libglib-2.0.so.0', 'usr/lib/libgmodule-2.0.so.0'} |
            {'usr/lib/lib' + family + '-2.0.so' + suffix for family in ('gio', 'gobject') for suffix in ('', '.0', '.0.7200.4')})

    def test_missing_extra_or_linked_family_member_rejects(self):
        for mutation in ('missing', 'extra', 'symlink', 'hardlink', 'mode'):
            records = copy.deepcopy(self.inventory); key = 'usr/lib/libgio-2.0.so'
            if mutation == 'missing': del records[key]
            elif mutation == 'extra': records['elsewhere/libgio-2.0.so.2'] = records[key]
            elif mutation == 'symlink': records[key]['kind'] = 'symlink'
            elif mutation == 'hardlink': records[key]['nlink'] = 2
            else: records[key]['mode'] = 0o755
            self.reject(self.final, records)
        records = copy.deepcopy(self.inventory)
        records['usr/lib/unrelated-name.so'] = dict(kind='symlink', target='libgio-2.0.so.0')
        self.reject(self.final, records)

    def test_missing_duplicate_pending_or_reordered_operation_rejects(self):
        for rows in (self.rows[:-2], self.rows + self.rows[-2:], self.rows[:-1],
                     self.rows[2:4] + self.rows[:2] + self.rows[4:]):
            self.reject(c.replay_operations, self.config, b''.join(map(encoded, rows)), self.logs)

    def test_sticky_failure_cannot_be_overridden_by_later_success(self):
        self.evidence['failed.json'] = encoded(dict(sequence=1, error='original_nonzero'))
        self.reject(self.final)
        del self.evidence['failed.json']
        state = c.decode(self.evidence['state.json']); state['phase'] = 'failed'
        self.evidence['state.json'] = encoded(state)
        self.reject(self.final)

    def test_compiler_binding_reconciles_actual_retained_evidence(self):
        self.assertEqual(c.read_binding(self.config, self.records), self.binding)
        for key in ('compiled', 'build_jsonl_bytes', 'compiler_copies_bytes'):
            records = copy.deepcopy(self.records); records[key] += b' '
            self.reject(c.read_binding, self.config, records)
        changed = copy.deepcopy(self.records); changed['events']['root']['executable'] += '.other'
        self.reject(c.read_binding, self.config, changed)

    def test_source_profile_run_attempt_and_config_mismatch_rejects(self):
        for key, value in (('profile', 'issue85-desktop-deb-v1'), ('source_sha', 'f' * 40),
                           ('source_tree', 'e' * 40), ('target_root', '/other/target')):
            b = copy.deepcopy(self.binding); b[key] = value
            self.evidence['compiler-binding.json'] = encoded(b)
            self.reject(c.read_binding, self.config, self.records)
        b = copy.deepcopy(self.binding); b['producer']['run_attempt'] = '3'
        self.evidence['compiler-binding.json'] = encoded(b)
        self.reject(c.read_binding, self.config, self.records)
        bad = copy.deepcopy(self.config); bad['caps']['calls'] += 1
        self.reject(c.validate_config, bad)

    def test_verbose_diagnostics_and_operation_receipts_must_agree(self):
        self.add_query()
        self.assertEqual(c.replay_operations(self.config, self.journal, self.logs)['calls'], 10)
        self.logs['stderr'] = ('DEBUG Using patchelf: ' + self.config['guard_path'] + '\n').encode()
        c.replay_operations(self.config, self.journal, self.logs)
        for stdout in (b'', self.logs['stdout'] + self.logs['stdout'].splitlines(keepends=True)[0],
                       self.logs['stdout'].replace(b'$ORIGIN', b'$INVALID', 1)):
            self.reject(c.replay_operations, self.config, self.journal, dict(stdout=stdout, stderr=b''))
        self.logs['stderr'] = b'DEBUG Using patchelf: /usr/bin/patchelf\n'
        self.reject(c.replay_operations, self.config, self.journal, self.logs)
        self.logs['stderr'] = b''
        begin, end = copy.deepcopy(self.rows[-2:]); absolute = self.config['appdir_root'] + '/usr/lib/ordinary.so'
        begin.update(sequence=11, operation='set-rpath', target='usr/lib/ordinary.so', monotonic_ns=110,
            argv=['--force-rpath', '--set-rpath', 'old', '--set-rpath', '$ORIGIN', absolute, 'ignored'],
            before=observation(absolute, self.compiled))
        end.update(sequence=11, monotonic_ns=111, after=observation(absolute, self.compiled, inode=11))
        self.rows.extend([begin, end]); self.refresh()
        original = self.config['appdir_root'] + '/usr/lib/ordinary-link.so'
        self.logs['stdout'] += ('Setting rpath in ELF file ' + original + ' to $ORIGIN\n' +
            'Calling patchelf on canonical path ' + absolute + ' instead of original path ' + original + '\n').encode()
        self.assertEqual(c.replay_operations(self.config, self.journal, self.logs)['calls'], 11)

    def test_swallowed_linuxdeploy_failure_blocks_package_gate(self):
        self.add_query(exit_code=1)
        self.reject(self.final)
        self.rows[-1]['exit'] = 0; self.refresh()
        for message in ('Call to patchelf failed:', 'Failed to set rpath in ELF file:',
                        'APPIMAGE_RELRO_GUARD_FAILURE:query_failed', 'Could not find patchelf'):
            self.logs['stderr'] = message.encode(); self.reject(self.final)

    def test_final_image_mutation_after_successful_guard_rejects(self):
        self.final()
        image = copy.deepcopy(self.inventory)
        path = 'usr/lib/libgio-2.0.so.0'
        image[path]['data'] = image[path]['data'][:-1] + b'x'
        image[path].update(c.byte_record(image[path]['data']))
        self.reject(self.final, self.inventory, image)
        image = copy.deepcopy(self.inventory); image[c.MAIN]['data'] = self.compiled
        image[c.MAIN].update(c.byte_record(self.compiled)); self.reject(self.final, self.inventory, image)

    def test_fixed_environment_preserves_tools_launcher_and_disabled_gstreamer(self):
        self.assertEqual(Path(__file__).with_name('appimage_relro_guard.py').read_text().splitlines()[0], '#!/usr/bin/python3 -BES')
        self.assertEqual(c.validate_config(self.config), self.config)
        for key, value in (('LD_LIBRARY_PATH', '/override'), ('NO_STRIP', '1'), ('guard_mode', 0o644),
                           ('original_patchelf_path', '/usr/bin/patchelf'), ('python_version', 'Python 3.12.15'), ('python_version', 'Python 3.13.1')):
            config = copy.deepcopy(self.config); config[key] = value; self.reject(c.validate_config, config)
        from AppImage入口配置v3 import elf_inventory
        inventory = copy.deepcopy(self.inventory)
        inventory[c.MEDIA_CORE] = copy.deepcopy(c.MEDIA_CORE_RECORD)
        self.final(inventory, inventory)
        for key, values in dict(kind=('directory', 'nonelf', 'symlink'), mode=(0o755, 420.0),
                nlink=(2, True), size=(1430063, 1430064.0), sha256=('0' * 64,)).items():
            for value in values:
                changed = copy.deepcopy(inventory); changed[c.MEDIA_CORE][key] = value
                with self.subTest(field=key, value=value):
                    with self.assertRaisesRegex(EvidenceError, 'unreviewed_media_inventory'):
                        self.final(changed, changed)
        changed = copy.deepcopy(inventory); changed[c.MEDIA_CORE]['extra'] = True
        self.reject(self.final, changed)
        forbidden = ('usr/lib/gstreamer-1.0', 'usr/lib/gstreamer1.0/gstreamer-1.0',
            'usr/lib/gst-plugin-scanner', 'usr/bin/gst-ptp-helper',
            'apprun-hooks/linuxdeploy-plugin-gstreamer.sh', 'usr/lib/libgstreamer-1.0.so.1')
        for relative in forbidden:
            changed = copy.deepcopy(self.inventory); changed[relative] = copy.deepcopy(c.MEDIA_CORE_RECORD)
            with self.assertRaisesRegex(EvidenceError, 'unreviewed_media_inventory'):
                self.final(changed, changed)
        for target in (c.MEDIA_CORE,) + forbidden:
            changed = copy.deepcopy(inventory)
            changed['alias'] = dict(kind='symlink', target='middle', mode=0o777)
            changed['middle'] = dict(kind='symlink', target=target, mode=0o777)
            with self.assertRaisesRegex(EvidenceError, 'unreviewed_media_inventory'):
                self.final(changed, changed)
        for relative, kind in [(c.MEDIA_CORE, 'file'), (c.MEDIA_CORE, 'elf'), (c.MEDIA_CORE, 'directory')] + [
                (path, 'directory' if index < 2 else 'file') for index, path in enumerate(forbidden)]:
            with self.subTest(member=relative, kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                if kind == 'directory': path.mkdir()
                else: path.write_bytes(self.compiled if kind == 'elf' else b'#!/bin/sh\nexit 0\n')
                with self.assertRaisesRegex(EvidenceError, 'unreviewed_media_inventory'):
                    elf_inventory(root)
        for target in (c.MEDIA_CORE, forbidden[0], forbidden[4]):
            with self.subTest(alias_target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); path = root / target
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'not ELF')
                (root / '!alias').symlink_to('middle'); (root / 'middle').symlink_to(target)
                with patch.object(c, 'verify_media_member', wraps=c.verify_media_member) as check:
                    with self.assertRaisesRegex(EvidenceError, 'unreviewed_media_inventory'):
                        elf_inventory(root)
                    self.assertEqual(check.call_args.args[0], target)
                    self.assertEqual(check.call_args.args[1]['kind'], 'symlink')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'ordinary.so').write_bytes(self.compiled)
            (root / 'alias').symlink_to('ordinary.so')
            self.assertEqual(set(elf_inventory(root)), {'ordinary.so', 'alias'})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'file'; path.write_bytes(b'bytes'); path.chmod(0o644)
            self.assertEqual(c.observe(path)[0], b'bytes')
            (Path(temporary) / 'alias').symlink_to(path); self.reject(c.observe, Path(temporary) / 'alias')
            os.link(path, Path(temporary) / 'hardlink'); self.reject(c.observe, path)
            config = copy.deepcopy(self.config); config['target_root'] = temporary + '/target'
            config['appdir_root'] = config['target_root'] + '/' + c.base.TARGET + '/release/bundle/appimage/Coding Tools MCP.AppDir'
            path = Path(config['appdir_root']) / 'usr/lib/libglib-2.0.so.0'
            path.parent.mkdir(parents=True); path.write_bytes(self.compiled); path.chmod(0o644)
            self.assertEqual(c.protected_record(config, path)['target'], 'usr/lib/libglib-2.0.so.0')
            path.parent.chmod(0o775); self.reject(c.protected_record, config, path); path.parent.chmod(0o755)
            with patch.object(c.os, 'geteuid', return_value=os.geteuid() + 1):
                self.reject(c.protected_record, config, path)
            observe = c.observe
            def replace_parent(*args, **kwargs):
                result = observe(*args, **kwargs)
                path.parent.rename(path.parent.with_name('replaced-lib')); path.parent.mkdir()
                return result
            with patch.object(c, 'observe', side_effect=replace_parent):
                self.reject(c.protected_record, config, path)

    def test_receipt_inventory_limits_and_untrusted_pass_flags_reject(self):
        result = self.final(); result['release_approved'] = True
        self.evidence['final.json'] = encoded(result); self.reject(self.final)
        del self.evidence['final.json']
        self.evidence['unexpected.json'] = b'{}'; self.reject(self.final)
        del self.evidence['unexpected.json']
        self.evidence['state.json'] = b' ' * (c.CAPS['state'] + 1); self.reject(self.final)
        self.reject(c.decode, b'{"key":1,"key":2}')
        self.reject(c.decode, b'{"value":NaN}')
        self.reject(c.replay_operations, self.config, self.journal + b'\n', self.logs)


if __name__ == '__main__':
    unittest.main()
