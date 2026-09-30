"""Pure topology contracts; actual Docker proof belongs to the dedicated CI job."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('runtime_topology',ROOT/'deploy/cloud-gateway/runtime_topology.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
IMAGES=dict(gateway='sha256:'+'a'*64,ingress='nginx@sha256:'+'b'*64,postgres='postgres@sha256:'+'c'*64)
CONNECTOR='00000000-0000-0000-0000-000000000001'


class RuntimeTopologyTests(unittest.TestCase):
    def value(self):return module.compose(Path('/tmp/private-fixture'),IMAGES,'gateway.example.invalid',CONNECTOR,28880)

    def test_only_namespace_publishes_explicit_loopback(self):
        services=self.value()['services']
        self.assertEqual(services['namespace']['ports'],[dict(target=8080,published='28880',host_ip='127.0.0.1',protocol='tcp')])
        for name in ('gateway','ingress','postgres','operator'):self.assertNotIn('ports',services[name])
        self.assertEqual(services['ingress']['network_mode'],'service:namespace')
        self.assertNotIn('networks',services['ingress'])

    def test_nonroot_private_db_and_no_host_network(self):
        value=self.value();self.assertTrue(value['networks']['database']['internal'])
        for name,service in value['services'].items():
            self.assertEqual(service['user'],'999:999' if name=='postgres' else '65532:65532')
            self.assertTrue(service['read_only']);self.assertEqual(service['cap_drop'],['ALL'])
            self.assertIn('no-new-privileges:true',service['security_opt'])
            self.assertNotEqual(service.get('network_mode'),'host')
        self.assertEqual(value['services']['postgres']['networks'],['database'])
        self.assertEqual(value['services']['operator']['networks'],['database'])

    def test_operator_secret_documents_never_use_service_logging(self):
        service=self.value()['services']['operator']
        self.assertEqual(service['logging'],{'driver':'none'})
        self.assertEqual(service['profiles'],['operator']);self.assertEqual(service['restart'],'no')
        self.assertEqual(service['command'],['--help'])

    def test_actual_json_cli_and_directory_mount_contract(self):
        gateway=self.value()['services']['gateway']
        self.assertEqual(gateway['command'],['serve','--config','/run/gateway/config.json','--secrets-file','/run/gateway/runtime.json'])
        self.assertNotIn('environment',gateway)
        volume=gateway['volumes'][0]
        self.assertTrue(volume['read_only']);self.assertFalse(volume['bind']['create_host_path'])
        self.assertEqual(volume['target'],'/run/gateway')

    def test_proxy_target_host_headers_and_no_query_logs(self):
        value=module.ingress_config('gateway.example.invalid',CONNECTOR)
        self.assertEqual(value.count('proxy_pass http://127.0.0.1:28880;'),4)
        self.assertIn('if ($http_host != "gateway.example.invalid") { return 421; }',value)
        for line in ('proxy_set_header Forwarded "";','proxy_set_header X-Forwarded-Host "";',
                     'proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;',
                     'proxy_set_header Sec-WebSocket-Protocol $http_sec_websocket_protocol;',
                     'access_log off;','error_log /dev/null crit;'):
            self.assertIn(line,value)
        self.assertNotIn('listen 443',value)
        self.assertEqual(value.count('proxy_set_header Upgrade $http_upgrade;'),1)

    def test_upgrade_route_matches_shipped_managed_channel(self):
        import re
        transport=(ROOT/'services/cloud-gateway/src/channel/transport.rs').read_text()
        routes=transport.split('pub fn managed_agent_channel_routes(',1)[1]
        suffix=re.search(r'let path = format!\("\{\}([^"\n]+)", control\.identity\(\)\.prefix\(\)\);',routes)
        self.assertIsNotNone(suffix,'Shipped route shape changed; review the proxy contract')
        route='/coding-tools'+suffix.group(1)
        self.assertEqual(route,'/coding-tools/agent')
        config=module.ingress_config('gateway.example.invalid',CONNECTOR)
        self.assertIn('location = '+route+' {',config)
        fixture=(ROOT/'tests/cloud-gateway-deployment/run_container_topology.py').read_text()
        self.assertIn('GET '+route+' HTTP/1.1',fixture)
        self.assertNotIn('/agent/connect',config)
        self.assertNotIn('/agent/connect',fixture)

    def test_mutable_or_foreign_images_and_unsafe_identity_rejected(self):
        for key,value in [('gateway','example.invalid/image:latest'),('ingress','nginx:stable'),('postgres','other@sha256:'+'c'*64)]:
            with self.assertRaises(ValueError):module.image_refs(dict(IMAGES,**{key:value}))
        for domain in ('foreign; return 200;', 'UPPER.example.invalid','localhost'):
            with self.assertRaises(ValueError):module.compose(Path('/tmp/fixture'),IMAGES,domain,CONNECTOR,28880)
        with self.assertRaises(ValueError):module.compose(Path('relative'),IMAGES,'gateway.example.invalid',CONNECTOR,28880)
        with self.assertRaises(ValueError):module.compose(Path('/tmp/fixture'),IMAGES,'gateway.example.invalid',CONNECTOR,443)

    def test_readonly_port_observation_never_claims_safe_apply(self):
        with tempfile.TemporaryDirectory() as raw:
            path=Path(raw)/'tcp'
            path.write_text('header\n 0: 0100007F:70D0 00000000:0000 0A ignored\n')
            value=module.port_observation(28880,[path])
            self.assertTrue(value['collision_observed']);self.assertFalse(value['availability_verified'])
            self.assertFalse(module.port_observation(28881,[path])['collision_observed'])
            self.assertIsNone(module.port_observation(28880,[Path(raw)/'missing'])['collision_observed'])

    def test_readonly_config_explicitly_includes_operator_profile(self):
        import ast
        source=(ROOT/'tests/cloud-gateway-deployment/container_fixture.py').read_text()
        calls=[node for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Call)
               and isinstance(node.func,ast.Attribute) and node.func.attr=='dc']
        config_calls=[[arg.value for arg in node.args if isinstance(arg,ast.Constant)]
                      for node in calls if any(isinstance(arg,ast.Constant) and arg.value=='config' for arg in node.args)]
        self.assertEqual(config_calls,[['--profile','operator','config','--format','json']])
        # Profile inclusion is read-only, not an unconditional operator service start.
        self.assertNotIn("self.dc('--profile','operator','up'",source)
        self.assertIn("normalized['services']['operator']['logging']['driver']=='none'",source)

    def test_command_diagnostics_never_expose_arguments_or_output(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(Path(__file__).parent))
        import container_fixture as fixture
        secret='unique-private-fixture-value'
        result=SimpleNamespace(returncode=126,stdout=secret.encode(),stderr=b'permission denied '+secret.encode())
        value=fixture.command_diagnostic(['/fixed/compose','-f',secret,'exec','-T','namespace','id','-u'],result,'/fixed/compose')
        self.assertEqual(value,dict(operation='compose_exec_namespace_id',exit_code=126,category='permission_denied'))
        self.assertNotIn(secret,str(value))
        result.stderr=b'unknown '+secret.encode()
        self.assertEqual(fixture.command_diagnostic(['unrecognized',secret],result,'/fixed/compose')['category'],'unspecified')

    def test_command_failure_retains_original_assertion_with_fixed_diagnostics(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(Path(__file__).parent))
        import container_fixture as fixture
        item=fixture.Fixture.__new__(fixture.Fixture);item.compose='/fixed/compose'
        with patch.object(fixture.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=b'',stderr=b'container is not running')):
            with self.assertRaises(fixture.FixtureFailure) as failure:item.exec(['/fixed/compose','up','-d','ingress'])
        self.assertEqual(failure.exception.code,'fixture_command_failed')
        self.assertEqual(failure.exception.diagnostic,dict(operation='compose_up_ingress',exit_code=1,category='container_not_running'))
        self.assertEqual(item.last_action,'compose_up_ingress')

    def test_docker_fixture_refuses_nonhosted_environment_before_actions(self):
        sys.path.insert(0,str(Path(__file__).parent))
        import container_fixture
        with patch.dict(container_fixture.os.environ,{},clear=True),patch.object(container_fixture.subprocess,'run') as command:
            with self.assertRaises(container_fixture.FixtureFailure):container_fixture.Fixture(Path('/tmp/no-tool'),IMAGES)
            command.assert_not_called()

    def process_fixture(self,service='namespace'):
        sys.path.insert(0,str(Path(__file__).parent))
        import container_fixture as fixture
        item=fixture.Fixture.__new__(fixture.Fixture);item.compose='/fixed/compose'
        uid='999' if service=='postgres' else '65532'
        record={'Config':{'User':uid+':'+uid},'State':{'Running':True,'Restarting':False,'Pid':123}}
        return fixture,item,record,uid

    def test_process_identity_observes_owned_live_processes_without_exec(self):
        from types import SimpleNamespace
        for service in ('namespace','gateway','ingress','postgres'):
            with self.subTest(service=service):
                fixture,item,record,uid=self.process_fixture(service)
                result=SimpleNamespace(stdout=f'  PID UID GID\n 123 {uid} {uid}\n 456 {uid} {uid}\n'.encode())
                with patch.object(item,'container',return_value=('a'*64,record)) as owned,\
                     patch.object(item,'exec',return_value=result) as observed,patch.object(item,'dc') as compose:
                    item.assert_process_identity(service)
                    owned.assert_called_once_with(service)
                    observed.assert_called_once_with(['docker','top','a'*64,'-eo','pid,uid,gid'])
                    compose.assert_not_called()

    def test_process_identity_refuses_wrong_or_stopped_container_before_top(self):
        for change in ({'Config':{'User':'0:0'}},{'Config':{'User':'65532:0'}},
                       {'State':{'Running':False,'Pid':123}}, {'State':{'Running':True,'Restarting':True,'Pid':123}},
                       {'State':{'Running':True,'Pid':0}}, {'State':{'Running':True,'Pid':'123'}},
                       {'State':{'Running':True,'Pid':True}}):
            with self.subTest(change=change):
                fixture,item,record,_=self.process_fixture();record.update(change)
                with patch.object(item,'container',return_value=('a'*64,record)),patch.object(item,'exec') as observed:
                    with self.assertRaises(fixture.FixtureFailure):item.assert_process_identity('namespace')
                    observed.assert_not_called()

    def test_process_identity_refuses_empty_malformed_mixed_or_stale_observation(self):
        from types import SimpleNamespace
        observations=(b'',b'PID UID GID\n',b'UID GID\n65532 65532\n',
                      b'PID UID GID COMMAND\n123 65532 65532 private-value\n',
                      b'PID UID GID\n123 65532\n',b'PID UID GID\n123 nobody 65532\n',
                      b'PID UID GID\n123 0 0\n',b'PID UID GID\n123 65532 0\n',
                      b'PID UID GID\n123 65532 65532\n456 0 0\n',
                      b'PID UID GID\n456 65532 65532\n',b'PID UID GID\n0 65532 65532\n',
                      b'PID UID GID\n123 65532 65532\n123 65532 65532\n',
                      b'PID UID GID\n123 65532 65532\n\n',b'PID UID GID\n123 \xff 65532\n')
        for output in observations:
            with self.subTest(output=output):
                fixture,item,record,_=self.process_fixture()
                with patch.object(item,'container',return_value=('a'*64,record)),\
                     patch.object(item,'exec',return_value=SimpleNamespace(stdout=output)):
                    with self.assertRaises(fixture.FixtureFailure) as failure:item.assert_process_identity('namespace')
                    self.assertNotIn('private-value',str(failure.exception))

    def test_process_identity_preserves_owned_container_and_command_failures(self):
        fixture,item,record,_=self.process_fixture()
        with patch.object(item,'container',side_effect=fixture.FixtureFailure('container_owner_mismatch')),\
             patch.object(item,'exec') as observed:
            with self.assertRaisesRegex(fixture.FixtureFailure,'container_owner_mismatch'):item.assert_process_identity('namespace')
            observed.assert_not_called()
        with patch.object(item,'container',return_value=('a'*64,record)),\
             patch.object(item,'exec',side_effect=fixture.FixtureFailure('fixture_command_failed')):
            with self.assertRaisesRegex(fixture.FixtureFailure,'fixture_command_failed'):item.assert_process_identity('namespace')

    def test_process_identity_refuses_unknown_service_without_actions(self):
        fixture,item,_,_=self.process_fixture()
        with patch.object(item,'container') as owned,patch.object(item,'exec') as observed:
            with self.assertRaises(fixture.FixtureFailure):item.assert_process_identity('foreign')
            owned.assert_not_called();observed.assert_not_called()

    def test_top_diagnostics_do_not_export_identity_rows_or_arguments(self):
        from types import SimpleNamespace
        fixture,item,_,_=self.process_fixture()
        result=SimpleNamespace(returncode=1,stdout=b'private-value',stderr=b'private-value is not running')
        value=fixture.command_diagnostic(['docker','top','private-value','-eo','pid,uid,gid'],result,item.compose)
        self.assertEqual(value,dict(operation='docker_top',exit_code=1,category='container_not_running'))

    def test_identity_observer_does_not_relax_anchor_limits_or_spawn_id(self):
        import ast
        self.assertEqual(self.value()['services']['namespace']['pids_limit'],4)
        self.assertEqual(self.value()['services']['namespace']['mem_limit'],'16m')
        tree=ast.parse((ROOT/'tests/cloud-gateway-deployment/run_container_topology.py').read_text())
        observer=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='inspect_boundaries')
        calls=[node for node in ast.walk(observer) if isinstance(node,ast.Call)]
        self.assertEqual(sum(isinstance(node.func,ast.Attribute) and node.func.attr=='assert_process_identity' for node in calls),1)
        for call in calls:
            if isinstance(call.func,ast.Attribute) and call.func.attr=='dc':
                self.assertNotIn('id',[arg.value for arg in call.args if isinstance(arg,ast.Constant)])


if __name__=='__main__':unittest.main()
