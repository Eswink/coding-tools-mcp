"""Pure helper and failure-path contracts; no native Nginx, Docker or Agent proof."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).parent))
import container_fixture
import run_current_nginx_runtime as runtime
sys.path.pop(0)
DOMAIN = runtime.DOMAIN
CONNECTOR = '00000000-0000-0000-0000-000000000001'


class TwoHopHelperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='two-hop-unit-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.nginx = self.root / 'nginx'
        self.nginx.write_bytes(b'inert helper identity; never executed')
        self.fixture = SimpleNamespace(root=self.root, port=28881, domain=DOMAIN,
            origin='https://' + DOMAIN, config={'connector': CONNECTOR}, password='synthetic-password',
            secret_values=[], project='ctm-topology-' + 'a' * 32,
            exec=Mock(return_value=SimpleNamespace(stdout=b'', stderr=b'nginx version: nginx/1.18.0 (Ubuntu)\n')))
        self.socket = Mock()
        self.socket.__enter__ = Mock(return_value=self.socket)
        self.socket.__exit__ = Mock(return_value=False)
        self.socket.getsockname.return_value = ('127.0.0.1', 28882)
        self.addCleanup(patch.stopall)
        patch.object(runtime.socket, 'socket', return_value=self.socket).start()

    def test_endpoint_reuses_http_without_repointing_fixture_or_secrets(self):
        endpoint = runtime.ProxyEndpoint(self.fixture, 28882)
        self.assertEqual((self.fixture.port, endpoint.port), (28881, 28882))
        for name in ('domain', 'origin', 'config', 'password', 'secret_values'):
            self.assertEqual(getattr(endpoint, name), getattr(self.fixture, name))
        endpoint.secret_values.append('synthetic-token')
        self.assertEqual(self.fixture.secret_values, ['synthetic-token'])
        response = Mock(status=200)
        response.getheaders.return_value = [('Content-Type', 'application/json')]
        response.read.return_value = b'{}'
        connection = Mock()
        connection.getresponse.return_value = response
        with patch.object(container_fixture.http.client, 'HTTPConnection', return_value=connection) as http:
            self.assertEqual(endpoint.http('GET', '/coding-tools/health/ready'),
                             (200, {'content-type': 'application/json'}, b'{}'))
        http.assert_called_once_with('127.0.0.1', 28882, timeout=8)
        connection.request.assert_called_once_with('GET', '/coding-tools/health/ready',
                                                   body=None, headers={'Host': DOMAIN})
        connection.close.assert_called_once_with()

    def test_constructor_renders_owned_private_outer_to_unchanged_inner_port(self):
        with patch.object(runtime.subprocess, 'Popen') as popen:
            outer = runtime.OuterProxy(self.fixture, self.nginx)
        popen.assert_not_called(); self.fixture.exec.assert_not_called()
        self.assertIsNone(outer.process)
        self.assertEqual((outer.endpoint.port, self.fixture.port), (28882, 28881))
        target = self.root / 'current-outer-private'
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
        config = (target / 'nginx.conf').read_text()
        self.assertEqual(stat.S_IMODE((target / 'nginx.conf').stat().st_mode), 0o600)
        self.assertIn('listen 127.0.0.1:28882;', config)
        self.assertIn(f'pid {target}/nginx.pid;', config)
        self.assertIn(f'include {target}/render/{runtime.current.INCLUDE};', config)
        for sentinel in ('existing-site', 'existing-prefix', 'existing-regex'):
            self.assertIn(sentinel, config)
        included = (target / 'render' / runtime.current.INCLUDE).read_bytes()
        self.assertEqual(included.count(b'proxy_pass http://127.0.0.1:28881;'), 4)
        self.assertEqual(outer.manifest['include_sha256'], hashlib.sha256(included).hexdigest())
        self.socket.bind.assert_called_once_with(('127.0.0.1', 0))

    def test_foreign_domain_or_unowned_project_rejected_before_side_effects(self):
        for field, value in [('domain', 'foreign.invalid'), ('project', 'existing-host-service')]:
            with self.subTest(field=field):
                original = getattr(self.fixture, field)
                setattr(self.fixture, field, value)
                with patch.object(runtime.current, 'render') as render, patch.object(runtime.subprocess, 'Popen') as popen:
                    with self.assertRaises(RuntimeError):
                        runtime.OuterProxy(self.fixture, self.nginx)
                setattr(self.fixture, field, original)
                render.assert_not_called(); popen.assert_not_called()
                self.socket.bind.assert_not_called()
                self.assertFalse((self.root / 'current-outer-private').exists())

    def test_outer_port_collision_is_rejected_before_render_or_process(self):
        self.socket.getsockname.return_value = ('127.0.0.1', self.fixture.port)
        with patch.object(runtime.current, 'render') as render, patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, 'distinct_'):
                runtime.OuterProxy(self.fixture, self.nginx)
        render.assert_not_called(); popen.assert_not_called(); self.fixture.exec.assert_not_called()

    def test_existing_outer_directory_is_never_adopted_or_overwritten(self):
        target = self.root / 'current-outer-private'
        target.mkdir(); sentinel = target / 'nginx.conf'; sentinel.write_text('keep')
        with patch.object(runtime.current, 'render') as render, patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaises(FileExistsError):
                runtime.OuterProxy(self.fixture, self.nginx)
        self.assertEqual(sentinel.read_text(), 'keep')
        render.assert_not_called(); popen.assert_not_called()

    def test_source_drift_is_terminal_before_starting_any_process(self):
        with patch.object(runtime.current, 'source_contract', side_effect=ValueError('source drift')), \
             patch.object(runtime.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'source drift'):
                runtime.OuterProxy(self.fixture, self.nginx)
        popen.assert_not_called(); self.fixture.exec.assert_not_called()

    def test_start_checks_exact_binary_and_keeps_owned_foreground_process(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.return_value = None
        with patch.object(runtime.subprocess, 'Popen', return_value=process) as popen, \
             patch.object(runtime, 'raw_request', return_value=(200, [], b'existing-site')) as request:
            outer.start()
        self.assertIs(outer.process, process)
        command = [str(value) for value in popen.call_args.args[0]]
        self.assertEqual(command[0], str(self.nginx))
        self.assertIn('daemon off; master_process off;', command)
        self.assertEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stderr'], subprocess.DEVNULL)
        commands = [[str(value) for value in args.args[0]] for args in self.fixture.exec.call_args_list]
        self.assertTrue(any(command[0] == str(self.nginx) and '-t' in command for command in commands))
        self.assertTrue(any(command == [str(self.nginx), '-v'] for command in commands))
        request.assert_called_once_with(28882, '/', [('Host', DOMAIN)])

    def test_startup_readiness_has_finite_attempts_and_retains_process_for_cleanup(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.return_value = None
        with patch.object(runtime.subprocess, 'Popen', return_value=process), \
             patch.object(runtime, 'raw_request', side_effect=OSError('not ready')) as request, \
             patch.object(runtime.time, 'sleep') as sleep:
            with self.assertRaisesRegex(RuntimeError, 'readiness'):
                outer.start()
        self.assertEqual(request.call_count, 40)
        self.assertLessEqual(sleep.call_count, 40)
        self.assertTrue(all(args == call(.05) for args in sleep.call_args_list))
        self.assertIs(outer.process, process)

    def test_dead_outer_process_cannot_pass_readiness(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.return_value = 1
        with patch.object(runtime.subprocess, 'Popen', return_value=process), \
             patch.object(runtime, 'raw_request') as request:
            with self.assertRaises(RuntimeError):
                outer.start()
        request.assert_not_called()
        self.assertIs(outer.process, process)

    def test_cleanup_reaps_only_owned_process_and_is_idempotent(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.side_effect = [None, 0]
        outer.process = process
        outer.close(); outer.close()
        process.terminate.assert_called_once_with(); process.wait.assert_called_once_with(timeout=5)
        process.kill.assert_not_called(); self.assertIsNone(outer.process)
        self.assertTrue((self.root / 'current-outer-private').is_dir())

    def test_cleanup_uses_bounded_kill_after_terminate_timeout(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.side_effect = [None, -9]
        process.wait.side_effect = [subprocess.TimeoutExpired('owned', 5), -9]
        outer.process = process; outer.close()
        process.terminate.assert_called_once_with(); process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_args_list, [call(timeout=5), call(timeout=5)])
        self.assertIsNone(outer.process)

    def test_cleanup_failure_remains_terminal_and_keeps_process_handle(self):
        outer = runtime.OuterProxy(self.fixture, self.nginx)
        process = Mock(); process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('owned', 5)
        outer.process = process
        with self.assertRaises(subprocess.TimeoutExpired):
            outer.close()
        self.assertIs(outer.process, process)
        self.assertTrue((self.root / 'current-outer-private').is_dir())

    def test_two_hop_hosted_gate_precedes_outer_and_all_external_effects(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(runtime, 'OuterProxy') as outer, \
             patch.object(container_fixture.subprocess, 'run') as command, \
             patch.object(container_fixture.tempfile, 'mkdtemp') as directory, \
             patch.object(runtime, 'install_private_include') as install:
            with self.assertRaisesRegex(container_fixture.FixtureFailure, 'hosted_disposable_ci_only'):
                runtime.runtime_checks(Path('/not-executed'), {}, two_hop=True, nginx=self.nginx)
        for effect in (outer, command, directory, install, self.socket.bind):
            effect.assert_not_called()

    def test_direct_inner_negatives_preserve_ordered_empty_and_duplicate_headers(self):
        with patch.object(runtime, 'raw_request', side_effect=[(403, [], b'')] * 5 + [(421, [], b'')]) as request, \
             patch.object(runtime, 'CASES', []):
            runtime.direct_inner_checks(self.fixture)
            self.assertEqual(len(runtime.CASES), 6)
        calls = request.call_args_list
        self.assertTrue(all(args.args[:2] == (28881, runtime.current.AGENT) for args in calls))
        self.assertEqual([args.args[2][-1] for args in calls[:3]],
                         [('Origin', ''), ('Cookie', ''), ('Authorization', '')])
        self.assertEqual(calls[4].args[2][-2:],
                         [('Sec-WebSocket-Protocol', ''), ('Sec-WebSocket-Protocol', runtime.current.SUBPROTOCOL)])
        self.assertEqual(calls[5].args[2][0], ('Host', 'foreign.invalid'))

    def test_startup_failure_reaps_before_fixture_cleanup_and_cleanup_failure_keeps_directory(self):
        for cleanup_fails in (False, True):
            with self.subTest(cleanup_fails=cleanup_fails):
                order = []
                f = Mock(port=28881, sentinel=Mock())
                f.prepare.return_value = {'compose_version': '2.27.0'}
                f.close.side_effect = lambda: order.append('fixture')
                outer = Mock(start=Mock(side_effect=RuntimeError('startup failed')))
                def close():
                    order.append('outer')
                    if cleanup_fails: raise RuntimeError('owned cleanup failed')
                outer.close.side_effect = close
                with patch.object(runtime, 'Fixture', return_value=f), \
                     patch.object(runtime, 'OuterProxy', return_value=outer), \
                     patch.object(runtime, 'install_private_include') as install, \
                     patch.object(runtime, 'direct_inner_checks'), \
                     patch.object(runtime, 'inner_ingress_evidence', return_value={}), \
                     patch.object(runtime, 'inspect_boundaries'), patch.object(runtime, 'CASES', []), \
                     patch.object(runtime, 'STAGE', 'setup'):
                    with self.assertRaisesRegex(RuntimeError, 'owned cleanup failed' if cleanup_fails else 'startup failed'):
                        runtime.runtime_checks(Path('/not-executed'), {}, two_hop=True, nginx=self.nginx)
                    if cleanup_fails: self.assertEqual(runtime.STAGE, 'owned_cleanup')
                self.assertEqual(order, ['outer'] if cleanup_fails else ['outer', 'fixture'])
                self.assertEqual(f.port, 28881); install.assert_not_called()

    def test_running_inner_config_drift_refuses_evidence_before_image_lookup(self):
        self.fixture.dc = Mock(return_value=SimpleNamespace(stdout=b'0' * 64 + b'  /run/ingress/nginx.conf\n'))
        self.fixture.container = Mock()
        with self.assertRaisesRegex(RuntimeError, 'running_inner_config_matches_renderer'):
            runtime.inner_ingress_evidence(self.fixture)
        self.fixture.dc.assert_called_once_with('exec', '-T', 'ingress', 'sha256sum', '/run/ingress/nginx.conf')
        self.fixture.container.assert_not_called(); self.fixture.exec.assert_not_called()


if __name__ == '__main__':
    unittest.main()
