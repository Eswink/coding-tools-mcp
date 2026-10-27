#!/usr/bin/env python3
"""G1 VPS deploy kit: plan, prepare-dirs, render and check.

Local file operations only. This tool never invokes container engines, remote shells,
service managers or proxy reloads; the operator runs those steps by hand (RUNBOOK.md).
Diagnostics are fixed codes only and never contain configuration or secret values.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('runtime_topology', HERE.parent / 'runtime_topology.py')
topology = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(topology)
current = topology.current

SQL_TEMPLATE = HERE / 'bootstrap-roles.sql.tmpl'
GATEWAY_OWNER = '65532:65532'
POSTGRES_OWNER = '999:999'
FOLDERS = ('gateway-private', 'ingress-private', 'postgres-private')
FILES = {'gateway-private': ('config.json', 'runtime.json'), 'ingress-private': ('nginx.conf',),
         'postgres-private': ('password',)}
EXAMPLES = {'config.json': HERE / 'config.example.json', 'runtime.json': HERE / 'runtime.example.json'}
CONFIG_KEYS = frozenset(('origin', 'prefix', 'connector', 'owner_subject', 'client_id', 'redirect_uri',
                         'client_authentication', 'bind'))
RUNTIME_KEYS = frozenset(('database_url', 'identity_key'))
PLACEHOLDER = re.compile(r'<[A-Z0-9_]+>')
UPSTREAM_PORT = 28880
REAL_IP_BLANK = 'proxy_set_header X-Real-IP "";'
REAL_IP_FORWARD = 'proxy_set_header X-Real-IP $remote_addr;'
PSQL_VALUES = {'app_password': r'[A-Za-z0-9_-]{16,128}', 'migration_password': r'[A-Za-z0-9_-]{16,128}',
               'database': r'[a-z_][a-z0-9_]{0,62}'}

PLAN = (
    ('g4_subdomain', 'Prerequisite: an independent subdomain (G4) with its own Baota site and TLS certificate.'),
    ('prepare_dirs', 'sudo python3 kit.py prepare-dirs --root <PRIVATE_ROOT>   (new absolute path; 0700 dirs, 0600 files)'),
    ('fill_private_files', 'Edit gateway-private/config.json and runtime.json; install postgres-private/password (0400).'),
    ('render', 'python3 kit.py render --private-root <PRIVATE_ROOT> --output <RENDER_DIR> ... [--trusted-proxy <CIDR>]'),
    ('install_ingress', 'Copy <RENDER_DIR>/nginx.runtime.conf to ingress-private/nginx.conf (0400, 65532:65532).'),
    ('check', 'sudo python3 kit.py check --root <PRIVATE_ROOT>   (read-only)'),
    ('operator_apply', 'By hand: compose up, bootstrap-roles.sql.tmpl phases, migrate, provision; see RUNBOOK.md.'),
    ('baota_merge', 'By hand: paste <RENDER_DIR>/baota-locations.conf into the G4 vhost; test before any reload.'),
)


class KitError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def owner(value):
    match = re.fullmatch(r'([0-9]{1,10}):([0-9]{1,10})', value or '')
    if not match:
        raise KitError('owner_must_be_uid_gid')
    return int(match.group(1)), int(match.group(2))


def new_absolute(path, code):
    path = Path(path)
    if not path.is_absolute() or any(part in ('.', '..') for part in path.parts) or path == Path('/'):
        raise KitError(code + '_must_be_absolute')
    if os.path.lexists(path):
        raise KitError(code + '_must_not_exist')
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise KitError(code + '_parent_must_be_real_directory')
    return path


# ---------------------------------------------------------------- plan

def plan():
    return {'applied': False, 'steps': [dict(id=key, action=text) for key, text in PLAN]}


# ---------------------------------------------------------------- prepare-dirs

def prepare_actions(root, gateway_owner, postgres_owner):
    root = new_absolute(root, 'root')
    owners = {'gateway-private': owner(gateway_owner), 'ingress-private': owner(gateway_owner),
              'postgres-private': owner(postgres_owner)}
    actions = [dict(op='mkdir', path=str(root)), dict(op='chmod', path=str(root), mode='0700')]
    for folder in FOLDERS:
        path = root / folder
        uid, gid = owners[folder]
        actions += [dict(op='mkdir', path=str(path)), dict(op='chmod', path=str(path), mode='0700')]
        if folder == 'gateway-private':
            for name in ('config.json', 'runtime.json'):
                actions += [dict(op='write_example', path=str(path / name), source=EXAMPLES[name].name),
                            dict(op='chmod', path=str(path / name), mode='0600'),
                            dict(op='chown', path=str(path / name), owner=f'{uid}:{gid}')]
        actions.append(dict(op='chown', path=str(path), owner=f'{uid}:{gid}'))
    return actions


def prepare_dirs(root, gateway_owner=GATEWAY_OWNER, postgres_owner=POSTGRES_OWNER, dry_run=False):
    actions = prepare_actions(root, gateway_owner, postgres_owner)
    if dry_run:
        return {'applied': False, 'dry_run': True, 'actions': actions}
    for action in actions:
        path = Path(action['path'])
        if action['op'] == 'mkdir':
            os.mkdir(path, 0o700)
        elif action['op'] == 'chmod':
            if os.path.islink(path):
                raise KitError('symlink_refused')
            os.chmod(path, int(action['mode'], 8))
        elif action['op'] == 'write_example':
            data = EXAMPLES[path.name].read_bytes()
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.fchmod(fd, 0o600)
                os.write(fd, data)
            finally:
                os.close(fd)
        elif action['op'] == 'chown':
            uid, gid = owner(action['owner'])
            if (os.lstat(path).st_uid, os.lstat(path).st_gid) != (uid, gid):
                os.chown(path, uid, gid, follow_symlinks=False)
    return {'applied': True, 'dry_run': False, 'actions': actions}


# ---------------------------------------------------------------- render

def trusted_proxies(values):
    try:
        return topology.trusted_proxy_cidrs(values)
    except ValueError:
        raise KitError('invalid_trusted_proxy') from None


def baota_locations(domain, connector, port, trusted):
    value = current.locations(domain, connector, port)
    if not trusted:
        return value
    if value.count(REAL_IP_BLANK) != 4:
        raise KitError('unexpected_reviewed_include_shape')
    return value.replace(REAL_IP_BLANK, REAL_IP_FORWARD)


def render(private_root, output, domain, connector, port, images, trusted=()):
    trusted = trusted_proxies(trusted)
    private_root = Path(private_root)
    if not private_root.is_absolute():
        raise KitError('private_root_must_be_absolute')
    output = new_absolute(output, 'output')
    try:
        compose = topology.compose(private_root, images, domain, connector, port)
        nginx = topology.ingress_config(domain, connector, trusted_proxies=trusted)
        outer = baota_locations(domain, connector, port, trusted)
    except ValueError:
        raise KitError('invalid_render_input') from None
    files = {'compose.runtime.json': json.dumps(compose, indent=2) + '\n', 'nginx.runtime.conf': nginx,
             'baota-locations.conf': outer}
    os.mkdir(output, 0o700)
    os.chmod(output, 0o700)
    manifest = dict(applied=False, trusted_proxies=list(trusted),
                    files={name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()})
    files['manifest.json'] = json.dumps(manifest, indent=2, sort_keys=True) + '\n'
    for name, text in files.items():
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, text.encode())
        finally:
            os.close(fd)
    return manifest


# ---------------------------------------------------------------- check

def _loopback_bind(value):
    if not isinstance(value, str):
        return False
    match = re.fullmatch(r'(127\.0\.0\.1|\[::1\]):([0-9]{1,5})', value)
    return bool(match) and int(match.group(2)) == UPSTREAM_PORT


def _placeholder(value):
    return isinstance(value, str) and bool(PLACEHOLDER.search(value))


def _load(path, failures, code):
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError):
        failures.append(code + '_unreadable_json')
        return None
    if not isinstance(value, dict):
        failures.append(code + '_not_object')
        return None
    return value


def check_config(value, failures):
    if set(value) != CONFIG_KEYS:
        failures.append('config_keys_mismatch')
    if any(_placeholder(item) for item in value.values()):
        failures.append('config_placeholder_present')
    if not _loopback_bind(value.get('bind')):
        failures.append('config_bind_not_loopback_28880')
    origin = value.get('origin')
    if not isinstance(origin, str) or not re.fullmatch(r'https://[a-z0-9.-]+', origin):
        failures.append('config_origin_not_https_host')
    if value.get('prefix') != '/coding-tools':
        failures.append('config_prefix_mismatch')
    if value.get('client_authentication') not in ('public', 'confidential'):
        failures.append('config_client_authentication_invalid')


def check_runtime(value, failures):
    if set(value) != RUNTIME_KEYS:
        failures.append('runtime_keys_must_be_database_url_identity_key_only')
    if any(_placeholder(item) or not isinstance(item, str) or not item for item in value.values()):
        failures.append('runtime_value_missing_or_placeholder')
    url = value.get('database_url')
    if isinstance(url, str) and not url.startswith(('postgresql://', 'postgres://')):
        failures.append('runtime_database_url_scheme')
    key = value.get('identity_key')
    if isinstance(key, str) and not re.fullmatch(r'[A-Za-z0-9_-]{43}', key):
        failures.append('runtime_identity_key_shape')


def check(root, gateway_owner=GATEWAY_OWNER, postgres_owner=POSTGRES_OWNER):
    """Read-only. Returns sorted failure codes; never values."""
    failures = []
    root = Path(root)
    owners = {'gateway-private': owner(gateway_owner), 'ingress-private': owner(gateway_owner),
              'postgres-private': owner(postgres_owner)}
    if not root.is_absolute():
        return ['root_must_be_absolute']
    try:
        info = os.lstat(root)
    except OSError:
        return ['root_missing']
    if not stat.S_ISDIR(info.st_mode):
        return ['root_not_real_directory']
    if stat.S_IMODE(info.st_mode) & 0o077:
        failures.append('root_group_or_other_bits')
    present = set(os.listdir(root))
    if present - set(FOLDERS):
        failures.append('root_unexpected_entry')
    for folder in FOLDERS:
        path = root / folder
        try:
            info = os.lstat(path)
        except OSError:
            failures.append(folder + '_missing')
            continue
        if not stat.S_ISDIR(info.st_mode):
            failures.append(folder + '_not_real_directory')
            continue
        if stat.S_IMODE(info.st_mode) != 0o700:
            failures.append(folder + '_mode_not_0700')
        if (info.st_uid, info.st_gid) != owners[folder]:
            failures.append(folder + '_owner_mismatch')
        names = set(os.listdir(path))
        if names - set(FILES[folder]):
            failures.append(folder + '_unexpected_entry')
        for name in FILES[folder]:
            item = path / name
            label = folder + '/' + name
            try:
                info = os.lstat(item)
            except OSError:
                failures.append(label + ':missing')
                continue
            if stat.S_ISLNK(info.st_mode):
                failures.append(label + ':symlink')
                continue
            if not stat.S_ISREG(info.st_mode):
                failures.append(label + ':not_regular_file')
                continue
            if stat.S_IMODE(info.st_mode) not in (0o400, 0o600):
                failures.append(label + ':mode_not_0400_or_0600')
            if (info.st_uid, info.st_gid) != owners[folder]:
                failures.append(label + ':owner_mismatch')
            if info.st_nlink != 1:
                failures.append(label + ':hardlinked')
    if any(item.is_symlink() for item in root.rglob('*')):
        failures.append('symlink_present')
    gateway = root / 'gateway-private'
    if (gateway / 'config.json').is_file() and not (gateway / 'config.json').is_symlink():
        value = _load(gateway / 'config.json', failures, 'config')
        if value is not None:
            check_config(value, failures)
    if (gateway / 'runtime.json').is_file() and not (gateway / 'runtime.json').is_symlink():
        value = _load(gateway / 'runtime.json', failures, 'runtime')
        if value is not None:
            check_runtime(value, failures)
    return sorted(set(failures))


# ---------------------------------------------------------------- SQL template

def sql_phase(name):
    """Return one `-- @phase NAME` section of the bootstrap template."""
    if name not in ('bootstrap', 'grants'):
        raise KitError('unknown_sql_phase')
    phases, active = {}, None
    for line in SQL_TEMPLATE.read_text().splitlines():
        match = re.match(r'-- @phase ([a-z]+)\b', line)
        if match:
            active = match.group(1)
            phases[active] = []
        elif active is not None:
            phases[active].append(line)
    return '\n'.join(phases[name]).strip() + '\n'


def psql_preamble(values):
    """psql `\\set` lines for stdin. Values are fixed-shape, so they never need escaping."""
    if set(values) != set(PSQL_VALUES):
        raise KitError('psql_values_mismatch')
    lines = []
    for key in sorted(values):
        if not isinstance(values[key], str) or not re.fullmatch(PSQL_VALUES[key], values[key]):
            raise KitError('psql_value_shape_' + key)
        lines.append(f'\\set {key} {values[key]}')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('plan')
    prep = sub.add_parser('prepare-dirs')
    prep.add_argument('--root', required=True)
    prep.add_argument('--gateway-owner', default=GATEWAY_OWNER)
    prep.add_argument('--postgres-owner', default=POSTGRES_OWNER)
    prep.add_argument('--dry-run', action='store_true')
    ren = sub.add_parser('render')
    ren.add_argument('--private-root', required=True)
    ren.add_argument('--output', required=True)
    for key in ('domain', 'connector', 'gateway-image', 'ingress-image', 'postgres-image'):
        ren.add_argument('--' + key, required=True)
    ren.add_argument('--port', type=int, required=True)
    ren.add_argument('--trusted-proxy', action='append', default=[],
                     help='CIDR of the proxy hop whose X-Real-IP is trusted; repeatable; default trusts nothing')
    chk = sub.add_parser('check')
    chk.add_argument('--root', required=True)
    chk.add_argument('--gateway-owner', default=GATEWAY_OWNER)
    chk.add_argument('--postgres-owner', default=POSTGRES_OWNER)
    a = p.parse_args(argv)
    try:
        if a.command == 'plan':
            result = plan()
        elif a.command == 'prepare-dirs':
            result = prepare_dirs(a.root, a.gateway_owner, a.postgres_owner, a.dry_run)
        elif a.command == 'render':
            images = dict(gateway=a.gateway_image, ingress=a.ingress_image, postgres=a.postgres_image)
            result = render(a.private_root, a.output, a.domain, a.connector, a.port, images, a.trusted_proxy)
        else:
            failures = check(a.root, a.gateway_owner, a.postgres_owner)
            result = {'ok': not failures, 'failures': failures}
            print(json.dumps(result))
            return 0 if not failures else 1
    except KitError as error:
        print(json.dumps({'ok': False, 'error': error.code}))
        return 2
    except OSError as error:
        print(json.dumps({'ok': False, 'error': 'filesystem_' + (os.strerror(error.errno).lower().replace(' ', '_')
                                                                 if error.errno else 'error')}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
