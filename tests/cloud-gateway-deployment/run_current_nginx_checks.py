#!/usr/bin/env python3
"""Actual private Nginx mechanics and Compose2.27 config; echo is not gateway proof."""
import argparse
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('current_include', ROOT / 'deploy/cloud-gateway/current_nginx_include.py')
current = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(current)
_spec = importlib.util.spec_from_file_location('current_topology', ROOT / 'deploy/cloud-gateway/runtime_topology.py')
topology = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(topology)
DOMAIN = 'gateway.example.invalid'
CONNECTOR = '00000000-0000-0000-0000-000000000001'


def require(value, label):
    if not value:
        raise RuntimeError(label)


def source_identity():
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_NO_REPLACE_OBJECTS='1')
    def read(ref):
        return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', 'rev-parse', ref],
                                       cwd=ROOT, env=env, text=True, timeout=10).strip()
    sha, tree = read('HEAD'), read('HEAD^{tree}')
    require(re.fullmatch('[0-9a-f]{40}', sha) and re.fullmatch('[0-9a-f]{40}', tree), 'source_identity')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        require(sha == os.environ.get('GITHUB_SHA'), 'exact_ci_source')
    return dict(source_sha=sha, source_tree=tree, github_run_id=os.environ.get('GITHUB_RUN_ID'),
                github_run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'))


def raw_request(port, path, pairs, body=b'', method='GET'):
    """Ordered wire headers: preserve duplicate and empty lines; never use a dict."""
    require(path.startswith('/') and not any(c in path for c in '\r\n '), 'fixed_raw_path')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for key, value in pairs:
            connection.putheader(key, value)
        if body:
            connection.putheader('Content-Length', str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        data = b'' if response.status == 101 else response.read(131073)
        require(len(data) <= 131072, 'bounded_http_response')
        return response.status, response.getheaders(), data
    finally:
        connection.close()


def request(port, path, extra=(), body=b'', method='GET'):
    return raw_request(port, path, [('Host', DOMAIN), *extra], body, method)


class ProbeUpstream(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        with self.server.hit_lock:
            self.server.hits += 1
        size = int(self.headers.get('Content-Length', '0'))
        require(0 <= size <= 65536, 'bounded_synthetic_body')
        body = self.rfile.read(size)
        value = json.dumps(dict(path=self.path, headers=list(self.headers.raw_items()),
                                body_sha256=hashlib.sha256(body).hexdigest())).encode()
        self.send_response(401 if self.path.endswith('/challenge') else 200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(value)))
        self.send_header('WWW-Authenticate', 'Bearer realm="synthetic-probe"')
        self.send_header('Mcp-Session-Id', 'synthetic-response-session')
        self.end_headers()
        self.wfile.write(value)

    do_POST = do_GET

    def log_message(self, *_):
        pass


def private_config(root, listen_port, upstream_port, include=None, listen_host='127.0.0.1', duplicate=False):
    require(type(listen_port) is int and type(upstream_port) is int and
            1024 <= listen_port <= 65535 and 1024 <= upstream_port <= 65535 and
            listen_port != upstream_port, 'distinct_private_listener_and_upstream')
    require(listen_host in ('127.0.0.1', '0.0.0.0'), 'private_fixture_listener')
    paths = [str(root)] + ([str(include)] if include else [])
    require(all(re.fullmatch(r'[A-Za-z0-9_./-]+', p) for p in paths), 'safe_private_config_path')
    included = f'include {include};' if include else ''
    collision = 'location = /coding-tools { return 200; }' if duplicate else ''
    return f'''worker_processes 1;
error_log /dev/null crit;
pid {root}/nginx.pid;
events {{ worker_connections 64; }}
http {{
    access_log off;
    client_body_temp_path {root}/body;
    proxy_temp_path {root}/proxy;
    fastcgi_temp_path {root}/fastcgi;
    uwsgi_temp_path {root}/uwsgi;
    scgi_temp_path {root}/scgi;
    client_header_timeout 5s;
    keepalive_timeout 2s;
    server {{
        listen {listen_host}:{listen_port};
        server_name {DOMAIN};
        location / {{ return 200 'existing-site'; }}
        location /legacy/ {{ return 200 'existing-prefix'; }}
        location ~ \\.php$ {{ return 200 'existing-regex'; }}
        {included}
        {collision}
    }}
}}
'''


def compose_checks(compose, root):
    version = subprocess.check_output([compose, 'version', '--short'], text=True, timeout=15).strip().lstrip('v')
    require(version == '2.27.0', 'exact_compose_2_27')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('COMPOSE_', 'DOCKER_'))}
    env.update(GATEWAY_IMAGE='example.invalid/gateway@sha256:' + '0' * 64,
               POSTGRES_IMAGE='example.invalid/postgres@sha256:' + '1' * 64)
    for key in ('GATEWAY_DATABASE_URL_FILE', 'GATEWAY_IDENTITY_KEY_FILE', 'POSTGRES_PASSWORD_FILE'):
        path = root / key.lower()
        path.write_text('synthetic-config-only-not-a-credential')
        path.chmod(0o600)
        env[key] = str(path)
    images = dict(gateway='sha256:' + 'a' * 64, ingress='nginx@sha256:' + 'b' * 64,
                  postgres='postgres@sha256:' + 'c' * 64)
    forms = [('historical', current.blueprint.compose_blueprint(DOMAIN, CONNECTOR, 28880), 'integration-pending'),
             ('current', topology.compose(root, images, DOMAIN, CONNECTOR, 28880), 'operator')]
    for label, form, profile in forms:
        config = root / (label + '.json')
        config.write_text(json.dumps(form))
        completed = subprocess.run([compose, '-f', str(config), '--profile', profile, 'config', '--format', 'json'],
                                   env=env, capture_output=True, timeout=20, check=True)
        services = json.loads(completed.stdout)['services']
        publisher = services['gateway' if label == 'historical' else 'namespace']
        require(publisher['ports'][0]['host_ip'] == '127.0.0.1', 'normalized_loopback_only')
        require(not services['postgres'].get('ports'), 'database_unpublished')
        require(services['gateway']['user'] == '65532:65532', 'nonroot_gateway')
        if label == 'current':
            require(services['operator']['logging']['driver'] == 'none', 'operator_config_profile')
            require(services['gateway']['network_mode'] == 'service:namespace', 'private_namespace')
    return version


def run_checks(compose, nginx):
    cases = []
    def passed(name, condition=True):
        require(condition and name not in cases, name)
        cases.append(name)
    report = dict(scope='private_nginx_echo_mechanics_only', authenticated_gateway_tested=False,
                  production_touched=False, real_host_tls_waf_tested=False, publish_approved=False,
                  **source_identity())
    with tempfile.TemporaryDirectory(prefix='ctm-current-nginx-') as folder:
        root = Path(folder)
        report['compose_version'] = compose_checks(compose, root)
        passed('exact_compose_2_27_historical_and_current_config')
        server = ThreadingHTTPServer(('127.0.0.1', 0), ProbeUpstream)
        server.daemon_threads = True
        server.hits, server.hit_lock = 0, threading.Lock()
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        process = None
        try:
            with socket.socket() as candidate:
                candidate.bind(('127.0.0.1', 0))
                port = candidate.getsockname()[1]
            manifest = current.render(root / 'render', DOMAIN, CONNECTOR, server.server_port)
            report['include'] = manifest
            include = root / 'render' / current.INCLUDE
            conf = root / 'nginx.conf'
            def stop():
                nonlocal process
                if process is None:
                    return
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                require(process.poll() is not None, 'private_nginx_reaped')
                process = None
            def launch(included):
                nonlocal process
                conf.write_text(private_config(root, port, server.server_port, included))
                subprocess.run([nginx, '-t', '-p', str(root), '-c', str(conf)],
                               capture_output=True, timeout=10, check=True)
                process = subprocess.Popen([nginx, '-p', str(root), '-c', str(conf), '-g',
                                            'daemon off; master_process off;'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for _ in range(40):
                    require(process.poll() is None, 'private_nginx_running')
                    try:
                        if request(port, '/')[0] == 200:
                            return
                    except OSError:
                        pass
                    time.sleep(.05)
                raise RuntimeError('private_nginx_readiness_deadline')
            def sentinels(stage):
                for path, body in [('/', b'existing-site'), ('/legacy/path', b'existing-prefix'),
                                   ('/legacy.php', b'existing-regex'), ('/coding-tools-other', b'existing-site'),
                                   ('/.well-known/unrelated', b'existing-site')]:
                    value = request(port, path)
                    require((value[0], value[2]) == (200, body), 'existing_handlers_' + stage)
                passed('existing_root_prefix_regex_' + stage)
            launch(None)
            sentinels('before')
            stop()
            launch(include)
            sentinels('included')
            passed('actual_private_nginx_syntax')
            upgrade = [('Upgrade', 'websocket'), ('Connection', 'Upgrade'),
                       ('Sec-WebSocket-Protocol', current.SUBPROTOCOL)]
            def echo(path, pairs=(), body=b'', method='GET'):
                status, headers, raw = request(port, path, pairs, body, method)
                require(status in (200, 401), 'echo_response')
                value = json.loads(raw)
                def values(name):
                    return [v for k, v in value['headers'] if k.lower() == name.lower()]
                return status, headers, value, values
            _, _, value, fields = echo(current.AGENT, upgrade)
            passed('exact_agent_upgrade_headers', fields('Upgrade') == ['websocket'] and
                   fields('Connection') == ['upgrade'] and fields('Sec-WebSocket-Protocol') == [current.SUBPROTOCOL])
            generic = ['/coding-tools/agent/connect', '/coding-tools/agent/', '/coding-tools/agent-other',
                       '/coding-tools/probe.php', '/coding-tools/oauth/token',
                       '/.well-known/oauth-authorization-server/coding-tools/oauth',
                       '/.well-known/oauth-protected-resource/coding-tools/mcp/' + CONNECTOR]
            for index, path in enumerate(generic):
                _, _, value, fields = echo(path, upgrade)
                passed('generic_nonupgrade_' + str(index), value['path'] == path and
                       all(not fields(n) for n in ('Upgrade', 'Connection', 'Sec-WebSocket-Protocol')))
            pairs = [('Origin', ''), ('Origin', 'https://' + DOMAIN), ('Cookie', ''), ('Cookie', 'synthetic=1'),
                     ('Authorization', ''), ('MCP-Protocol-Version', '2025-06-18'), ('MCP-Protocol-Version', ''),
                     ('Mcp-Method', 'tools/list'), ('Mcp-Method', ''), ('Mcp-Name', 'synthetic'), ('Mcp-Name', ''),
                     ('Mcp-Session-Id', 'synthetic-session'), ('Last-Event-ID', 'synthetic-event'),
                     ('Accept', 'application/json'), ('Content-Type', 'application/json')]
            body = b'{"synthetic":true}'
            status, response_headers, value, fields = echo('/coding-tools/probe?raw=%2F&x=1', pairs, body, 'POST')
            for name in {k.lower() for k, _ in pairs}:
                require(fields(name) == [v for k, v in pairs if k.lower() == name], 'native_end_to_end_preservation')
            passed('native_duplicate_empty_and_mcp_headers', value['body_sha256'] == hashlib.sha256(body).hexdigest())
            passed('original_unrewritten_query_uri', value['path'] == '/coding-tools/probe?raw=%2F&x=1')
            for suffix, protocol_pairs in [('duplicate', [('Sec-WebSocket-Protocol', current.SUBPROTOCOL), ('Sec-WebSocket-Protocol', 'invalid')]),
                                           ('empty', [('Sec-WebSocket-Protocol', ''), ('Sec-WebSocket-Protocol', current.SUBPROTOCOL)])]:
                _, _, _, fields = echo(current.AGENT, upgrade[:2] + protocol_pairs)
                passed('native_subprotocol_' + suffix, fields('Sec-WebSocket-Protocol') == [v for _, v in protocol_pairs])
            for name in ('Host', 'Authorization'):
                hits = server.hits
                status, _, _ = raw_request(port, current.AGENT, [('Host', DOMAIN)] +
                                          ([(name, DOMAIN)] if name == 'Host' else [(name, ''), (name, 'synthetic')]))
                passed('parser_duplicate_' + name.lower(), status == 400 and server.hits == hits)
            hits = server.hits
            passed('parser_missing_host', raw_request(port, current.AGENT, [])[0] == 400 and server.hits == hits)
            for index, host in enumerate(('foreign.invalid', DOMAIN.upper(), DOMAIN + ':443', DOMAIN + '.', '')):
                hits = server.hits
                status, _, _ = raw_request(port, '/coding-tools/probe', [('Host', host), ('X-Forwarded-Host', DOMAIN)])
                passed('original_host_refused_' + str(index), status in (400, 421) and server.hits == hits)
            _, _, _, fields = echo('/coding-tools/probe', [('Forwarded', 'host=foreign.invalid'),
                                    ('X-Forwarded-Host', 'foreign.invalid'), ('X-Forwarded-For', '192.0.2.1'),
                                    ('X-Real-IP', '192.0.2.2'), ('X-Forwarded-Proto', 'http')])
            passed('untrusted_forwarding_removed', fields('Host') == [DOMAIN] and fields('X-Forwarded-Proto') == ['https'] and
                   all(not fields(n) for n in ('Forwarded', 'X-Forwarded-Host', 'X-Forwarded-For', 'X-Real-IP')))
            for host, expected in [(DOMAIN, 404), ('foreign.invalid', 421)]:
                status, headers, _ = raw_request(port, '/coding-tools', [('Host', host)])
                require(status == expected and not any(k.lower() == 'location' for k, _ in headers), 'bare_guard_no_redirect')
            passed('bare_namespace_guard_no_301')
            status, headers, _, _ = echo('/coding-tools/challenge')
            passed('response_status_challenge_session', status == 401 and ('WWW-Authenticate', 'Bearer realm="synthetic-probe"') in headers and
                   ('Mcp-Session-Id', 'synthetic-response-session') in headers)
            for index, path in enumerate(('/coding-tools//agent', '/coding-tools/%61gent')):
                _, _, value, fields = echo(path, upgrade)
                passed('normalized_agent_original_uri_' + str(index), value['path'] == path and fields('Upgrade') == ['websocket'])
            passed('normalized_escape_existing_destination', request(port, '/coding-tools/../legacy.php')[2] == b'existing-regex')
            passed('body_limit_64k', request(port, '/coding-tools/probe', body=b'x' * 65537, method='POST')[0] == 413)
            collision = root / 'collision.conf'
            collision.write_text(private_config(root, port, server.server_port, include, duplicate=True))
            result = subprocess.run([nginx, '-t', '-p', str(root), '-c', str(collision)], capture_output=True, timeout=10)
            passed('duplicate_location_syntax_refused', result.returncode != 0)
            stop()
            launch(None)
            sentinels('removed')
            stop()
            passed('owned_nginx_cleanup')
        finally:
            try:
                if process is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                require(not thread.is_alive(), 'owned_echo_cleanup')
    version = subprocess.run([nginx, '-v'], capture_output=True, text=True, timeout=10, check=True)
    report.update(passed=True, cases=cases, case_count=len(cases), nginx_version=version.stderr.strip(),
                  tool_sha256={name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                               for name, path in [('compose', compose), ('nginx', nginx)]})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose', type=Path, required=True)
    parser.add_argument('--nginx', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = None
    try:
        report = run_checks(str(args.compose.resolve(strict=True)), str(args.nginx.resolve(strict=True)))
    except Exception:
        report = dict(passed=False, error='private_native_check_failed', production_touched=False)
        raise
    finally:
        if report is not None:
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, indent=2)
                stream.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
