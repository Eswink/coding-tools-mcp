"""Fresh hosted-CI Docker project only. Secret documents never enter evidence."""
import base64
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile
import time
import tomllib
import uuid

ROOT=Path(__file__).resolve().parents[2]
_spec=importlib.util.spec_from_file_location('runtime_topology',ROOT/'deploy/cloud-gateway/runtime_topology.py')
topology=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(topology)


class FixtureFailure(RuntimeError):
    def __init__(self,code,diagnostic=None):
        super().__init__(code);self.code=code;self.diagnostic=diagnostic


def require(condition,name):
    if not condition:raise FixtureFailure(name)


def command_diagnostic(args,result,compose):
    """Fixed labels only: never return command arguments or process output."""
    tokens=list(map(str,args))
    operation='external_command'
    services=('namespace','gateway','ingress','postgres','operator')
    if tokens and tokens[0]==compose:
        operation='compose'
        for verb in ('config','version','up','run','exec','ps','create','rm','stop','start','logs','down'):
            if verb in tokens:
                operation+='_'+verb
                rest=tokens[tokens.index(verb)+1:]
                selected=next((name for name in services if name in rest),None)
                if selected:operation+='_'+selected
                if verb=='exec':
                    action=next((name for name in ('id','cat','sha256sum','psql') if name in rest),None)
                    if action:operation+='_'+action
                break
    elif tokens[:2]==['docker','inspect']:operation='docker_inspect'
    elif tokens[:2]==['docker','network']:operation='docker_network'
    elif tokens[:2]==['docker','context']:operation='docker_context'
    elif tokens[:2]==['docker','version']:operation='docker_version'
    elif tokens[:2]==['docker','image']:operation='docker_image'
    elif tokens[:2]==['docker','ps']:operation='docker_ps'
    elif tokens[:2]==['docker','top']:operation='docker_top'
    elif tokens[:2]==['docker','rm']:operation='docker_rm'
    elif tokens[:2]==['sudo','chown']:operation='fixture_chown'
    elif tokens[:2]==['sudo','rm']:operation='fixture_cleanup'
    category='unspecified'
    raw=(result.stdout+b'\n'+result.stderr).lower()
    for name,markers in [
        ('resource_limit',(b'resource temporarily unavailable',b'pids limit',b'cannot allocate memory')),
        ('permission_denied',(b'permission denied',b'operation not permitted')),
        ('container_not_running',(b'is not running',b'non running container',b'not running')),
        ('missing_executable_or_path',(b'no such file or directory',b'executable file not found',b'not found in $path')),
        ('read_only_filesystem',(b'read-only file system',)),
        ('address_collision',(b'address already in use',b'port is already allocated')),
        ('dependency_failure',(b'dependency failed',b'is unhealthy')),
        ('oci_runtime_failure',(b'oci runtime',))]:
        if any(marker in raw for marker in markers):category=name;break
    return dict(operation=operation,exit_code=result.returncode,category=category)


class Fixture:
    def __init__(self,compose,images):
        require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
                and os.environ.get('GITHUB_REPOSITORY')=='Eswink/coding-tools-mcp','hosted_disposable_ci_only')
        require(os.environ.get('DOCKER_HOST','unix:///var/run/docker.sock')=='unix:///var/run/docker.sock'
                and os.environ.get('DOCKER_CONTEXT','default')=='default','local_default_docker_only')
        topology.image_refs(images)
        self.compose=str(compose.resolve(strict=True));self.images=images
        self.project='ctm-topology-'+uuid.uuid4().hex
        self.root=Path(tempfile.mkdtemp(prefix='ctm-container-fixture-',dir=os.environ['RUNNER_TEMP']))
        self.file=self.root/'compose.runtime.json';self.secret_values=[];self.created=False;self.last_action='private_fixture_setup'
        self.command=[self.compose,'--ansi','never','-p',self.project,'-f',str(self.file)]
        self.sentinel=None
        try:
            self.sentinel=socket.socket();self.sentinel.bind(('127.0.0.1',0));self.sentinel.listen(2)
            self.port=self.sentinel.getsockname()[1]
            self.domain='gateway.example.invalid';self.origin='https://'+self.domain
            self.config=dict(origin=self.origin,prefix='/coding-tools',connector=str(uuid.uuid4()),
                owner_subject=str(uuid.uuid4()),client_id='container-fixture',
                redirect_uri='https://client.example.invalid/callback',client_authentication='public',bind='127.0.0.1:28880')
            self.password=secrets.token_urlsafe(32);dbpassword=secrets.token_hex(24)
            self.packet=dict(database_url=f'postgresql://ctm_app:{dbpassword}@postgres:5432/coding_tools_identity_test',
                             identity_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('='))
            self.dbpassword=dbpassword
            migration_password=secrets.token_hex(24)
            self.migration_packet=dict(self.packet,database_url=f'postgresql://ctm_migration:{migration_password}@postgres:5432/coding_tools_identity_test')
            self.migration_password=migration_password
            self.secret_values=[self.password,dbpassword,self.packet['identity_key'],self.packet['database_url'],migration_password,self.migration_packet['database_url']]
            for folder in ('gateway-private','ingress-private','postgres-private'):(self.root/folder).mkdir(mode=0o700)
            def write(folder,name,value):
                path=self.root/folder/name;path.write_text(value);path.chmod(0o400)
            write('gateway-private','config.json',json.dumps(self.config))
            write('gateway-private','runtime.json',json.dumps(self.packet))
            write('gateway-private','enrollment.json',json.dumps({k:self.config[k] for k in ('origin','prefix','connector')}))
            write('ingress-private','nginx.conf',topology.ingress_config(self.domain,self.config['connector']))
            bootstrap_password=secrets.token_urlsafe(32);self.secret_values.append(bootstrap_password)
            write('postgres-private','password',bootstrap_password)
            for folder,uid in [('gateway-private',65532),('ingress-private',65532),('postgres-private',999)]:
                self.exec(['sudo','chown','-R',f'{uid}:{uid}',str(self.root/folder)])
            self.file.write_text(json.dumps(topology.compose(self.root,images,self.domain,self.config['connector'],self.port)))
        except Exception:
            self.close()
            raise

    def exec(self,args,*,packet=None,timeout=60,success=True):
        data=json.dumps(packet).encode() if packet is not None else b''
        self.last_action=command_diagnostic(args,subprocess.CompletedProcess(args,0,b'',b''),self.compose)['operation']
        result=subprocess.run(list(map(str,args)),input=data,capture_output=True,timeout=timeout,check=False)
        diagnostic=command_diagnostic(args,result,self.compose)
        self.last_action=diagnostic['operation']
        if success and result.returncode!=0:
            raise FixtureFailure('fixture_command_failed',diagnostic)
        return result

    def dc(self,*args,**kwargs):return self.exec([*self.command,*args],**kwargs)
    def container(self,service):
        value=self.dc('ps','-aq',service).stdout.decode().strip()
        require(re.fullmatch(r'[0-9a-f]{12,64}',value) is not None,'one_owned_container_required')
        record=json.loads(self.exec(['docker','inspect',value]).stdout)[0]
        require(record['Config']['Labels']['com.docker.compose.project']==self.project,'container_owner_mismatch')
        return value,record

    def assert_process_identity(self,service):
        """Observe existing tasks from the daemon, without exec in the target cgroup."""
        identities={'namespace':65532,'gateway':65532,'ingress':65532,'postgres':999}
        require(service in identities,'fixed_identity_observation_service')
        uid=identities[service];container,record=self.container(service)
        require(record['Config']['User']==f'{uid}:{uid}','actual_nonroot_service_user_config')
        state=record['State'];pid=state.get('Pid')
        require(state.get('Running') is True and not state.get('Restarting',False)
                and type(pid) is int and pid>0,'running_service_identity_required')
        # Docker filters daemon-side ps output by container PID. Keep PID mandatory,
        # and request only numeric IDs, never command arguments or environment.
        rows=self.exec(['docker','top',container,'-eo','pid,uid,gid']).stdout.splitlines()
        require(len(rows)>1 and rows[0].split()==[b'PID',b'UID',b'GID'],'process_identity_header_required')
        observed=set()
        for row in rows[1:]:
            fields=row.split()
            require(len(fields)==3 and all(re.fullmatch(rb'[0-9]+',field) for field in fields),
                    'numeric_process_identity_required')
            task,user,group=map(int,fields)
            require(task>0 and task not in observed,'unique_live_process_identity_required')
            require(user==uid and group==uid,'actual_nonroot_service_process_identity')
            observed.add(task)
        require(pid in observed,'running_service_init_identity_required')

    def cli(self,binary,args,packet=None,success=True):
        self.last_action='cli_'+binary+'_'+args[0]
        result=self.dc('run','--rm','-T','--no-deps','--entrypoint','/usr/local/bin/'+binary,'operator',
                       *args,packet=packet,timeout=40,success=False)
        require((result.returncode==0)==success,'shipped_cli_status')
        for secret in self.secret_values:require(secret.encode() not in result.stderr,'cli_diagnostic_secret')
        if success:return json.loads(result.stdout) if result.stdout.strip() else None
        docs=[]
        for line in result.stderr.splitlines():
            if line.startswith(b'{'):
                try:docs.append(json.loads(line))
                except ValueError:pass
        require(len(docs)==1,'exact_application_error_required')
        return docs[0]

    def sql(self,text,database="postgres"):
        require(database in ("postgres","coding_tools_identity_test"),"fixed_fixture_database")
        result=subprocess.run([*self.command,'exec','-T','postgres','psql','-U','postgres','-d',database,
                               '-v','ON_ERROR_STOP=1','-At'],input=text.encode(),capture_output=True,timeout=30,check=False)
        require(result.returncode==0,'private_database_sql_failed')
        return result.stdout.decode().strip()

    def wait_postgres(self):
        for _ in range(45):
            _,record=self.container('postgres')
            if record['State'].get('Health',{}).get('Status')=='healthy':return
            time.sleep(1)
        raise RuntimeError('private_database_readiness_deadline')

    def prepare(self):
        version=self.exec([self.compose,'version','--short']).stdout.decode().strip().lstrip('v')
        require(version=='2.27.0','exact_compose_2_27_required')
        context=self.exec(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).stdout.decode().strip()
        require(context=='unix:///var/run/docker.sock','remote_docker_forbidden')
        require(not self.exec(['docker','ps','-aq','--filter','label=com.docker.compose.project='+self.project]).stdout.strip(),
                'project_must_be_new')
        engine=self.exec(['docker','version','--format','{{.Server.Version}}']).stdout.decode().strip()
        require(re.fullmatch(r'\d+\.\d+\.\d+',engine) and tuple(map(int,engine.split('.')))>=(28,0,0),'docker_loopback_security_floor')
        image=json.loads(self.exec(['docker','image','inspect',self.images['gateway']]).stdout)[0]
        component=tomllib.loads((ROOT/'services/cloud-gateway/Cargo.toml').read_text())['package']['version']
        require(image['Id']==self.images['gateway'] and image['Config']['User']=='65532:65532'
                and image['Config']['Labels']['org.opencontainers.image.revision']==os.environ['GITHUB_SHA']
                and image['Config']['Labels']['org.opencontainers.image.version']==component,'exact_gateway_image_source')
        normalized=json.loads(self.dc('--profile','operator','config','--format','json').stdout)
        require(normalized['services']['namespace']['ports'][0]['host_ip']=='127.0.0.1','normalized_loopback_binding')
        require(not normalized['services']['postgres'].get('ports'),'no_database_host_port')
        require(normalized['services']['operator']['logging']['driver']=='none','operator_secret_output_must_not_be_logged')
        self.created=True;self.dc('up','-d','postgres',timeout=120);self.wait_postgres()
        self.dc('create','--no-build','operator')
        _,operator=self.container('operator')
        require(operator['HostConfig']['LogConfig']['Type']=='none','actual_operator_log_driver')
        # Role name and random hex password are fixed-shape; SQL remains stdin only.
        self.sql("CREATE ROLE ctm_app LOGIN PASSWORD '"+self.dbpassword+"' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
                 "CREATE ROLE ctm_migration LOGIN PASSWORD '"+self.migration_password+"' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
                 'CREATE DATABASE coding_tools_identity_test OWNER ctm_migration;')
        require(self.sql("SELECT rolsuper::text||','||rolcreatedb::text||','||rolcreaterole::text FROM pg_roles WHERE rolname='ctm_app'")
                =='false,false,false','least_privilege_database_role')
        flags=['--config','/run/gateway/config.json','--secrets-stdin']
        self.cli('coding-tools-gateway',['migrate',*flags],self.migration_packet)
        database='coding_tools_identity_test'
        self.sql('REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO ctm_app; '
                 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO ctm_app; '
                 'GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO ctm_app;',database=database)
        tables=self.sql("SELECT tablename FROM pg_tables WHERE schemaname='public' AND left(tablename,4)='ctm_' ORDER BY tablename",database=database).splitlines()
        require(0<len(tables)<100 and all(re.fullmatch(r'ctm_[a-z0-9_]+',name) for name in tables),'fixed_application_tables')
        for name in tables:self.sql('GRANT INSERT,UPDATE,DELETE ON public."'+name+'" TO ctm_app;',database=database)
        require(self.sql("SELECT has_schema_privilege('ctm_app','public','CREATE')::text||','||has_table_privilege('ctm_app','public._sqlx_migrations','UPDATE')::text",database=database)=='false,false','runtime_cannot_change_schema_or_migration_ledger')
        self.cli('coding-tools-gateway',['provision-owner',*flags],dict(self.packet,password=self.password))
        self.cli('coding-tools-gateway',['register-client',*flags],self.packet)
        key=self.cli('coding-tools-agent',['generate-key','--output-stdout'])
        invitation=self.cli('coding-tools-gateway',['invite-device',*flags,'--output-stdout'],self.packet)
        self.secret_values += [key['pkcs8'],invitation['token']]
        proof=self.cli('coding-tools-agent',['prove-enrollment','--config','/run/gateway/enrollment.json',
                       '--bundle-stdin','--output-stdout'],dict(invitation=invitation,key=key))
        require('pkcs8' not in json.dumps(proof),'private_key_never_sent_to_gateway')
        connection=self.cli('coding-tools-gateway',['redeem-device','--config','/run/gateway/config.json',
                            '--bundle-stdin','--output-stdout'],dict(secrets=self.packet,proof=proof))
        self.device=connection['device']
        require(connection['origin']==self.origin and connection['connector']==self.config['connector'],'immutable_enrollment_identity')
        self.cli('coding-tools-control-gateway',['select-device',*flags,'--device',self.device],self.packet)
        return {'compose_version':version,'docker_version':engine,'gateway_component_version':component}

    def http(self,method,path,data=None,headers=None):
        h={'Host':self.domain};h.update(headers or {})
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=8)
        try:
            connection.request(method,path,body=data,headers=h);response=connection.getresponse()
            return response.status,{k.lower():v for k,v in response.getheaders()},response.read()
        finally:connection.close()

    def ready(self):
        for _ in range(40):
            try:
                if self.http('GET','/coding-tools/health/ready')[0]==200:return
            except OSError:pass
            time.sleep(.25)
        raise RuntimeError('container_gateway_readiness_deadline')

    def logs_clean(self):
        result=self.dc('logs','--no-color',success=False)
        require(result.returncode==0,'container_logs_observed')
        output=result.stdout
        for secret in self.secret_values:require(secret.encode() not in output,'container_log_secret_leak')
        return output

    def close(self):
        if self.sentinel is not None:self.sentinel.close()
        if self.created:
            self.dc('down','--volumes','--remove-orphans','--timeout','15',timeout=90)
            remaining=self.exec(['docker','ps','-aq','--filter','label=com.docker.compose.project='+self.project]).stdout.decode().split()
            # One-off CLI containers are also fresh and identified by this random project label.
            for container in remaining:self.exec(['docker','rm','-f',container],timeout=30)
            require(not self.exec(['docker','ps','-aq','--filter','label=com.docker.compose.project='+self.project]).stdout.strip(),
                    'owned_container_cleanup_incomplete')
        self.exec(['sudo','rm','-rf','--',str(self.root)],timeout=20)
