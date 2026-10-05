#!/usr/bin/env python3
"""Hosted-only authenticated native TLS two-hop proof; private material stays private."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import threading
import time

# Ubuntu22's Python3.10 executes only the stdlib-only container branch.
if len(sys.argv) > 1 and sys.argv[1] == '--inside':
    ROOT = Path(__file__).resolve().parents[2]
    DOMAIN = 'gateway.example.invalid'
    def require(value, label):
        if not value:
            raise RuntimeError(label)
else:
    from container_fixture import Fixture, FixtureFailure, ROOT, require, topology
    from run_current_nginx_checks import current, DOMAIN, source_identity
    from run_current_nginx_runtime import inner_ingress_evidence

PREFIX = 'tools::cloud_host::live::wss_tests::'
BASELINE = tuple(PREFIX + name for name in (
    'actual_native_pause_resume_fences_stale_cloud_projection_and_pending_allocation',
    'agent_absence_keeps_oauth_refresh_and_public_catalog_available_without_queue',
    'catalog_tests::cloud_worktree_catalog_executes_real_owned_create_list_remove_without_root_override',
    'catalog_tests::full_catalog_routes_real_read_and_mutation_without_replay_or_foreign_output',
    'cloud_oauth_forgery_and_foreign_session_never_approve_or_disclose_native_files',
    'cloud_request_reaches_native_pending_and_only_native_decision_enables_real_tools',
    'managed_drain_tests::cancelled_native_waiter_keeps_real_journal_locked_until_callback_finishes',
    'managed_drain_tests::managed_native_approval_dispatch_and_stop_release_only_after_drain',
    'managed_drain_tests::queued_native_callback_after_stop_is_rejected_before_effects',
    'native_agent_restart_preserves_request_tombstone_without_reexecution',
    'native_revoke_and_both_signed_drain_barriers_precede_successor_execution'))
NEW = tuple(PREFIX + 'two_hop_tests::tls_two_hop_' + name for name in (
    'native_pending_grant_read_foreign', 'reconnect_generation_restart_no_replay',
    'native_grant_revoke_survives_restart', 'device_revoke_survives_gateway_database_restart',
    'gateway_shutdown_drains_authenticated_socket', 'managed_callback_retains_journal_until_drain',
    'untrusted_ca_refused', 'wrong_hostname_refused', 'expired_certificate_refused'))
ALL = tuple(sorted(BASELINE + NEW))
OPS = frozenset(('inspect', 'gateway_stop', 'gateway_start', 'revoke_device', 'restart_database'))
MANIFEST = Path('/usr/share/coding-tools/native-manifest.json')
RUNNER = Path(__file__).resolve()


def verify_source(manifest):
    identity = source_identity()
    require(manifest['source_sha'] == identity['source_sha'] and
            manifest['source_tree'] == identity['source_tree'] and
            manifest['source_root'] == str(ROOT), 'native_source_drift')
    require(re.fullmatch(r'ubuntu@sha256:[0-9a-f]{64}', manifest['base_image']), 'native_immutable_base')
    require(set(manifest['binaries']) == {'native-tests', 'native-fixture'} and all(
        re.fullmatch('[0-9a-f]{64}', value) for value in manifest['binaries'].values()), 'native_binary_manifest')
    require(not subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', 'status', '--porcelain',
            '--untracked-files=all'], cwd=ROOT, timeout=10), 'native_clean_source_required')
    current.source_contract()
    return identity


def declared_inventory():
    found = []
    for file, module in [('wss_tests.rs', ''), ('wss_catalog_tests.rs', 'catalog_tests::'),
                         ('wss_drain_tests.rs', 'managed_drain_tests::'), ('wss_two_hop_tests.rs', 'two_hop_tests::')]:
        source = (ROOT / 'src-tauri/src/tools/cloud_host/live' / file).read_text()
        found += [PREFIX + module + name for name in re.findall(
            r'#\[tokio::test[^\]]*\]\s*async fn (\w+)', source)]
        require('#[ignore' not in source, 'native_no_ignored_cases')
    require(sorted(found) == list(ALL), 'exact_native_source_inventory')
    return sorted(found)


def private_file(path, uid):
    path = Path(path)
    info, parent = path.lstat(), path.parent.lstat()
    require(path.is_absolute() and path.resolve(strict=True) == path and stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1 and 0 < info.st_size <= (16384 if path.name == 'ca.der' else 32768)
            and info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o600
            and stat.S_ISDIR(parent.st_mode) and parent.st_uid == uid
            and stat.S_IMODE(parent.st_mode) == 0o700, 'private_native_file')
    return path


def validate_request(request, peer_uid, last_id):
    require(peer_uid == 65532 and type(request) is dict and set(request) == {'id', 'op'}
            and type(request['id']) is int and request['id'] == last_id + 1
            and request['id'] <= 10000 and type(request['op']) is str and request['op'] in OPS, 'invalid_control_request')
    return request['id'], request['op']


def require_bind443(raw):
    require(type(raw) is bytes and raw.strip().isdigit() and 0 <= int(raw) <= 443,
            'bind443_existing_policy_required')
    return int(raw)


def unique_json(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate_json_field')
        value[key] = item
    return value


def agent_compose(f, native_image):
    require(f.domain == DOMAIN and re.fullmatch(r'ctm-topology-[0-9a-f]{32}', f.project)
            and re.fullmatch(r'sha256:[0-9a-f]{64}', native_image), 'owned_native_fixture')
    value = json.loads(f.file.read_text())
    require(not value['services']['postgres'].get('ports'), 'no_database_host_port')
    value['services']['namespace']['networks'] = {'edge': {'aliases': [DOMAIN]}, 'database': {}}
    common = dict(image=native_image, pull_policy='never', user='65532:65532', read_only=True,
                  cap_drop=['ALL'], security_opt=['no-new-privileges:true'], restart='no',
                  pids_limit=256, mem_limit='2g', logging={'driver': 'none'})
    def bind(source, target):
        return dict(type='bind', source=str(source), target=target, read_only=True, bind={'create_host_path': False})
    value['services']['native'] = dict(common, profiles=['native'], networks=['edge'],
        entrypoint=['python3', str(RUNNER), '--inside'],
        tmpfs=['/tmp:rw,nosuid,size=256m,uid=65532,gid=65532,mode=1777'],
        volumes=[bind(ROOT, str(ROOT)), bind(f.root / 'native-private', '/run/native')],
        environment={'CTM_TWO_HOP_BOOTSTRAP': '/run/native/bootstrap.json'})
    outer = dict(value['services']['ingress'])
    outer.update(restart='no', command=['-c', '/run/tls/nginx.conf', '-g', 'daemon off;'],
                 volumes=[bind(f.root / 'tls-private', '/run/tls')], depends_on={'ingress': {'condition': 'service_started'}})
    value['services']['outer'] = outer
    require(all('sysctls' not in service and 'cap_add' not in service for service in value['services'].values()),
            'existing_low_port_policy_only')
    require(value['services']['namespace']['ports'] == [dict(target=8080, published=str(f.port),
            host_ip='127.0.0.1', protocol='tcp')], 'unchanged_inner_only_host_binding')
    return value


def certificate_material(root, mode):
    spec = importlib.util.spec_from_file_location('fixture_certificates',
        ROOT / 'services/cloud-gateway/tests/host_agent_support/relay.py')
    relay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(relay)
    leaf, key = relay.certificates(root, DOMAIN, mode)
    decoded = ssl._ssl._test_decode_cert(str(leaf))
    require(decoded['issuer'] == ssl._ssl._test_decode_cert(str(root / 'ca.pem'))['subject'], 'leaf_issuer')
    san = 'wrong.example.invalid' if mode == 'wrong_hostname' else DOMAIN
    require(decoded['subjectAltName'] == (('DNS', san),), 'exact_leaf_san')
    before, after = map(ssl.cert_time_to_seconds, (decoded['notBefore'], decoded['notAfter']))
    require((before == 946684800 and after == 978307200) if mode == 'expired'
            else before <= time.time() < after, 'exact_leaf_validity')
    trusted = root / ('unrelated.pem' if mode == 'untrusted_ca' else 'ca.pem')
    check = subprocess.run(['openssl', 'verify', '-no-CApath', '-CAfile', str(trusted),
        '-verify_hostname', DOMAIN, str(leaf)], capture_output=True, timeout=10, check=False)
    errors = re.findall(rb'error (\d+) at', check.stderr)
    expected = {'valid': [], 'untrusted_ca': [b'20'], 'wrong_hostname': [b'62'], 'expired': [b'10']}[mode]
    require(errors == expected and (check.returncode == 0) == (mode == 'valid'), 'specific_certificate_preflight')
    return dict(mode=mode, leaf_sha256=hashlib.sha256(leaf.read_bytes()).hexdigest(),
                issuer_sha256=hashlib.sha256((root / 'ca.pem').read_bytes()).hexdigest(),
                san=san, not_before=int(before), not_after=int(after))


class Control:
    def __init__(self, fixture):
        self.f, self.last_id, self.receipts = fixture, 0, []
        self.closed, self.lock, self.workers = threading.Event(), threading.Lock(), []
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(fixture.root / 'native-private/control.sock'))
        self.listener.listen(4)
        self.listener.settimeout(.2)
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def inspect(self):
        sql = """BEGIN READ ONLY; SET LOCAL statement_timeout='500ms';
SELECT json_build_object('connected',c.connected,'gateway_boot',c.gateway_boot,'session',c.session,
'generation',c.generation,'last_seq',c.last_seq,'lease_until',c.lease_until,
'database_now',floor(extract(epoch FROM clock_timestamp()))::bigint,'reconciled',p.reconciled,
'phase',p.state_text::json->>'phase','authority_epoch',(p.state_text::json->>'authority_epoch')::bigint,
'device_revoked',d.revoked,'ledger',COALESCE((SELECT json_agg(l ORDER BY request_id) FROM
(SELECT request_id,state,channel_generation,created_at,updated_at,result_ok FROM ctm_request_ledger
ORDER BY request_id LIMIT 128) l),'[]'::json))
FROM ctm_agent_channel c JOIN ctm_grant_projection p USING(connector)
JOIN ctm_devices d ON d.id=p.device; COMMIT;"""
        lines = self.f.sql(sql, database='coding_tools_identity_test').splitlines()
        rows = [json.loads(line) for line in lines if line.startswith('{')]
        require(len(rows) == 1 and len(json.dumps(rows[0])) <= 3500, 'bounded_raw_observation')
        return rows[0]

    def operation(self, op):
        f = self.f
        if op == 'inspect':
            return self.inspect()
        if op == 'gateway_stop':
            f.dc('stop', '--timeout', '15', 'gateway', timeout=25)
            state = f.container('gateway')[1]['State']
            require(not state['Running'] and state['ExitCode'] == 0
                    and b'"status":"stopped"' in f.logs_clean(), 'actual_gateway_stopped_receipt')
            result = dict(stopped=True, exit_code=0)
        elif op == 'gateway_start':
            if self.inspect()['device_revoked']:
                error = f.cli('coding-tools-mcp-gateway', ['serve', '--config', '/run/gateway/config.json',
                    '--secrets-file', '/run/gateway/runtime.json'], success=False)
                require(error == {'ok': False, 'error': 'provisioning_not_ready'}, 'bounded_revoked_start_refusal')
                result = dict(started=False, error='provisioning_not_ready')
            else:
                f.dc('start', 'gateway', timeout=40)
                f.ready()
                result = dict(started=True)
        elif op == 'revoke_device':
            f.cli('coding-tools-gateway', ['revoke-device', '--config', '/run/gateway/config.json',
                  '--secrets-stdin', '--device', f.device], f.packet)
            result = dict(revoked=self.inspect()['device_revoked'])
        else:
            f.dc('restart', 'postgres', timeout=45)
            f.wait_postgres()
            result = dict(restarted=True, device_revoked=self.inspect()['device_revoked'])
        with self.lock:
            self.receipts.append(dict(op=op, result=result))
        return result

    def respond(self, connection, ident, op):
        with connection:
            try:
                result = dict(id=ident, ok=True, result=self.operation(op))
            except Exception:
                result = dict(id=ident, ok=False, error='control_operation_failed')
            connection.sendall(json.dumps(result).encode() + b'\n')

    def serve(self):
        while not self.closed.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            try:
                connection.settimeout(3)
                uid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
                data = bytearray()
                while not data.endswith(b'\n') and len(data) <= 4096:
                    chunk = connection.recv(4097 - len(data))
                    require(bool(chunk), 'control_eof')
                    data.extend(chunk)
                require(len(data) <= 4096 and data.count(b'\n') == 1, 'bounded_control_frame')
                request = json.loads(data, object_pairs_hook=unique_json)
                ident, op = validate_request(request, uid, self.last_id)
                self.last_id = ident
                self.workers = [worker for worker in self.workers if worker.is_alive()]
                require(len(self.workers) < 4, 'bounded_control_workers')
                worker = threading.Thread(target=self.respond, args=(connection, ident, op), daemon=True)
                self.workers.append(worker)
                worker.start()
            except Exception:
                connection.close()

    def close(self):
        self.closed.set()
        if self.thread.is_alive():
            self.thread.join(4)
            require(not self.thread.is_alive(), 'control_listener_reaped')
        self.listener.close()
        for worker in self.workers:
            worker.join(75)
            require(not worker.is_alive(), 'control_worker_reaped')


def inside(arguments):
    require(os.getuid() == os.getgid() == 65532, 'actual_native_uid')
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    require(all(int(status[key], 16) == 0 for key in ('CapEff', 'CapPrm', 'CapBnd'))
            and int(status['NoNewPrivs']) == 1, 'actual_native_caps_and_no_new_privileges')
    manifest = json.loads(MANIFEST.read_text())
    for name, expected in manifest['binaries'].items():
        require(hashlib.sha256(Path('/usr/local/bin', name).read_bytes()).hexdigest() == expected, 'actual_native_binary_hash')
    if arguments == ['--probe']:
        with socket.create_connection((DOMAIN, 443), timeout=3):
            pass
        print('CTM_TCP443_READY', flush=True)
        return
    if '--list' not in arguments and '--baseline' not in arguments:
        private_file('/run/native/bootstrap.json', 65532)
        private_file('/run/native/ca.der', 65532)
    if '--baseline' in arguments:
        arguments.remove('--baseline')
    print('CTM_NATIVE_IDENTITY=' + json.dumps(dict(uid=65532, caps=0, no_new_privileges=True)), flush=True)
    os.execv('/usr/local/bin/native-tests', ['/usr/local/bin/native-tests', *arguments])


def executed(output, expected, listed=False):
    text = output.decode('utf-8', errors='strict')
    pattern = r'^(' + re.escape(PREFIX) + r'\w+(?:::\w+)*): test$' if listed else r'^test (\S+) \.\.\. (\w+)$'
    matches = re.findall(pattern, text, re.M)
    actual = matches if listed else [name for name, state in matches if state == 'ok']
    require(sorted(actual) == sorted(expected) and len(matches) == len(expected), 'exact_native_executed_inventory')
    if not listed:
        require(re.search(r'test result: ok\. ' + str(len(expected)) + r' passed; 0 failed; 0 ignored;', text), 'native_zero_fail_skip')
    require('CTM_NATIVE_IDENTITY={"uid": 65532, "caps": 0, "no_new_privileges": true}' in text, 'actual_native_identity_receipt')
    return sorted(actual)


def cleanup(f, control, native_name):
    # Reap the exact owned one-off before closing IPC or deleting its private mounts.
    if native_name:
        rows = f.exec(['docker', 'ps', '-aq', '--filter', 'name=^/' + native_name + '$']).stdout.split()
        for container in rows:
            record = json.loads(f.exec(['docker', 'inspect', container.decode()]).stdout)[0]
            require(record['Config']['Labels']['com.docker.compose.project'] == f.project, 'owned_native_cleanup')
            f.exec(['docker', 'rm', '-f', container.decode()], timeout=30)
    if control:
        control.close()
    f.close()
    for kind in ('network', 'volume'):
        require(not f.exec(['docker', kind, 'ls', '-q', '--filter', 'label=com.docker.compose.project=' + f.project]).stdout.strip(),
                'owned_' + kind + '_cleanup')


def safe_report(report, secrets):
    allowed = set(('passed declared cases production_touched baseline compiled source native_manifest source_sha source_tree '
        'github_run_id github_run_attempt source_root base_image binaries native-tests native-fixture build_profile '
        'dev_debug test_debug rust engineering_only project certificate receipts native_observations native_image '
        'mode leaf_sha256 issuer_sha256 san not_before not_after op result stopped exit_code started error revoked '
        'restarted device_revoked database_now lease_until native_remaining_ms elapsed_ms inner rendered_inner '
        'rendered_outer outer_config_sha256 existing_low_port_start versions cleanup_completed error_code diagnostic '
        'failed_cases operation category compose_version docker_version gateway_component_version schema '
        'compatibility_baseline source_sha256 renderer_sha256 include_sha256 domain connector immediate_loopback_upstream_port '
        'agent_route subprotocol location_count scope upstream_reachability_verified applied production_ready '
        'real_host_tls_waf_tested publish_approved old_ingress_two_hop_supported inner_config_sha256 '
        'inner_nginx_version inner_image_id inner_renderer_sha256 images gateway ingress postgres '
        'security service uid capabilities no_new_privileges network_mode published_ports').split()) | set(current.SOURCE_HASHES)
    forbidden = {'pkcs8', 'password', 'owner_password', 'bootstrap', 'connection', 'key', 'access_token', 'refresh_token', 'stdout'}
    def scan(value):
        if isinstance(value, dict):
            require(set(value) <= allowed and not forbidden.intersection(value), 'private_report_field')
            for item in value.values():
                scan(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                scan(item)
    scan(report)
    encoded = json.dumps(report, sort_keys=True)
    require(all(secret not in encoded for secret in secrets if secret), 'private_report_value')
    return report


def native_run(f, name, arguments, expected, timeout=240, listed=False):
    result = f.dc('run', '--rm', '-T', '--no-deps', '--name', name, 'native', *arguments, timeout=timeout, success=False)
    failed = re.findall(rb'^test (\S+) \.\.\. FAILED$', result.stdout, re.M)
    failed = [item.decode() for item in failed if item.decode() in expected]
    if result.returncode != 0:
        raise FixtureFailure('native_test_process_failed', dict(exit_code=result.returncode, failed_cases=failed))
    f.native_observations = []
    for raw in re.findall(rb'^CTM_NATIVE_DRAIN (.+)$', result.stdout, re.M):
        observation = json.loads(raw)
        require(set(observation) == {'database_now', 'lease_until', 'native_remaining_ms', 'elapsed_ms'}
                and all(type(value) is int and 0 <= value < 2**63 for value in observation.values()), 'bounded_drain_evidence')
        f.native_observations.append(observation)
    require(len(f.native_observations) == int(expected == [NEW[4]]), 'exact_drain_evidence')
    return executed(result.stdout, expected, listed)


def run_case(args, case):
    f = control = None
    name = None
    try:
        f = Fixture(args.compose, dict(gateway=args.gateway_image, ingress=args.ingress_image, postgres=args.postgres_image))
        native = f.root / 'native-private'
        native.mkdir(mode=0o700)
        tls = f.root / 'tls-private'
        tls.mkdir(mode=0o700)
        value = agent_compose(f, args.native_image)
        if case is None:
            value['services']['native'].pop('networks')
            value['services']['native']['network_mode'] = 'service:postgres'
            value['services']['native']['environment'] = {
                'CTM_NATIVE_GATEWAY_FIXTURE_BIN': '/usr/local/bin/native-fixture',
                'TEST_DATABASE_URL': f.migration_packet['database_url'].replace('@postgres:', '@127.0.0.1:')}
        f.file.write_text(json.dumps(value))
        f.created = True
        manifest = json.loads(f.exec(['docker', 'run', '--rm', '--network', 'none', '--user', '65532:65532',
            '--label', 'com.docker.compose.project=' + f.project, '--name', f.project + '-manifest',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--log-driver', 'none',
            '--entrypoint', 'cat', args.native_image, str(MANIFEST)]).stdout)
        source = verify_source(manifest)
        image = json.loads(f.exec(['docker', 'image', 'inspect', args.native_image]).stdout)[0]
        require(image['Id'] == args.native_image and image['Config']['User'] == '65532:65532'
                and image['Config']['Labels']['org.opencontainers.image.revision'] == source['source_sha'], 'native_image_source')
        versions = f.prepare()
        name = f.project + '-native'
        if case is None:
            listed = native_run(f, name, [PREFIX, '--list'], ALL, listed=True)
            cases = native_run(f, name, ['--baseline', PREFIX, '--skip', PREFIX + 'two_hop_tests::', '--test-threads=1'], BASELINE, timeout=900)
            result = dict(cases=cases, compiled=listed, source=source, native_manifest=manifest)
        else:
            mode = next((mode for mode in ('untrusted_ca', 'wrong_hostname', 'expired') if mode in case), 'valid')
            certificate = certificate_material(tls, mode)
            inner = current.render(tls / 'inner-render', f.domain, f.config['connector'], 28880)
            outer = current.render(tls / 'render', f.domain, f.config['connector'], 8080)
            config = topology.ingress_config(f.domain, f.config['connector'])
            config = config.replace('listen 8080;', 'listen 443 ssl;\nssl_certificate /run/tls/leaf.pem;\nssl_certificate_key /run/tls/leaf.key;')
            config = config.replace(current.locations(f.domain, f.config['connector'], 28880),
                                    'include /run/tls/render/' + current.INCLUDE + ';')
            (tls / 'nginx.conf').write_text(config)
            connection = f.enrollment_connection
            require(set(connection) == {'version', 'origin', 'prefix', 'connector', 'device', 'device_epoch',
                    'authority_epoch', 'public_key', 'run_seconds'} and connection['version'] == 1, 'exact_shipped_connection_v1')
            bootstrap = dict(schema=1, key=f.enrollment_key, connection=connection, owner_password=f.password,
                client_id=f.config['client_id'], redirect_uri=f.config['redirect_uri'], control_socket='/run/native/control.sock',
                ca_der_file='/run/native/ca.der', case=case.rsplit('::', 1)[1], certificate_mode=mode, certificate_preflight=True)
            (native / 'bootstrap.json').write_text(json.dumps(bootstrap))
            shutil.copyfile(tls / 'ca.der', native / 'ca.der')
            for path in native.iterdir():
                path.chmod(0o600)
                private_file(path, os.getuid())
            control = Control(f)
            for folder in (native, tls):
                f.exec(['sudo', 'chown', '-R', '65532:65532', str(folder)])
            control.thread.start()
            f.sentinel.close()
            f.sentinel = None
            f.dc('up', '-d', 'gateway', timeout=90)
            f.dc('up', '-d', 'ingress', timeout=60)
            f.ready()
            low = f.dc('exec', '-T', 'ingress', 'cat', '/proc/sys/net/ipv4/ip_unprivileged_port_start').stdout.strip()
            require_bind443(low)
            f.dc('run', '--rm', '-T', '--no-deps', 'outer', '-t', '-c', '/run/tls/nginx.conf')
            f.dc('up', '-d', 'outer', timeout=60)
            probe = f.dc('run', '--rm', '-T', '--no-deps', 'native', '--probe')
            require(probe.stdout.strip() == b'CTM_TCP443_READY', 'actual_native_tcp443')
            security = []
            for service in ('outer', 'ingress', 'gateway', 'namespace'):
                _, record = f.container(service)
                require(record['Config']['User'] == '65532:65532' and record['HostConfig']['CapDrop'] == ['ALL']
                        and record['HostConfig']['ReadonlyRootfs'] and 'no-new-privileges:true' in record['HostConfig']['SecurityOpt'],
                        'actual_nonroot_hardened_proxy')
                require(record['State']['Running'] and type(record['State']['Pid']) is int and record['State']['Pid'] > 0, 'live_owned_pid')
                status = Path(f"/proc/{record['State']['Pid']}/status").read_text()
                require(f.container(service)[1]['State'] == record['State'], 'stable_container_pid_and_start')
                fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
                require(all(int(fields[key], 16) == 0 for key in ('CapEff', 'CapPrm', 'CapBnd'))
                        and int(fields['NoNewPrivs']) == 1 and fields['Uid'].split() == ['65532'] * 4,
                        'actual_proxy_process_security')
                security.append(dict(service=service, uid=int(fields['Uid'].split()[0]),
                    capabilities=[int(fields[key], 16) for key in ('CapEff', 'CapPrm', 'CapBnd')],
                    no_new_privileges=int(fields['NoNewPrivs']), network_mode=record['HostConfig']['NetworkMode'],
                    published_ports=[8080] if service == 'namespace' else []))
                if service != 'namespace':
                    require(not record['HostConfig'].get('PortBindings') and record['HostConfig']['NetworkMode']
                            == 'container:' + f.container('namespace')[0], 'actual_namespace_unpublished443')
                else:
                    require(record['HostConfig']['PortBindings'] == {'8080/tcp': [{'HostIp': '127.0.0.1', 'HostPort': str(f.port)}]},
                            'actual_only_inner_host_binding')
                    require(any(DOMAIN in net.get('Aliases', []) for net in record['NetworkSettings']['Networks'].values()),
                            'actual_network_local_canonical_alias')
            for filename, expected in [('nginx.conf', hashlib.sha256(config.encode()).hexdigest()), ('leaf.pem', certificate['leaf_sha256']),
                                       ('render/' + current.INCLUDE, outer['include_sha256'])]:
                observed = f.dc('exec', '-T', 'outer', 'sha256sum', '/run/tls/' + filename).stdout.decode().split()[0]
                require(observed == expected, 'actual_outer_config_certificate')
            cases = native_run(f, name, [case, '--exact', '--test-threads=1', '--show-output'], [case])
            result = dict(cases=cases, project=f.project, certificate=certificate, receipts=control.receipts,
                native_observations=f.native_observations, native_image=args.native_image, security=security,
                inner=inner_ingress_evidence(f), rendered_inner=inner, rendered_outer=outer,
                outer_config_sha256=hashlib.sha256(config.encode()).hexdigest(), existing_low_port_start=int(low))
        f.logs_clean()
        result.update(versions=versions, images=f.images, native_image=args.native_image, cleanup_completed=True)
        return safe_report(result, f.secret_values)
    finally:
        if f is not None:
            cleanup(f, control, name)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--inside':
        inside(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose', type=Path, required=True)
    for name in ('gateway', 'ingress', 'postgres', 'native'):
        parser.add_argument('--' + name + '-image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = dict(passed=False, declared=declared_inventory(), cases=[], production_touched=False)
    try:
        report['baseline'] = run_case(args, None)
        for case in NEW:
            report['cases'].append(run_case(args, case))
        require(sorted(report['baseline']['cases'] + [entry['cases'][0] for entry in report['cases']]) == list(ALL), 'native20_exact')
        report.update(passed=True, cleanup_completed=True, source=source_identity())
    except Exception as error:
        report['error_code'] = error.code if isinstance(error, FixtureFailure) else 'native_fixture_failed'
        if isinstance(error, FixtureFailure):
            report['diagnostic'] = error.diagnostic
    args.output.write_text(json.dumps(safe_report(report, []), indent=2) + '\n')
    print(json.dumps(dict(passed=report['passed'], native_cases=20 if report['passed'] else 0)))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
