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

    def test_docker_fixture_refuses_nonhosted_environment_before_actions(self):
        sys.path.insert(0,str(Path(__file__).parent))
        import container_fixture
        with patch.dict(container_fixture.os.environ,{},clear=True),patch.object(container_fixture.subprocess,'run') as command:
            with self.assertRaises(container_fixture.FixtureFailure):container_fixture.Fixture(Path('/tmp/no-tool'),IMAGES)
            command.assert_not_called()


if __name__=='__main__':unittest.main()
