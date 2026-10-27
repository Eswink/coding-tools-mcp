#!/usr/bin/env python3
"""Disposable probe/caller tests, not native build acceptance evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import desktop_glib_probes as p
import desktop_glib_link as link
import desktop_glib_build_contract as contract
import desktop_glib_build_evidence_tests as contract_tests
import desktop_glib_link_tests as link_tests


def digest(data):
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}


def probe_fixture(name='anyhow', version='1.0.103', relative=None):
    target, cwd = '/owned/target', '/registry/' + name + '-' + version
    out = target + '/' + p.TARGET + '/release/build/' + name + '-2222222222222222/out'
    env = dict(CARGO_PKG_NAME=name, CARGO_PKG_VERSION=version, CARGO_MANIFEST_DIR=cwd,
               OUT_DIR=out, PROFILE='release', HOST=p.TARGET, TARGET=p.TARGET)
    if name == 'rustix':
        args = ['--crate-type=rlib', '--emit=metadata', '--target', p.TARGET, '-o', out + '/rustix_test_can_compile', '-']
    elif name in p.AUTOCFG_CALLERS:
        args = ['--crate-name', 'autocfg_1234567890abcdef_0', '--crate-type=lib', '--out-dir', out,
                '--emit=llvm-ir', '--target', p.TARGET, '-']
    else:
        relative = relative or next(k[2] for k in p.FILE_PROBES if k[:2] == (name, version))
        args = (['--cfg=procmacro2_build_probe'] if name == 'proc-macro2' else
                ['--cfg=anyhow_build_probe'] if name == 'anyhow' else [])
        args += ['--edition=' + ('2021' if name == 'proc-macro2' else '2018'),
                 '--crate-name=' + name.replace('-', '_'), '--crate-type=lib', '--cap-lints=allow',
                 '--emit=dep-info,metadata', '--out-dir', out + '/probe', relative, '--target', p.TARGET]
    unit = p.classify_probe(args, cwd, target, env)
    source = None
    if unit['source']:
        size, sha = p.FILE_PROBES[(name, version, relative)]
        source = dict(path=unit['source'], before={'sha256': sha, 'size': size}, after={'sha256': sha, 'size': size})
    parent_dir = target + '/release/build/' + name + '-1111111111111111'
    parent_path = parent_dir + '/build-script-build'
    parent_hash = digest(b'parent-elf')
    build_source = dict(path=cwd + '/build.rs', before={'sha256': p.PINS[(name, version)][1], 'size': 1},
                        after={'sha256': p.PINS[(name, version)][1], 'size': 1})
    parent = dict(role='host', finished_ns=10, returncode=0, error=None, source=build_source, environment=env.copy(), externs=[],
                  unit={'crate_name': 'build_script_build', 'crate_types': ['bin'], 'emits': ['link']})
    output = dict(path=parent_dir + '/build_script_build-1111111111111111', kind='link', **parent_hash)
    owners, units = {output['path']: ('parent', output)}, {'parent': parent}
    package_id = p.REGISTRY + '#' + name + '@' + version
    target_row = dict(kind=['custom-build'], crate_types=['bin'], name='build-script-build', src_path=cwd + '/build.rs')
    package = dict(id=package_id, name=name, version=version, source=p.REGISTRY,
                   manifest_path=cwd + '/Cargo.toml', targets=[target_row])
    context = dict(packages=[package], lock_packages=[dict(name=name, version=version, source=p.REGISTRY,
        checksum=p.PINS[(name, version)][0])], artifacts=[dict(reason='compiler-artifact', package_id=package_id,
        manifest_path=package['manifest_path'], target=target_row, fresh=False, profile={'test': False},
        filenames=[parent_path])], executed=[dict(reason='build-script-executed', package_id=package_id, out_dir=out)])
    if name in p.AUTOCFG_CALLERS:
        auto_dir = '/registry/autocfg-1.5.1'
        context['packages'].append(dict(id=p.REGISTRY + '#autocfg@1.5.1', name='autocfg', version='1.5.1',
            source=p.REGISTRY, manifest_path=auto_dir + '/Cargo.toml'))
        context['lock_packages'].append(dict(name='autocfg', version='1.5.1', source=p.REGISTRY,
                                            checksum=p.PINS[('autocfg', '1.5.1')][0]))
        auto_output = dict(path=target + '/release/deps/libautocfg-123.rlib', kind='link', **digest(b'autocfg'))
        auto_source = dict(path=auto_dir + '/src/lib.rs', before={'sha256': p.PINS[('autocfg', '1.5.1')][1], 'size': 1},
                           after={'sha256': p.PINS[('autocfg', '1.5.1')][1], 'size': 1})
        units['autocfg'] = dict(role='host', returncode=0, error=None, source=auto_source,
            unit={'crate_name': 'autocfg', 'crate_types': ['lib'], 'emits': ['link']},
            environment=dict(CARGO_PKG_NAME='autocfg', CARGO_PKG_VERSION='1.5.1', CARGO_MANIFEST_DIR=auto_dir))
        owners[auto_output['path']] = ('autocfg', auto_output)
        parent['externs'] = [dict(name='autocfg', path=auto_output['path'], before=digest(b'autocfg'), after=digest(b'autocfg'))]
    record = dict(role='probe', unit=unit, argv=['/real/rustc'] + args, cwd=cwd, environment=env,
        source=source, started_ns=20, returncode=1, error=None, outputs=[], externs=[],
        parent=dict(pid=123, path=parent_path, before=parent_hash.copy(), after=parent_hash.copy()))
    return record, {'target_dir': target, 'probe_context': context}, units, owners


class ProbeContractTests(unittest.TestCase):
    def test_all_nine_packages_five_families_and_file_variants(self):
        cases = [key for key in p.PINS if key[0] != 'autocfg']
        for name, version in cases:
            relatives = [key[2] for key in p.FILE_PROBES if key[:2] == (name, version)] or [None]
            for relative in relatives:
                for status in (0, 1):
                    with self.subTest(package=(name, version), relative=relative, status=status):
                        f = probe_fixture(name, version, relative)
                        f[0]['returncode'] = status
                        with patch('os.open', side_effect=AssertionError('replay accessed filesystem')):
                            p.verify_probe_trace(*f)

    def test_unknown_identity_extra_arguments_and_output_changes_reject(self):
        f = probe_fixture()
        record, expected = f[:2]
        for args in (record['argv'][1:] + ['--extern', 'x=/x.rlib'], ['-o', '/tmp/x', '-'],
                     record['argv'][1:] + ['--emit=link'], record['argv'][1:-1] + ['aarch64-unknown-linux-gnu']):
            self.assertIsNone(p.classify_probe(args, record['cwd'], expected['target_dir'], record['environment']))
        for key, value in [('CARGO_PKG_VERSION', '9.0'), ('CARGO_PKG_NAME', 'glib')]:
            env = dict(record['environment'], **{key: value})
            self.assertIsNone(p.classify_probe(record['argv'][1:], record['cwd'], expected['target_dir'], env))
        for key in ('PROFILE', 'HOST', 'TARGET', 'CARGO_MANIFEST_DIR'):
            env = dict(record['environment'], **{key: 'wrong'})
            with self.assertRaises(ValueError):
                p.classify_probe(record['argv'][1:], record['cwd'], expected['target_dir'], env)

    def test_autocfg_name_and_output_forms_are_finite(self):
        rec, exp, _, _ = probe_fixture('memoffset', '0.9.1')
        for name in ('autocfg_1234567890abcdef_1048576', 'autocfg_1234567890abcdef_01',
                     'autocfg_1234567890ABCDEF_1', 'glib'):
            args = rec['argv'][1:].copy(); args[1] = name
            self.assertIsNone(p.classify_probe(args, rec['cwd'], exp['target_dir'], rec['environment']))
        for out in ('/outside/out', '/owned/target/' + p.TARGET + '/debug/build/memoffset-2222222222222222/out'):
            args = rec['argv'][1:].copy(); args[4] = out
            env = dict(rec['environment'], OUT_DIR=out)
            with self.assertRaises(ValueError):
                p.classify_probe(args, rec['cwd'], exp['target_dir'], env)

    def test_stdin_cannot_gain_invented_source_or_artifact_proof(self):
        for key, value in [('source', {'before':digest(b'pretend')}), ('outputs', [{'path':'/out'}]),
                           ('externs', [{'name':'glib'}]), ('unit', {})]:
            f = probe_fixture('rustix', '1.1.4'); f[0][key] = value
            with self.assertRaises((ValueError, KeyError, TypeError)):
                p.verify_probe_trace(*f)

    def test_probe_status_capture_source_parent_and_context_mutations_reject(self):
        mutations = [lambda r,e,u,o,value=x:r.update(returncode=value) for x in (True, 1.0, 101, -15, None)]
        mutations += [lambda r,e,u,o:r.update(error='capture failure'), lambda r,e,u,o:r.update(parent=None),
            lambda r,e,u,o:r['parent'].update(pid=True), lambda r,e,u,o:r['parent'].update(path='/other'),
            lambda r,e,u,o:r['parent']['after'].update(sha256='f'*64),
            lambda r,e,u,o:r['source']['after'].update(sha256='f'*64),
            lambda r,e,u,o:r.update(outputs=[{'path':'/probe-output'}]),
            lambda r,e,u,o:r['environment'].update(CARGO_MANIFEST_DIR='/wrong'),
            lambda r,e,u,o:e['probe_context']['lock_packages'][0].update(checksum='0'*64),
            lambda r,e,u,o:e['probe_context']['packages'][0].update(source='other'),
            lambda r,e,u,o:e['probe_context']['artifacts'].clear(),
            lambda r,e,u,o:e['probe_context']['artifacts'][0].update(fresh=True),
            lambda r,e,u,o:e['probe_context']['artifacts'].append(e['probe_context']['artifacts'][0]),
            lambda r,e,u,o:e['probe_context']['executed'][0].update(out_dir='/wrong'),
            lambda r,e,u,o:u['parent'].update(error='capture failed'),
            lambda r,e,u,o:u['parent'].update(finished_ns=100),
            lambda r,e,u,o:o.update(alias=next(iter(o.values()))),
            lambda r,e,u,o:e['probe_context']['artifacts'][0].update(package_id='other'),
            lambda r,e,u,o:e['probe_context']['executed'].append(e['probe_context']['executed'][0]),
            lambda r,e,u,o:u['parent'].update(returncode=1), lambda r,e,u,o:u['parent'].update(role='target'),
            lambda r,e,u,o:u['parent']['source']['before'].update(sha256='f'*64),
            lambda r,e,u,o:u['parent']['environment'].update(CARGO_PKG_VERSION='wrong'),
            lambda r,e,u,o:o.clear()]
        for mutation in mutations:
            f = probe_fixture()
            mutation(*f)
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, KeyError, TypeError)):
                p.verify_probe_trace(*f)

    def test_autocfg_requires_actual_consumed_accepted_source_owner(self):
        for change in (lambda r,e,u,o:u['parent']['externs'].clear(),
                       lambda r,e,u,o:u['autocfg']['source']['before'].update(sha256='f'*64),
                       lambda r,e,u,o:u['autocfg'].update(role='target'),
                       lambda r,e,u,o:u['parent']['externs'][0]['after'].update(sha256='f'*64),
                       lambda r,e,u,o:u['autocfg']['environment'].update(CARGO_PKG_VERSION='2.0')):
            f = probe_fixture('num-traits', '0.2.19')
            change(*f)
            with self.assertRaises(ValueError):
                p.verify_probe_trace(*f)

    def test_failed_probe_is_diagnostic_but_failed_product_still_rejects(self):
        base = link_tests.TraceTests()
        base.setUp()
        probe, extra, units, owners = probe_fixture()
        base.add('build_script_build', 'bin', units['parent']['source']['path'])
        parent = base.records[3]
        parent['finished_ns'] = 100
        at = parent['argv'].index('--target'); del parent['argv'][at:at + 2]
        at = parent['argv'].index('--out-dir'); parent['argv'][at + 1] = str(Path(probe['parent']['path']).parent)
        parent['source'] = units['parent']['source']; parent['environment'] = units['parent']['environment']
        base.reparse(3)
        parent['outputs'][0].update(probe['parent']['before'])
        full = dict(base.records[0], **{k:v for k,v in probe.items() if k not in ('argv',)})
        full.update(id='f'*32, started_ns=110, finished_ns=120,
                    argv=[base.expected['real_rustc']] + probe['argv'][1:])
        base.records.append(full); base.expected.update(extra)
        result = base.verify()
        self.assertEqual((result['diagnostic_probes'], result['diagnostic_probe_failures'], result['target_ancestry_units']), (1,1,3))
        base.records[0]['returncode'] = 1
        base.reject()
        base.records[0]['returncode'] = 0
        path = probe['unit']['out_dir'] + '/probe/libanyhow.rmeta'
        base.records[2]['argv'] += ['--extern', 'probe=' + path]
        base.records[2]['externs'].append(dict(name='probe', path=path, before=digest(b'probe'), after=digest(b'probe')))
        with self.assertRaisesRegex(ValueError, 'unmatched_extern_producer'):
            base.verify()

    def test_event_context_order_and_refreshed_receipt_inventory_contradiction(self):
        f = contract_tests.fixture()
        target = dict(name='build-script-build', kind=['custom-build'], src_path='/trusted/source/dependency/build.rs')
        f[0]['packages'][2]['targets'].append(target)
        artifact = dict(f[2][2], target=target)
        executed = dict(reason='build-script-executed', package_id='dependency', out_dir='/owned/target/release/build/dependency/out')
        f[2][-1:-1] = [artifact, executed]
        result = contract_tests.check_events(f)
        self.assertEqual(result['build_scripts'], {'artifacts':[artifact], 'executed':[executed]})
        existing = contract_tests.EnvelopeBoundaryTests()
        existing.setUp()
        try:
            path = existing.evidence / 'compiler-copies.json'
            value = json.loads(path.read_text())
            value['events']['build_scripts']['executed'].append(executed)
            path.write_text(json.dumps(value))
            existing.envelope['files'] = contract.evidence_inventory(existing.evidence)
            with self.assertRaisesRegex(ValueError, 'contradictory_runner_receipt:compiler-copies.json'):
                existing.run_verifier()
        finally:
            existing.doCleanups()


class ParentProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.target = self.root / 'target'
        self.out = self.target / p.TARGET / 'release/build/rustix-2222222222222222/out'
        self.parent = self.target / 'release/build/rustix-1111111111111111/build-script-build'
        self.out.mkdir(parents=True); self.parent.parent.mkdir(parents=True)
        shutil.copyfile(Path(sys.executable).resolve(), self.parent); self.parent.chmod(0o700)
        self.cwd = self.root / 'registry/rustix-1.1.4'; self.cwd.mkdir(parents=True)
        self.evidence = self.root / 'evidence'; self.evidence.mkdir()

    def command(self, status):
        compiler = self.root / 'rustc'
        compiler.write_text('#!' + sys.executable + '\nimport os,sys\nos.write(1,b"ready\\n")\n'
                            'data=sys.stdin.buffer.read()\nsys.stdout.buffer.write(data)\n'
                            'sys.stdout.buffer.flush()\nsys.exit(' + str(status) + ')\n')
        compiler.chmod(0o700)
        args = [str(compiler), '--crate-type=rlib', '--emit=metadata', '--target', p.TARGET,
                '-o', str(self.out / 'rustix_test_can_compile'), '-']
        config = dict(real_rustc=str(compiler), real_rustc_sha256=contract.file_record(compiler)['sha256'],
            source_root=str(self.cwd), source_sha='a'*40, target_dir=str(self.target), evidence_dir=str(self.evidence))
        driver = 'import sys;sys.path.insert(0,' + repr(str(Path(__file__).parent)) + ');import desktop_glib_link as l;' + (
                 'l.propagate_exit(l.capture_rustc(' + repr(args) + ',' + repr(config) + '))')
        parent_driver = 'import subprocess,sys;sys.exit(subprocess.call(' + repr([sys.executable, '-c', driver]) + '))'
        env = {k:v for k,v in os.environ.items() if not k.startswith(('GIT_', 'CARGO_'))}
        env.update(PYTHONHOME=sys.base_prefix, CARGO_PKG_NAME='rustix', CARGO_PKG_VERSION='1.1.4', CARGO_MANIFEST_DIR=str(self.cwd),
                   OUT_DIR=str(self.out), PROFILE='release', TARGET=p.TARGET, HOST=p.TARGET)
        return [str(self.parent), '-c', parent_driver], env

    def test_live_binary_stdin_and_status_are_untouched_with_real_parent(self):
        for status in (0, 1):
            command, env = self.command(status)
            child = subprocess.Popen(command, cwd=self.cwd, env=env, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ready = child.stdout.readline()
            if ready != b'ready\n':
                _, error = child.communicate(timeout=10)
                self.fail(error.decode())
            self.assertIsNone(child.poll())
            data = bytes(range(256)) * 8192
            stdout, stderr = child.communicate(data, timeout=20)
            self.assertEqual((stdout, stderr, child.returncode), (data, b'', status))
        for path in self.evidence.glob('rustc-*.json'):
            rec = json.loads(path.read_text())
            self.assertEqual((rec['schema'], rec['role'], rec['unit']['stdin'], rec['source']), (2,'probe','unobserved',None))
            self.assertEqual(rec['parent']['path'], str(self.parent))
            self.assertEqual(rec['parent']['before'], rec['parent']['after'])
            self.assertEqual(rec['outputs'], [])

    def test_parent_and_output_ancestor_mutations_reject(self):
        with patch('os.getppid', side_effect=[123,124]), patch('os.readlink', return_value=str(self.parent)):
            with self.assertRaisesRegex(ValueError, 'probe_parent_changed'):
                p.capture_probe_parent(str(self.target), str(self.out))
        with patch('os.getppid', return_value=123), patch('os.readlink', return_value=str(self.parent)):
            before = p.capture_probe_parent(str(self.target), str(self.out))
            self.parent.write_bytes(b'mutated')
            with self.assertRaisesRegex(ValueError, 'probe_parent_changed'):
                p.capture_probe_parent(str(self.target), str(self.out), before)
        alias = self.root / 'alias'; alias.symlink_to(self.out.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            p.capture_probe_parent(str(self.target), str(alias / 'out'))
        self.parent.unlink(); self.parent.symlink_to(Path(sys.executable).resolve())
        with patch('os.getppid', return_value=123), patch('os.readlink', return_value=str(self.parent)):
            with self.assertRaises(OSError):
                p.capture_probe_parent(str(self.target), str(self.out))


if __name__ == '__main__':
    unittest.main()
