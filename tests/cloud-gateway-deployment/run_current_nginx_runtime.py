#!/usr/bin/env python3
"""Fresh hosted-only single/two-hop Nginx -> actual Gateway/PostgreSQL engineering proof."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess
import time

from container_fixture import Fixture, FixtureFailure, require, topology
from run_container_topology import oauth, mcp, inspect_boundaries, upgraded_socket
from run_current_nginx_checks import current, DOMAIN, private_config, raw_request, source_identity

STAGE = 'setup'
CASES = []


def passed(name, value=True):
    require(value and name not in CASES, name)
    CASES.append(name)


def install_private_include(fixture, listen_port=8080, upstream_port=28880):
    """Only the fresh fixture bind is changed; the tracked old topology is untouched."""
    # Check same-namespace self-proxy before accessing a fixture or changing any file.
    config = private_config(Path('/tmp'), listen_port, upstream_port,
                            Path('/run/ingress/render') / current.INCLUDE, listen_host='0.0.0.0')
    require(fixture.domain == DOMAIN, 'fixed_private_fixture_domain')
    require(re.fullmatch(r'ctm-topology-[0-9a-f]{32}', fixture.project), 'owned_fixture_project')
    target = fixture.root / 'current-ingress-private'
    target.mkdir(mode=0o700, exist_ok=False)
    manifest = current.render(target / 'render', fixture.domain, fixture.config['connector'], upstream_port)
    path = target / 'nginx.conf'
    path.write_text(config)
    path.chmod(0o400)
    fixture.exec(['sudo', 'chown', '-R', '65532:65532', str(target)])
    value = json.loads(fixture.file.read_text())
    volume = value['services']['ingress']['volumes'][0]
    require(volume['target'] == '/run/ingress' and volume['read_only'] is True and
            volume['bind']['create_host_path'] is False, 'unchanged_private_ingress_mount_contract')
    volume['source'] = str(target)
    fixture.file.write_text(json.dumps(value))
    return manifest


def agent_headers(host=DOMAIN, protocol=current.SUBPROTOCOL):
    return [('Host', host), ('Upgrade', 'websocket'), ('Connection', 'Upgrade'),
            ('Sec-WebSocket-Version', '13'),
            ('Sec-WebSocket-Key', base64.b64encode(b'0123456789abcdef').decode()),
            ('Sec-WebSocket-Protocol', protocol)]


def modern_request(token, method='tools/list', name=None):
    params = {'_meta': {'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                        'io.modelcontextprotocol/clientCapabilities': {}}}
    if name is not None:
        params['name'] = name
        params['arguments'] = {}
    message = dict(jsonrpc='2.0', id=1, method=method, params=params)
    headers = [('Host', DOMAIN), ('Authorization', 'Bearer ' + token),
               ('Content-Type', 'application/json'), ('Accept', 'application/json, text/event-stream'),
               ('MCP-Protocol-Version', '2026-07-28'), ('Mcp-Method', method)]
    if name is not None:
        headers.append(('Mcp-Name', name))
    return json.dumps(message).encode(), headers


class ProxyEndpoint:
    """Client route only; never change the physical fixture's published port."""
    def __init__(self, fixture, port):
        require(type(port) is int and 1024 <= port <= 65535 and port != fixture.port,
                'distinct_outer_and_inner_ports')
        self.port = port
        for name in ('domain', 'origin', 'config', 'password', 'secret_values'):
            setattr(self, name, getattr(fixture, name))

    def http(self, method, path, data=None, headers=None):
        return Fixture.http(self, method, path, data, headers)


class OuterProxy:
    """Owned runner-local process, assigned before start so every failure can reap it."""
    def __init__(self, fixture, nginx):
        self.process = None
        require(fixture.domain == DOMAIN and re.fullmatch(r'ctm-topology-[0-9a-f]{32}', fixture.project),
                'owned_outer_fixture')
        self.fixture, self.nginx = fixture, Path(nginx).resolve(strict=True)
        self.root = fixture.root / 'current-outer-private'
        self.root.mkdir(mode=0o700, exist_ok=False)
        with socket.socket() as candidate:
            candidate.bind(('127.0.0.1', 0))
            port = candidate.getsockname()[1]
        self.endpoint = ProxyEndpoint(fixture, port)
        self.manifest = current.render(self.root / 'render', fixture.domain, fixture.config['connector'], fixture.port)
        config = private_config(self.root, port, fixture.port, self.root / 'render' / current.INCLUDE)
        self.config = self.root / 'nginx.conf'
        self.config.write_text(config)
        self.config.chmod(0o600)
        self.evidence = dict(outer_loopback_port=port, inner_published_loopback_port=fixture.port,
                             inner_namespace_port=8080, gateway_namespace_loopback_port=28880,
                             outer_config_sha256=hashlib.sha256(config.encode()).hexdigest(),
                             outer_nginx_sha256=hashlib.sha256(self.nginx.read_bytes()).hexdigest())

    def start(self):
        require(self.process is None, 'outer_process_already_owned')
        f = self.fixture
        f.exec([self.nginx, '-t', '-p', self.root, '-c', self.config], timeout=10)
        version = f.exec([self.nginx, '-v'], timeout=10).stderr.decode().strip()
        require(re.fullmatch(r'nginx version: nginx/\d+\.\d+\.\d+(?: \(Ubuntu\))?', version), 'actual_outer_nginx_version')
        self.evidence['outer_nginx_version'] = version
        self.process = subprocess.Popen([str(self.nginx), '-p', str(self.root), '-c', str(self.config),
                                         '-g', 'daemon off; master_process off;'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            require(self.process.poll() is None, 'owned_outer_nginx_running')
            try:
                status, _, body = raw_request(self.endpoint.port, '/', [('Host', DOMAIN)])
                if (status, body) == (200, b'existing-site'):
                    return
            except OSError:
                pass
            time.sleep(.05)
        raise FixtureFailure('outer_nginx_readiness_deadline')

    def close(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        require(self.process.poll() is not None, 'owned_outer_nginx_reaped')
        self.process = None


def inner_ingress_evidence(fixture):
    """Bind the repaired config actually mounted in the running inner Nginx."""
    expected = hashlib.sha256(topology.ingress_config(fixture.domain, fixture.config['connector']).encode()).hexdigest()
    actual = fixture.dc('exec', '-T', 'ingress', 'sha256sum', '/run/ingress/nginx.conf').stdout.decode().split()
    require(actual == [expected, '/run/ingress/nginx.conf'], 'running_inner_config_matches_renderer')
    version = fixture.dc('exec', '-T', 'ingress', '/usr/sbin/nginx', '-v').stderr.decode().strip()
    require(re.fullmatch(r'nginx version: nginx/\d+\.\d+\.\d+(?: \(Ubuntu\))?', version), 'actual_inner_nginx_version')
    _, record = fixture.container('ingress')
    image = json.loads(fixture.exec(['docker', 'image', 'inspect', fixture.images['ingress']]).stdout)[0]
    require(record['Image'] == image['Id'] and fixture.images['ingress'] in image['RepoDigests'],
            'actual_inner_nginx_image_identity')
    return dict(inner_config_sha256=expected, inner_nginx_version=version, inner_image_id=image['Id'],
                inner_renderer_sha256=hashlib.sha256(Path(topology.__file__).read_bytes()).hexdigest())


def direct_inner_checks(fixture):
    for name in ('Origin', 'Cookie', 'Authorization'):
        status, _, _ = raw_request(fixture.port, current.AGENT, agent_headers() + [(name, '')])
        passed('inner_agent_empty_' + name.lower() + '_403', status == 403)
    base = [(k, v) for k, v in agent_headers() if k != 'Sec-WebSocket-Protocol']
    for label, values in [('valid_invalid', [current.SUBPROTOCOL, 'invalid']),
                          ('empty_valid', ['', current.SUBPROTOCOL])]:
        status, _, _ = raw_request(fixture.port, current.AGENT, base + [('Sec-WebSocket-Protocol', v) for v in values])
        passed('inner_agent_duplicate_protocol_' + label + '_403', status == 403)
    status, _, _ = raw_request(fixture.port, current.AGENT, agent_headers(host='foreign.invalid'))
    passed('inner_agent_original_host_421', status == 421)


def pending_lifecycle_checks(f, client, outer, token):
    """Reuse shipped CLI and pending-socket assertions; never claim Agent authentication."""
    pending = None
    try:
        anchor, ingress = f.container('namespace')[0], f.container('ingress')[0]
        process = outer.process
        opened = time.monotonic()
        pending = upgraded_socket(client)
        passed('two_hop_pending_websocket_upgrade')
        started = time.monotonic()
        f.dc('stop', '--timeout', '15', 'gateway', timeout=25)
        _, stopped = f.container('gateway')
        require(stopped['State']['ExitCode'] == 0 and not stopped['State']['Running'] and
                time.monotonic() - started < 22, 'graceful_gateway_shutdown')
        require(b'"status":"stopped"' in f.logs_clean(), 'gateway_stopped_receipt')
        pending.settimeout(1)
        closed, received = False, 0
        while time.monotonic() < opened + 8:
            try:
                data = pending.recv(4096)
                if not data:
                    closed = True
                    break
                received += len(data)
                require(received < 65536, 'bounded_pending_socket_output')
            except ConnectionResetError:
                closed = True
                break
            except socket.timeout:
                pass
        passed('two_hop_pending_socket_drained_before_auth_expiry', closed and time.monotonic() < opened + 8)
        pending.close()
        pending = None
        f.dc('start', 'gateway', timeout=60)
        f.ready()
        require(f.container('namespace')[0] == anchor and f.container('ingress')[0] == ingress and
                outer.process is process and process.poll() is None, 'same_live_proxy_chain_after_restart')
        passed('two_hop_restart_preserves_proxy_chain_and_oauth', mcp(client, token)[0] == 200)
        f.cli('coding-tools-gateway', ['revoke-device', '--config', '/run/gateway/config.json',
              '--secrets-stdin', '--device', f.device], f.packet)
        f.dc('stop', '--timeout', '15', 'ingress', 'gateway', timeout=40)
        f.dc('restart', 'postgres', timeout=45)
        f.wait_postgres()
        require(f.sql('SELECT count(*) FROM ctm_devices WHERE revoked', database='coding_tools_identity_test') == '1',
                'revocation_survives_database_restart')
        error = f.cli('coding-tools-mcp-gateway', ['serve', '--config', '/run/gateway/config.json',
                      '--secrets-file', '/run/gateway/runtime.json'], success=False)
        passed('two_hop_revoked_authority_not_resurrected', error == {'ok': False, 'error': 'provisioning_not_ready'})
    finally:
        if pending is not None:
            pending.close()


def runtime_checks(compose, images, *, two_hop=False, nginx=None):
    global STAGE
    f = None
    outer = None
    result = None
    require(not two_hop or nginx is not None, 'two_hop_nginx_required')
    try:
        f = Fixture(compose, images)
        manifest = None if two_hop else install_private_include(f)
        client = f
        hop_evidence = {}
        STAGE = 'prepare_current_runtime'
        versions = f.prepare()
        passed('compose_2_27_and_actual_empty_bootstrap', versions['compose_version'] == '2.27.0')
        require(f.sentinel is not None, 'owned_port_sentinel')
        f.sentinel.close()
        f.sentinel = None
        f.dc('up', '-d', 'gateway', timeout=90)
        f.dc('run', '--rm', '-T', '--no-deps', 'ingress', '-t', '-c', '/run/ingress/nginx.conf')
        passed('actual_include_nginx_syntax')
        f.dc('up', '-d', 'ingress', timeout=60)
        f.ready()
        inspect_boundaries(f)
        passed('exact_image_binaries_nonroot_loopback_private_database')
        if two_hop:
            hop_evidence = inner_ingress_evidence(f)
            passed('actual_private_ingress_source_checked_config')
            direct_inner_checks(f)
            outer = OuterProxy(f, nginx)
            outer.start()
            client, manifest = outer.endpoint, outer.manifest
            hop_evidence.update(outer.evidence)
            passed('two_hop_distinct_endpoints_and_real_nginx_versions')
        STAGE = 'existing_vhost_routes'
        for path, expected in [('/', b'existing-site'), ('/legacy/path', b'existing-prefix'),
                               ('/legacy.php', b'existing-regex'), ('/coding-tools-other', b'existing-site'),
                               ('/.well-known/unrelated', b'existing-site')]:
            status, _, body = client.http('GET', path)
            require((status, body) == (200, expected), 'existing_vhost_sentinels')
        passed('existing_root_prefix_regex_preserved')
        status, _, body = client.http('GET', '/coding-tools/probe.php')
        passed('generic_namespace_not_captured_by_existing_regex', status == 404 and body != b'existing-regex')
        for host, expected in [(DOMAIN, 404), ('foreign.invalid', 421)]:
            status, headers, _ = raw_request(client.port, '/coding-tools', [('Host', host)])
            require(status == expected and not any(k.lower() == 'location' for k, _ in headers), 'bare_namespace_guard')
        passed('bare_namespace_404_foreign_421_no_redirect')
        metadata = '/.well-known/oauth-authorization-server/coding-tools/oauth'
        status, _, body = client.http('GET', metadata, headers={'Forwarded': 'host=foreign.invalid',
                                                        'X-Forwarded-Host': 'foreign.invalid'})
        passed('actual_discovery_canonical_authority', status == 200 and
               json.loads(body)['issuer'] == f.origin + '/coding-tools/oauth')
        resource_path = '/coding-tools/mcp/' + f.config['connector']
        status, _, body = client.http('GET', '/.well-known/oauth-protected-resource' + resource_path)
        passed('actual_resource_discovery', status == 200 and json.loads(body)['resource'] == f.origin + resource_path)
        for index, host in enumerate(('foreign.invalid', DOMAIN.upper(), DOMAIN + ':443', DOMAIN + '.')):
            status, _, _ = raw_request(client.port, metadata, [('Host', host), ('X-Forwarded-Host', DOMAIN)])
            passed('original_host_421_' + str(index), status == 421)
        STAGE = 'oauth_mcp'
        token = oauth(client)
        passed('actual_oauth_pkce_through_current_include')
        for version in ('2025-06-18', '2025-11-25'):
            status, _, body = mcp(client, token, version, initialize=True)
            require(status == 200 and json.loads(body)['result']['protocolVersion'] == version, 'mcp_initialize')
            status, _, body = mcp(client, token, version)
            passed('actual_legacy_mcp_' + version, status == 200 and bool(json.loads(body)['result']['tools']))
        data, headers = modern_request(token)
        status, _, body = raw_request(client.port, resource_path, headers, data, 'POST')
        passed('actual_modern_mcp_mirror', status == 200 and bool(json.loads(body)['result']['tools']))
        bad_mirror = [(k, 'server/discover' if k == 'Mcp-Method' else v) for k, v in headers]
        status, _, body = raw_request(client.port, resource_path, bad_mirror, data, 'POST')
        passed('actual_modern_mirror_rejected', status == 400 and json.loads(body)['error']['code'] == -32020)
        status, _, body = mcp(client, token, '1900-01-01')
        passed('actual_unsupported_protocol_rejected', status == 400 and json.loads(body)['error']['code'] == -32022)
        for name, first in [('MCP-Protocol-Version', '2026-07-28'), ('Mcp-Method', 'tools/list'), ('Mcp-Name', 'synthetic')]:
            base = [(k, v) for k, v in headers if k != name]
            for kind, second in [('invalid', 'invalid'), ('empty', '')]:
                status, _, body = raw_request(client.port, resource_path, base + [(name, first), (name, second)], data, 'POST')
                passed('actual_duplicate_' + name.lower() + '_' + kind,
                       status == 400 and json.loads(body)['error']['code'] == -32020)
        for label, extra in [('empty', [('Origin', '')]),
                             ('duplicate', [('Origin', f.origin), ('Origin', f.origin)])]:
            status, _, _ = raw_request(client.port, resource_path, headers + extra, data, 'POST')
            passed('actual_mcp_origin_' + label + '_403', status == 403)
        for label, extra in [('authorization', [('Authorization', '')]), ('host', [('Host', DOMAIN)])]:
            status, _, _ = raw_request(client.port, resource_path, headers + extra, data, 'POST')
            passed('nginx_parser_duplicate_' + label + '_400', status == 400)
        # Generic HTTP keeps working with attempted upgrade headers; no WebSocket promotion.
        status, _, body = raw_request(client.port, resource_path, headers + [('Upgrade', 'websocket'),
                                     ('Connection', 'Upgrade'), ('Sec-WebSocket-Protocol', current.SUBPROTOCOL)], data, 'POST')
        passed('actual_mcp_nonupgrade', status == 200 and bool(json.loads(body)['result']['tools']))
        STAGE = 'current_agent_protocol'
        status, response_headers, _ = raw_request(client.port, current.AGENT, agent_headers())
        selected = [v for k, v in response_headers if k.lower() == 'sec-websocket-protocol']
        passed('actual_pending_agent_101_exact_subprotocol', status == 101 and selected == [current.SUBPROTOCOL])
        status, _, _ = raw_request(client.port, current.AGENT, agent_headers(protocol='unsupported-agent.v0'))
        passed('actual_agent_wrong_subprotocol_403', status == 403)
        base = [(k, v) for k, v in agent_headers() if k != 'Sec-WebSocket-Protocol']
        for label, offers in [('valid_invalid', [current.SUBPROTOCOL, 'invalid']),
                              ('empty_valid', ['', current.SUBPROTOCOL])]:
            status, _, _ = raw_request(client.port, current.AGENT, base + [('Sec-WebSocket-Protocol', value) for value in offers])
            passed('actual_agent_duplicate_protocol_' + label + '_403', status == 403)
        for name in ('Origin', 'Cookie', 'Authorization'):
            status, _, _ = raw_request(client.port, current.AGENT, agent_headers() + [(name, '')])
            passed('actual_agent_empty_' + name.lower() + '_403', status == 403)
        status, _, _ = raw_request(client.port, current.AGENT, agent_headers() + [('Origin', f.origin), ('Origin', f.origin)])
        passed('actual_agent_duplicate_origin_403', status == 403)
        status, _, _ = raw_request(client.port, current.AGENT + '?synthetic=1', agent_headers())
        passed('actual_agent_query_403', status == 403)
        status, _, _ = raw_request(client.port, current.AGENT, agent_headers(host='foreign.invalid'))
        passed('actual_agent_original_host_421', status == 421)
        for index, path in enumerate(('/coding-tools/agent/connect', '/coding-tools/agent/',
                                      '/coding-tools/agent-other', '/coding-tools//agent', '/coding-tools/%61gent')):
            status, _, _ = raw_request(client.port, path, agent_headers())
            passed('actual_agent_nonendpoint_' + str(index), status in (400, 403, 404))
        if two_hop:
            STAGE = 'two_hop_pending_lifecycle'
            pending_lifecycle_checks(f, client, outer, token)
        STAGE = 'clean_evidence'
        f.logs_clean()
        passed('fixture_secret_log_scan')
        result = dict(passed=True, **source_identity(), cases=list(CASES), case_count=len(CASES),
                      versions=versions, images=images, include=manifest,
                      compose_sha256=hashlib.sha256(compose.read_bytes()).hexdigest(),
                      scope=('two_proxy_hops_current_include_private_ingress_real_gateway' if two_hop else
                             'single_proxy_hop_current_include_to_real_gateway'),
                      two_hop=hop_evidence, repaired_private_ingress_tested=two_hop,
                      authenticated_agent_lifecycle_tested=False,
                      pending_websocket_authenticated=False, production_touched=False,
                      real_host_tls_waf_tested=False, publish_approved=False,
                      old_ingress_two_hop_supported=False)
    finally:
        if f is not None:
            try:
                # Never delete the owned fixture directory before confirming outer reaping.
                if outer is not None:
                    outer.close()
                f.close()
            except Exception:
                STAGE = 'owned_cleanup'
                raise
    result['cleanup_completed'] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose', type=Path, required=True)
    for name in ('gateway', 'ingress', 'postgres'):
        parser.add_argument('--' + name + '-image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--two-hop', action='store_true')
    parser.add_argument('--nginx', type=Path)
    args = parser.parse_args()
    try:
        result = runtime_checks(args.compose.resolve(strict=True),
                                dict(gateway=args.gateway_image, ingress=args.ingress_image, postgres=args.postgres_image),
                                two_hop=args.two_hop, nginx=args.nginx)
    except Exception as error:
        result = dict(passed=False, stage=STAGE, completed_cases=list(CASES),
                      error_code=error.code if isinstance(error, FixtureFailure) else 'current_runtime_check_failed',
                      diagnostic=error.diagnostic if isinstance(error, FixtureFailure) else None,
                      production_touched=False, real_host_tls_waf_tested=False, publish_approved=False)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))
    if result['passed'] is not True:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
