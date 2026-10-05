#!/usr/bin/env python3
"""Synthetic trace and real disposable-process tests; no native acceptance claim."""
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import desktop_glib_link as link
from desktop_glib_build_contract import file_record, stable_file


def identity(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(source_sha='a' * 40, source_root='/owned/source',
            target_dir='/owned/target', real_rustc='/owned/rustc', real_rustc_sha256='b' * 64,
            local_source_hashes={})
        self.records = []
        self.add('glib', 'lib', '/owned/source/vendor/glib/src/lib.rs')
        self.add('middle', 'rlib', '/owned/source/middle/src/lib.rs', [(0, '.rmeta')])
        self.add('coding_tools_mcp_desktop', 'bin', '/owned/source/src-tauri/src/main.rs', [(1, '.rlib')])
        for label, index in [('glib', 0), ('root', 2)]:
            source = self.records[index]['source']
            self.expected[label + '_source'] = source['path']
            self.expected[label + '_source_sha256'] = source['before']['sha256']
        self.expected['glib_rlib'] = self.output(0, '.rlib').copy()
        self.expected['root_executable'] = dict(self.records[2]['outputs'][0],
            path='/owned/target/' + link.TARGET + '/release/coding-tools-mcp-desktop')

    def output(self, index, suffix):
        return next(o for o in self.records[index]['outputs'] if o['path'].endswith(suffix))

    def add(self, name, kind, source, inputs=()):
        index = len(self.records)
        out = self.expected['target_dir'] + '/' + link.TARGET + '/release/deps'
        args = [self.expected['real_rustc'], '--crate-name', name, '--crate-type', kind,
                '--edition=2021', source, '--emit=' + ('dep-info,link' if kind == 'bin' else 'dep-info,metadata,link'),
                '--target', link.TARGET, '--out-dir', out, '-C', 'extra-filename=-' + str(index),
                '-C', 'opt-level=3', '-C', 'embed-bitcode=no', '--check-cfg', 'cfg(docsrs,test)']
        externs = []
        for producer, suffix in inputs:
            output = self.output(producer, suffix)
            ext = {'name': self.records[producer]['unit']['crate_name'], 'path': output['path'],
                   'before': {k: output[k] for k in ('sha256', 'size')},
                   'after': {k: output[k] for k in ('sha256', 'size')}}
            externs.append(ext)
            args += ['--extern', ext['name'] + '=' + ext['path']]
        parsed = link.rustc_outputs(args[1:], '/owned/source', self.expected['target_dir'])
        source_hash = identity(source.encode())
        self.expected['local_source_hashes'][source] = source_hash['sha256']
        self.records.append(dict(schema=1, id=f'{index:032x}', argv=args, cwd='/owned/source',
            compiler={'path': self.expected['real_rustc'], 'sha256': self.expected['real_rustc_sha256']},
            source_sha=self.expected['source_sha'], source_root=self.expected['source_root'],
            target_dir=self.expected['target_dir'], environment={}, role=parsed['role'], unit=parsed['unit'],
            source={'path': source, 'before': source_hash.copy(), 'after': source_hash.copy()},
            externs=externs, outputs=[dict(o, **identity(o['path'].encode())) for o in parsed['outputs']],
            started_ns=10 + index * 10, finished_ns=60 - index * 10, returncode=0, error=None))

    def verify(self):
        return link.verify_link_trace(self.records, self.expected)

    def reject(self):
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.verify()

    def reparse(self, index):
        rec = self.records[index]
        parsed = link.rustc_outputs(rec['argv'][1:], rec['cwd'], self.expected['target_dir'])
        rec.update(role=parsed['role'], unit=parsed['unit'])
        rec['outputs'] = [dict(o, **identity(o['path'].encode())) for o in parsed['outputs']]

    def test_pipelined_metadata_and_later_archive_are_accepted(self):
        result = self.verify()
        self.assertEqual(result['target_ancestry_units'], 3)
        self.assertFalse(result['native_linker_consumption_verified'])
        self.assertFalse(result['retained_glib_code_verified'])
        self.assertLess(self.records[1]['started_ns'], self.records[0]['finished_ns'])

    def test_root_uplift_path_need_not_equal_deps_path(self):
        self.assertNotEqual(self.records[2]['outputs'][0]['path'], self.expected['root_executable']['path'])
        self.verify()

    def test_no_metadata_emission_order_is_invented(self):
        self.records[0]['started_ns'] = 35
        self.verify()  # timestamps are diagnostic; only each interval is well formed

    def test_rmeta_hash_cannot_be_replaced_with_sibling_rlib_hash(self):
        ext = self.records[1]['externs'][0]
        ext['before'] = ext['after'] = {k: self.output(0, '.rlib')[k] for k in ('sha256', 'size')}
        self.reject()

    def test_changed_extern_or_source(self):
        for field in ('source', 'extern'):
            with self.subTest(field=field):
                saved = copy.deepcopy(self.records)
                entry = self.records[1]['source'] if field == 'source' else self.records[1]['externs'][0]
                entry['after']['sha256'] = 'f' * 64
                self.reject()
                self.records = saved

    def test_mutations_fail(self):
        mutations = [(0, 'returncode', 1), (1, 'returncode', -signal.SIGTERM),
            (2, 'returncode', None), (0, 'returncode', False), (0, 'schema', True),
            (0, 'started_ns', 1.0), (0, 'finished_ns', 0), (0, 'source_sha', 'c' * 40),
            (0, 'role', 'host'), (0, 'source_root', '/other'), (0, 'target_dir', '/other'),
            (1, 'error', 'capture failed'), (0, 'environment', {'AWS_SECRET_ACCESS_KEY': 'secret'})]
        for index, key, value in mutations:
            with self.subTest(key=key, value=value):
                saved = copy.deepcopy(self.records)
                self.records[index][key] = value
                self.reject()
                self.records = saved

    def test_substituted_compiler_and_argv(self):
        self.records[0]['compiler']['sha256'] = 'f' * 64
        self.reject()
        self.records[0]['compiler']['sha256'] = self.expected['real_rustc_sha256']
        self.records[0]['argv'][0] = '/another/rustc'
        self.reject()

    def test_source_not_from_trusted_checkout(self):
        self.expected['local_source_hashes'][self.records[0]['source']['path']] = 'f' * 64
        self.reject()

    def test_duplicate_owner_or_invocation(self):
        self.records.append(copy.deepcopy(self.records[0]))
        self.reject()
        self.records[-1]['id'] = 'f' * 32
        self.reject()

    def test_missing_producer_or_glib_ancestry(self):
        self.records.pop(1)
        self.reject()

    def test_emitted_glib_with_no_ancestry(self):
        root = self.records[2]
        root['argv'] = root['argv'][:-2]
        root['externs'] = []
        self.reject()

    def test_wrong_target_profile_output_override_and_unknown_syntax(self):
        for suffix in (['-o', '/tmp/other'], ['--emit=link=/tmp/out'], ['--test'],
                       ['--target=aarch64-unknown-linux-gnu'], ['-C', 'incremental=/tmp/cache'],
                       ['--sysroot=/tmp'], ['@response'], ['-C', 'link-arg=-Wl,-o,alternate']):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                link.rustc_outputs(self.records[0]['argv'][1:] + suffix, '/owned/source', '/owned/target')
        args = self.records[0]['argv'][1:]
        for changed in ('/owned/target/' + link.TARGET + '/debug/deps', '/outside/release/deps'):
            with self.assertRaises(ValueError):
                link.rustc_outputs([changed if v.endswith('/release/deps') else v for v in args],
                                   '/owned/source', '/owned/target')

    def test_check_only_unit_cannot_produce_ancestry(self):
        rec = self.records[0]
        rec['argv'] = ['--emit=metadata' if a.startswith('--emit=') else a for a in rec['argv']]
        self.reparse(0)
        self.reject()

    def test_query_cannot_substitute_a_compile(self):
        rec = self.records[0]
        rec.update(argv=[self.expected['real_rustc'], '-vV'], role='query', unit=None,
                   source=None, outputs=[], externs=[])
        self.reject()

    def test_cycles_reject_even_with_matching_hashes(self):
        ext = self.output(1, '.rmeta')
        rec = self.records[0]
        rec['argv'] += ['--extern', 'middle=' + ext['path']]
        rec['externs'].append({'name': 'middle', 'path': ext['path'],
            'before': {k: ext[k] for k in ('sha256', 'size')},
            'after': {k: ext[k] for k in ('sha256', 'size')}})
        self.reject()

    def test_output_and_copy_mutations(self):
        for label in ('glib_rlib', 'root_executable'):
            saved = copy.deepcopy(self.expected)
            self.expected[label]['sha256'] = 'f' * 64
            self.reject()
            self.expected = saved
        self.records[0]['outputs'][0]['size'] = True
        self.reject()

    def test_repeated_and_comma_separated_linux_crate_types(self):
        args = self.records[0]['argv'][1:] + ['--crate-type=staticlib,cdylib', '--crate-type', 'rlib']
        parsed = link.rustc_outputs(args, '/owned/source', '/owned/target')
        self.assertEqual({Path(o['path']).suffix for o in parsed['outputs']}, {'.a', '.so', '.rlib', '.rmeta'})
        for crate_type in ('lib', 'rlib', 'bin', 'staticlib', 'cdylib', 'dylib', 'proc-macro'):
            with self.subTest(crate_type=crate_type):
                args = self.records[0]['argv'][1:].copy()
                args[3] = crate_type
                self.assertTrue(link.rustc_outputs(args, '/owned/source', '/owned/target')['outputs'])

    def test_trace_count_argv_and_resource_bounds(self):
        for args in ([], ['x'] * 4097, ['x' * 16385], ['x\x00']):
            with self.assertRaises(ValueError):
                link.valid_argv(args)
        for records in ([], [self.records[0]] * 8193):
            with self.assertRaises(ValueError):
                link.verify_link_trace(records, self.expected)
        self.records[0]['source']['before']['size'] = link.MAX_BINARY + 1
        self.reject()

    def test_proc_macro_bare_sysroot_extern_is_host_only(self):
        args = ['--crate-name', 'macros', '--crate-type', 'proc-macro', '/owned/source/macros.rs',
                '--emit=dep-info,link', '--out-dir', '/owned/target/release/deps', '--extern', 'proc_macro']
        parsed = link.rustc_outputs(args, '/owned/source', '/owned/target')
        self.assertEqual(parsed['unit']['sysroot_externs'], ['proc_macro'])
        self.assertEqual(parsed['externs'], [])
        for changed in (args[:-1] + ['glib'], args + ['--extern', 'proc_macro'],
                        [a.replace('/target/release', '/target/' + link.TARGET + '/release') for a in args]
                        + ['--target', link.TARGET],
                        ['rlib' if a == 'proc-macro' else a for a in args]):
            with self.assertRaises(ValueError):
                link.rustc_outputs(changed, '/owned/source', '/owned/target')

    def test_host_macro_edge_is_valid_but_cannot_supply_target_ancestry(self):
        self.add('macros', 'proc-macro', '/owned/source/macros.rs')
        macro = self.records[3]
        macro['finished_ns'] = 80
        i = macro['argv'].index('--target')
        del macro['argv'][i:i + 2]
        macro['argv'] = [a.replace('/target/' + link.TARGET, '/target') for a in macro['argv']]
        macro['argv'] += ['--extern', 'proc_macro']
        self.reparse(3)
        output = self.output(3, '.so')
        root = self.records[2]
        root['argv'] += ['--extern', 'macros=' + output['path']]
        root['externs'].append({'name': 'macros', 'path': output['path'],
            'before': {k: output[k] for k in ('sha256', 'size')},
            'after': {k: output[k] for k in ('sha256', 'size')}})
        self.assertEqual(self.verify()['target_ancestry_units'], 3)
        macro['argv'] = ['rlib' if a == 'proc-macro' else a for a in macro['argv'][:-2]]
        self.reparse(3)
        self.reject()

    def test_deep_and_nonfinite_trace_data_reject(self):
        value = None
        for _ in range(65):
            value = [value]
        self.records[0]['error'] = value
        self.reject()
        self.records[0]['error'] = float('nan')
        self.reject()


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / 'target'
        self.evidence = self.root / 'evidence'
        self.target.mkdir()
        self.evidence.mkdir()
        self.compiler = self.root / 'rustc'
        self.script = 'import os,sys,signal,time\n'
        self.config = dict(real_rustc=str(self.compiler), source_root=str(self.root),
            target_dir=str(self.target), evidence_dir=str(self.evidence), source_sha='a' * 40)

    def prepare(self, script, args=None):
        self.compiler.write_text('#!' + sys.executable + '\n' + self.script + script)
        self.compiler.chmod(0o700)
        self.config['real_rustc_sha256'] = file_record(self.compiler)['sha256']
        driver = ('import sys;sys.path.insert(0,' + repr(str(Path(__file__).parent)) + ');'
                  'import desktop_glib_link as l;l.propagate_exit(l.capture_rustc(' +
                  repr([str(self.compiler)] + (args or ['-vV'])) + ',' + repr(self.config) + '))')
        return [sys.executable, '-c', driver]

    def trace(self):
        files = list(self.evidence.glob('rustc-*.json'))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def test_byte_exact_large_stdout_stderr_and_environment_allowlist(self):
        command = self.prepare('os.write(1,b"metadata\\x00\\xff"*200000)\nos.write(2,b"diagnostic\\x00\\xfe"*200000)\n')
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(AWS_SECRET_ACCESS_KEY='must-not-be-recorded', CARGO_PKG_NAME='fixture')
        process = subprocess.run(command, capture_output=True, env=env, timeout=20)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(process.stdout, b'metadata\x00\xff' * 200000)
        self.assertEqual(process.stderr, b'diagnostic\x00\xfe' * 200000)
        self.assertEqual(self.trace()['environment'].get('CARGO_PKG_NAME'), 'fixture')
        self.assertNotIn('AWS_SECRET_ACCESS_KEY', self.trace()['environment'])

    def test_metadata_is_live_before_compiler_completes(self):
        command = self.prepare('os.write(1,b"metadata-ready\\n")\ntime.sleep(0.6)\nos.write(1,b"finished\\n")\n')
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(process.stdout.readline(), b'metadata-ready\n')
        self.assertIsNone(process.poll())
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual((stdout, stderr, process.returncode), (b'finished\n', b'', 0))

    def test_ordinary_failure_status(self):
        process = subprocess.run(self.prepare('sys.exit(37)\n'), capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 37)
        self.assertEqual(self.trace()['returncode'], 37)

    def test_child_signals_are_reproduced_after_trace_write(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(sig=sig):
                for path in self.evidence.iterdir():
                    path.unlink()
                command = self.prepare(f'os.kill(os.getpid(),{int(sig)})\n')
                process = subprocess.run(command, capture_output=True, timeout=10)
                self.assertEqual(process.returncode, -sig, process.stderr)
                self.assertEqual(self.trace()['returncode'], -sig)

    def test_jobserver_pipe_round_trip(self):
        read_fd, write_fd = os.pipe()
        try:
            command = self.prepare(f'os.write({write_fd},b"token")\nassert os.read({read_fd},5)==b"token"\n')
            env = dict(os.environ, CARGO_MAKEFLAGS=f'-j --jobserver-fds={read_fd},{write_fd} --jobserver-auth={read_fd},{write_fd}')
            process = subprocess.run(command, env=env, pass_fds=(read_fd, write_fd), capture_output=True, timeout=10)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(self.trace()['returncode'], 0)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_fifo_absent_and_invalid_jobserver(self):
        fifo = self.root / 'jobserver'
        os.mkfifo(fifo)
        self.assertEqual(link.jobserver_fds({}), ())
        self.assertEqual(link.jobserver_fds({'CARGO_MAKEFLAGS': '-j'}), ())
        self.assertEqual(link.jobserver_fds({'CARGO_MAKEFLAGS': '--jobserver-auth=fifo:' + str(fifo)}), ())
        for value in ('--jobserver-auth=broken', '--jobserver-auth=1,2', '--jobserver-style=unknown',
                      '--jobserver-auth=3,4 --jobserver-fds=5,6', '--jobserver-fds=fifo:' + str(fifo),
                      '--jobserver-auth=fifo:' + str(self.root)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                link.jobserver_fds({'CARGO_MAKEFLAGS': value})
        command = self.prepare('assert os.environ["CARGO_MAKEFLAGS"].startswith("--jobserver-auth=fifo:")\n')
        process = subprocess.run(command, env=dict(os.environ, CARGO_MAKEFLAGS='--jobserver-auth=fifo:' + str(fifo)),
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_invalid_jobserver_leaves_failure_trace_without_running_child(self):
        command = self.prepare('os.write(1,b"must-not-run")\n')
        process = subprocess.run(command, env=dict(os.environ, CARGO_MAKEFLAGS='--jobserver-auth=invalid'),
                                 capture_output=True, timeout=10)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(process.stdout, b'')
        self.assertIsNone(self.trace()['returncode'])
        self.assertIsNotNone(self.trace()['error'])

    def test_capture_compilation_retains_exact_argv_cwd_source_and_cooutputs(self):
        out = self.target / link.TARGET / 'release/deps'
        out.mkdir(parents=True)
        source = self.root / 'lib.rs'
        source.write_bytes(b'pub fn fixture() {}')
        args = ['--crate-name', 'fixture', '--crate-type=rlib', str(source),
                '--emit=dep-info,metadata,link', '--target', link.TARGET,
                '--out-dir', str(out), '-C', 'opt-level=3', '-C', 'extra-filename=-0123']
        script = ('assert sys.argv[1:]==' + repr(args) + '\nassert os.getcwd()==' + repr(str(self.root)) + '\n'
                  + 'open(' + repr(str(out / 'libfixture-0123.rmeta')) + ',"wb").write(b"metadata")\n'
                  + 'open(' + repr(str(out / 'libfixture-0123.rlib')) + ',"wb").write(b"archive")\n')
        process = subprocess.run(self.prepare(script, args), cwd=self.root, capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        rec = self.trace()
        self.assertIsNone(rec['error'])
        self.assertEqual(rec['argv'], [str(self.compiler)] + args)
        self.assertEqual(rec['cwd'], str(self.root))
        self.assertEqual(rec['source']['before'], rec['source']['after'])
        self.assertEqual({o['sha256'] for o in rec['outputs']},
                         {identity(b'metadata')['sha256'], identity(b'archive')['sha256']})

    def test_capture_records_mutated_source_and_extern_after_child(self):
        out = self.target / link.TARGET / 'release/deps'
        out.mkdir(parents=True)
        source, dep = self.root / 'lib.rs', out / 'libdep.rmeta'
        source.write_bytes(b'before-source')
        dep.write_bytes(b'before-dep')
        args = ['--crate-name', 'fixture', '--crate-type=rlib', str(source),
                '--emit=metadata,link', '--target', link.TARGET, '--out-dir', str(out),
                '--extern', 'dep=' + str(dep)]
        script = ''.join('open(' + repr(str(path)) + ',"wb").write(b"changed")\n'
                         for path in (source, dep, out / 'libfixture.rlib', out / 'libfixture.rmeta'))
        process = subprocess.run(self.prepare(script, args), cwd=self.root, capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        record = self.trace()
        self.assertIsNone(record['error'])
        self.assertNotEqual(record['source']['before'], record['source']['after'])
        self.assertNotEqual(record['externs'][0]['before'], record['externs'][0]['after'])

    def test_unknown_compile_syntax_preserves_execution_and_blocks_trace(self):
        process = subprocess.run(self.prepare('os.write(1,b"executed")\n', ['-o', '/unreviewed']),
                                 capture_output=True, timeout=10)
        self.assertEqual((process.returncode, process.stdout), (0, b'executed'))
        self.assertIsNotNone(self.trace()['error'])
        self.assertEqual(self.trace()['outputs'], [])

    def test_safe_hash_reads_reject_symlink_ancestor_and_external_hardlink(self):
        path = self.target / 'unit'
        path.write_bytes(b'archive')
        alias = self.target / 'alias'
        os.link(path, alias)
        self.assertEqual(stable_file(path, self.target, allow_hardlinks=True), identity(b'archive'))
        outside = self.root / 'outside'
        os.link(path, outside)
        with self.assertRaises(ValueError):
            stable_file(path, self.target, allow_hardlinks=True)
        symlink = self.root / 'linked'
        symlink.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(OSError):
            file_record(symlink / 'unit')


if __name__ == '__main__':
    unittest.main()
