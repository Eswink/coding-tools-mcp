"""Exact public JSON projections. Never export raw evidence or exception args."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_PUBLIC = 2 * 1024 * 1024
RAW_NAMES = ('LAUNCH.json', 'NATIVE-CLOSURE.json', 'cases/receipt.json',
             'cases/cases.log', 'cases/session-stdout.log',
             'cases/session-stderr.log', 'controller-stdout.log',
             'controller-stderr.log')
FILES = ('PUBLIC-SAFE-RESULT.json', 'SOURCE-BINDING-SAFE.json',
         'TOOL-PROVENANCE-SAFE.json', 'RAW-SEAL-DIGESTS-SAFE.json')
SCHEMA = 'rc070-public-projection-1'
UNKNOWN = []


def exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError('Exact public object keys required')


def enum(value, options):
    if type(value) is not str or value not in options:
        raise ValueError('Public enum mismatch')


def integer(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Public integer bound')


def digest(value, length=64, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not str or not re.fullmatch('[0-9a-f]{' + str(length) + '}', value):
        raise ValueError('Literal digest required')


def bool_only(value):
    if type(value) is not bool:
        raise ValueError('Boolean required')


def profile(value, count):
    exact(value, ('status', 'loaded', 'executed', 'success', 'failures', 'errors',
                  'skips', 'xfails', 'xpasses'))
    enum(value['status'], ('NOT_RUN', 'BLOCKED', 'FAIL_UNKNOWN', 'QUALIFIED'))
    for key in set(value) - {'status'}:
        integer(value[key], count)
    if value['status'] in ('NOT_RUN', 'BLOCKED') and any(value[k] for k in set(value) - {'status'}):
        raise ValueError('Nonexecuted profile counts')
    if value['status'] == 'QUALIFIED' and (
            any(value[k] != count for k in ('loaded', 'executed', 'success'))
            or any(value[k] for k in ('failures', 'errors', 'skips', 'xfails', 'xpasses'))):
        raise ValueError('Qualified count mismatch')


def validate_public_projection(name, value):
    if name not in FILES or type(value) is not dict or value.get('schema') != SCHEMA:
        raise ValueError('Public schema mismatch')
    if name == FILES[0]:
        exact(value, ('schema', 'scope', 'setup_status', 'profiles', 'phases',
                      'release_authorized', 'product_install_runs', 'projection_only'))
        if (value['scope'] != 'compatible-publisher-component-only'
                or value['release_authorized'] is not False
                or type(value['product_install_runs']) is not int
                or value['product_install_runs'] != 0 or value['projection_only'] is not True):
            raise ValueError('Component scope mismatch')
        enum(value['setup_status'], ('NOT_RUN', 'BLOCKED', 'FAIL', 'PASS'))
        exact(value['profiles'], ('necessary85', 'original300'))
        for name, count in [('necessary85', 85), ('original300', 300)]:
            profile(value['profiles'][name], count)
        exact(value['phases'], ('gpg', 'build', 'install', 'probe'))
        for name, bound in [('gpg', 60000), ('build', 484000), ('install', 64000), ('probe', 34000)]:
            row = value['phases'][name]
            exact(row, ('status', 'exit_code', 'elapsed_ms'))
            enum(row['status'], ('NOT_RUN', 'BLOCKED', 'FAIL', 'PASS'))
            if row['exit_code'] is not None:
                if type(row['exit_code']) is not int or not -128 <= row['exit_code'] <= 255:
                    raise ValueError('Exit range')
            if row['elapsed_ms'] is not None:
                integer(row['elapsed_ms'], bound)
            if row['status'] == 'PASS' and row['exit_code'] != 0:
                raise ValueError('Phase pass without realzero')
    elif name == FILES[1]:
        exact(value, ('schema', 'repository', 'management_commit', 'source_tree',
                      'backup_commit', 'pure_source_count', 'runner_bytes',
                      'runner_sha256', 'fixture_sha256', 'inventory85_sha256',
                      'inventory300_sha256'))
        if (value['repository'] != 'Eswink/coding-tools-mcp'
                or value['source_tree'] != 'b9cfb8a0b58f8e0863c764e50cf3d38920eefeae'
                or type(value['pure_source_count']) is not int
                or value['pure_source_count'] != 1878
                or type(value['runner_bytes']) is not int or value['runner_bytes'] != 6259):
            raise ValueError('Exact original source binding required')
        for key in ('management_commit', 'source_tree', 'backup_commit'):
            digest(value[key], 40)
        for key in ('runner_sha256', 'fixture_sha256', 'inventory85_sha256', 'inventory300_sha256'):
            digest(value[key])
        if (value['runner_sha256'] != '687ec2a408507284b557806569d6f5df0ead625b9c282b9c8bbb74782d633f0a'
                or value['fixture_sha256'] != '233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5'):
            raise ValueError('Runner or fixture drift')
    elif name == FILES[2]:
        hashes = ('archive_sha256', 'signature_sha256', 'key_sha256', 'tar_sha256',
                  'builder_source_sha256', 'installed_binary_sha256',
                  'build_log_sha256', 'install_log_sha256')
        exact(value, ('schema', 'git_version', 'image_platform', 'runtime_kind',
                      'image_provenance', *hashes, 'archive_bytes', 'signature_bytes',
                      'key_bytes', 'tar_bytes', 'gpg_primary', 'gpg_subkey',
                      'signature_valid', 'system_git_unchanged', 'prefix_preabsent',
                      'configs_count', 'gitk_upstream_fallback_observed'))
        if value['git_version'] != '2.55.0' or value['image_platform'] != 'linux/amd64':
            raise ValueError('Tool version/platform')
        enum(value['runtime_kind'], ('HOSTED_VM', 'CONTAINER'))
        image = value['image_provenance']
        exact(image, ('kind', 'image_version', 'container_manifest_digest',
                      'container_config_digest', 'provenance_verified'))
        if image['kind'] != value['runtime_kind']:
            raise ValueError('Realm kind mismatch')
        bool_only(image['provenance_verified'])
        if image['kind'] == 'HOSTED_VM':
            if (type(image['image_version']) is not str
                    or not re.fullmatch('[0-9][0-9.\-]{0,79}', image['image_version'])
                    or image['container_manifest_digest'] is not None
                    or image['container_config_digest'] is not None
                    or image['provenance_verified'] is not False):
                raise ValueError('Hosted label is not image digest proof')
        else:
            if image['image_version'] is not None:
                raise ValueError('Container identity mismatch')
            digest(image['container_manifest_digest'])
            digest(image['container_config_digest'])
            # No actual running-container binding exists in this source scope.
            if image['provenance_verified'] is not False:
                raise ValueError('Unimplemented container provenance')
        for key in hashes:
            digest(value[key], nullable=key in ('installed_binary_sha256', 'build_log_sha256', 'install_log_sha256'))
        for key, number in [('archive_bytes', 8177180), ('signature_bytes', 566),
                            ('key_bytes', 68820), ('tar_bytes', 51916800)]:
            if type(value[key]) is not int or value[key] != number:
                raise ValueError('Fixed tool byte identity')
        for key, expected in [('gpg_primary', '96E07AF25771955980DAD10020D04E5A713660A7'),
                              ('gpg_subkey', 'E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB')]:
            if value[key] != expected:
                raise ValueError('Pinned signer mismatch')
        for key in ('signature_valid', 'system_git_unchanged', 'prefix_preabsent'):
            bool_only(value[key])
        if type(value['configs_count']) is not int or value['configs_count'] not in (0, 2):
            raise ValueError('Owned config count')
        if value['gitk_upstream_fallback_observed'] is not None:
            bool_only(value['gitk_upstream_fallback_observed'])
    else:
        exact(value, ('schema', 'projection_only', 'original_raw_available_privately', 'profiles'))
        if value['projection_only'] is not True:
            raise ValueError('Raw digest derivative required')
        enum(value['original_raw_available_privately'], ('VERIFIED', 'UNAVAILABLE', 'UNKNOWN'))
        # No genuinely private durable channel is implemented in this controller.
        if value['original_raw_available_privately'] == 'VERIFIED':
            raise ValueError('Private persistence unsupported')
        exact(value['profiles'], ('necessary85', 'original300'))
        for row in value['profiles'].values():
            exact(row, ('original_seal_sha256', 'files'))
            digest(row['original_seal_sha256'], nullable=True)
            if type(row['files']) is not list or len(row['files']) not in (0, 8):
                raise ValueError('Original raw inventory bound')
            seen = set()
            for item in row['files']:
                exact(item, ('name', 'bytes', 'sha256'))
                enum(item['name'], RAW_NAMES)
                if item['name'] in seen:
                    raise ValueError('Duplicate raw row')
                seen.add(item['name'])
                integer(item['bytes'], 32 * 1024 * 1024)
                digest(item['sha256'])
            if bool(row['files']) != (row['original_seal_sha256'] is not None):
                raise ValueError('Seal without original inventory')
    return value


def parse_projection(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def project_public_evidence(records, output, secrets=()):
    exact(records, FILES)
    buffers = {}
    for name in FILES:
        validate_public_projection(name, records[name])
        raw = (json.dumps(records[name], sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')
        if (re.search(rb'(?i)(BEGIN [A-Z ]*PRIVATE KEY|authorization|gh[pousr]_|github_pat_|bearer )', raw)
                or any(type(secret) is bytes and len(secret) >= 6 and secret in raw for secret in secrets)):
            raise ValueError('Public content refused')
        buffers[name] = raw
    if sum(map(len, buffers.values())) > MAX_PUBLIC:
        raise ValueError('Public output bound')
    # No profile evidence is ever admitted by the public exporter.
    if records[FILES[0]]['profiles']['original300']['status'] != 'NOT_RUN':
        raise ValueError('Private durable evidence unavailable; 300 not authorized')
    output = Path(output)
    if output.parent.resolve() != output.parent:
        raise ValueError('Literal owned parent required')
    if os.path.lexists(output):
        raise ValueError('Fresh public output required')
    pending = output.with_name(output.name + '.pending-private')
    pending.mkdir(mode=0o700)
    directory = os.open(pending, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    primary, errors, current = None, [], None
    try:
        for name in FILES:
            current = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
            try:
                info = os.fstat(current)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise ValueError('Exclusive owned public file required')
                remaining = memoryview(buffers[name])
                while remaining:
                    n = os.write(current, remaining)
                    if not 0 < n <= len(remaining):
                        raise ValueError('Incomplete public write')
                    remaining = remaining[n:]
                os.fsync(current)
            except BaseException as error:
                primary = error
            finally:
                fd, current = current, None
                try:
                    os.close(fd)
                except BaseException as error:
                    UNKNOWN.append(('file', fd))
                    errors.append(error)
            if primary is not None or errors:
                break
    except BaseException as error:
        if primary is None:
            primary = error
        else:
            errors.append(error)
    finally:
        try:
            os.close(directory)
        except BaseException as error:
            UNKNOWN.append(('directory', directory))
            errors.append(error)
    if errors:
        raise BaseExceptionGroup('Projection primary and cleanup failures',
                                 ([primary] if primary is not None else []) + errors)
    if primary is not None:
        raise primary
    # Public path appears only after complete validation and all successful closes.
    # Partial or UNKNOWN candidate remains private and cannot match upload path.
    os.rename(pending, output)
    return {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            for name, raw in buffers.items()}
