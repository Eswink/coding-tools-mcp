"""Pure/CLI and owned raw-wire mechanics only; no native Nginx or Docker acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'deploy/cloud-gateway/current_nginx_include.py'
sys.path.insert(0, str(Path(__file__).parent))
import container_fixture
import run_current_nginx_checks as checks
import run_current_nginx_runtime as runtime
sys.path.pop(0)
current = checks.current
DOMAIN, CONNECTOR, PORT = checks.DOMAIN, checks.CONNECTOR, 28880
PINS = {
    'services/cloud-gateway/src/channel/transport.rs': '2662be4f84b22cf6784d8392a9d1dcd2481128147657eed4d070dcbd62c3153d',
    'services/cloud-gateway/src/channel/protocol.rs': 'baefe29876c5034af951c012846246b99004051cbbed5b86cd99de8c592f9b53',
    'services/cloud-gateway/src/config.rs': '79207a0744d01f20c7abff595aa0d2a10c9edc7436766ac2abc8d1b332bf32a7',
    'services/cloud-gateway/src/mcp/http.rs': '1034eebe6fff8e2036209646a4c7f3b821fd675f88240b9b3d49285f19f88421',
    'services/cloud-gateway/src/mcp/protocol.rs': '607d2bea785fdde87fc2d36d1f937ced240d640977e5ff656bfd171747235254',
}


class CurrentIncludeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='current-include-unit-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'review'

    def copied_source(self):
        root = self.root / 'source'
        for relative in PINS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        return root

    def test_valid_identity_and_boundary_ports(self):
        for port in (1024, PORT, 65535):
            value = current.locations(DOMAIN, CONNECTOR, port)
            self.assertEqual(value.count(f'proxy_pass http://127.0.0.1:{port};'), 4)

    def test_bad_identity_and_port_inputs_rejected(self):
        invalid = [('', CONNECTOR, PORT), ('LOCAL.invalid', CONNECTOR, PORT),
                   ('https://site.invalid', CONNECTOR, PORT), ('site.invalid:443', CONNECTOR, PORT),
                   ('site.invalid.', CONNECTOR, PORT), ('x\nreturn 200;', CONNECTOR, PORT),
                   ('under_score.invalid', CONNECTOR, PORT), ('é.invalid', CONNECTOR, PORT),
                   ('singlelabel', CONNECTOR, PORT), ('a' * 64 + '.invalid', CONNECTOR, PORT),
                   (None, CONNECTOR, PORT), (7, CONNECTOR, PORT), (DOMAIN, None, PORT),
                   (DOMAIN, 7, PORT), (DOMAIN, '00000000-0000-0000-0000-000000000000', PORT),
                   (DOMAIN, 'AAAAAAAA-0000-0000-0000-000000000001', PORT),
                   (DOMAIN, CONNECTOR.replace('-', ''), PORT), (DOMAIN, 'bad', PORT)]
        invalid += [(DOMAIN, CONNECTOR, port) for port in (0, 443, 1023, 65536, True, None, '28880', 28880.0)]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                current.locations(*values)

    def test_five_scoped_locations_original_host_and_upstream(self):
        value = current.locations(DOMAIN, CONNECTOR, PORT)
        blocks = re.findall(r'^location ([^{]+) \{\n(.*?)^\}', value, re.M | re.S)
        self.assertEqual([route.strip() for route, _ in blocks], [
            '= /coding-tools', '= /.well-known/oauth-protected-resource/coding-tools/mcp/' + CONNECTOR,
            '= /.well-known/oauth-authorization-server/coding-tools/oauth', '^~ /coding-tools/',
            '= /coding-tools/agent'])
        for index, (_, body) in enumerate(blocks):
            self.assertTrue(body.startswith(f'    if ($http_host != "{DOMAIN}") {{ return 421; }}\n'))
            self.assertIn('access_log off;', body)
            if index == 0:
                self.assertIn('return 404;', body)
                self.assertNotIn('proxy_', body)
            else:
                self.assertIn('proxy_set_header Host $http_host;', body)
                self.assertIn(f'proxy_pass http://127.0.0.1:{PORT};', body)
        self.assertNotIn('$host', value)
        self.assertNotIn('/agent/connect', value)
        self.assertNotRegex(value, r'(?m)^\s*(?:http|server|listen|map|upstream|root|rewrite|include|ssl_\w*)\b')

    def test_native_end_to_end_headers_are_never_reconstructed(self):
        value = current.locations(DOMAIN, CONNECTOR, PORT)
        overrides = [name.lower() for name in re.findall(r'proxy_set_header\s+(\S+)', value)]
        for name in ('Authorization', 'Origin', 'Cookie', 'Accept', 'Content-Type', 'MCP-Protocol-Version',
                     'Mcp-Session-Id', 'Mcp-Method', 'Mcp-Name', 'Last-Event-ID'):
            self.assertNotIn(name.lower(), overrides)
        self.assertEqual(value.count('proxy_pass_request_headers on;'), 4)
        self.assertNotIn('$http_sec_websocket_protocol', value)
        self.assertNotRegex(value, r'\$http_(?:authorization|origin|cookie|accept|mcp|last_event|content_type)')

    def test_only_exact_agent_allows_upgrade_and_native_subprotocol(self):
        blocks = re.findall(r'^location ([^{]+) \{\n(.*?)^\}', current.locations(DOMAIN, CONNECTOR, PORT), re.M | re.S)
        for route, body in blocks[1:]:
            if route.strip() == '= /coding-tools/agent':
                self.assertIn('proxy_set_header Upgrade $http_upgrade;', body)
                self.assertIn('proxy_set_header Connection "upgrade";', body)
                self.assertNotIn('proxy_set_header Sec-WebSocket-Protocol', body)
            else:
                for name in ('Upgrade', 'Connection', 'Sec-WebSocket-Protocol'):
                    self.assertIn(f'proxy_set_header {name} "";', body)

    def test_forwarding_scrub_and_bounded_proxy_contract(self):
        value = current.locations(DOMAIN, CONNECTOR, PORT)
        lines = [f'proxy_set_header {name} "";' for name in
                 ('Forwarded', 'X-Forwarded-Host', 'X-Forwarded-For', 'X-Real-IP')]
        lines += ['proxy_set_header X-Forwarded-Proto https;', 'proxy_http_version 1.1;',
                  'proxy_buffering off;', 'proxy_request_buffering off;', 'proxy_cache off;',
                  'proxy_intercept_errors off;', 'proxy_redirect off;', 'client_max_body_size 64k;',
                  'proxy_connect_timeout 3s;', 'proxy_read_timeout 75s;', 'proxy_send_timeout 30s;',
                  'client_body_timeout 10s;']
        for line in lines:
            self.assertEqual(value.count(line), 4, line)

    def test_reviewed_source_pins_are_exact_and_returned_copy(self):
        self.assertEqual(current.SOURCE_HASHES, PINS)
        self.assertEqual(current.source_contract(), PINS)
        result = current.source_contract()
        result.clear()
        self.assertEqual(current.source_contract(), PINS)

    def test_byte_drift_and_missing_source_fail_for_every_pin(self):
        root = self.copied_source()
        for relative in PINS:
            path = root / relative
            original = path.read_bytes()
            for replacement in (original + b'\n', None):
                with self.subTest(relative=relative, missing=replacement is None):
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_bytes(replacement)
                    with self.assertRaises((OSError, ValueError)):
                        current.source_contract(root)
                    path.write_bytes(original)

    def test_source_symlink_directory_fifo_empty_and_oversize_fail(self):
        root = self.copied_source()
        relative = next(iter(PINS))
        path = root / relative
        original = path.read_bytes()
        for kind in ('symlink', 'directory', 'fifo', 'empty', 'oversize'):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == 'symlink':
                    path.symlink_to(ROOT / relative)
                elif kind == 'directory':
                    path.mkdir()
                elif kind == 'fifo':
                    os.mkfifo(path)
                else:
                    path.write_bytes(b'' if kind == 'empty' else b'x' * 262145)
                with self.assertRaises((OSError, ValueError)):
                    current.source_contract(root)
                path.rmdir() if kind == 'directory' else path.unlink()
                path.write_bytes(original)

    def test_each_exact_shape_count_guard_rejects_zero_or_duplicate(self):
        root = self.copied_source()
        fragments = [
            ('channel/transport.rs', 'pub fn managed_agent_channel_routes('),
            ('channel/transport.rs', 'let path = format!("{}/agent", control.identity().prefix());'),
            ('channel/transport.rs', 'Router::new().route(&path, get(upgrade)).with_state(state)'),
            ('channel/protocol.rs', 'pub const SUBPROTOCOL: &str = "coding-tools-agent.v1";'),
            ('config.rs', '"/.well-known/oauth-protected-resource{}"'),
            ('config.rs', '"/.well-known/oauth-authorization-server{}/oauth"'),
            ('config.rs', 'format!("{}/mcp/{}", self.prefix, self.connector)'),
        ]
        for suffix, fragment in fragments:
            relative = 'services/cloud-gateway/src/' + suffix
            path, original = root / relative, (ROOT / relative).read_text()
            for changed in (original.replace(fragment, 'REMOVED_SHAPE'), original + '\n' + fragment):
                with self.subTest(fragment=fragment, count=changed.count(fragment)):
                    path.write_text(changed)
                    # Isolate the secondary diagnostic; production pins are never changed.
                    with patch.dict(current.SOURCE_HASHES, {relative: hashlib.sha256(path.read_bytes()).hexdigest()}):
                        with self.assertRaisesRegex(ValueError, 'ambiguous'):
                            current.source_contract(root)
                    path.write_text(original)

    def test_render_private_three_file_manifest_and_false_acceptance_flags(self):
        old_umask = os.umask(0)
        try:
            result = current.render(self.output, DOMAIN, CONNECTOR, PORT)
        finally:
            os.umask(old_umask)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o700)
        self.assertEqual({p.name for p in self.output.iterdir()}, {current.INCLUDE, 'source-contract.json', 'REVIEW_ONLY.txt'})
        for path in self.output.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads((self.output / 'source-contract.json').read_text()), result)
        self.assertEqual(result['source_sha256'], PINS)
        self.assertEqual(result['renderer_sha256'], hashlib.sha256(SCRIPT.read_bytes()).hexdigest())
        self.assertEqual(result['include_sha256'], hashlib.sha256((self.output / current.INCLUDE).read_bytes()).hexdigest())
        self.assertEqual(result['compatibility_baseline'], '310ad16c8aa9cc8182c4b0f6a196184fcf34bc52')
        self.assertEqual((result['location_count'], result['agent_route'], result['subprotocol']),
                         (5, '/coding-tools/agent', 'coding-tools-agent.v1'))
        for key in ('applied', 'production_ready', 'real_host_tls_waf_tested', 'publish_approved',
                    'upstream_reachability_verified', 'old_ingress_two_hop_supported'):
            self.assertIs(result[key], False)
        self.assertIn('unsupported', (self.output / 'REVIEW_ONLY.txt').read_text())

    def test_existing_output_directory_file_and_symlinks_never_overwritten(self):
        target = self.root / 'sentinel'
        target.write_text('keep')
        for kind in ('directory', 'file', 'symlink', 'dangling'):
            with self.subTest(kind=kind):
                if kind == 'directory':
                    self.output.mkdir()
                elif kind == 'file':
                    self.output.write_text('keep')
                else:
                    self.output.symlink_to(target if kind == 'symlink' else self.root / 'absent')
                with self.assertRaises(FileExistsError):
                    current.render(self.output, DOMAIN, CONNECTOR, PORT)
                self.assertEqual(target.read_text(), 'keep')
                if kind == 'file':
                    self.assertEqual(self.output.read_text(), 'keep')
                self.output.rmdir() if kind == 'directory' else self.output.unlink()

    def test_file_creation_is_exclusive_even_after_directory_creation(self):
        real_open = os.open
        sentinel = self.root / 'sentinel'
        sentinel.write_text('keep')
        def collide(path, flags, mode=0o777):
            if Path(path) == self.output / current.INCLUDE:
                self.assertTrue(flags & os.O_EXCL and flags & os.O_NOFOLLOW)
                Path(path).symlink_to(sentinel)
            return real_open(path, flags, mode)
        with patch.object(current.os, 'open', side_effect=collide), self.assertRaises(FileExistsError):
            current.render(self.output, DOMAIN, CONNECTOR, PORT)
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_source_refusal_and_bad_inputs_precede_output_creation(self):
        with patch.object(current, 'source_contract', side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):
                current.render(self.output, DOMAIN, CONNECTOR, PORT)
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            current.render(self.output, DOMAIN, CONNECTOR, 443)
        self.assertFalse(self.output.exists())

    def test_partial_output_failure_is_retained_and_never_retried_as_success(self):
        real_open = os.open
        def fail_manifest(path, flags, mode=0o777):
            if Path(path) == self.output / 'source-contract.json':
                raise OSError('synthetic write failure')
            return real_open(path, flags, mode)
        with patch.object(current.os, 'open', side_effect=fail_manifest), self.assertRaises(OSError):
            current.render(self.output, DOMAIN, CONNECTOR, PORT)
        self.assertEqual({p.name for p in self.output.iterdir()}, {current.INCLUDE})
        before = (self.output / current.INCLUDE).read_bytes()
        with self.assertRaises(FileExistsError):
            current.render(self.output, DOMAIN, CONNECTOR, PORT)
        self.assertEqual((self.output / current.INCLUDE).read_bytes(), before)

    def test_offline_render_invokes_no_process_or_network(self):
        with patch.object(subprocess, 'run') as run, patch.object(subprocess, 'Popen') as popen, \
             patch.object(socket, 'socket') as connection:
            current.render(self.output, DOMAIN, CONNECTOR, PORT)
        run.assert_not_called()
        popen.assert_not_called()
        connection.assert_not_called()

    def test_historical_renderer_and_runtime_sources_stay_byte_unchanged(self):
        pins = {'deploy/cloud-gateway/render.py': 'acea9a34118a2ed8a68e5176f64be286aadbc4f018daa4c4fc3bb6b07288b199',
                'tests/cloud-gateway-deployment/run_container_topology.py': 'd194cb411121c9ab9a03fda7234b5ec1dd444fc76ce3e3aa0d79ea2c38378d59'}
        for relative, expected in pins.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected, relative)

    def test_cli_explicit_output_success_and_repeat_refusal(self):
        command = [sys.executable, str(SCRIPT), '--domain', DOMAIN, '--connector-id', CONNECTOR, '--output', str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['rendered'], True)
        before = {p.name: p.read_bytes() for p in self.output.iterdir()}
        repeat = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(repeat.returncode, 0)
        self.assertEqual({p.name: p.read_bytes() for p in self.output.iterdir()}, before)

    def test_cli_drift_is_sanitized_and_writes_nothing(self):
        root = self.copied_source()
        script = root / 'deploy/cloud-gateway/current_nginx_include.py'
        script.parent.mkdir(parents=True)
        shutil.copyfile(SCRIPT, script)
        shutil.copyfile(SCRIPT.with_name('render.py'), script.with_name('render.py'))
        (root / next(iter(PINS))).write_text('synthetic-private-drift')
        result = subprocess.run([sys.executable, str(script), '--connector-id', CONNECTOR, '--output', str(self.output)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('review render rejected', result.stderr)
        self.assertNotIn('synthetic-private-drift', result.stderr + result.stdout)
        self.assertFalse(self.output.exists())

    def test_both_private_wrappers_refuse_self_proxy_before_effects(self):
        with self.assertRaisesRegex(RuntimeError, 'distinct_private'):
            checks.private_config(self.root, PORT, PORT)
        with patch.object(current, 'render') as render:
            with self.assertRaisesRegex(RuntimeError, 'distinct_private'):
                runtime.install_private_include(None, PORT, PORT)
            render.assert_not_called()
        for port in (True, '8080', 443, 65536):
            with self.subTest(port=port), self.assertRaises(RuntimeError):
                checks.private_config(self.root, port, PORT)

    def test_private_config_includes_emitted_file_and_existing_site_sentinels(self):
        value = checks.private_config(self.root, 18080, PORT, self.output / current.INCLUDE)
        self.assertIn(f'include {self.output / current.INCLUDE};', value)
        self.assertIn('listen 127.0.0.1:18080;', value)
        for sentinel in ('existing-site', 'existing-prefix', 'existing-regex'):
            self.assertIn(sentinel, value)
        self.assertNotIn('proxy_pass', value)
        with self.assertRaises(RuntimeError):
            checks.private_config(Path('/tmp/unsafe;return'), 18080, PORT)

    def test_ordered_duplicate_empty_headers_and_raw_uri_really_go_on_wire(self):
        captured, failures = [], []
        pairs = [('Host', DOMAIN), ('Origin', ''), ('Origin', 'https://' + DOMAIN),
                 ('Cookie', ''), ('Authorization', ''), ('Mcp-Method', 'tools/list'), ('Mcp-Method', ''),
                 ('Sec-WebSocket-Protocol', ''), ('Sec-WebSocket-Protocol', current.SUBPROTOCOL)]
        body, path = b'{"synthetic":true}', '/coding-tools/%61gent?x=%2F'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            listener.settimeout(5)
            def receive():
                try:
                    with listener.accept()[0] as peer:
                        peer.settimeout(5)
                        data = b''
                        while b'\r\n\r\n' not in data:
                            chunk = peer.recv(4096)
                            if not chunk or len(data) > 65536:
                                raise AssertionError('bounded wire header')
                            data += chunk
                        head, received = data.split(b'\r\n\r\n', 1)
                        while len(received) < len(body):
                            chunk = peer.recv(4096)
                            if not chunk:
                                raise AssertionError('incomplete wire body')
                            received += chunk
                        captured.append((head, received))
                        peer.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')
                except Exception as error:
                    failures.append(error)
            thread = threading.Thread(target=receive)
            thread.start()
            try:
                response = runtime.raw_request(listener.getsockname()[1], path, pairs, body, 'POST')
            finally:
                thread.join(6)
            self.assertFalse(thread.is_alive(), 'owned test receiver must stop')
        self.assertEqual(failures, [])
        self.assertIs(runtime.raw_request, checks.raw_request)
        self.assertEqual((response[0], response[2]), (200, b'ok'))
        lines = [f'POST {path} HTTP/1.1', *[f'{k}: {v}' for k, v in pairs], f'Content-Length: {len(body)}']
        self.assertEqual(captured, [('\r\n'.join(lines).encode(), body)])

    def test_hosted_runtime_denial_precedes_all_effects(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(container_fixture.subprocess, 'run') as command, \
             patch.object(container_fixture.tempfile, 'mkdtemp') as directory, patch.object(socket, 'socket') as connection, \
             patch.object(runtime, 'install_private_include') as install:
            with self.assertRaisesRegex(container_fixture.FixtureFailure, 'hosted_disposable_ci_only'):
                runtime.runtime_checks(Path('/does-not-exist'), {})
        for effect in (command, directory, connection, install):
            effect.assert_not_called()

    def test_invalid_raw_path_rejected_before_socket_creation(self):
        for path in ('http://foreign.invalid/', '/bad path', '/bad\r\nX: injected'):
            with self.subTest(path=path), patch.object(socket, 'socket') as connection:
                with self.assertRaisesRegex(RuntimeError, 'fixed_raw_path'):
                    checks.raw_request(18080, path, [])
                connection.assert_not_called()

    def test_successful_cleanup_preserves_original_failure_stage(self):
        fixture = SimpleNamespace(close=Mock(), prepare=Mock(side_effect=RuntimeError('prepare failed')))
        with patch.object(runtime, 'Fixture', return_value=fixture), \
             patch.object(runtime, 'install_private_include', return_value={}), patch.object(runtime, 'STAGE', 'setup'):
            with self.assertRaisesRegex(RuntimeError, 'prepare failed'):
                runtime.runtime_checks(Path('/not-executed'), {})
            self.assertEqual(runtime.STAGE, 'prepare_current_runtime')
        fixture.close.assert_called_once_with()

    def test_runtime_cleanup_failure_is_retained_as_failure(self):
        fixture = SimpleNamespace(close=Mock(side_effect=RuntimeError('owned cleanup failed')))
        with patch.object(runtime, 'Fixture', return_value=fixture), \
             patch.object(runtime, 'install_private_include', side_effect=RuntimeError('setup failed')), \
             patch.object(runtime, 'STAGE', 'setup'):
            with self.assertRaisesRegex(RuntimeError, 'owned cleanup failed'):
                runtime.runtime_checks(Path('/not-executed'), {})
            self.assertEqual(runtime.STAGE, 'owned_cleanup')
        fixture.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
