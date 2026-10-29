"""Synthetic metadata and Docker-argument tests; native image proof is CI-only."""
import copy
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import cloud_image_gate as gate

IMAGE='sha256:'+'a'*64
EXPECTED={'source_sha':'b'*40,'product_version':'1.2.3-rc.4'}


class ImageTests(unittest.TestCase):
    def fixture(self):
        return dict(Id=IMAGE,Architecture='amd64',Os='linux',Config=dict(User='65532:65532',
            Entrypoint=['/usr/local/bin/coding-tools-mcp-gateway'],Cmd=['--help'],Labels={
                'org.opencontainers.image.revision':EXPECTED['source_sha'],
                'org.opencontainers.image.version':EXPECTED['product_version']}))

    def test_nonroot_exact_image_metadata(self):
        gate.metadata(self.fixture(),IMAGE,EXPECTED)

    def test_wrong_uid_entrypoint_version_or_source_rejected(self):
        for key,value in [('User','0'),('Entrypoint',['/bin/sh']),('Cmd',['serve'])]:
            data=self.fixture();data['Config'][key]=value
            with self.assertRaises(ValueError):gate.metadata(data,IMAGE,EXPECTED)
        for key in ('org.opencontainers.image.revision','org.opencontainers.image.version'):
            data=self.fixture();data['Config']['Labels'][key]='wrong'
            with self.assertRaises(ValueError):gate.metadata(data,IMAGE,EXPECTED)

    def test_no_declared_ports_or_persistent_volumes(self):
        for key in ('ExposedPorts','Volumes'):
            data=self.fixture();data['Config'][key]={'unreviewed':{}}
            with self.assertRaises(ValueError):gate.metadata(data,IMAGE,EXPECTED)

    def test_commands_have_fixed_isolation_and_readonly_fixture(self):
        command=gate.command(IMAGE,'coding-tools-gateway',['--help'],Path('/tmp/fresh-fixture'))
        self.assertEqual(command[:2],['docker','run'])
        for required in ('none','--read-only','ALL','no-new-privileges:true','65532:65532'):
            self.assertIn(required,command)
        self.assertIn('type=bind,src=/tmp/fresh-fixture,dst=/run/fixture,readonly',command)
        self.assertNotIn('--privileged',command);self.assertNotIn('--publish',command)
        self.assertNotIn('--network=host',command)

    def test_unpinned_image_and_arbitrary_entrypoint_rejected(self):
        with self.assertRaises(ValueError):gate.command('ubuntu:latest','id',['-u'])
        with self.assertRaises(ValueError):gate.command(IMAGE,'sh',['-c','anything'])
        with self.assertRaises(ValueError):gate.command(IMAGE,'id',['-u'],Path('/tmp/a,b'))

    def test_exact_failure_stage_not_generic_error(self):
        good=subprocess.CompletedProcess([],1,b'',b'{"ok":false,"error":"file_protection_failed"}')
        gate.exact_error(good,'file_protection_failed')
        for wrong in [subprocess.CompletedProcess([],0,b'',good.stderr),
                      subprocess.CompletedProcess([],1,b'unexpected',good.stderr),
                      subprocess.CompletedProcess([],1,b'',b'{"ok":false,"error":"invalid_secret_input"}')]:
            with self.assertRaises(ValueError):gate.exact_error(wrong,'file_protection_failed')

    def test_local_or_self_hosted_execution_rejected_before_docker(self):
        with patch.dict(gate.os.environ,{},clear=True),patch.object(gate.subprocess,'check_output') as docker:
            with self.assertRaises(ValueError):gate.run(IMAGE,Path('/tmp/unused'),EXPECTED)
            docker.assert_not_called()


if __name__=='__main__':unittest.main()
