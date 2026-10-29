"""Hosted-CI-only image fixture: no service deployment or real credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from cloud_release_bundle import BINS, identity
from final_rc_evidence import read_json
from rc_version_gate import require


FLAGS = ['--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
         '--security-opt', 'no-new-privileges:true', '--pids-limit', '128', '--memory', '512m',
         '--user', '65532:65532', '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532']


def metadata(value, image, expected):
    require(value.get('Id') == image and value.get('Architecture') == 'amd64' and value.get('Os') == 'linux',
            'image identity/platform mismatch')
    config = value.get('Config', {})
    require(config.get('User') == '65532:65532'
            and config.get('Entrypoint') == ['/usr/local/bin/coding-tools-mcp-gateway']
            and config.get('Cmd') == ['--help'], 'unexpected default image user/entrypoint')
    labels = config.get('Labels', {})
    require(labels.get('org.opencontainers.image.revision') == expected['source_sha']
            and labels.get('org.opencontainers.image.version') == expected['product_version'], 'image source/version mismatch')
    require(not config.get('Volumes') and not config.get('ExposedPorts'), 'unexpected image state/port declaration')


def command(image, binary, args, fixture=None):
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) is not None, 'immutable local image ID required')
    require(binary in BINS or binary in ('id', 'sha256sum'), 'fixed image executable required')
    path = '/usr/bin/' + binary if binary in ('id', 'sha256sum') else '/usr/local/bin/' + binary
    argv = ['docker', 'run', *FLAGS]
    if fixture is not None:
        require(fixture.is_absolute() and ',' not in str(fixture), 'invalid fixture mount')
        argv += ['--mount', f'type=bind,src={fixture},dst=/run/fixture,readonly']
    return [*argv, '--entrypoint', path, image, *args]


def invoke(image, binary, args, fixture=None):
    return subprocess.run(command(image, binary, args, fixture), capture_output=True, timeout=40, check=False)


def exact_error(result, error):
    require(result.returncode == 1 and not result.stdout and
            json.loads(result.stderr) == {'ok': False, 'error': error}, 'wrong fixture failure stage')


def run(image, context, expected):
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'Eswink/coding-tools-mcp', 'hosted disposable CI only')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) is not None, 'immutable local image required')
    inspected = subprocess.check_output(['docker', 'image', 'inspect', image], timeout=20)
    entries = json.loads(inspected); require(len(entries) == 1, 'one exact image required')
    metadata(entries[0], image, expected)
    manifest = read_json(context / 'manifest.json')
    require(all(manifest.get(k) == v for k,v in expected.items()), 'consumed archive identity mismatch')
    uid = invoke(image, 'id', ['-u'])
    require(uid.returncode == 0 and uid.stdout.strip() == b'65532', 'non-root runtime UID required')
    tests = ['image_metadata', 'actual_non_root_uid']
    for name in BINS:
        observed = invoke(image, 'sha256sum', ['/usr/local/bin/' + name])
        require(observed.returncode == 0 and observed.stdout.decode().split()[0] == manifest['binaries'][name]['sha256'],
                'container binary differs from accepted release archive')
        for arg in ('--help', '--version'):
            result = invoke(image, name, [arg])
            require(result.returncode == 0 and not result.stderr and name.encode() in result.stdout, 'container CLI failed')
            if arg == '--version':
                require(result.stdout.decode().split()[:2] == [name, expected['product_version']], 'container version drift')
        tests.append(name + '_exact_bytes_and_cli')
    fixture = Path(tempfile.mkdtemp(prefix='ctm-image-public-fixture-', dir=os.environ['RUNNER_TEMP']))
    try:
        config = dict(origin='https://gateway.example.invalid', prefix='/coding-tools',
                      connector='00000000-0000-0000-0000-000000000001',
                      owner_subject='00000000-0000-0000-0000-000000000002', client_id='image-fixture',
                      redirect_uri='https://client.example.invalid/callback', client_authentication='public',
                      bind='127.0.0.1:28880')
        (fixture/'config.json').write_text(json.dumps(config))
        # Intentionally not a credential document. Successful read reaches the
        # parser's exact rejection; no signing key, password or DSN is created.
        (fixture/'secret-input.json').write_text('{"public_noncredential_fixture":true}')
        for path in fixture.iterdir(): path.chmod(0o400)
        subprocess.run(['sudo','chown','-R','65532:65532',str(fixture)], check=True, timeout=10)
        result = invoke(image, 'coding-tools-gateway', ['check-config','--config','/run/fixture/config.json'], fixture)
        require(result.returncode == 0 and json.loads(result.stdout) == {'ok':True,'check':'configuration_only'},
                'private config mount rejected')
        args = ['serve','--config','/run/fixture/config.json','--secrets-file','/run/fixture/secret-input.json']
        exact_error(invoke(image, 'coding-tools-mcp-gateway', args, fixture), 'invalid_secret_input')
        tests.append('private_mount_reaches_parser_without_credentials')
        subprocess.run(['sudo','chmod','0444',str(fixture/'secret-input.json')], check=True, timeout=10)
        exact_error(invoke(image, 'coding-tools-mcp-gateway', args, fixture), 'file_protection_failed')
        tests.append('world_readable_secret_mount_rejected')
    finally:
        # Only this newly created fixture directory is removed. No caller path
        # or existing host data can reach this cleanup operation.
        subprocess.run(['sudo','rm','-rf','--',str(fixture)], check=True, timeout=10)
    return dict(expected, passed=True, image_id=image, tests=tests, publish_approved=False,
                production_touched=False, network_mode='none',
                scope='Image build, exact CLI bytes and protected-file fixture only; functional ingress requires the separate exact-source container topology gate')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True);parser.add_argument('--version',required=True)
    parser.add_argument('--context',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    value=run(args.image,args.context.resolve(),identity(root,args.version))
    args.output.write_text(json.dumps(value,indent=2)+'\n')


if __name__ == '__main__':main()
