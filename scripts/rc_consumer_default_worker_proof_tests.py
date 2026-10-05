"""Offline synthetic orchestration tests; none is a live default-worker proof.

The 912-byte historical ZIP below is opaque data only: never parsed or executed.
Import/discovery performs no repository loading, credential read, or network work.
"""
import ast
import base64
from contextlib import ExitStack, contextmanager, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from rc_consumer_proof_fixtures import install_historical

ROOT = Path(__file__).absolute().parents[1]
NAMES = ('rc_consumer_io', 'rc_consumer_transport_worker', 'rc_consumer_transport')
# Data-only fixture from artifact11134440327; digest independently fixed in tests.
FIXTURE = (
    'UEsDBBQACAgIAE0EQV0AAAAAAAAAAAAAAAAQAAAA5rqQ56CB54mI5pysLnR4dAXBwREAMAQEwH+quWMklMOg/xKyOzIg962kJntd'
    'varNnbgCq4jousT5UEsHCB1GVR4pAAAAKQAAAFBLAwQUAAgICABNBEFdAAAAAAAAAAAAAAAAGAAAAOeJiOacrOagoemqjOaXpeW/'
    'l3Y0LnR4dHWRwZKCMAyG7/sUTM+2U3Blges+iBPaVKtd0mmKF8d3d0B2PIDX/F/+5E/ugg1FFF0hEgYERmlgsN5CRnnDxJ4GCYOV'
    'TGMyKHaFiMCMVnRFTiPuCrFQk4VWtdIyGfU9ga+WI59h0rBCXZbux1Wwh9K6Zt/0vT00TanrSh/6tm1tX5davC1ZdMVdRDBXOKG6'
    '8NaQRZWBzHVGuo/7rNGlwioR5XXDL6QTqUx/4Z/8xEyWXUx0QbPhk2FMXhka3FaIx/tUJgCzd95AXhKsnjIHGfvg+XyEGBPd5l84'
    'CIyPrydQSwcIzZuoAd8AAADPAQAAUEsDBBQACAgIAE0EQV0AAAAAAAAAAAAAAAATAAAA6aG555uu54mI5pysdjQuanNvbn2RTW6D'
    'MBCF95zC8rq2DGkosO1BosEeJ05cBnlMNlHuXkGoGqmk25nvvfl5t0IIyZZGlJ2QCSMCo7IwuOAgo7pi4kCDgsEppilZlG+zZARm'
    'dLITOU24VFZytjG61kYlq98f8EN44BPMXazQlKX/8BXsoHS+2TV97/ZNU5q6Mvu+bVvX16WRz7YsO3ErhFhG2wscUZ95c9ovoSLZ'
    'y4J1r5fbxNcK60SUt0WfkI6kM33FH/o/brbuxkRntC/8MkwpaEuD3zqsEOL+/EobgTn4YCGvZ/2Jbs1p6mPg0wHGMdF1ScxDZCzu'
    'xTdQSwcIxhLuoegAAAD7AQAAUEsBAi0DFAAICAgATQRBXR1GVR4pAAAAKQAAABAAAAAAAAAAAAAgAKSBAAAAAOa6kOeggeeJiOac'
    'rC50eHRQSwECLQMUAAgICABNBEFdzZuoAd8AAADPAQAAGAAAAAAAAAAAACAApIFnAAAA54mI5pys5qCh6aqM5pel5b+XdjQudHh0'
    'UEsBAi0DFAAICAgATQRBXcYS7qHoAAAA+wEAABMAAAAAAAAAAAAgAKSBjAEAAOmhueebrueJiOacrHY0Lmpzb25QSwUGAAAAAAMA'
    'AwDFAAAAtQIAAAAA'
)

def load_harness():
    path = ROOT / 'scripts/rc_consumer_default_worker_proof.py'
    spec = importlib.util.spec_from_file_location('synthetic_proof_under_test', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), module.__dict__)
    return module

class DefaultWorkerProofTests(unittest.TestCase):
    """Twenty-four named design categories; subtests are also fully offline."""
    def setUp(self):
        self.h = load_harness()
        install_historical(self)
        self.data = base64.b64decode(FIXTURE)

    def buffers(self):
        return {name: (self.h.ROOT / 'scripts' / (name + '.py')).read_bytes() for name in NAMES}

    @contextmanager
    def production(self, buffers=None):
        old = {name: sys.modules.pop(name) for name in NAMES if name in sys.modules}
        try:
            yield self.h.load_production(self.buffers() if buffers is None else buffers)
        finally:
            for name in NAMES:
                sys.modules.pop(name, None)
            sys.modules.update(old)

    def records(self):
        repo = {'id': 1360355522, 'full_name': 'Eswink/coding-tools-mcp'}
        branch = 'ci/rc-tag-evidence-e2e011-cumulative'
        source = 'e2e011f7f2a3a1df838bbd588106205b999db610'
        run = dict(id=36796834637, run_attempt=1, workflow_id=352786852, head_sha=source,
                   event='push', head_branch=branch, path='.github/workflows/发布来源验证v4.yml',
                   status='completed', conclusion='success', created_at='2026-10-01T00:34:16Z',
                   run_started_at='2026-10-01T00:34:16Z', updated_at='2026-10-01T00:35:27Z',
                   repository=repo.copy(), head_repository=repo.copy())
        art = dict(id=11134440327, name='发布来源证据v4-ubuntu-latest-36796834637', size_in_bytes=912,
                   digest='sha256:dcc70362712162e99d6884942f0720934bc16c7d6a817361ffbfd1602601fa60',
                   expired=False, created_at='2026-10-01T00:34:27Z', updated_at='2026-10-01T00:34:27Z',
                   expires_at='2026-10-08T00:34:27Z', workflow_run=dict(id=36796834637,
                   repository_id=1360355522, head_repository_id=1360355522, head_sha=source, head_branch=branch))
        return [repo, run, {'total_count': 2, 'artifacts': [{'id': 11133683955}, copy.deepcopy(art)]}, art]

    def reject(self, callback, code=None):
        with self.assertRaises(Exception) as caught:
            callback()
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_01_import_and_discovery_are_inert(self):
        saved = {name: sys.modules.get(name) for name in NAMES}
        with patch.dict(os.environ, {'GH_TOKEN': 'synthetic-secret', 'GITHUB_REF': 'sentinel'}), \
             patch.object(os.environ, 'pop', side_effect=AssertionError('credential access')), \
             patch.object(os.environ, 'get', side_effect=AssertionError('environment access')), \
             patch('subprocess.Popen', side_effect=AssertionError('process launch')), \
             patch('http.client.HTTPSConnection', side_effect=AssertionError('network')):
            h = load_harness()
            unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
            self.assertEqual(os.environ['GH_TOKEN'], 'synthetic-secret')
            self.assertEqual(os.environ['GITHUB_REF'], 'sentinel')
            self.assertFalse(hasattr(h, 'transport'))
        self.assertEqual(saved, {name: sys.modules.get(name) for name in NAMES})

    def valid_identity(self):
        h = self.h
        return dict(GITHUB_REPOSITORY=h.REPOSITORY, GITHUB_REPOSITORY_ID=str(h.REPOSITORY_ID),
            GITHUB_EVENT_NAME='push', GITHUB_REF=h.REF, GITHUB_WORKFLOW_REF=h.WORKFLOW_REF,
            GITHUB_RUN_ATTEMPT='1', GITHUB_WORKSPACE=str(h.ROOT), GITHUB_SHA='a' * 40,
            GITHUB_WORKFLOW_SHA='a' * 40, GITHUB_RUN_ID='123', RUNNER_TEMP='/tmp')

    def git_rows(self):
        h = self.h
        return ['a' * 40, 'a' * 40 + ' ' + h.C_COMMIT, h.C_TREE, 'b' * 40,
            '\n'.join(':000000 100644 ' + '0' * 40 + ' ' + 'c' * 40 + ' A\t' + p for p in h.ADDED), '']

    def test_02_source_binding_and_verified_bytes_defeat_hostile_pyc(self):
        h = self.h
        self.assertEqual(h.C_COMMIT, '93c2ad95304668ecc112da0cb073e46fe177e4f7')
        self.assertEqual(h.C_TREE, '2eb0f0b3809c98331f9db4ae56a137c8817b3489')
        self.assertEqual(tuple(h.HASHES), NAMES)
        with patch.object(h, 'git', side_effect=self.git_rows()):
            binding, buffers = h.source_snapshot(self.valid_identity())
        self.assertEqual(binding['module_sha256'], {n: hashlib.sha256(b).hexdigest() for n, b in buffers.items()})
        for index, bad in ((0, 'd' * 40), (1, 'a' * 40 + ' ' + 'd' * 40), (2, 'd' * 40),
                           (4, self.git_rows()[4].replace('100644', '100755')), (4, '')):
            rows = self.git_rows(); rows[index] = bad
            with self.subTest(source_gate=index, bad=bad[:15]), patch.object(h, 'git', side_effect=rows):
                self.reject(lambda: h.source_snapshot(self.valid_identity()), 'source_rejected')
        with tempfile.TemporaryDirectory() as temp, patch.object(h, 'ROOT', Path(temp)):
            scripts = Path(temp) / 'scripts'; scripts.mkdir()
            for name, data in buffers.items():
                path = scripts / (name + '.py'); path.write_bytes(data)
                cache = Path(importlib.util.cache_from_source(str(path))); cache.parent.mkdir(exist_ok=True)
                hostile = compile('HOSTILE_CACHE_WAS_USED = True', str(path), 'exec')
                cache.write_bytes(importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, int(path.stat().st_mtime), len(data)) + marshal.dumps(hostile))
                cached = h.importlib.machinery.SourceFileLoader(name, str(path)).get_code(name)
                self.assertIn('HOSTILE_CACHE_WAS_USED', cached.co_names)
            old_path = list(sys.path); get_code = h.importlib.machinery.SourceFileLoader.get_code
            def guarded_code(loader, name):
                if name in NAMES: raise AssertionError('repository cache read')
                return get_code(loader, name)
            with patch.object(h.importlib.machinery.SourceFileLoader, 'get_code', guarded_code), \
                 patch.object(h.Path, 'read_bytes', side_effect=AssertionError('source reopen')), \
                 patch.object(h.os, 'open', side_effect=AssertionError('source reopen')), self.production(buffers) as modules:
                self.assertFalse(any(hasattr(m, 'HOSTILE_CACHE_WAS_USED') for m in modules))
                self.assertEqual([m.__name__ for m in modules], list(NAMES))
            self.assertEqual(sys.path, old_path)
            for mutation in ('hash', 'worker_link'):
                with self.subTest(mutation=mutation):
                    worker = scripts / (NAMES[1] + '.py'); worker.unlink()
                    if mutation == 'hash': worker.write_bytes(buffers[NAMES[1]] + b'\n')
                    else: worker.symlink_to(ROOT / 'scripts' / (NAMES[1] + '.py'))
                    self.reject(h.source_bytes, 'source_rejected')
        for name in NAMES:
            with patch.dict(sys.modules, {name: SimpleNamespace()}):
                self.reject(lambda: h.load_production(buffers), 'source_rejected')
        with patch.object(h.importlib.util, 'spec_from_file_location', return_value=None):
            self.reject(self.load_once, 'source_rejected')
        for invalid in ({}, dict(reversed(list(buffers.items()))), buffers | {NAMES[0]: 'not bytes'}, buffers | {NAMES[0]: b'bad'}):
            self.reject(lambda: self.load_once(invalid), 'source_rejected')
        spec_factory = h.importlib.util.spec_from_file_location
        for part, key in (('spec', 'name'), ('spec', 'origin'), ('loader', 'path')):
            def corrupt(name, path, part=part, key=key):
                spec = spec_factory(name, path)
                setattr(spec.loader if part == 'loader' else spec, key, 'wrong'); return spec
            with patch.object(h.importlib.util, 'spec_from_file_location', side_effect=corrupt):
                self.reject(self.load_once, 'source_rejected')

    def test_03_tracked_untracked_and_ignored_source_drift(self):
        for drift in (' M scripts/rc_consumer_io.py', '?? surprise.py', '!! ignored.pyc'):
            with self.subTest(drift=drift), patch.object(self.h, 'git', side_effect=self.git_rows()[:-1] + [drift]):
                self.reject(lambda: self.h.source_snapshot(self.valid_identity()), 'source_rejected')

    def test_04_identity_ref_event_attempt_and_token_isolation(self):
        values = self.valid_identity()
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(self.h.identity(), values)
        for key in values:
            for bad in ('', '01' if key == 'GITHUB_RUN_ID' else 'wrong'):
                with self.subTest(key=key, bad=bad), patch.dict(os.environ, values | {key: bad}, clear=True):
                    self.reject(self.h.identity, 'identity_rejected')
        with patch.dict(os.environ, values | {'GH_TOKEN': 'synthetic-only'}, clear=True):
            before = {k: v for k, v in os.environ.items() if k.startswith('GITHUB_')}
            rc, result = self.entry(lambda token: (_ for _ in ()).throw(self.h.ProofError('identity_rejected')), real_pop=True)
            self.assertEqual(rc, 1); self.assertFalse(result['passed']); self.assertNotIn('GH_TOKEN', os.environ)
            self.assertEqual(before, {k: v for k, v in os.environ.items() if k.startswith('GITHUB_')})

    def test_05_runtime_and_arguments_are_exact(self):
        h = self.h
        valid = dict(argv=['proof'], implementation=SimpleNamespace(name='cpython'), version_info=(3, 12, 14),
                     flags=SimpleNamespace(isolated=1, no_site=1), dont_write_bytecode=True)
        with patch.multiple(h.sys, **valid), patch.object(h.platform, 'system', return_value='Linux'):
            h.runtime()
            for key, value in (('argv', ['proof', 'extra']), ('version_info', (3, 12, 13)),
                               ('implementation', SimpleNamespace(name='pypy')), ('dont_write_bytecode', False),
                               ('flags', SimpleNamespace(isolated=0, no_site=1)), ('flags', SimpleNamespace(isolated=1, no_site=0))):
                with self.subTest(key=key), patch.object(h.sys, key, value):
                    self.reject(h.runtime, 'runtime_rejected')
            with patch.object(h.platform, 'system', return_value='Windows'):
                self.reject(h.runtime, 'runtime_rejected')

    def test_06_singleton_constants_and_fixed_default_launch(self):
        with self.production() as (_, wire, transport):
            self.assertEqual(wire.TRUSTED_STORAGE_HOSTS, self.h.HOSTS)
            self.assertEqual(transport.TRUSTED_STORAGE_HOSTS, self.h.HOSTS)
            self.assertEqual((transport.TOTAL_TIMEOUT, transport.CLEANUP_TIMEOUT, wire.READ_TIMEOUT), (300, 5, 15))
        with patch.object(self.h, 'HOSTS', frozenset()):
            self.reject(lambda: self.load_once(), 'source_rejected')
        text = (ROOT / 'scripts/rc_consumer_default_worker_proof.py').read_text()
        self.assertNotIn('sys.path', text); self.assertNotIn('exec_module(', text)
        self.assertIn("compile(data, path, 'exec', dont_inherit=True)", text)
        self.assertEqual(text.count('download_artifact_zip('), 1)

    def load_once(self, buffers=None):
        with self.production(buffers) as modules:
            return modules

    def test_07_metadata_fixed_paths_only(self):
        with patch.object(self.h.http.client, 'HTTPSConnection') as connection:
            for path in ('https://evil.test/x', self.h.METADATA_PATHS[-1] + '/zip', '/arbitrary'):
                self.reject(lambda: self.h.metadata_get(path, 'synthetic'), 'metadata_rejected')
            connection.assert_not_called()

    def get_json(self, raw=b'{}', status=200, headers=None):
        h = self.h; h.STATE.update(deadline=float('inf'), expired=False)
        response = Mock(status=status)
        response.getheaders.return_value = headers if headers is not None else [('Content-Type', 'application/json')]
        response.read.return_value = raw
        connection = Mock(); connection.getresponse.return_value = response
        with patch.object(h.http.client, 'HTTPSConnection', return_value=connection) as ctor:
            result = h.metadata_get(h.METADATA_PATHS[0], 'synthetic-token')
        ctor.assert_called_once_with('api.github.com', port=443, timeout=10)
        response.read.assert_called_once_with(131073); response.close.assert_called_once(); connection.close.assert_called_once()
        self.assertEqual(connection.request.call_args.args, ('GET', h.METADATA_PATHS[0]))
        return result

    def test_08_strict_http_and_bounded_json(self):
        self.assertEqual(self.get_json(), {})
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1.5}', b'{"x":999999999999999999999}',
                    b'[]', b'{' + b' ' * 131072, b'\xff', b'{'):
            with self.subTest(raw=raw[:30]): self.reject(lambda: self.get_json(raw))
        for status in (302, 404, True):
            with self.subTest(status=status): self.reject(lambda: self.get_json(status=status))
        for extra in ([('Location', 'secret')], [('Link', 'next')], [('Content-Encoding', 'gzip')],
                      [('Content-Length', '4')], [('Content-Length', '2'), ('Content-Length', '2')],
                      [('Content-Length', '2'), ('Transfer-Encoding', 'chunked')], [('X-Long', 'x' * 16384)]):
            with self.subTest(headers=extra[0][0]):
                self.reject(lambda: self.get_json(headers=[('Content-Type', 'application/json')] + extra))

    def observe(self, records=None, phase='a'):
        self.h.STATE.update(deadline=float('inf'), expired=False)
        with patch.object(self.h, 'metadata_get', side_effect=records or self.records()) as get, patch.object(self.h, 'expiry'):
            result = self.h.metadata('synthetic', phase)
        self.assertEqual([c.args for c in get.call_args_list], [(p, 'synthetic') for p in self.h.METADATA_PATHS])
        return result

    def test_09_typed_repository_run_source_attempt_fields(self):
        self.observe()
        for index in (0, 1):
            for key, original in self.records()[index].items():
                if isinstance(original, dict): continue
                for bad in (None, True if type(original) is int else 'wrong'):
                    rows = self.records(); rows[index][key] = bad
                    with self.subTest(record=index, key=key, bad=bad): self.reject(lambda: self.observe(rows))
        for key in ('repository', 'head_repository'):
            rows = self.records(); rows[1][key]['id'] = True
            self.reject(lambda: self.observe(rows))

    def test_10_listed_direct_tuple_and_unselected_urls(self):
        baseline = self.observe()
        for where in ('listed', 'direct'):
            for nested, fields in ((False, self.h.ARTIFACT_FIELDS), (True, self.h.NESTED_FIELDS)):
                for key, _ in fields:
                    rows = self.records(); item = rows[2]['artifacts'][1] if where == 'listed' else rows[3]
                    (item['workflow_run'] if nested else item)[key] = None
                    with self.subTest(where=where, key=key): self.reject(lambda: self.observe(rows))
        rows = self.records()
        for item in (rows[2]['artifacts'][1], rows[3]): item['archive_download_url'] = 'https://secret.invalid/?token=sentinel'
        observed = self.observe(rows); self.assertEqual(observed, baseline)
        self.assertNotIn('sentinel', repr(observed))

    def test_11_inventory_missing_duplicate_noncanonical_and_drift(self):
        for total, ids in ((1, [11134440327]), (2, [11134440327] * 2), (2, [True, 11134440327]),
                           (2, ['11133683955', 11134440327]), (2, [11133683956, 11134440327]), (True, [])):
            rows = self.records(); rows[2] = dict(total_count=total, artifacts=[{'id': n} for n in ids])
            with self.subTest(total=total, ids=ids): self.reject(lambda: self.observe(rows))

    def test_12_expiry_literal_false_and_phase_margins(self):
        for value in (True, 0, None, 'false'):
            rows = self.records(); rows[3]['expired'] = value
            self.reject(lambda: self.observe(rows))
        h = self.h; expires = h.datetime.fromisoformat(h.EXPIRES.replace('Z', '+00:00'))
        for phase, seconds, allowed in (('a', 431, True), ('a', 430, False), ('b', 1, True), ('b', 0, False)):
            clock = Mock(); clock.fromisoformat.side_effect = h.datetime.fromisoformat
            clock.now.return_value = expires - h.timedelta(seconds=seconds)
            with self.subTest(phase=phase, margin=seconds), patch.object(h, 'datetime', clock):
                if allowed: h.expiry(phase)
                else: self.reject(lambda: h.expiry(phase), 'expiry_rejected')

    @contextmanager
    def synthetic(self, download=None, metadata=None, closing=False, source=None):
        """Synthetic orchestration only; real local file I/O, zero worker/network."""
        h = self.h
        with self.production() as (private_io, _, production_transport), tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            roots = []
            def factory(*args, **kwargs):
                root = private_io.PrivateRoot(*args, **kwargs); roots.append(root)
                if not closing: return root
                class CloseFailure:
                    def __getattr__(self, name): return getattr(root, name)
                    def __enter__(self): return root
                    def __exit__(self, *_):
                        root.close(); raise OSError('synthetic-secret')
                return CloseFailure()
            def success(api, artifact, root, *, opener):
                return root.write('artifact.zip', self.data)
            downloader = Mock(side_effect=download or success)
            buffers = self.buffers(); binding = dict(c_commit=h.C_COMMIT, c_tree=h.C_TREE,
                h_commit='a' * 40, h_tree='b' * 40, module_sha256=h.HASHES.copy())
            values = self.valid_identity() | {'RUNNER_TEMP': temp}
            for name, value in dict(runtime=lambda: None, identity=lambda: values,
                source_snapshot=Mock(side_effect=source or [(binding, buffers)] * 2),
                load_production=lambda _: (SimpleNamespace(PrivateRoot=factory), None,
                    SimpleNamespace(download_artifact_zip=downloader, SAFE_ERRORS=production_transport.SAFE_ERRORS)),
                metadata=Mock(side_effect=metadata or [(('synthetic',), {'id': h.ARTIFACT_ID})] * 2),
                expiry=lambda _: None).items(): stack.enter_context(patch.object(h, name, value))
            h.STATE.update(stage='preflight', deadline=float('inf'), expired=False, cleanup=None)
            try: yield downloader, roots
            finally:
                for root in roots: root.close()

    def entry(self, work, signals=None, timers=None, real_pop=False):
        output = io.StringIO()
        with patch.object(os.environ, 'pop', side_effect=os.environ.pop if real_pop else lambda *_: 'synthetic-only') as pop, \
             patch.object(self.h, 'run_proof', side_effect=work), \
             patch.object(self.h.signal, 'signal', side_effect=signals), \
             patch.object(self.h.signal, 'setitimer', side_effect=timers), redirect_stdout(output):
            rc = self.h.main(); pop.assert_called_once_with('GH_TOKEN', '')
        lines = output.getvalue().splitlines(); self.assertEqual(len(lines), 1)
        self.assertNotIn('synthetic-secret', lines[0]); self.assertNotIn('Traceback', lines[0])
        return rc, json.loads(lines[0])

    def test_13_metadata_a_failure_prevents_download(self):
        with self.synthetic(metadata=[self.h.ProofError('metadata_rejected')]) as (call, roots):
            self.reject(lambda: self.h.run_proof('synthetic'), 'metadata_rejected')
            call.assert_not_called(); self.assertEqual(roots, [])

    def test_14_exactly_one_explicit_default_call_no_retry(self):
        with self.synthetic() as (call, _):
            self.h.run_proof('synthetic')
            call.assert_called_once(); self.assertEqual(call.call_args.kwargs, {'opener': None})
            self.assertEqual(call.call_args.args[0].token, 'synthetic')
        with self.synthetic(download=Mock(side_effect=RuntimeError('synthetic-secret'))) as (call, _):
            self.reject(lambda: self.h.run_proof('synthetic')); call.assert_called_once()

    def test_15_synthetic_success_is_orchestration_only(self):
        self.assertEqual((len(self.data), hashlib.sha256(self.data).hexdigest()), (912, self.h.DIGEST[7:]))
        with patch('socket.create_connection', side_effect=AssertionError('offline only')), self.synthetic() as (call, roots):
            report = self.h.run_proof('synthetic')
            self.assertTrue(report['passed']); call.assert_called_once()
            self.assertIsNone(roots[0].fd); self.assertTrue((roots[0].path / 'artifact.zip').exists())
            self.assertFalse(report['independent_worker_network_telemetry'])

    def test_16_transport_codes_and_secret_sanitization(self):
        for code in self.h.CODES | {'https://secret.invalid/?token=synthetic-secret', 'UNKNOWN'}:
            def failure(_token, code=code):
                error = RuntimeError('synthetic-secret'); error.code = code; raise error
            with self.subTest(code=code):
                rc, report = self.entry(failure)
                self.assertEqual(rc, 1); self.assertFalse(report['passed'])
                self.assertEqual(report['code'], code if code in self.h.CODES else 'proof_failed')

    def test_17_cleanup_uncertainty_overrides_deadline(self):
        def uncertain(*args, **kwargs):
            self.h.STATE['expired'] = True
            error = RuntimeError('synthetic-secret'); error.code = 'transport_cleanup_uncertain'
            error.original_error_code = 'download_size_mismatch'; raise error
        with self.synthetic(download=uncertain), patch.dict(os.environ, {'GH_TOKEN': 'synthetic'}):
            work = self.h.run_proof; rc, report = self.entry(work)
        self.assertEqual((rc, report['code'], report['original_error_code']),
                         (1, 'transport_cleanup_uncertain', 'download_size_mismatch'))

    def test_18_private_path_inventory_mode_link_inode_size_hash(self):
        with self.production() as (private_io, _, _), tempfile.TemporaryDirectory() as temp:
            for mutation in ('path', 'extra', 'mode', 'link', 'inode', 'size', 'hash'):
                with self.subTest(mutation=mutation), private_io.PrivateRoot(temp) as root:
                    path = root.write('artifact.zip', self.data)
                    if mutation == 'path': path = root.path / 'other.zip'
                    elif mutation == 'extra': root.write('extra', b'x')
                    elif mutation == 'mode': path.chmod(0o644)
                    elif mutation == 'link': os.link(path, root.path / 'linked')
                    elif mutation == 'inode':
                        replacement = root.path / 'replacement'; replacement.write_bytes(self.data)
                        replacement.chmod(0o600); os.replace(replacement, path)
                    elif mutation == 'size': path.write_bytes(self.data + b'x')
                    else: path.write_bytes(b'x' * 912)
                    self.reject(lambda: self.h.readback(root, path))
            # Ownership mismatch is synthetic: no chown or production monkeypatch.
            root = SimpleNamespace(path=Path(temp), files=Mock(side_effect=private_io.ConsumerError('unsafe_private_file')))
            self.reject(lambda: self.h.readback(root, root.path / 'artifact.zip'), 'unsafe_private_file')

    def test_19_real_readback_and_post_metadata_file_change(self):
        with self.production() as (private_io, _, _), tempfile.TemporaryDirectory() as temp:
            with private_io.PrivateRoot(temp) as root:
                path = root.write('artifact.zip', self.data)
                self.assertEqual(path.stat().st_uid, os.geteuid())
                self.assertEqual(self.h.readback(root, path), {'size_in_bytes': 912, 'digest': self.h.DIGEST})
        def alter(token, phase):
            if phase == 'b': (roots[0].path / 'artifact.zip').write_bytes(b'x' * 912)
            return ('synthetic',), {'id': self.h.ARTIFACT_ID}
        with self.synthetic(metadata=alter) as (call, roots):
            self.reject(lambda: self.h.run_proof('synthetic'), 'file_rejected'); call.assert_called_once()
        tree = ast.parse((ROOT / 'scripts/rc_consumer_default_worker_proof.py').read_text())
        self.assertFalse(any(isinstance(n, ast.Import) and any(a.name in {'zipfile', 'tarfile'} for a in n.names) for n in ast.walk(tree)))

    def test_20_metadata_b_drift_or_failure_forbids_success(self):
        for after in ((('changed',), {}), self.h.ProofError('metadata_rejected')):
            with self.synthetic(metadata=[(('synthetic',), {}), after]) as (call, _):
                self.reject(lambda: self.h.run_proof('synthetic'), 'metadata_rejected'); call.assert_called_once()

    def test_21_root_close_and_exit_source_drift(self):
        with self.synthetic(closing=True): self.reject(lambda: self.h.run_proof('synthetic'), 'root_close_failed')
        with self.synthetic(source=[({}, self.buffers()), ({'drift': True}, self.buffers())]):
            self.reject(lambda: self.h.run_proof('synthetic'), 'source_rejected')

    def test_22_sticky_alarm_and_late_completion(self):
        def caught(api, artifact, root, *, opener):
            try: self.h.alarm(None, None)
            except self.h.ProofError: pass
            return root.write('artifact.zip', self.data)
        with self.synthetic(download=caught): self.reject(lambda: self.h.run_proof('synthetic'), 'overall_deadline')
        def late(_token):
            self.h.STATE['deadline'] = -1
            return {'passed': True}
        rc, report = self.entry(late); self.assertEqual((rc, report['code']), (1, 'overall_deadline'))
        for signals, timers, code in ((OSError('synthetic-secret'), None, 'signal_setup_failed'),
            (None, [OSError('synthetic-secret'), None], 'signal_setup_failed'),
            (None, [None, OSError('synthetic-secret')], 'signal_cleanup_failed'),
            ([0, OSError('synthetic-secret')], None, 'signal_cleanup_failed')):
            with self.subTest(signals=signals, timers=timers):
                rc, report = self.entry(lambda _: {'passed': True}, signals, timers)
                self.assertEqual((rc, report['passed'], report['code']), (1, False, code))
        def cleanup_pending(_token):
            self.h.STATE['cleanup'] = 'download_size_mismatch'
            raise self.h.ProofError('transport_cleanup_uncertain')
        rc, report = self.entry(cleanup_pending, timers=[None, OSError('synthetic-secret')])
        self.assertEqual((rc, report['code'], report['original_error_code']),
                         (1, 'transport_cleanup_uncertain', 'download_size_mismatch'))

    def test_23_report_allowlist_false_flags_and_one_output(self):
        with self.synthetic(): report = self.h.run_proof('synthetic')
        expected = {'schema', 'scope', 'passed', 'source', 'run_id', 'run_attempt', 'workflow_ref', 'runtime',
            'producer_run_id', 'artifact_id', 'observed_owned_file', 'production_default_call_returned',
            'independent_owned_file_readback', 'metadata_a_b_equal', 'private_root_closed', 'source_unchanged',
            'source_enforced_success_contract', 'independent_worker_network_telemetry', 'snapshot_atomic',
            'release_approved', 'publish_approved', 'final_bundle_validated'}
        self.assertEqual(set(report), expected)
        for flag in ('snapshot_atomic', 'release_approved', 'publish_approved', 'final_bundle_validated'):
            self.assertIs(report[flag], False)
        self.assertEqual(report['source_enforced_success_contract']['evidence_basis'], 'reviewed_unchanged_default_path')
        self.assertNotIn('observed_http_status', json.dumps(report)); self.assertNotIn('observed_exit_code', json.dumps(report))
        rc, output = self.entry(lambda _: report); self.assertEqual((rc, output), (0, report))

    def test_24_workflow_exact_trigger_pins_permissions_and_watchdog(self):
        text = (ROOT / '.github/workflows/rc-artifact-default-worker-proof.yml').read_text()
        text = '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#')) + '\n'
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertEqual(text.split('on:\n')[1].split('permissions:')[0].strip(),
                         'push:\n    branches:\n      - ci/rc-artifact-default-worker-proof-20261004')
        self.assertEqual(text.count('\non:'), 1)
        self.assertNotRegex(text, r'(?m)^\s*(workflow_dispatch|pull_request|pull_request_target|workflow_run|schedule|workflow_call|paths|cache|environment|secrets):')
        self.assertEqual(text.split('permissions:\n')[1].split('jobs:')[0].strip(), 'contents: read\n  actions: read')
        self.assertEqual(re.findall(r'uses: ([^\s]+)', text), [
            'actions/checkout@11d5960a326750d5838078e36cf38b85af677262',
            'actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065'])
        for required in ('ref: ${{ github.sha }}', 'persist-credentials: false', 'fetch-depth: 2',
                         "python-version: '3.12.14'", 'runs-on: ubuntu-24.04', 'timeout-minutes: 10',
                         'timeout --signal=KILL 430s python -B -I -S scripts/rc_consumer_default_worker_proof.py'):
            self.assertIn(required, text)
        before, live = text.split('GH_TOKEN: ${{ github.token }}')
        self.assertNotIn('GH_TOKEN:', before); self.assertEqual(text.count('GH_TOKEN:'), 1)
        self.assertIn('rc_consumer_default_worker_proof_tests.py', before)
        self.assertNotRegex(text, r'(write-all|id-token:|: write|upload-artifact|download-artifact|pip install|npm |--foreground|continue-on-error|git push|FINAL)')
        for guard in ("github.run_attempt == 1", "github.run_id > 0", "github.workflow_sha == github.sha",
                      "github.repository_id == '1360355522'", "github.repository == 'Eswink/coding-tools-mcp'",
                      "github.event_name == 'push' && !github.event.deleted", self.h.REF, self.h.WORKFLOW_REF):
            self.assertIn(guard, text)
        self.assertEqual(re.findall(r'^  ([a-z_]+):$', text.split('permissions:')[0], re.M), ['push'])
        live_step = text.split('      - name: One fixed default-worker transfer', 1)[1]
        self.assertIn('        env:\n          GH_TOKEN: ${{ github.token }}', live_step)
        self.assertNotIn('GH_TOKEN', text.split('    steps:')[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
