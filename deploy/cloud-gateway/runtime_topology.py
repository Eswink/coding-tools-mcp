"""Opt-in nonproduction topology render only; never invokes Docker or edits a host."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

_spec=importlib.util.spec_from_file_location('deployment_blueprint',Path(__file__).with_name('render.py'))
blueprint=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(blueprint)
_spec=importlib.util.spec_from_file_location('current_include',Path(__file__).with_name('current_nginx_include.py'))
current=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(current)


def image_refs(images):
    if set(images) != {'gateway','ingress','postgres'}:
        raise ValueError('three exact images required')
    for name,pattern in [('gateway',r'sha256:[0-9a-f]{64}'),('ingress',r'nginx@sha256:[0-9a-f]{64}'),
                         ('postgres',r'postgres@sha256:[0-9a-f]{64}')]:
        if not isinstance(images[name],str) or not re.fullmatch(pattern,images[name]):
            raise ValueError('fixed official digest or immutable local gateway image required')


# G3 ingress limits. Keys are empty outside each route class, and Nginx does not count empty keys.
RATE_LIMITS=('map $uri $ctm_auth_key {\ndefault "";\n~^/coding-tools/oauth/ $binary_remote_addr;\n'
             '~^/\\.well-known/oauth- $binary_remote_addr;\n}\n'
             'map $uri $ctm_mcp_key {\ndefault "";\n~^/coding-tools/mcp/ $binary_remote_addr;\n}\n'
             'map $uri $ctm_agent_key {\ndefault "";\n/coding-tools/agent $binary_remote_addr;\n}\n'
             'limit_req_zone $ctm_auth_key zone=ctm_auth:1m rate=10r/m;\n'
             'limit_req_zone $ctm_mcp_key zone=ctm_mcp:2m rate=10r/s;\n'
             'limit_conn_zone $ctm_agent_key zone=ctm_agent:1m;\n'
             'limit_req_status 429;\nlimit_conn_status 429;\nlimit_req_log_level warn;\nlimit_conn_log_level warn;\n')
SERVER_LIMITS=('limit_req zone=ctm_auth burst=5 nodelay;\nlimit_req zone=ctm_mcp burst=40 nodelay;\n'
               'limit_conn ctm_agent 4;\n')
MAX_TRUSTED_PROXIES=8


def trusted_proxy_cidrs(values):
    """Strict operator-supplied real-IP sources. Empty means trust nothing."""
    import ipaddress
    result=[]
    for value in values:
        if not isinstance(value,str) or not re.fullmatch(r'[0-9A-Fa-f:.]+/[0-9]{1,3}',value):
            raise ValueError('trusted proxy must be an explicit CIDR')
        try:network=ipaddress.ip_network(value,strict=True)
        except ValueError:raise ValueError('trusted proxy CIDR has host bits or is malformed') from None
        if str(network)!=value.lower():raise ValueError('trusted proxy CIDR must be canonical')
        if network.prefixlen==0 or network.is_unspecified or network.is_multicast:
            raise ValueError('trusted proxy CIDR is too broad')
        if not (network.is_private or network.is_loopback):
            raise ValueError('trusted proxy CIDR must be private or loopback')
        if str(network) in result:raise ValueError('duplicate trusted proxy CIDR')
        result.append(str(network))
    if len(result)>MAX_TRUSTED_PROXIES:raise ValueError('too many trusted proxy CIDRs')
    return tuple(result)


def ingress_config(domain,connector,*,trusted_proxies=(),rate_limits=False):
    # Default stays byte-identical to the frozen RC fixtures; every deploy renderer passes rate_limits=True.
    # Both hops use the reviewed native-header contract; drift fails before rendering.
    current.source_contract()
    locations=current.locations(domain,connector,28880)
    trusted=trusted_proxy_cidrs(trusted_proxies)
    realip=''.join(f'set_real_ip_from {cidr};\n' for cidr in trusted)
    if trusted:realip+='real_ip_header X-Real-IP;\nreal_ip_recursive off;\n'
    return ('worker_processes 1;\nerror_log /dev/null crit;\npid /tmp/nginx.pid;\n'
            'events { worker_connections 128; }\nhttp {\naccess_log off;\n'
            'client_body_temp_path /tmp/body;\nproxy_temp_path /tmp/proxy;\n'
            'fastcgi_temp_path /tmp/fastcgi;\nuwsgi_temp_path /tmp/uwsgi;\nscgi_temp_path /tmp/scgi;\n'
            'client_max_body_size 64k;\nclient_body_timeout 10s;\nclient_header_timeout 10s;\n'
            'keepalive_timeout 15s;\nlarge_client_header_buffers 2 8k;\n'+realip+(RATE_LIMITS if rate_limits else '')+
            'server {\nlisten 8080;\n'
            f'server_name {domain};\nif ($http_host != "{domain}") {{ return 421; }}\n'
            +(SERVER_LIMITS if rate_limits else '')+
            'location = / { return 404; }\n'+locations+'\n}\n}\n')


def compose(directory,images,domain,connector,port):
    directory=Path(directory)
    if not directory.is_absolute() or any(p in ('.','..') for p in directory.parts):
        raise ValueError('absolute private render directory required')
    blueprint.validate(domain,connector,port);image_refs(images)
    def bind(folder,target):
        return {'type':'bind','source':str(directory/folder),'target':target,'read_only':True,
                'bind':{'create_host_path':False}}
    common={'read_only':True,'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
            'restart':'unless-stopped','pids_limit':128,'mem_limit':'512m','cpus':'1.0'}
    namespace={**common,'image':images['gateway'],'pull_policy':'never','user':'65532:65532',
               'entrypoint':['/usr/bin/sleep'],'command':['infinity'],'init':True,
               'networks':['edge','database'],'mem_limit':'16m','pids_limit':4,'cpus':'0.1',
               'ports':[{'target':8080,'published':str(port),'host_ip':'127.0.0.1','protocol':'tcp'}],
               'stop_grace_period':'5s','logging':{'driver':'none'}}
    gateway={**common,'image':images['gateway'],'pull_policy':'never','user':'65532:65532',
             'command':['serve','--config','/run/gateway/config.json','--secrets-file','/run/gateway/runtime.json'],
             'volumes':[bind('gateway-private','/run/gateway')],
             'tmpfs':['/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532'],
             'network_mode':'service:namespace','depends_on':{'postgres':{'condition':'service_healthy'},
                'namespace':{'condition':'service_started','restart':True}},
             'stop_grace_period':'15s','logging':{'driver':'local','options':{'max-size':'1m','max-file':'2'}}}
    ingress={**common,'image':images['ingress'],'pull_policy':'never','user':'65532:65532',
             'network_mode':'service:namespace','depends_on':{'gateway':{'condition':'service_started'},
                'namespace':{'condition':'service_started','restart':True}},
             'entrypoint':['/usr/sbin/nginx'],'command':['-c','/run/ingress/nginx.conf','-g','daemon off;'],
             'volumes':[bind('ingress-private','/run/ingress')],
             'tmpfs':['/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532'],
             'mem_limit':'128m','pids_limit':32,'stop_grace_period':'5s',
             'logging':{'driver':'local','options':{'max-size':'1m','max-file':'2'}}}
    postgres={**common,'image':images['postgres'],'pull_policy':'never','user':'999:999',
              'environment':{'POSTGRES_USER':'postgres','POSTGRES_DB':'postgres',
                             'POSTGRES_PASSWORD_FILE':'/run/postgres-secret/password',
                             'POSTGRES_INITDB_ARGS':'--auth-host=scram-sha-256 --auth-local=trust'},
              'volumes':['database-data:/var/lib/postgresql/data',bind('postgres-private','/run/postgres-secret')],
              'tmpfs':['/tmp:rw,noexec,nosuid,size=16m,uid=999,gid=999',
                       '/var/run/postgresql:rw,nosuid,size=16m,uid=999,gid=999,mode=3775'],
              'networks':['database'],'stop_grace_period':'15s','mem_limit':'768m',
              'command':['postgres','-c','log_statement=none','-c','log_min_error_statement=panic',
                         '-c','log_parameter_max_length=0','-c','log_parameter_max_length_on_error=0'],
              'healthcheck':{'test':['CMD','pg_isready','-U','postgres','-d','postgres'],
                             'interval':'2s','timeout':'2s','retries':30},
              'logging':{'driver':'local','options':{'max-size':'1m','max-file':'2'}}}
    operator={**common,'image':images['gateway'],'pull_policy':'never','user':'65532:65532',
              'profiles':['operator'],'restart':'no','entrypoint':['/usr/local/bin/coding-tools-gateway'],
              'command':['--help'],'volumes':[bind('gateway-private','/run/gateway')],
              'tmpfs':['/tmp:rw,noexec,nosuid,size=16m,uid=65532,gid=65532'],
              'networks':['database'],'logging':{'driver':'none'}}
    return {'x-delivery-state':'NONPRODUCTION_EXPLICIT_OPERATOR_TOPOLOGY','services':{
            'namespace':namespace,'gateway':gateway,'ingress':ingress,'postgres':postgres,'operator':operator},
            'networks':{'edge':{},'database':{'internal':True}},'volumes':{'database-data':{}}}


def port_observation(port,tables=None):
    """Sanitized read-only observation; absence is never permission to apply."""
    if type(port) is not int or not 1024 <= port <= 65535:raise ValueError('unprivileged port required')
    tables=tables or (Path('/proc/net/tcp'),Path('/proc/net/tcp6'))
    observed=False;readable=0
    for path in tables:
        try:lines=Path(path).read_text().splitlines()[1:]
        except OSError:continue
        readable+=1
        for line in lines:
            fields=line.split()
            if len(fields)>3 and fields[3].upper()=='0A':
                try:bound=int(fields[1].rsplit(':',1)[1],16)
                except (ValueError,IndexError):continue
                if bound==port:observed=True
    return {'collision_observed':observed if readable else None,'read_only':True,
            'availability_verified':False,'applied':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('gateway-image','ingress-image','postgres-image','domain','connector'):p.add_argument('--'+key,required=True)
    p.add_argument('--port',type=int,default=28880);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trusted-proxy',action='append',default=[])
    a=p.parse_args();output=a.output.resolve();images=dict(gateway=a.gateway_image,ingress=a.ingress_image,postgres=a.postgres_image)
    value=compose(output,images,a.domain,a.connector,a.port);nginx=ingress_config(a.domain,a.connector,trusted_proxies=a.trusted_proxy,rate_limits=True)
    output.mkdir(mode=0o700,exist_ok=False)
    (output/'compose.runtime.json').write_text(json.dumps(value,indent=2)+'\n')
    (output/'nginx.runtime.conf').write_text(nginx)
    print(json.dumps({'rendered':True,'applied':False,'production_ready':False,'port_observation':port_observation(a.port)}))


if __name__=='__main__':main()
