"""G1 deploy kit and G3 ingress limit contracts. Offline; optional real-Nginx proof via CTM_TEST_NGINX."""
import ast
import hashlib
import contextlib
import http.client
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / 'deploy/cloud-gateway/kit'
spec = importlib.util.spec_from_file_location('deploy_kit_under_test', KIT / 'kit.py')
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)
topology = kit.topology
DOMAIN = 'gateway.example.invalid'
CONNECTOR = '11111111-1111-4111-8111-111111111111'
IMAGES = dict(gateway='sha256:' + 'a' * 64, ingress='nginx@sha256:' + 'b' * 64, postgres='postgres@sha256:' + 'c' * 64)
ME = f'{os.getuid()}:{os.getgid()}'
DUMMY_CONFIG = dict(origin='https://' + DOMAIN, prefix='/coding-tools', connector=CONNECTOR,
                    owner_subject='22222222-2222-4222-8222-222222222222', client_id='dummy-client',
                    redirect_uri='https://client.example.invalid/callback', client_authentication='public',
                    bind='127.0.0.1:28880')
DUMMY_RUNTIME = dict(database_url='postgresql://ctm_app:dummy@postgres:5432/dummy', identity_key='A' * 43)
LEGACY_GRANTS = ('REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO ctm_app; '
                 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO ctm_app; '
                 'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO ctm_app;')


def expand(template, values):
    """Minimal psql variable expansion for :'name' and :name, enough for the shipped template."""
    text = re.sub(r":'([a-z_]+)'", lambda m: "'" + values[m.group(1)] + "'", template)
    return re.sub(r'(?<![:\w]):([a-z_]+)\b', lambda m: values[m.group(1)], text)


def sql_statements(text):
    lines = [line for line in text.splitlines() if not line.startswith('--')]
    return [part.strip() for part in ' '.join(lines).split(';') if part.strip()]


def legacy_bootstrap(app, migration):
    return ("CREATE ROLE ctm_app LOGIN PASSWORD '" + app + "' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
            "CREATE ROLE ctm_migration LOGIN PASSWORD '" + migration + "' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
            'CREATE DATABASE coding_tools_identity_test OWNER ctm_migration;')


def entropy(token):
    counts = {c: token.count(c) for c in set(token)}
    return -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())


class KitFiles(unittest.TestCase):
    def test_kit_files_carry_placeholders_and_no_secrets(self):
        allowed = {'/coding-tools', 'public', '127.0.0.1:28880'}
        for name in ('config.example.json', 'runtime.example.json'):
            value = json.loads((KIT / name).read_text())
            for item in value.values():
                self.assertTrue(item in allowed or re.fullmatch(r'<[A-Z0-9_]+>', item), (name, item))
        self.assertEqual(set(json.loads((KIT / 'config.example.json').read_text())), kit.CONFIG_KEYS)
        self.assertEqual(set(json.loads((KIT / 'runtime.example.json').read_text())), kit.RUNTIME_KEYS)
        for path in sorted(p for p in KIT.iterdir() if p.is_file()):
            text = path.read_text()
            self.assertNotRegex(text, r'(?i)(postgres(ql)?://[^<\s]+:[^<\s@]+@)', path.name)
            self.assertNotRegex(text, r"(?i)\bPASSWORD\s+'", path.name)
            self.assertNotRegex(text, r'-----BEGIN [A-Z ]*PRIVATE KEY-----', path.name)
            for token in re.findall(r'[A-Za-z0-9+/_-]{24,}', text):
                self.assertNotRegex(token, r'[0-9a-fA-F]{32,}', (path.name, 'hex_secret_like_token'))
                if re.fullmatch(r'/?[A-Za-z]+(?:[_/-][A-Za-z]+)*', token):
                    continue  # identifiers, paths and prose, not key material
                self.assertLess(entropy(token), 4.0, (path.name, 'high_entropy_token'))

    def test_kit_never_drives_engines_remote_shells_services_or_reloads(self):
        source = (KIT / 'kit.py').read_text()
        for pattern in (r'(?i)\bdocker\b', r'(?i)\bpodman\b', r'(?i)\bssh\b', r'(?i)systemctl', r'(?i)nginx\s+-s',
                        r'(?i)\bservice\s+nginx\b'):
            self.assertNotRegex(source, pattern)
        tree = ast.parse(source)
        imported = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names} | {node.module.split('.')[0] for node in ast.walk(tree)
                                                if isinstance(node, ast.ImportFrom) and node.module}
        self.assertTrue(imported.isdisjoint({'subprocess', 'pty', 'socket', 'shlex', 'asyncio', 'multiprocessing',
                                             'urllib', 'http', 'paramiko', 'ctypes'}), imported)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'os':
                self.assertNotRegex(node.attr, r'^(system|popen|exec\w*|spawn\w*|fork\w*|posix_spawn\w*|kill\w*)$')
        # The renderer it reuses is equally process- and network-free.
        with patch.object(subprocess, 'run') as run, patch.object(subprocess, 'Popen') as popen, \
             patch.object(socket, 'socket') as connection, tempfile.TemporaryDirectory() as tmp:
            kit.render('/srv/ctm-private', Path(tmp) / 'out', DOMAIN, CONNECTOR, 28880, IMAGES, ['172.18.0.1/32'])
        run.assert_not_called(); popen.assert_not_called(); connection.assert_not_called()

    def test_plan_is_ordered_and_never_applied(self):
        value = kit.plan()
        self.assertFalse(value['applied'])
        self.assertEqual([step['id'] for step in value['steps']][0], 'g4_subdomain')
        self.assertIn('check', [step['id'] for step in value['steps']])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(kit.main(['plan']), 0)
        self.assertFalse(json.loads(out.getvalue())['applied'])


class PrepareAndCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'private'

    def prepared(self):
        kit.prepare_dirs(self.root, ME, ME)
        gateway = self.root / 'gateway-private'
        for name, value in (('config.json', DUMMY_CONFIG), ('runtime.json', DUMMY_RUNTIME)):
            (gateway / name).write_text(json.dumps(value))
        for path, text in ((self.root / 'ingress-private/nginx.conf', topology.ingress_config(DOMAIN, CONNECTOR)),
                           (self.root / 'postgres-private/password', 'dummy-password-0000\n')):
            path.write_text(text); path.chmod(0o400)
        return gateway

    def test_dry_run_lists_chmod_and_chown_and_touches_nothing(self):
        result = kit.prepare_dirs(self.root, dry_run=True)
        self.assertFalse(result['applied']); self.assertFalse(self.root.exists())
        ops = [action['op'] for action in result['actions']]
        self.assertIn('chmod', ops); self.assertIn('chown', ops); self.assertIn('write_example', ops)
        owners = {Path(a['path']).name: a['owner'] for a in result['actions'] if a['op'] == 'chown'}
        self.assertEqual(owners['postgres-private'], '999:999'); self.assertEqual(owners['gateway-private'], '65532:65532')
        self.assertEqual(owners['ingress-private'], '65532:65532')
        self.assertTrue(all(a['mode'] in ('0700', '0600') for a in result['actions'] if a['op'] == 'chmod'))

    def test_prepare_refuses_relative_existing_or_bad_owner(self):
        for root, code in (('relative/private', 'root_must_be_absolute'), (self.tmp.name, 'root_must_not_exist'),
                           (str(Path(self.tmp.name) / 'missing/private'), 'root_parent_must_be_real_directory')):
            with self.assertRaises(kit.KitError) as error:
                kit.prepare_dirs(root, ME, ME, dry_run=True)
            self.assertEqual(error.exception.code, code)
        with self.assertRaises(kit.KitError):
            kit.prepare_dirs(self.root, 'root', ME, dry_run=True)

    def test_prepare_then_check_reports_unfilled_placeholders_only_as_codes(self):
        kit.prepare_dirs(self.root, ME, ME)
        self.assertEqual(oct((self.root / 'gateway-private/runtime.json').stat().st_mode & 0o777), '0o600')
        failures = kit.check(self.root, ME, ME)
        self.assertIn('config_placeholder_present', failures)
        self.assertIn('runtime_value_missing_or_placeholder', failures)
        self.assertIn('ingress-private/nginx.conf:missing', failures)
        self.assertFalse(any('<' in item or 'example' in item for item in failures))

    def test_check_positive(self):
        self.prepared()
        self.assertEqual(kit.check(self.root, ME, ME), [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(kit.main(['check', '--root', str(self.root), '--gateway-owner', ME, '--postgres-owner', ME]), 0)
        self.assertEqual(json.loads(out.getvalue()), {'ok': True, 'failures': []})

    def test_check_negative_group_readable(self):
        self.prepared().joinpath('runtime.json').chmod(0o640)
        self.assertIn('gateway-private/runtime.json:mode_not_0400_or_0600', kit.check(self.root, ME, ME))

    def test_check_negative_symlink(self):
        target = Path(self.tmp.name) / 'elsewhere.conf'; target.write_text('x'); target.chmod(0o600)
        link = self.root / 'ingress-private/nginx.conf'
        self.prepared(); link.unlink(); link.symlink_to(target)
        failures = kit.check(self.root, ME, ME)
        self.assertIn('ingress-private/nginx.conf:symlink', failures); self.assertIn('symlink_present', failures)

    def test_check_negative_extra_runtime_key(self):
        gateway = self.prepared()
        (gateway / 'runtime.json').write_text(json.dumps(dict(DUMMY_RUNTIME, password='dummy')))
        self.assertIn('runtime_keys_must_be_database_url_identity_key_only', kit.check(self.root, ME, ME))

    def test_check_negative_non_loopback_bind(self):
        gateway = self.prepared()
        for bind in ('0.0.0.0:28880', '172.18.0.2:28880', '127.0.0.1:28881', '[::]:28880'):
            (gateway / 'config.json').write_text(json.dumps(dict(DUMMY_CONFIG, bind=bind)))
            self.assertIn('config_bind_not_loopback_28880', kit.check(self.root, ME, ME), bind)

    def test_check_negative_wrong_owner(self):
        self.prepared()
        failures = kit.check(self.root, kit.GATEWAY_OWNER, ME) if ME != kit.GATEWAY_OWNER else kit.check(self.root, '1:1', ME)
        self.assertIn('gateway-private_owner_mismatch', failures)
        self.assertIn('gateway-private/runtime.json:owner_mismatch', failures)
        self.assertIn('ingress-private/nginx.conf:owner_mismatch', failures)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(kit.main(['check', '--root', str(self.root)]), 1 if ME != kit.GATEWAY_OWNER else 0)

    def test_check_negative_extras_and_hardlinks(self):
        gateway = self.prepared()
        (gateway / 'notes.txt').write_text('x')
        os.link(gateway / 'config.json', Path(self.tmp.name) / 'copy.json')
        failures = kit.check(self.root, ME, ME)
        self.assertIn('gateway-private_unexpected_entry', failures)
        self.assertIn('gateway-private/config.json:hardlinked', failures)


class TrustedProxies(unittest.TestCase):
    def test_accepts_explicit_private_or_loopback_cidrs(self):
        self.assertEqual(topology.trusted_proxy_cidrs([]), ())
        value = ['172.18.0.1/32', '10.0.0.0/8', '192.168.1.0/24', '127.0.0.1/32', 'fd00::/8', '::1/128', 'FD12:3456::/32']
        self.assertEqual(topology.trusted_proxy_cidrs(value)[-1], 'fd12:3456::/32')

    def test_rejects_ambiguous_broad_public_or_excess_cidrs(self):
        bad = ['172.18.0.1', '172.18.0.1/16', '0.0.0.0/0', '::/0', '8.8.8.0/24', '2001:4860::/32', '10.0.0.0/08',
               '010.0.0.0/8', '224.0.0.0/4', '0.0.0.0/32', 'localhost/32', ' 10.0.0.0/8', '10.0.0.0/8 ', '10.0.0.0/33',
               '10.0.0.0/8;', 'all', '', '172.18.0.1/32\nset_real_ip_from 0.0.0.0/0']
        for value in bad:
            with self.assertRaises(ValueError, msg=repr(value)):
                topology.trusted_proxy_cidrs([value])
        with self.assertRaises(ValueError):topology.trusted_proxy_cidrs(['10.0.0.0/8', '10.0.0.0/8'])
        with self.assertRaises(ValueError):topology.trusted_proxy_cidrs([None])
        with self.assertRaises(ValueError):topology.trusted_proxy_cidrs([f'10.0.{i}.0/24' for i in range(9)])
        with self.assertRaises(kit.KitError) as error:kit.trusted_proxies(['0.0.0.0/0'])
        self.assertEqual(error.exception.code, 'invalid_trusted_proxy')

    def test_cli_trusted_proxy_is_repeatable_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = ['render', '--private-root', '/srv/ctm-private', '--domain', DOMAIN, '--connector', CONNECTOR,
                    '--port', '28880', '--gateway-image', IMAGES['gateway'], '--ingress-image', IMAGES['ingress'],
                    '--postgres-image', IMAGES['postgres']]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(kit.main(base + ['--output', tmp + '/bad', '--trusted-proxy', '0.0.0.0/0']), 2)
            self.assertEqual(json.loads(out.getvalue())['error'], 'invalid_trusted_proxy')
            self.assertFalse(Path(tmp, 'bad').exists())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(kit.main(base + ['--output', tmp + '/ok', '--trusted-proxy', '172.18.0.1/32',
                                                  '--trusted-proxy', 'fd00::/8']), 0)
            text = Path(tmp, 'ok/nginx.runtime.conf').read_text()
            self.assertEqual(re.findall(r'set_real_ip_from (\S+);', text), ['172.18.0.1/32', 'fd00::/8'])


class RenderedIngress(unittest.TestCase):
    def config(self, trusted=()):return topology.ingress_config(DOMAIN, CONNECTOR, trusted_proxies=trusted)

    def test_default_trusts_nothing_and_keys_on_connection_address(self):
        text = self.config()
        for directive in ('set_real_ip_from', 'real_ip_header', 'real_ip_recursive', '$http_x_real_ip',
                          '$http_x_forwarded_for', '$proxy_add_x_forwarded_for', '$realip_remote_addr'):
            self.assertNotIn(directive, text)
        self.assertNotRegex(topology.RATE_LIMITS + topology.SERVER_LIMITS, r'127\.0\.0\.1')
        keys = re.findall(r'map \$uri \$(ctm_[a-z]+_key) \{\ndefault "";\n((?:[^}]*\n)*?)\}', text)
        self.assertEqual([key for key, _ in keys], ['ctm_auth_key', 'ctm_mcp_key', 'ctm_agent_key'])
        for _, body in keys:
            self.assertEqual(set(re.findall(r' (\$\w+);', body)), {'$binary_remote_addr'})

    def test_trusted_sources_only_feed_real_ip_and_gateway_header_stays_blank(self):
        text = self.config(('172.18.0.1/32',))
        self.assertEqual(text.count('set_real_ip_from '), 1)
        self.assertIn('set_real_ip_from 172.18.0.1/32;\nreal_ip_header X-Real-IP;\nreal_ip_recursive off;\n', text)
        self.assertLess(text.index('real_ip_recursive off;'), text.index('server {'))
        self.assertEqual(text.count('proxy_set_header X-Real-IP "";'), 4)
        self.assertNotIn('X-Real-IP $', text)
        self.assertEqual(text.replace('set_real_ip_from 172.18.0.1/32;\nreal_ip_header X-Real-IP;\nreal_ip_recursive off;\n', ''),
                         self.config())

    def test_limits_shape_and_placement(self):
        text = self.config()
        for line in ('limit_req_zone $ctm_auth_key zone=ctm_auth:1m rate=10r/m;',
                     'limit_req_zone $ctm_mcp_key zone=ctm_mcp:2m rate=10r/s;',
                     'limit_conn_zone $ctm_agent_key zone=ctm_agent:1m;', 'limit_req_status 429;', 'limit_conn_status 429;',
                     'limit_req zone=ctm_auth burst=5 nodelay;', 'limit_req zone=ctm_mcp burst=40 nodelay;',
                     'limit_conn ctm_agent 4;'):
            self.assertEqual(text.count(line), 1, line)
        self.assertIn('~^/coding-tools/oauth/ $binary_remote_addr;', text)
        self.assertIn('~^/\\.well-known/oauth- $binary_remote_addr;', text)
        self.assertIn('~^/coding-tools/mcp/ $binary_remote_addr;', text)
        self.assertIn('\n/coding-tools/agent $binary_remote_addr;', text)
        host = text.index('if ($http_host != "' + DOMAIN + '") { return 421; }\n')
        self.assertLess(host, text.index('limit_req zone=ctm_auth'))
        self.assertLess(text.index('limit_conn ctm_agent 4;'), text.index('location = / {'))
        # Locations are the reviewed include, byte-identical; no per-location limit overrides.
        locations = topology.current.locations(DOMAIN, CONNECTOR, 28880)
        self.assertIn(locations, text); self.assertNotIn('limit_', locations)
        self.assertEqual(text.count('access_log off;'), 1 + locations.count('access_log off;'))
        self.assertNotRegex(text, r'access_log (?!off)')
        legacy = topology.ingress_config(DOMAIN, CONNECTOR, rate_limits=False)
        self.assertNotIn('limit_', legacy)
        self.assertEqual(text.replace(topology.RATE_LIMITS, '').replace(topology.SERVER_LIMITS, ''), legacy)

    def test_render_outputs_manifest_and_baota_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = kit.render('/srv/ctm-private', Path(tmp) / 'plain', DOMAIN, CONNECTOR, 28880, IMAGES)
            trusted = kit.render('/srv/ctm-private', Path(tmp) / 'trusted', DOMAIN, CONNECTOR, 28880, IMAGES,
                                 ['172.18.0.1/32'])
            for name, manifest in (('plain', plain), ('trusted', trusted)):
                folder = Path(tmp) / name
                self.assertEqual(oct(folder.stat().st_mode & 0o777), '0o700')
                self.assertEqual(sorted(p.name for p in folder.iterdir()),
                                 ['baota-locations.conf', 'compose.runtime.json', 'manifest.json', 'nginx.runtime.conf'])
                self.assertFalse(manifest['applied'])
                for file, digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256((folder / file).read_bytes()).hexdigest(), digest)
                    self.assertEqual(oct((folder / file).stat().st_mode & 0o777), '0o600')
            self.assertEqual((Path(tmp) / 'plain/baota-locations.conf').read_text(),
                             topology.current.locations(DOMAIN, CONNECTOR, 28880))
            outer = (Path(tmp) / 'trusted/baota-locations.conf').read_text()
            self.assertEqual(outer.count(kit.REAL_IP_FORWARD), 4); self.assertNotIn(kit.REAL_IP_BLANK, outer)
            self.assertEqual(trusted['trusted_proxies'], ['172.18.0.1/32']); self.assertEqual(plain['trusted_proxies'], [])
            compose = json.loads((Path(tmp) / 'plain/compose.runtime.json').read_text())
            self.assertEqual(compose['services']['namespace']['ports'][0]['host_ip'], '127.0.0.1')
            with self.assertRaises(kit.KitError) as error:
                kit.render('/srv/ctm-private', Path(tmp) / 'plain', DOMAIN, CONNECTOR, 28880, IMAGES)
            self.assertEqual(error.exception.code, 'output_must_not_exist')


class SqlTemplate(unittest.TestCase):
    VALUES = dict(app_password='dummy_app_password_0001', migration_password='dummy_migration_password_02',
                  database='coding_tools_identity_test')

    def test_template_has_two_phases_and_no_values(self):
        template = kit.SQL_TEMPLATE.read_text()
        self.assertEqual(re.findall(r'^-- @phase (\w+)', template, re.M), ['bootstrap', 'grants'])
        self.assertNotRegex(template, r"PASSWORD '")
        self.assertIn(":'app_password'", kit.sql_phase('bootstrap'))
        self.assertIn('\\gexec', kit.sql_phase('grants'))
        with self.assertRaises(kit.KitError):kit.sql_phase('other')

    def test_preamble_rejects_non_fixed_shape_values(self):
        self.assertEqual(kit.psql_preamble(self.VALUES).splitlines()[0], '\\set app_password dummy_app_password_0001')
        for key, value in (('app_password', "x'; DROP ROLE postgres; --xxxxxxx"), ('app_password', 'short'),
                           ('migration_password', 'with space in it 0000'), ('database', 'Bad-Name'),
                           ('database', 'x;\\! id')):
            with self.assertRaises(kit.KitError):kit.psql_preamble(dict(self.VALUES, **{key: value}))
        with self.assertRaises(kit.KitError):kit.psql_preamble(dict(self.VALUES, extra='x'))

    def test_expansion_matches_previous_fixture_statements(self):
        bootstrap = expand(kit.sql_phase('bootstrap'), self.VALUES)
        self.assertEqual(sql_statements(bootstrap),
                         sql_statements(legacy_bootstrap(self.VALUES['app_password'], self.VALUES['migration_password'])))
        tables = ['ctm_devices', 'ctm_owner']
        grants = kit.sql_phase('grants')
        static, generator = [line for line in grants.splitlines() if not line.startswith('--')]
        self.assertEqual(static, LEGACY_GRANTS)
        self.assertRegex(generator, r"tablename ~ '\^ctm_\[a-z0-9_\]\+\$' ORDER BY tablename \\gexec$")
        generated = ['GRANT INSERT,UPDATE,DELETE ON public."' + name + '" TO ctm_app' for name in tables]
        self.assertEqual(generated, sql_statements(''.join('GRANT INSERT,UPDATE,DELETE ON public."' + n + '" TO ctm_app;'
                                                           for n in tables)))

    def test_fixture_reads_template_and_probes_denials(self):
        source = (ROOT / 'tests/cloud-gateway-deployment/container_fixture.py').read_text()
        self.assertNotIn('CREATE ROLE ctm_app', source); self.assertNotIn("PASSWORD '", source)
        self.assertIn("kit.sql_phase('bootstrap')", source); self.assertIn("kit.sql_phase('grants')", source)
        probes = re.findall(r"\('(runtime_cannot_[a-z_]+)',", source)
        self.assertEqual(probes, ['runtime_cannot_create_table', 'runtime_cannot_update_migration_ledger',
                                  'runtime_cannot_create_role'])
        self.assertIn("'runtime_cannot_change_schema_or_migration_ledger'", source)
        self.assertIn("'least_privilege_database_role'", source)

    def test_container_acceptance_has_native_limit_and_real_ip_stages(self):
        source = (ROOT / 'tests/cloud-gateway-deployment/run_container_topology.py').read_text()
        order = [source.index(f"STAGE='{name}'") for name in ('oauth_mcp', 'rate_limits', 'trusted_real_ip', 'shutdown')]
        self.assertEqual(order, sorted(order))
        for case in ('token_429_after_burst_forged_real_ip_rotation_ignored', 'untrusted_forged_real_ip_shares_connection_bucket',
                     'mcp_normal_rate_never_429', 'agent_sequential_upgrades_never_429', 'agent_limit_conn_4_per_ip',
                     'edge_bridge_gateway_inside_trusted_ci_ranges', 'trusted_real_ip_buckets_per_client'):
            self.assertIn(case, source)


NGINX = os.environ.get('CTM_TEST_NGINX')  # opt-in only; hosted CI proves the shipped image natively


class _Upstream(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        data = b''
        while b'\r\n\r\n' not in data:
            chunk = self.request.recv(4096)
            if not chunk:return
            data += chunk
        if b'\r\nupgrade: websocket' in data.lower():
            self.request.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n')
            with contextlib.suppress(OSError):
                while self.request.recv(4096):pass
            return
        length = re.search(rb'(?i)\r\ncontent-length: *([0-9]+)', data)
        body = data.split(b'\r\n\r\n', 1)[1]
        while length and len(body) < int(length.group(1)):
            body += self.request.recv(4096)
        self.request.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]


@unittest.skipUnless(NGINX and os.access(NGINX, os.X_OK), 'set CTM_TEST_NGINX to an nginx binary with realip')
class RealNginx(unittest.TestCase):
    """Offline functional proof against a stub upstream; the container job proves the shipped image."""

    def start(self, trusted):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        upstream = _Upstream(('127.0.0.1', 0), _Handler)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        self.addCleanup(upstream.server_close); self.addCleanup(upstream.shutdown)
        self.port = free_port(); tmp = self.tmp.name
        text = topology.ingress_config(DOMAIN, CONNECTOR, trusted_proxies=trusted)
        text = (text.replace('listen 8080;', f'listen 127.0.0.1:{self.port};')
                .replace('proxy_pass http://127.0.0.1:28880;', f'proxy_pass http://127.0.0.1:{upstream.server_address[1]};')
                .replace('/tmp/', tmp + '/'))
        Path(tmp, 'nginx.conf').write_text(text)
        command = [NGINX, '-p', tmp, '-e', '/dev/null', '-c', tmp + '/nginx.conf']
        checked = subprocess.run(command + ['-t'], capture_output=True, text=True, timeout=20)
        if checked.returncode:self.fail('nginx_config_test_failed: ' + (checked.stderr or checked.stdout)[-2000:])
        process = subprocess.Popen(command + ['-g', 'daemon off;'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(process.wait, 10); self.addCleanup(process.terminate)
        for _ in range(100):
            with contextlib.suppress(OSError):
                socket.create_connection(('127.0.0.1', self.port), timeout=1).close(); return
            time.sleep(.05)
        self.fail('nginx_not_listening')

    def request(self, method, path, real_ip=None):
        headers = {'Host': DOMAIN, 'Content-Type': 'application/x-www-form-urlencoded'}
        if real_ip:headers['X-Real-IP'] = real_ip
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, body='grant_type=invalid' if method == 'POST' else None, headers=headers)
            response = connection.getresponse(); response.read(); return response.status
        finally:connection.close()

    def burst(self, real_ip):
        statuses = []
        for index in range(10):
            statuses.append(self.request('POST', '/coding-tools/oauth/token', real_ip(index)))
            if statuses[-1] == 429:break
        self.assertEqual(statuses, [200] * 6 + [429])

    def upgrade(self):
        connection = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        connection.sendall((f'GET /coding-tools/agent HTTP/1.1\r\nHost: {DOMAIN}\r\nUpgrade: websocket\r\n'
                            'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n'
                            'Sec-WebSocket-Protocol: coding-tools-agent.v1\r\n\r\n').encode())
        status = int(connection.recv(4096).split(b' ', 2)[1])
        return status, connection

    def test_untrusted_forged_real_ip_cannot_split_buckets(self):
        self.start(())
        self.burst(lambda index: f'203.0.113.{index + 1}')
        self.assertEqual(self.request('POST', '/coding-tools/oauth/token', '198.51.100.77'), 429)
        self.assertEqual(self.request('GET', '/.well-known/oauth-authorization-server/coding-tools/oauth'), 429)
        self.assertEqual(self.request('GET', '/coding-tools/health/ready'), 200)
        for _ in range(20):
            self.assertEqual(self.request('POST', '/coding-tools/mcp/' + CONNECTOR), 200); time.sleep(.12)
        self.assertEqual(self.request('GET', '/coding-tools/oauth/token'), 429)

    def test_agent_limit_conn_four_per_address(self):
        self.start(())
        held = []
        try:
            for _ in range(4):
                status, connection = self.upgrade(); held.append(connection); self.assertEqual(status, 101)
            status, connection = self.upgrade(); connection.close()
            self.assertEqual(status, 429)
        finally:
            for connection in held:connection.close()
        time.sleep(.3)
        status, connection = self.upgrade(); connection.close(); self.assertEqual(status, 101)

    def test_mcp_burst_exhaustion_is_429(self):
        self.start(())
        statuses = [self.request('POST', '/coding-tools/mcp/' + CONNECTOR) for _ in range(60)]
        self.assertIn(429, statuses); self.assertNotIn(429, statuses[:41])

    def test_trusted_source_gets_per_real_ip_buckets(self):
        self.start(('127.0.0.1/32',))
        self.burst(lambda index: '198.51.100.1')
        self.assertEqual(self.request('POST', '/coding-tools/oauth/token', '198.51.100.2'), 200)
        self.assertEqual(self.request('POST', '/coding-tools/oauth/token', None), 200)
        self.assertEqual(self.request('POST', '/coding-tools/oauth/token', '198.51.100.1'), 429)

    def test_trust_of_other_source_keeps_connection_key(self):
        self.start(('10.0.0.0/8',))
        self.burst(lambda index: f'198.51.100.{index + 1}')
        self.assertEqual(self.request('POST', '/coding-tools/oauth/token', '198.51.100.200'), 429)


if __name__ == '__main__':
    unittest.main()
