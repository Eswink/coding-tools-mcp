#!/usr/bin/env python3
"""Actual disposable Compose/Nginx/Gateway/PostgreSQL acceptance; no live host."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time
from urllib.parse import parse_qs,urlencode,urlsplit
from container_fixture import Fixture,FixtureFailure,require,topology

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


def inspect_boundaries(f):
    gateway,gw=f.container('gateway');anchor,ns=f.container('namespace');_,proxy=f.container('ingress');_,db=f.container('postgres')
    require(ns['HostConfig']['PortBindings']=={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':str(f.port)}]},'actual_loopback_only_binding')
    require(not db['HostConfig'].get('PortBindings'),'actual_database_not_published')
    require(proxy['HostConfig']['NetworkMode']=='container:'+anchor and gw['HostConfig']['NetworkMode']=='container:'+anchor,
            'actual_shared_stable_namespace')
    require(not gw['HostConfig'].get('PortBindings'),'gateway_has_no_separate_host_binding')
    for service,uid in [('namespace','65532'),('gateway','65532'),('ingress','65532'),('postgres','999')]:
        result=f.dc('exec','-T',service,'id','-u')
        require(result.stdout.decode().strip()==uid,'actual_nonroot_service_uid')
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
