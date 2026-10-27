"""G1+G3 hosted-CI fixture for run_container_topology only.

container_fixture.py is byte-pinned by the frozen RC two-hop contract, so the G1 kit
bootstrap SQL, G3 ingress limits and ctm_app denial probes live here as a subclass.
"""
import importlib.util
import os
import re

import container_fixture as base
from container_fixture import ROOT, FixtureFailure, require, topology

_spec = importlib.util.spec_from_file_location('deploy_kit', ROOT / 'deploy/cloud-gateway/kit/kit.py')
kit = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(kit)
__all__ = ['CI_TRUSTED_PROXIES', 'DENIED_PROBES', 'KitFixture', 'FixtureFailure', 'require', 'topology', 'kit']
# Hosted-CI only: covers every Docker default bridge pool. The live edge gateway is asserted inside it.
CI_TRUSTED_PROXIES = ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')
# Each must fail as ctm_app with a permission error after the grants phase.
DENIED_PROBES = (('runtime_cannot_create_table', 'CREATE TABLE public.ctm_probe(x int);'),
                 ('runtime_cannot_update_migration_ledger', 'UPDATE public._sqlx_migrations SET description=description;'),
                 ('runtime_cannot_create_role', 'CREATE ROLE ctm_probe;'))


class KitFixture(base.Fixture):
    def __init__(self, compose, images):
        super().__init__(compose, images)
        try:
            ingress = self.root / 'ingress-private'
            # The frozen base wrote the pre-G3 default and handed the folder to 65532; reclaim, rewrite, hand back.
            self.exec(['sudo', 'chown', '-R', f'{os.getuid()}:{os.getgid()}', str(ingress)])
            for name, trusted in (('nginx.conf', ()), ('nginx.trusted.conf', CI_TRUSTED_PROXIES)):
                path = ingress / name
                if path.exists():path.chmod(0o600)
                path.write_text(topology.ingress_config(self.domain, self.config['connector'],
                                                        trusted_proxies=trusted, rate_limits=True))
                path.chmod(0o400)
            self.exec(['sudo', 'chown', '-R', '65532:65532', str(ingress)])
        except Exception:
            self.close()
            raise

    def sql_denied(self, statement, name):
        """Fixed probe statements only; a permission error is the only accepted outcome."""
        result = base.subprocess.run([*self.command, 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d',
                                      'coding_tools_identity_test', '-v', 'ON_ERROR_STOP=1', '-At'],
                                     input=('SET ROLE ctm_app;\n' + statement + '\n').encode(),
                                     capture_output=True, timeout=30, check=False)
        require(result.returncode != 0 and b'permission denied' in result.stderr.lower(), name)

    def sql(self, text, database='postgres'):
        """Route the frozen base's three inline bootstrap statements to the shipped kit template."""
        if text.startswith('CREATE ROLE ctm_app LOGIN PASSWORD '):
            require(database == 'postgres', 'kit_bootstrap_database')
            result = super().sql(kit.psql_preamble(dict(app_password=self.dbpassword, migration_password=self.migration_password,
                                                        database='coding_tools_identity_test')) + kit.sql_phase('bootstrap'))
            self._kit_bootstrap_done = True  # runtime proof the frozen inline bootstrap was routed to the kit template
            return result
        if text.startswith('REVOKE CREATE ON SCHEMA public FROM PUBLIC;'):
            require(database == 'coding_tools_identity_test', 'kit_grants_database')
            require(getattr(self, '_kit_bootstrap_done', False), 'kit_bootstrap_before_grants')
            self._kit_grants_done = True
            return super().sql(kit.sql_phase('grants'), database=database)
        if re.fullmatch(r'GRANT INSERT,UPDATE,DELETE ON public\."ctm_[a-z0-9_]+" TO ctm_app;', text):
            require(getattr(self, '_kit_grants_done', False), 'kit_grants_cover_tables')
            return ''
        result = super().sql(text, database=database)
        if text.startswith("SELECT has_schema_privilege('ctm_app','public','CREATE')"):
            for probe, statement in DENIED_PROBES:self.sql_denied(statement, probe)
            self.denied_probes = [probe for probe, _ in DENIED_PROBES]
        return result

    def prepare(self):
        versions = super().prepare()
        require(getattr(self, '_kit_bootstrap_done', False) is True, 'kit_bootstrap_routed')
        require(getattr(self, '_kit_grants_done', False) is True, 'kit_grants_routed')
        require(getattr(self, 'denied_probes', None) == [p for p, _ in DENIED_PROBES], 'kit_denial_probes_ran')
        return dict(versions, denied_probes=list(self.denied_probes))
