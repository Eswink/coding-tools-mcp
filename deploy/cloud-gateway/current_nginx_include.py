#!/usr/bin/env python3
"""Offline, source-pinned single-hop Nginx review include. Never applies configuration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('historical_validation', Path(__file__).with_name('render.py'))
blueprint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(blueprint)
BASELINE = '310ad16c8aa9cc8182c4b0f6a196184fcf34bc52'
PREFIX = '/coding-tools'
AGENT = PREFIX + '/agent'
SUBPROTOCOL = 'coding-tools-agent.v1'
SOURCE_HASHES = {
    'services/cloud-gateway/src/channel/transport.rs': '2662be4f84b22cf6784d8392a9d1dcd2481128147657eed4d070dcbd62c3153d',
    'services/cloud-gateway/src/channel/protocol.rs': 'baefe29876c5034af951c012846246b99004051cbbed5b86cd99de8c592f9b53',
    'services/cloud-gateway/src/config.rs': '79207a0744d01f20c7abff595aa0d2a10c9edc7436766ac2abc8d1b332bf32a7',
    'services/cloud-gateway/src/mcp/http.rs': '1034eebe6fff8e2036209646a4c7f3b821fd675f88240b9b3d49285f19f88421',
    'services/cloud-gateway/src/mcp/protocol.rs': '607d2bea785fdde87fc2d36d1f937ced240d640977e5ff656bfd171747235254',
}
INCLUDE = 'nginx-locations.current.review.conf'


def source_contract(root=ROOT):
    """Only already reviewed whole source bytes may satisfy this compatibility contract."""
    contents = {}
    for relative, expected in SOURCE_HASHES.items():
        path = Path(root) / relative
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 262144:
                raise ValueError('unsupported source file')
            value = stream.read(262145)
        if hashlib.sha256(value).hexdigest() != expected:
            raise ValueError('current source contract changed; review required')
        contents[relative] = value.decode('utf-8')
    transport = contents['services/cloud-gateway/src/channel/transport.rs']
    protocol = contents['services/cloud-gateway/src/channel/protocol.rs']
    identity = contents['services/cloud-gateway/src/config.rs']
    required = [
        (transport, 'pub fn managed_agent_channel_routes('),
        (transport, 'let path = format!("{}/agent", control.identity().prefix());'),
        (transport, 'Router::new().route(&path, get(upgrade)).with_state(state)'),
        (protocol, 'pub const SUBPROTOCOL: &str = "coding-tools-agent.v1";'),
        (identity, '"/.well-known/oauth-protected-resource{}"'),
        (identity, '"/.well-known/oauth-authorization-server{}/oauth"'),
        (identity, 'format!("{}/mcp/{}", self.prefix, self.connector)'),
    ]
    if any(text.count(fragment) != 1 for text, fragment in required):
        raise ValueError('ambiguous current source contract')
    return dict(SOURCE_HASHES)


def locations(domain, connector, port):
    if type(domain) is not str or type(connector) is not str:
        raise ValueError('canonical string identity required')
    blueprint.validate(domain, connector, port)
    blocks = [
        '# CURRENT SOURCE-PINNED REVIEW INCLUDE; single proxy hop only.',
        '# Requires a separately reviewed gateway endpoint in this Nginx network namespace.',
        '# The old runtime topology published ingress is NOT a suitable default upstream.',
        '# No deployment, TLS, WAF, route-collision or supported-host acceptance is implied.',
        f'location = {PREFIX} {{\n'
        f'    if ($http_host != "{domain}") {{ return 421; }}\n'
        '    access_log off;\n    return 404;\n}',
    ]
    routes = [
        (f'= /.well-known/oauth-protected-resource{PREFIX}/mcp/{connector}', False),
        (f'= /.well-known/oauth-authorization-server{PREFIX}/oauth', False),
        (f'^~ {PREFIX}/', False),
        (f'= {AGENT}', True),
    ]
    for route, websocket in routes:
        lines = [f'location {route} {{',
                 f'    if ($http_host != "{domain}") {{ return 421; }}',
                 f'    proxy_pass http://127.0.0.1:{port};',
                 '    proxy_http_version 1.1;',
                 '    proxy_pass_request_headers on;',
                 '    proxy_set_header Host $http_host;',
                 '    proxy_set_header Forwarded "";',
                 '    proxy_set_header X-Forwarded-Host "";',
                 '    proxy_set_header X-Forwarded-For "";',
                 '    proxy_set_header X-Real-IP "";',
                 '    proxy_set_header X-Forwarded-Proto https;',
                 '    proxy_buffering off;',
                 '    proxy_request_buffering off;',
                 '    proxy_cache off;',
                 '    proxy_intercept_errors off;',
                 '    proxy_redirect off;',
                 '    proxy_connect_timeout 3s;',
                 '    proxy_read_timeout 75s;',
                 '    proxy_send_timeout 30s;',
                 '    client_max_body_size 64k;',
                 '    client_body_timeout 10s;',
                 '    access_log off;']
        if websocket:
            # End-to-end headers are NOT rebuilt via $http_*: preserve empty/duplicates.
            lines += ['    proxy_set_header Upgrade $http_upgrade;',
                      '    proxy_set_header Connection "upgrade";']
        else:
            lines += ['    proxy_set_header Upgrade "";',
                      '    proxy_set_header Connection "";',
                      '    proxy_set_header Sec-WebSocket-Protocol "";']
        blocks.append('\n'.join(lines + ['}']))
    return '\n\n'.join(blocks) + '\n'


def render(output, domain, connector, port):
    text = locations(domain, connector, port)
    source = source_contract()
    manifest = dict(schema=1, compatibility_baseline=BASELINE, source_sha256=source,
                    renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    include_sha256=hashlib.sha256(text.encode()).hexdigest(),
                    domain=domain, connector=connector, immediate_loopback_upstream_port=port,
                    agent_route=AGENT, subprotocol=SUBPROTOCOL, location_count=5,
                    scope='review_only_single_proxy_hop', upstream_reachability_verified=False,
                    applied=False, production_ready=False, real_host_tls_waf_tested=False,
                    publish_approved=False, old_ingress_two_hop_supported=False)
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    documents = {
        INCLUDE: text,
        'source-contract.json': json.dumps(manifest, indent=2, sort_keys=True) + '\n',
        'REVIEW_ONLY.txt': ('Not an installer. Never apply without independent endpoint, site, '
                            'Host, route, TLS, WAF and supported-host review.\n'
                            'The unchanged old-ingress two-hop topology is unsupported.\n'),
    }
    # Fresh owned directory only. A failed partial write is retained, never retried as success.
    for name, value in documents.items():
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(value)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default=blueprint.DEFAULT_DOMAIN)
    parser.add_argument('--connector-id', required=True)
    parser.add_argument('--port', type=int, default=28880)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = render(args.output, args.domain, args.connector_id, args.port)
    except (OSError, ValueError, UnicodeError):
        parser.exit(1, 'review render rejected; inputs, current source or new output contract failed\n')
    print(json.dumps(dict(rendered=True, applied=False, production_ready=False,
                          include_sha256=manifest['include_sha256'])))


if __name__ == '__main__':
    main()
