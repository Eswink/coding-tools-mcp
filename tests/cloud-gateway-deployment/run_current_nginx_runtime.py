#!/usr/bin/env python3
"""Fresh hosted-only single-hop include -> actual Gateway/PostgreSQL engineering proof."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re

from container_fixture import Fixture, FixtureFailure, require
from run_container_topology import oauth, mcp, inspect_boundaries
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


def runtime_checks(compose, images):
    global STAGE
    f = None
    result = None
    try:
        f = Fixture(compose, images)
        manifest = install_private_include(f)
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
        STAGE = 'existing_vhost_routes'
        for path, expected in [('/', b'existing-site'), ('/legacy/path', b'existing-prefix'),
                               ('/legacy.php', b'existing-regex'), ('/coding-tools-other', b'existing-site'),
                               ('/.well-known/unrelated', b'existing-site')]:
            status, _, body = f.http('GET', path)
            require((status, body) == (200, expected), 'existing_vhost_sentinels')
        passed('existing_root_prefix_regex_preserved')
        status, _, body = f.http('GET', '/coding-tools/probe.php')
        passed('generic_namespace_not_captured_by_existing_regex', status == 404 and body != b'existing-regex')
        for host, expected in [(DOMAIN, 404), ('foreign.invalid', 421)]:
            status, headers, _ = raw_request(f.port, '/coding-tools', [('Host', host)])
            require(status == expected and not any(k.lower() == 'location' for k, _ in headers), 'bare_namespace_guard')
        passed('bare_namespace_404_foreign_421_no_redirect')
        metadata = '/.well-known/oauth-authorization-server/coding-tools/oauth'
        status, _, body = f.http('GET', metadata, headers={'Forwarded': 'host=foreign.invalid',
                                                        'X-Forwarded-Host': 'foreign.invalid'})
        passed('actual_discovery_canonical_authority', status == 200 and
               json.loads(body)['issuer'] == f.origin + '/coding-tools/oauth')
        resource_path = '/coding-tools/mcp/' + f.config['connector']
        status, _, body = f.http('GET', '/.well-known/oauth-protected-resource' + resource_path)
        passed('actual_resource_discovery', status == 200 and json.loads(body)['resource'] == f.origin + resource_path)
        for index, host in enumerate(('foreign.invalid', DOMAIN.upper(), DOMAIN + ':443', DOMAIN + '.')):
            status, _, _ = raw_request(f.port, metadata, [('Host', host), ('X-Forwarded-Host', DOMAIN)])
            passed('original_host_421_' + str(index), status == 421)
        STAGE = 'oauth_mcp'
        token = oauth(f)
        passed('actual_oauth_pkce_through_current_include')
        for version in ('2025-06-18', '2025-11-25'):
            status, _, body = mcp(f, token, version, initialize=True)
            require(status == 200 and json.loads(body)['result']['protocolVersion'] == version, 'mcp_initialize')
            status, _, body = mcp(f, token, version)
            passed('actual_legacy_mcp_' + version, status == 200 and bool(json.loads(body)['result']['tools']))
        data, headers = modern_request(token)
        status, _, body = raw_request(f.port, resource_path, headers, data, 'POST')
        passed('actual_modern_mcp_mirror', status == 200 and bool(json.loads(body)['result']['tools']))
        bad_mirror = [(k, 'server/discover' if k == 'Mcp-Method' else v) for k, v in headers]
        status, _, body = raw_request(f.port, resource_path, bad_mirror, data, 'POST')
        passed('actual_modern_mirror_rejected', status == 400 and json.loads(body)['error']['code'] == -32020)
        status, _, body = mcp(f, token, '1900-01-01')
        passed('actual_unsupported_protocol_rejected', status == 400 and json.loads(body)['error']['code'] == -32022)
        for name, first in [('MCP-Protocol-Version', '2026-07-28'), ('Mcp-Method', 'tools/list'), ('Mcp-Name', 'synthetic')]:
            base = [(k, v) for k, v in headers if k != name]
            for kind, second in [('invalid', 'invalid'), ('empty', '')]:
                status, _, body = raw_request(f.port, resource_path, base + [(name, first), (name, second)], data, 'POST')
                passed('actual_duplicate_' + name.lower() + '_' + kind,
                       status == 400 and json.loads(body)['error']['code'] == -32020)
        for label, extra in [('empty', [('Origin', '')]),
                             ('duplicate', [('Origin', f.origin), ('Origin', f.origin)])]:
            status, _, _ = raw_request(f.port, resource_path, headers + extra, data, 'POST')
            passed('actual_mcp_origin_' + label + '_403', status == 403)
        for label, extra in [('authorization', [('Authorization', '')]), ('host', [('Host', DOMAIN)])]:
            status, _, _ = raw_request(f.port, resource_path, headers + extra, data, 'POST')
            passed('nginx_parser_duplicate_' + label + '_400', status == 400)
        # Generic HTTP keeps working with attempted upgrade headers; no WebSocket promotion.
        status, _, body = raw_request(f.port, resource_path, headers + [('Upgrade', 'websocket'),
                                     ('Connection', 'Upgrade'), ('Sec-WebSocket-Protocol', current.SUBPROTOCOL)], data, 'POST')
        passed('actual_mcp_nonupgrade', status == 200 and bool(json.loads(body)['result']['tools']))
        STAGE = 'current_agent_protocol'
        status, response_headers, _ = raw_request(f.port, current.AGENT, agent_headers())
        selected = [v for k, v in response_headers if k.lower() == 'sec-websocket-protocol']
        passed('actual_pending_agent_101_exact_subprotocol', status == 101 and selected == [current.SUBPROTOCOL])
        status, _, _ = raw_request(f.port, current.AGENT, agent_headers(protocol='unsupported-agent.v0'))
        passed('actual_agent_wrong_subprotocol_403', status == 403)
        base = [(k, v) for k, v in agent_headers() if k != 'Sec-WebSocket-Protocol']
        for label, offers in [('valid_invalid', [current.SUBPROTOCOL, 'invalid']),
                              ('empty_valid', ['', current.SUBPROTOCOL])]:
            status, _, _ = raw_request(f.port, current.AGENT, base + [('Sec-WebSocket-Protocol', value) for value in offers])
            passed('actual_agent_duplicate_protocol_' + label + '_403', status == 403)
        for name in ('Origin', 'Cookie', 'Authorization'):
            status, _, _ = raw_request(f.port, current.AGENT, agent_headers() + [(name, '')])
            passed('actual_agent_empty_' + name.lower() + '_403', status == 403)
        status, _, _ = raw_request(f.port, current.AGENT, agent_headers() + [('Origin', f.origin), ('Origin', f.origin)])
        passed('actual_agent_duplicate_origin_403', status == 403)
        status, _, _ = raw_request(f.port, current.AGENT + '?synthetic=1', agent_headers())
        passed('actual_agent_query_403', status == 403)
        status, _, _ = raw_request(f.port, current.AGENT, agent_headers(host='foreign.invalid'))
        passed('actual_agent_original_host_421', status == 421)
        for index, path in enumerate(('/coding-tools/agent/connect', '/coding-tools/agent/',
                                      '/coding-tools/agent-other', '/coding-tools//agent', '/coding-tools/%61gent')):
            status, _, _ = raw_request(f.port, path, agent_headers())
            passed('actual_agent_nonendpoint_' + str(index), status in (400, 403, 404))
        STAGE = 'clean_evidence'
        f.logs_clean()
        passed('fixture_secret_log_scan')
        result = dict(passed=True, **source_identity(), cases=list(CASES), case_count=len(CASES),
                      versions=versions, images=images, include=manifest,
                      compose_sha256=hashlib.sha256(compose.read_bytes()).hexdigest(),
                      scope='single_proxy_hop_current_include_to_real_gateway',
                      pending_websocket_authenticated=False, production_touched=False,
                      real_host_tls_waf_tested=False, publish_approved=False,
                      old_ingress_two_hop_supported=False)
    finally:
        if f is not None:
            try:
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
    args = parser.parse_args()
    try:
        result = runtime_checks(args.compose.resolve(strict=True),
                                dict(gateway=args.gateway_image, ingress=args.ingress_image, postgres=args.postgres_image))
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
