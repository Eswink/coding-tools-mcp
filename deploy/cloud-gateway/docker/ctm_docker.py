#!/usr/bin/env python3
"""One-host Docker Compose operator for the Coding Tools cloud gateway (stdlib only).

  sudo python3 ctm_docker.py setup  --private-root /opt/ctm/private --domain gw.example.com \
       --gateway-image sha256:<id> --postgres-image postgres@sha256:<d> --ingress-image nginx@sha256:<d>
  sudo python3 ctm_docker.py invite-device --output /root/ctm-invitation.json
  sudo python3 ctm_docker.py redeem-device --proof /root/ctm-proof.json --output /root/ctm-connection.json
  sudo python3 ctm_docker.py select-device --device <DEVICE_UUID>
  sudo docker compose --env-file .env -f compose.yaml up -d
  sudo python3 ctm_docker.py check
  sudo python3 ctm_docker.py migrate     # after loading a new image (upgrade)

Secrets (DB passwords, identity key, owner password, invitation tokens) are generated in memory,
written only to 0400 files owned by the container uid, or passed to containers over stdin.
They are never printed, never put on argv, and never written to .env or compose.yaml.
"""
import argparse
import base64
import getpass
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
KIT_DIR = HERE.parent / 'kit'
_spec = importlib.util.spec_from_file_location('ctm_kit', KIT_DIR / 'kit.py')
kit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kit)
topology = kit.topology

COMPOSE_FILE = HERE / 'compose.yaml'
DATABASE = 'coding_tools_identity'
PREFIX = '/coding-tools'
BIND = '127.0.0.1:28880'
GATEWAY_UID = 65532
POSTGRES_UID = 999
SECRET_FLAGS = ['--config', '/run/gateway/config.json', '--secrets-stdin']
IMAGE_RE = {'gateway': r'(sha256:[0-9a-f]{64}|[a-z0-9./_-]+@sha256:[0-9a-f]{64})',
            'postgres': r'[a-z0-9./_-]*postgres@sha256:[0-9a-f]{64}',
            'ingress': r'[a-z0-9./_-]*nginx@sha256:[0-9a-f]{64}'}
DOMAIN_RE = r'(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}'


class OperatorError(RuntimeError):
    """Fixed code only. Never carries a value, a path to a secret, or process output."""


def fail(code):
    raise OperatorError(code)


# ---------------------------------------------------------------- env file (non-secret)

def read_env(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'CTM_[A-Z_]+', key):
            fail('env_line_invalid')
        values[key] = value
    return values


def validate_env(values):
    for key, kind in (('CTM_GATEWAY_IMAGE', 'gateway'), ('CTM_POSTGRES_IMAGE', 'postgres'),
                      ('CTM_INGRESS_IMAGE', 'ingress')):
        if not re.fullmatch(IMAGE_RE[kind], values.get(key, '')):
            fail(key.lower() + '_must_be_pinned_digest')
    if not re.fullmatch(DOMAIN_RE, values.get('CTM_DOMAIN', '')):
        fail('ctm_domain_invalid')
    port = values.get('CTM_PORT', '28880')
    if not re.fullmatch(r'[0-9]{4,5}', port) or not 1024 <= int(port) <= 65535:
        fail('ctm_port_invalid')
    root = values.get('CTM_PRIVATE_ROOT', '')
    if not root.startswith('/') or any(p in ('.', '..') for p in Path(root).parts):
        fail('ctm_private_root_must_be_absolute')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,62}', values.get('CTM_PROJECT', 'coding-tools-gateway')):
        fail('ctm_project_invalid')
    return values


def write_env(path, values):
    body = ['# Written by ctm_docker.py setup. Non-secret settings only.']
    body += [f'{key}={values[key]}' for key in sorted(values)]
    data = ('\n'.join(body) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


# ---------------------------------------------------------------- private files

def write_private(path, data, uid):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    try:
        os.fchmod(fd, 0o400)
        os.write(fd, data)
        os.fchown(fd, uid, uid)
    finally:
        os.close(fd)


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1:
            fail('private_file_mode_unsafe')
        return stream.read(65536)


def owner_password(path):
    if path:
        value = read_private(path).decode().rstrip('\n')
    elif sys.stdin.isatty():
        value = getpass.getpass('Owner password (16+ chars, not echoed): ')
        if getpass.getpass('Repeat owner password: ') != value:
            fail('owner_password_mismatch')
    else:
        fail('owner_password_file_or_tty_required')
    if not 16 <= len(value.encode()) <= 1024 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail('owner_password_shape')
    return value


# ---------------------------------------------------------------- docker compose

class Compose:
    def __init__(self, env_file):
        self.env_file = Path(env_file).resolve()
        self.values = validate_env(read_env(self.env_file))
        self.root = Path(self.values['CTM_PRIVATE_ROOT'])
        self.base = ['docker', 'compose', '--ansi', 'never', '--env-file', str(self.env_file),
                     '-f', str(COMPOSE_FILE)]

    def run(self, *args, data=b'', timeout=120, check=True, label='compose'):
        result = subprocess.run([*self.base, *args], input=data, capture_output=True,
                                timeout=timeout, check=False)
        if check and result.returncode != 0:
            fail(label + '_failed')
        return result

    def config(self):
        return json.loads(self.run('--profile', 'operator', 'config', '--format', 'json',
                                   label='compose_config').stdout)

    def wait_healthy(self, service, deadline=120):
        for _ in range(deadline):
            cid = self.run('ps', '-q', service, label='compose_ps').stdout.decode().strip()
            if cid:
                state = subprocess.run(['docker', 'inspect', '--format', '{{.State.Health.Status}}', cid],
                                       capture_output=True, check=False).stdout.decode().strip()
                if state == 'healthy':
                    return
            time.sleep(1)
        fail(service + '_health_deadline')

    def psql(self, text, database='postgres'):
        result = self.run('exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', database,
                          '-v', 'ON_ERROR_STOP=1', '-At', data=text.encode(), check=False)
        if result.returncode != 0:
            fail('database_sql_failed')
        return result.stdout.decode()

    def cli(self, binary, args, packet=None, label=None):
        data = json.dumps(packet).encode() if packet is not None else b''
        result = self.run('--profile', 'operator', 'run', '--rm', '-T', '--no-deps',
                          '--entrypoint', '/usr/local/bin/' + binary, 'operator', *args,
                          data=data, timeout=60, check=False)
        if result.returncode != 0:
            code = 'cli_failed'
            for line in result.stderr.splitlines():
                try:
                    doc = json.loads(line)
                except ValueError:
                    continue
                if isinstance(doc, dict) and re.fullmatch(r'[a-z0-9_]{1,64}', str(doc.get('error', ''))):
                    code = doc['error']
            fail((label or binary + '_' + args[0]) + ':' + code)
        out = result.stdout.strip()
        return json.loads(out) if out else None

    def secrets_packet(self):
        return json.loads(read_private(self.root / 'gateway-private' / 'runtime.json'))


def require_root():
    if os.geteuid() != 0:
        fail('run_with_sudo_root_required_for_private_file_ownership')


def assert_topology(normalized, values):
    """Acceptance guard: one loopback port, internal DB, no docker.sock, no ops-console."""
    services = normalized['services']
    published = {name: svc.get('ports') for name, svc in services.items() if svc.get('ports')}
    if list(published) != ['namespace'] or len(published['namespace']) != 1:
        fail('only_namespace_may_publish')
    port = published['namespace'][0]
    if port.get('host_ip') != '127.0.0.1' or str(port.get('published')) != values.get('CTM_PORT', '28880'):
        fail('published_port_must_be_loopback')
    if not normalized['networks']['database'].get('internal'):
        fail('database_network_must_be_internal')
    if services['postgres'].get('networks', {}).keys() - {'database'}:
        fail('postgres_must_stay_internal')
    for name, svc in services.items():
        for volume in svc.get('volumes', []):
            if 'docker.sock' in str(volume.get('source', '')):
                fail('docker_socket_mount_forbidden')
        if svc.get('privileged') or svc.get('cap_add'):
            fail('privilege_forbidden')
        image = svc.get('image', '')
        if '@sha256:' not in image and not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            fail('image_must_be_pinned')
    if set(services) != {'namespace', 'gateway', 'ingress', 'postgres', 'operator'}:
        fail('unexpected_service_present')
    return {'published': f"127.0.0.1:{port.get('published')}->8080", 'database_internal': True,
            'docker_sock': False, 'ops_console': False}


# ---------------------------------------------------------------- commands

def cmd_setup(args):
    require_root()
    env_file = Path(args.env_file).resolve()
    if env_file.exists():
        fail('env_file_exists_refusing_to_overwrite')
    root = Path(args.private_root)
    values = validate_env({'CTM_PROJECT': args.project, 'CTM_GATEWAY_IMAGE': args.gateway_image,
                           'CTM_POSTGRES_IMAGE': args.postgres_image, 'CTM_INGRESS_IMAGE': args.ingress_image,
                           'CTM_PRIVATE_ROOT': str(root), 'CTM_DOMAIN': args.domain, 'CTM_PORT': str(args.port)})
    password = owner_password(args.owner_password_file)
    if root.exists():
        fail('private_root_exists_refusing_to_overwrite')
    origin = 'https://' + args.domain
    config = dict(origin=origin, prefix=PREFIX, connector=str(uuid.uuid4()), owner_subject=str(uuid.uuid4()),
                  client_id=args.client_id, redirect_uri=args.redirect_uri,
                  client_authentication=args.client_authentication, bind=BIND)
    app_password, migration_password = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    packet = dict(database_url=f'postgresql://ctm_app:{app_password}@postgres:5432/{DATABASE}',
                  identity_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))
    migration = dict(packet, database_url=f'postgresql://ctm_migration:{migration_password}@postgres:5432/{DATABASE}')
    nginx = topology.ingress_config(args.domain, config['connector'], trusted_proxies=tuple(args.trusted_proxy),
                                    rate_limits=True)
    # Private root: 0700 root-owned, folders 0700 owned by the consuming container uid, files 0400.
    os.mkdir(root, 0o700)
    for folder, uid, files in (
            ('gateway-private', GATEWAY_UID, {'config.json': json.dumps(config, indent=2) + '\n',
                                              'runtime.json': json.dumps(packet) + '\n'}),
            ('ingress-private', GATEWAY_UID, {'nginx.conf': nginx}),
            ('postgres-private', POSTGRES_UID, {'password': secrets.token_urlsafe(32)})):
        os.mkdir(root / folder, 0o700)
        for name, body in files.items():
            write_private(root / folder / name, body.encode(), uid)
        os.chown(root / folder, uid, uid)
    failures = kit.check(root)
    if failures:
        fail('kit_check:' + ','.join(failures))
    write_env(env_file, values)
    dc = Compose(env_file)
    guard = assert_topology(dc.config(), values)
    dc.run('up', '-d', 'postgres', timeout=180, label='compose_up_postgres')
    dc.wait_healthy('postgres')
    dc.psql(kit.psql_preamble(dict(app_password=app_password, migration_password=migration_password,
                                   database=DATABASE)) + kit.sql_phase('bootstrap'))
    dc.cli('coding-tools-gateway', ['migrate', *SECRET_FLAGS], migration)
    dc.psql(kit.sql_phase('grants'), database=DATABASE)
    dc.psql(f"ALTER ROLE ctm_migration PASSWORD '{secrets.token_urlsafe(32)}';\n")  # discard migration credential
    dc.cli('coding-tools-gateway', ['provision-owner', *SECRET_FLAGS], dict(packet, password=password))
    client = dict(packet)
    if args.client_authentication == 'confidential':
        client['client_secret'] = owner_password(args.client_secret_file)
    dc.cli('coding-tools-gateway', ['register-client', *SECRET_FLAGS], client)
    del password, migration, migration_password, client
    print(json.dumps({'setup': 'ok', 'env_file': str(env_file), 'origin': origin, 'prefix': PREFIX,
                      'connector': config['connector'], 'owner_subject': config['owner_subject'],
                      'client_id': config['client_id'], 'mcp_url': f"{origin}{PREFIX}/mcp/{config['connector']}",
                      'guard': guard, 'next': 'invite-device -> redeem-device -> select-device -> compose up -d'},
                     indent=2))


def write_out(path, document):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(document, stream)
        stream.write('\n')


def cmd_invite(args):
    require_root()
    dc = Compose(args.env_file)
    invitation = dc.cli('coding-tools-gateway', ['invite-device', *SECRET_FLAGS, '--output-stdout'],
                        dc.secrets_packet())
    write_out(args.output, invitation)
    print(json.dumps({'invite_device': 'ok', 'output': str(args.output), 'mode': '0600'}))


def cmd_redeem(args):
    require_root()
    dc = Compose(args.env_file)
    proof = json.loads(read_private(args.proof))
    if 'pkcs8' in json.dumps(proof):
        fail('proof_must_not_contain_private_key')
    connection = dc.cli('coding-tools-gateway', ['redeem-device', '--config', '/run/gateway/config.json',
                        '--bundle-stdin', '--output-stdout'], dict(secrets=dc.secrets_packet(), proof=proof))
    write_out(args.output, connection)
    print(json.dumps({'redeem_device': 'ok', 'device': connection.get('device'), 'output': str(args.output)}))


def cmd_select(args):
    require_root()
    if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', args.device):
        fail('device_uuid_invalid')
    dc = Compose(args.env_file)
    dc.cli('coding-tools-control-gateway', ['select-device', *SECRET_FLAGS, '--device', args.device],
           dc.secrets_packet())
    print(json.dumps({'select_device': 'ok', 'device': args.device}))


def cmd_migrate(args):
    """Upgrade path: one-shot random ctm_migration password (never persisted), migrate, re-grant."""
    require_root()
    dc = Compose(args.env_file)
    migration_password = secrets.token_urlsafe(32)
    if not re.fullmatch(kit.PSQL_VALUES['migration_password'], migration_password):
        fail('migration_password_shape')
    dc.psql(f"ALTER ROLE ctm_migration PASSWORD '{migration_password}';\n")
    migration = dict(dc.secrets_packet(),
                     database_url=f'postgresql://ctm_migration:{migration_password}@postgres:5432/{DATABASE}')
    dc.cli('coding-tools-gateway', ['migrate', *SECRET_FLAGS], migration)
    dc.psql(kit.sql_phase('grants'), database=DATABASE)
    dc.psql(f"ALTER ROLE ctm_migration PASSWORD '{secrets.token_urlsafe(32)}';\n")
    print(json.dumps({'migrate': 'ok'}))


def cmd_check(args):
    dc = Compose(args.env_file)
    report = {'topology': assert_topology(dc.config(), dc.values)}
    if os.geteuid() == 0:
        report['private_root_failures'] = kit.check(dc.root)
    print(json.dumps(report, indent=2))
    return 1 if report.get('private_root_failures') else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env-file', default=str(HERE / '.env'))
    sub = parser.add_subparsers(dest='command', required=True)
    setup = sub.add_parser('setup', help='private files + postgres roles + migrate + owner + OAuth client')
    setup.add_argument('--private-root', required=True)
    setup.add_argument('--domain', required=True)
    setup.add_argument('--port', type=int, default=28880)
    setup.add_argument('--project', default='coding-tools-gateway')
    setup.add_argument('--gateway-image', required=True)
    setup.add_argument('--postgres-image', required=True)
    setup.add_argument('--ingress-image', required=True)
    setup.add_argument('--client-id', default='coding-tools-mcp')
    setup.add_argument('--redirect-uri', required=True)
    setup.add_argument('--client-authentication', choices=('public', 'confidential'), default='public')
    setup.add_argument('--client-secret-file')
    setup.add_argument('--owner-password-file')
    setup.add_argument('--trusted-proxy', action='append', default=[])
    invite = sub.add_parser('invite-device')
    invite.add_argument('--output', required=True)
    redeem = sub.add_parser('redeem-device')
    redeem.add_argument('--proof', required=True)
    redeem.add_argument('--output', required=True)
    select = sub.add_parser('select-device')
    select.add_argument('--device', required=True)
    sub.add_parser('migrate', help='upgrade: migrate with a one-shot migration password, then re-grant')
    sub.add_parser('check')
    args = parser.parse_args(argv)
    try:
        return {'setup': cmd_setup, 'invite-device': cmd_invite, 'redeem-device': cmd_redeem,
                'select-device': cmd_select, 'migrate': cmd_migrate, 'check': cmd_check}[args.command](args) or 0
    except (OperatorError, kit.KitError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(json.dumps({'error': 'command_timeout'}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
