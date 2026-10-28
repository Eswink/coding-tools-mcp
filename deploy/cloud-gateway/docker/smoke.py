#!/usr/bin/env python3
"""Disposable end-to-end smoke for compose.yaml + ctm_docker.py (root, local Docker only).

  sudo python3 smoke.py --gateway-image sha256:<id> --postgres-image postgres@sha256:<d> \
       --ingress-image nginx@sha256:<d> [--evidence out.json] [--keep]

Uses the placeholder domain gateway.example.invalid and fresh random secrets in a temp dir.
The device enrollment that a desktop MCP app normally performs is simulated with the image's own
coding-tools-agent (network none). Evidence JSON carries status codes and ids only, never secrets.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ctm_docker as op  # noqa: E402

DOMAIN = 'gateway.example.invalid'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def probe(port, path, host=DOMAIN, method='GET'):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=8)
    try:
        conn.request(method, path, headers={'Host': host})
        response = conn.getresponse()
        response.read()
        return response.status
    finally:
        conn.close()


def agent(image, mount, args, packet=None):
    data = json.dumps(packet).encode() if packet is not None else b''
    result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none', '--read-only', '--user', '65532:65532',
                             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                             '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532',
                             '-v', f'{mount}:/run/enroll:ro', '--entrypoint', '/usr/local/bin/coding-tools-agent',
                             image, *args], input=data, capture_output=True, timeout=60, check=False)
    if result.returncode != 0:
        op.fail('agent_' + args[0] + '_failed')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway-image', required=True)
    parser.add_argument('--postgres-image', required=True)
    parser.add_argument('--ingress-image', required=True)
    parser.add_argument('--evidence')
    parser.add_argument('--keep', action='store_true')
    args = parser.parse_args()
    op.require_root()
    work = Path(tempfile.mkdtemp(prefix='ctm-docker-smoke-'))
    os.chmod(work, 0o700)
    project = 'ctm-smoke-' + secrets.token_hex(4)
    env_file = work / 'smoke.env'
    port = free_port()
    evidence = {'project': project, 'domain': DOMAIN, 'port': port, 'steps': []}
    dc = None
    try:
        password_file = work / 'owner-password'
        fd = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, secrets.token_urlsafe(32).encode())
        os.close(fd)
        op.main(['--env-file', str(env_file), 'setup', '--private-root', str(work / 'private'), '--domain', DOMAIN,
                 '--port', str(port), '--project', project, '--gateway-image', args.gateway_image,
                 '--postgres-image', args.postgres_image, '--ingress-image', args.ingress_image,
                 '--redirect-uri', 'https://client.example.invalid/callback',
                 '--owner-password-file', str(password_file)]) == 0 or op.fail('setup_failed')
        evidence['steps'].append('setup')
        dc = op.Compose(env_file)
        config = json.loads(op.read_private(dc.root / 'gateway-private' / 'config.json'))
        enroll = work / 'enroll'
        os.mkdir(enroll, 0o700)
        op.write_private(enroll / 'enrollment.json',
                         json.dumps({k: config[k] for k in ('origin', 'prefix', 'connector')}).encode(), 65532)
        os.chown(enroll, 65532, 65532)
        # Gateway must refuse to serve before a device is selected (fail closed).
        key = agent(args.gateway_image, enroll, ['generate-key', '--output-stdout'])
        op.main(['--env-file', str(env_file), 'invite-device', '--output', str(work / 'invitation.json')]) == 0 \
            or op.fail('invite_failed')
        invitation = json.loads(op.read_private(work / 'invitation.json'))
        proof = agent(args.gateway_image, enroll, ['prove-enrollment', '--config', '/run/enroll/enrollment.json',
                                                   '--bundle-stdin', '--output-stdout'],
                      dict(invitation=invitation, key=key))
        fd = os.open(work / 'proof.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, json.dumps(proof).encode())
        os.close(fd)
        op.main(['--env-file', str(env_file), 'redeem-device', '--proof', str(work / 'proof.json'),
                 '--output', str(work / 'connection.json')]) == 0 or op.fail('redeem_failed')
        connection = json.loads(op.read_private(work / 'connection.json'))
        evidence['steps'] += ['invite-device', 'prove-enrollment(agent)', 'redeem-device']
        op.main(['--env-file', str(env_file), 'select-device', '--device', connection['device']]) == 0 \
            or op.fail('select_failed')
        evidence['steps'].append('select-device')
        dc.run('up', '-d', timeout=180, label='compose_up')
        evidence['steps'].append('compose up -d')
        dc.wait_healthy('gateway', deadline=90)
        evidence['gateway_container_health'] = 'healthy'
        op.main(['--env-file', str(env_file), 'migrate']) == 0 or op.fail('upgrade_migrate_failed')
        op.main(['--env-file', str(env_file), 'check']) == 0 or op.fail('check_failed')
        evidence['steps'] += ['migrate(upgrade path, idempotent)', 'check']
        prefix = op.PREFIX
        for _ in range(30):
            try:
                if probe(port, prefix + '/health/live') == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        evidence['http'] = {
            'health_live': probe(port, prefix + '/health/live'),
            'health_ready': probe(port, prefix + '/health/ready'),
            'oauth_protected_resource': probe(port, '/.well-known/oauth-protected-resource' + prefix + '/mcp/'
                                             + config['connector']),
            'wrong_host_rejected': probe(port, prefix + '/health/live', host='evil.example.invalid'),
        }
        ps = json.loads('[' + ','.join(dc.run('ps', '--format', 'json', label='compose_ps').stdout.decode()
                                       .strip().splitlines()) + ']')
        evidence['services'] = sorted((row['Service'], row['State'], row.get('Health', '')) for row in ps)
        evidence['published'] = sorted({f"{p['URL']}:{p['PublishedPort']}->{p['TargetPort']}"
                                        for row in ps for p in (row.get('Publishers') or []) if p.get('PublishedPort')})
        users = {}
        for row in ps:
            info = json.loads(subprocess.run(['docker', 'inspect', row['ID']], capture_output=True, check=True).stdout)[0]
            mounts = [m.get('Source', '') for m in info['Mounts']]
            users[row['Service']] = {'user': info['Config']['User'], 'read_only': info['HostConfig']['ReadonlyRootfs'],
                                     'cap_drop': info['HostConfig']['CapDrop'],
                                     'docker_sock_mounted': any('docker.sock' in m for m in mounts),
                                     'networks': sorted(info['NetworkSettings']['Networks'])}
        evidence['containers'] = users
        evidence['topology_guard'] = op.assert_topology(dc.config(), dc.values)
        evidence['private_root_kit_check_failures'] = op.kit.check(dc.root)
        image = json.loads(subprocess.run(['docker', 'image', 'inspect', args.gateway_image],
                                          capture_output=True, check=True).stdout)[0]
        evidence['gateway_image'] = {'id': image['Id'], 'user': image['Config']['User'],
                                     'labels': image['Config']['Labels'],
                                     'env': image['Config']['Env']}
        # Secret leak scan: values must not appear in logs, rendered compose config, or the .env file.
        runtime = json.loads(op.read_private(dc.root / 'gateway-private' / 'runtime.json'))
        values = [runtime['identity_key'], runtime['database_url'].split(':')[2].split('@')[0],
                  op.read_private(dc.root / 'postgres-private' / 'password').decode(),
                  op.read_private(password_file).decode(), invitation.get('token', ''), key.get('pkcs8', '')]
        haystack = (dc.run('logs', '--no-color', label='compose_logs').stdout
                    + dc.run('--profile', 'operator', 'config', label='compose_config').stdout
                    + env_file.read_bytes() + json.dumps(evidence).encode())
        evidence['secret_leak_scan'] = {'values_checked': sum(1 for v in values if v),
                                        'found': sum(1 for v in values if v and v.encode() in haystack)}
        evidence['compose_yaml_sha256'] = hashlib.sha256((HERE / 'compose.yaml').read_bytes()).hexdigest()
        ok = (evidence['http']['health_live'] == 200 and evidence['http']['health_ready'] == 200
              and evidence['http']['wrong_host_rejected'] == 421 and not evidence['private_root_kit_check_failures']
              and evidence['published'] == [f'127.0.0.1:{port}->8080']
              and evidence['secret_leak_scan']['found'] == 0)
        evidence['result'] = 'PASS' if ok else 'FAIL'
        return 0 if ok else 1
    except op.OperatorError as error:
        evidence['result'] = 'FAIL'
        evidence['error'] = str(error)
        return 1
    finally:
        if dc is None and env_file.exists():
            dc = op.Compose(env_file)
        if dc is not None and not args.keep:
            dc.run('--profile', 'operator', 'down', '-v', '--remove-orphans', timeout=120, check=False)
            evidence['teardown'] = 'down -v'
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        text = json.dumps(evidence, indent=2, sort_keys=True)
        print(text)
        if args.evidence:
            Path(args.evidence).write_text(text + '\n')


if __name__ == '__main__':
    sys.exit(main())
