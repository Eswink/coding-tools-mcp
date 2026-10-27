#!/usr/bin/env python3
"""Actual disposable Compose/Nginx/Gateway/PostgreSQL acceptance; no live host."""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.parse import parse_qs,urlencode,urlsplit
from kit_fixture import CI_TRUSTED_PROXIES,KitFixture as Fixture,FixtureFailure,require,topology

CASES=[]
STAGE='setup'


def passed(name):CASES.append(name)


def oauth(f):
    resource=f.origin+'/coding-tools/mcp/'+f.config['connector'];verifier='a'*43
    f.secret_values.append(verifier)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    path='/coding-tools/oauth/authorize?'+urlencode(dict(response_type='code',client_id=f.config['client_id'],
        redirect_uri=f.config['redirect_uri'],resource=resource,scope='mcp',state='container-fixture',
        code_challenge=challenge,code_challenge_method='S256'))
    def page(path,data=None,cookie=None):
        headers={'Origin':f.origin}
        if data is not None:headers['Content-Type']='application/x-www-form-urlencoded'
        if cookie:headers['Cookie']=cookie
        status,h,body=f.http('POST' if data is not None else 'GET',path,urlencode(data) if data is not None else None,headers)
        require(status==200,'oauth_page')
        cookie=h['set-cookie'].split(';',1)[0]
        match=re.search(rb'name=csrf value="([A-Za-z0-9_-]+)"',body);require(match is not None,'oauth_csrf')
        csrf=match.group(1).decode();f.secret_values += [cookie.split('=',1)[1],csrf]
        return cookie,csrf
    cookie,csrf=page(path)
    cookie,csrf=page('/coding-tools/oauth/login',dict(csrf=csrf,password=f.password),cookie)
    status,h,_=f.http('POST','/coding-tools/oauth/consent',urlencode(dict(csrf=csrf,decision='allow')),
                    {'Origin':f.origin,'Cookie':cookie,'Content-Type':'application/x-www-form-urlencoded'})
    require(status==303 and h['location'].startswith(f.config['redirect_uri']+'?'),'explicit_consent_callback')
    callback=parse_qs(urlsplit(h['location']).query);require(callback['state']==['container-fixture'],'callback_state')
    code=callback['code'][0];f.secret_values.append(code)
    status,_,body=f.http('POST','/coding-tools/oauth/token',urlencode(dict(grant_type='authorization_code',
        client_id=f.config['client_id'],code=code,redirect_uri=f.config['redirect_uri'],code_verifier=verifier,
        resource=resource)),{'Content-Type':'application/x-www-form-urlencoded'})
    require(status==200,'real_proxy_pkce_exchange');tokens=json.loads(body)
    f.secret_values += [tokens['access_token'],tokens['refresh_token']]
    return tokens['access_token']


def mcp(f,token,version='2025-06-18',initialize=False):
    method='initialize' if initialize else 'tools/list'
    params={'protocolVersion':version,'capabilities':{},'clientInfo':{'name':'container-fixture','version':'1'}} if initialize else {}
    return f.http('POST','/coding-tools/mcp/'+f.config['connector'],
        json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params)),
        {'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'application/json, text/event-stream',
         'MCP-Protocol-Version':version})


def upgraded_socket(f,host=None,protocol="coding-tools-agent.v1",expected=101):
    connection=socket.create_connection(('127.0.0.1',f.port),timeout=5)
    key=base64.b64encode(b'0123456789abcdef').decode()
    request=(f'GET /coding-tools/agent HTTP/1.1\r\nHost: {host or f.domain}\r\n'
             'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
             f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Protocol: {protocol}\r\n\r\n')
    connection.sendall(request.encode());header=bytearray()
    while not header.endswith(b'\r\n\r\n') and len(header)<8192:
        data=connection.recv(1);require(bool(data),'websocket_header_eof');header.extend(data)
    if expected != 101:
        connection.close()
        require(header.startswith(f'HTTP/1.1 {expected} '.encode()),'exact_websocket_negative_status')
        return None
    require(header.startswith(b'HTTP/1.1 101 ') and b'coding-tools-agent.v1' in header,'actual_websocket_upgrade')
    return connection


TOKEN='/coding-tools/oauth/token'
NGINX_429=b'<title>429 Too Many Requests</title>'
AUTH_REFILL_SECONDS=40  # 10r/m refills burst=5 in 30s


def nginx_429(status,body):
    # Gateway 429s carry try_later/agent_connection_rejected; only Nginx renders this page.
    return status==429 and NGINX_429 in body and b'try_later' not in body


def token_attempt(f,real_ip=None):
    headers={'Content-Type':'application/x-www-form-urlencoded'}
    if real_ip is not None:headers['X-Real-IP']=real_ip
    status,_,body=f.http('POST',TOKEN,'grant_type=invalid',headers)
    return status,body


def token_burst(f,real_ip):
    """Fast /token requests until Nginx answers 429; real_ip(index) gives the X-Real-IP or None."""
    statuses=[]
    for index in range(10):
        status,body=token_attempt(f,real_ip(index))
        require(status!=429 or nginx_429(status,body),'only_nginx_may_rate_limit_token')
        statuses.append(status)
        if status==429:break
    # burst=5 nodelay: six immediate requests pass; one more may pass if a 6s token leaked meanwhile.
    require(429 not in statuses[:6] and statuses[-1]==429 and len(statuses)<=8,'token_429_after_auth_burst')
    return statuses


def agent_raw_status(f):
    connection=socket.create_connection(('127.0.0.1',f.port),timeout=5)
    try:
        key=base64.b64encode(b'0123456789abcdef').decode()
        connection.sendall((f'GET /coding-tools/agent HTTP/1.1\r\nHost: {f.domain}\r\nUpgrade: websocket\r\n'
                            'Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
                            f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Protocol: coding-tools-agent.v1\r\n\r\n').encode())
        data=bytearray()
        while b'\r\n\r\n' not in data and len(data)<8192:
            chunk=connection.recv(4096)
            if not chunk:break
            data.extend(chunk)
        head,_,body=bytes(data).partition(b'\r\n\r\n')
        length=re.search(rb'(?im)^content-length:\s*([0-9]{1,5})\s*$',head)
        while length and len(body)<int(length.group(1)):
            chunk=connection.recv(4096)
            if not chunk:break
            body+=chunk
        match=re.match(rb'HTTP/1\.1 ([0-9]{3}) ',head);require(match is not None,'agent_status_line')
        return int(match.group(1)),body
    finally:connection.close()


def rate_limit_checks(f,token):
    """G3 on the default config: limits key on the connection address, X-Real-IP is ignored."""
    time.sleep(AUTH_REFILL_SECONDS)
    token_burst(f,lambda index:f'203.0.113.{index+1}')
    passed('token_429_after_burst_forged_real_ip_rotation_ignored')
    status,body=token_attempt(f,'203.0.113.200')
    require(nginx_429(status,body),'untrusted_forged_real_ip_cannot_open_new_bucket')
    passed('untrusted_forged_real_ip_shares_connection_bucket')
    for _ in range(20):
        require(mcp(f,token)[0]==200,'mcp_normal_rate_never_429');time.sleep(.15)
    passed('mcp_normal_rate_never_429')
    for _ in range(6):
        upgraded_socket(f).close();time.sleep(.3)
    passed('agent_sequential_upgrades_never_429')
    time.sleep(1.2);held=[]
    try:
        for _ in range(4):held.append(upgraded_socket(f))
        # Gateway would still admit a fifth (8/s attempts, 8 sockets), so this 429 is limit_conn.
        status,body=agent_raw_status(f)
        require(nginx_429(status,body),'agent_fifth_concurrent_upgrade_429')
    finally:
        for connection in held:connection.close()
    time.sleep(1.2)
    passed('agent_limit_conn_4_per_ip')


def trusted_real_ip_checks(f):
    """Hosted CI only: alternate config trusts the live edge bridge gateway via CI_TRUSTED_PROXIES."""
    networks=[name for name in f.container('namespace')[1]['NetworkSettings']['Networks'] if name.endswith('_edge')]
    require(len(networks)==1,'one_edge_network')
    ipam=json.loads(f.exec(['docker','network','inspect',networks[0]]).stdout)[0]['IPAM']['Config'] or []
    gateways=[ipaddress.ip_address(item['Gateway']) for item in ipam if item.get('Gateway')]
    require(bool(gateways) and all(any(g in ipaddress.ip_network(c) for c in CI_TRUSTED_PROXIES) for g in gateways),
            'edge_bridge_gateway_inside_trusted_ci_ranges')
    passed('edge_bridge_gateway_inside_trusted_ci_ranges')
    f.dc('run','--rm','-T','--no-deps','ingress','-t','-c','/run/ingress/nginx.trusted.conf')
    passed('actual_nonroot_nginx_syntax_trusted_real_ip')
    f.dc('stop','--timeout','10','ingress',timeout=30)
    run=f.dc('run','-d','--rm','--no-deps','ingress','-c','/run/ingress/nginx.trusted.conf','-g','daemon off;',timeout=60)
    name=run.stdout.decode().strip().splitlines()[-1] if run.stdout.strip() else ''
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',name) is not None,'trusted_ingress_run_container')
    try:
        f.ready()
        token_burst(f,lambda index:'198.51.100.1')
        passed('trusted_real_ip_bucket_exhausted')
        require(token_attempt(f,'198.51.100.2')[0]!=429,'trusted_distinct_client_has_own_bucket')
        require(token_attempt(f)[0]!=429,'trusted_proxy_address_has_own_bucket')
        passed('trusted_real_ip_buckets_per_client')
    finally:
        f.exec(['docker','rm','-f',name],timeout=30)
    f.dc('start','ingress',timeout=60);f.ready()


def inspect_boundaries(f):
    gateway,gw=f.container('gateway');anchor,ns=f.container('namespace');_,proxy=f.container('ingress');_,db=f.container('postgres')
    require(ns['HostConfig']['PortBindings']=={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(f.port)}]},'actual_loopback_only_binding')
    require(not db['HostConfig'].get('PortBindings'),'actual_database_not_published')
    require(proxy['HostConfig']['NetworkMode']=='container:'+anchor and gw['HostConfig']['NetworkMode']=='container:'+anchor,
            'actual_shared_stable_namespace')
    require(not gw['HostConfig'].get('PortBindings'),'gateway_has_no_separate_host_binding')
    for service in ('namespace','gateway','ingress','postgres'):
        f.assert_process_identity(service)
    dbnet=[name for name in db['NetworkSettings']['Networks'] if name.endswith('_database')]
    require(len(dbnet)==1,'one_private_database_network')
    network=json.loads(f.exec(['docker','network','inspect',dbnet[0]]).stdout)[0]
    require(network['Internal'] is True,'database_network_internal')
    manifest=json.loads(f.dc('exec','-T','gateway','cat','/usr/share/coding-tools/manifest.json').stdout)
    require(manifest['source_sha']==os.environ['GITHUB_SHA'] and manifest['engineering_only'] is True,'image_binary_manifest_source')
    require(set(manifest['binaries'])=={'coding-tools-gateway','coding-tools-agent','coding-tools-control-gateway','coding-tools-mcp-gateway'},'all_four_image_binaries')
    for name,expected in manifest['binaries'].items():
        require(name in ('coding-tools-gateway','coding-tools-agent','coding-tools-control-gateway','coding-tools-mcp-gateway'),'fixed_binary_manifest')
        actual=f.dc('exec','-T','gateway','sha256sum','/usr/local/bin/'+name).stdout.decode().split()[0]
        require(actual==expected,'actual_image_binary_hash')
    logs=f.logs_clean()
    require(b'"listen":"127.0.0.1:28880"' in logs,'gateway_actual_loopback_listen')


def main():
    global STAGE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compose',type=Path,required=True)
    for name in ('gateway','ingress','postgres'):p.add_argument('--'+name+'-image',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    f=None;pending=None;report=None
    try:
        f=Fixture(a.compose,dict(gateway=a.gateway_image,ingress=a.ingress_image,postgres=a.postgres_image))
        versions=f.prepare();passed('compose_2_27_and_shipped_from_empty_bootstrap')
        for probe in versions['denied_probes']:passed(probe)
        STAGE='port_collision'
        require(topology.port_observation(f.port)['collision_observed'] is True,'read_only_port_collision_preflight')
        passed('read_only_collision_observed_before_apply')
        collision=f.dc('up','-d','namespace',success=False,timeout=90)
        error=collision.stderr.decode().lower()
        require(collision.returncode!=0 and str(f.port) in error
                and ('address already in use' in error or 'port is already allocated' in error),'exact_occupied_port_refusal')
        check=socket.create_connection(('127.0.0.1',f.port),timeout=2);check.close()
        accepted,_=f.sentinel.accept();accepted.close()
        f.dc('rm','-s','-f','namespace');f.sentinel.close();passed('collision_preserves_existing_listener')
        STAGE='start_topology'
        f.dc('up','-d','gateway',timeout=90)
        f.dc('run','--rm','-T','--no-deps','ingress','-t','-c','/run/ingress/nginx.conf')
        passed('actual_nonroot_nginx_syntax')
        f.dc('up','-d','ingress',timeout=60);f.ready();inspect_boundaries(f)
        passed('nonroot_loopback_namespace_and_private_database')
        require(f.http('GET','/')[0]==404,'ingress_has_no_root_site')
        path='/.well-known/oauth-authorization-server/coding-tools/oauth'
        status,_,body=f.http('GET',path,headers={'Forwarded':'host=foreign.invalid','X-Forwarded-Host':'foreign.invalid'})
        require(status==200 and json.loads(body)['issuer']==f.origin+'/coding-tools/oauth','forwarded_host_cannot_choose_issuer')
        require(f.http('GET',path,headers={'Host':'foreign.invalid','X-Forwarded-Host':f.domain})[0]==421,'foreign_original_host_refused')
        passed('canonical_origin_routes_and_no_forwarded_host_trust')
        STAGE='oauth_mcp'
        token=oauth(f);passed('real_container_oauth_pkce')
        status,_,body=mcp(f,token,initialize=True)
        require(status==200 and json.loads(body)['result']['protocolVersion']=='2025-06-18','mcp_initialize_through_ingress')
        require(json.loads(body)['result']['serverInfo']['version']==versions['gateway_component_version'],'externally_visible_component_version')
        status,_,body=mcp(f,token)
        require(status==200 and bool(json.loads(body)['result']['tools']),'legacy_mcp_header_preserved')
        status,_,body=mcp(f,token,version='1900-01-01')
        require(status==400 and json.loads(body)['error']['code']==-32022,'unsupported_header_reaches_actual_protocol_gate')
        passed('mcp_protocol_headers_and_negative_version_gate')
        upgraded_socket(f,host='foreign.invalid',expected=421)
        upgraded_socket(f,protocol='unsupported-agent.v0',expected=403)
        passed('agent_upgrade_foreign_host_and_protocol_refused')
        STAGE='rate_limits'
        rate_limit_checks(f,token)
        STAGE='trusted_real_ip'
        trusted_real_ip_checks(f)
        STAGE='shutdown'
        anchor_id=f.container('namespace')[0];ingress_id=f.container('ingress')[0]
        opened=time.monotonic();pending=upgraded_socket(f);passed('actual_agent_websocket_upgrade_headers')
        started=time.monotonic();f.dc('stop','--timeout','15','gateway',timeout=25)
        _,stopped=f.container('gateway')
        require(stopped['State']['ExitCode']==0 and not stopped['State']['Running']
                and time.monotonic()-started<22,'graceful_gateway_shutdown')
        require(b'"status":"stopped"' in f.logs_clean(),'gateway_stopped_receipt')
        pending.settimeout(1);deadline=opened+8;closed=False;received=0
        while time.monotonic()<deadline:
            try:
                data=pending.recv(4096)
                if not data:closed=True;break
                received+=len(data);require(received<65536,'bounded_pending_socket_output')
            except ConnectionResetError:closed=True;break
            except socket.timeout:pass
        require(closed and time.monotonic()<opened+8,'upgraded_socket_drain_before_auth_expiry');pending.close();pending=None
        passed('actual_gateway_shutdown_drains_upgraded_socket')
        f.dc('start','gateway',timeout=60);f.ready()
        require(f.container('namespace')[0]==anchor_id and f.container('ingress')[0]==ingress_id,'restart_keeps_live_ingress_namespace')
        require(mcp(f,token)[0]==200,'oauth_authority_survives_container_restart')
        passed('gateway_restart_preserves_namespace_and_authority')
        STAGE='revocation'
        f.cli('coding-tools-gateway',['revoke-device','--config','/run/gateway/config.json','--secrets-stdin',
                                     '--device',f.device],f.packet)
        f.dc('stop','--timeout','15','ingress','gateway',timeout=40)
        f.dc('restart','postgres',timeout=45);f.wait_postgres()
        require(f.sql('SELECT count(*) FROM ctm_devices WHERE revoked',database='coding_tools_identity_test')=='1',
                'revocation_survives_database_restart')
        error=f.cli('coding-tools-mcp-gateway',['serve','--config','/run/gateway/config.json',
                    '--secrets-file','/run/gateway/runtime.json'],success=False)
        require(error=={'ok':False,'error':'provisioning_not_ready'},'revoked_device_must_not_resurrect')
        passed('revoked_authority_not_resurrected_after_restart')
        f.logs_clean();passed('no_credential_payload_logging')
        source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        require(source==os.environ['GITHUB_SHA'],'exact_source_identity')
        report=dict(passed=True,source_sha=source,cases=CASES,versions=versions,images=f.images,
                    production_touched=False,real_host_tls_waf_tested=False,publish_approved=False,
                    scope='Disposable runnable container topology; HTTP proxy and pending WebSocket, not public TLS/WSS provenance')
    except Exception:
        STAGE += ':' + getattr(f,'last_action','not_created')
        raise
    finally:
        if pending is not None:pending.close()
        if f is not None:f.close()
    report['cleanup_completed']=True
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'cases':len(CASES),'cleanup_completed':True,'production_touched':False}))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(json.dumps({'passed':False,'stage':STAGE,'error_class':type(error).__name__,'error_code':error.code if isinstance(error,FixtureFailure) else None,'diagnostic':error.diagnostic if isinstance(error,FixtureFailure) else None,'completed_cases':CASES}))
        raise SystemExit(1) from None
