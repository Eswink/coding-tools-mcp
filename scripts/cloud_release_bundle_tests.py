"""Synthetic archive contracts only; these tests do not certify native binaries."""
import ast
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import cloud_release_bundle as gate

EXPECTED = dict(source_sha='a'*40, source_tree='b'*40, run_id='123', product_version='1.2.3-rc.4',
                component_versions={'coding-tools-cloud-gateway':'1.2.3-rc.4',
                                    'coding-tools-cloud-agent':'0.1.0','coding-tools-local-agent':'0.1.0'},
                target=gate.TARGET)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / 'binary'; self.binary.mkdir()
        self.package = self.root / 'package'; self.output = self.root / 'unpacked'
        docs = self.root / 'docs/releases'; docs.mkdir(parents=True)
        (docs / 'cloud-binary-install.md').write_text('Synthetic fixture README, no credentials')
        self.elf_bytes = b'\x7fELF\x02\x01' + b'\0'*12 + b'\x3e\x00' + b'synthetic, not executable'
        for name in gate.BINS: (self.binary / name).write_bytes(self.elf_bytes)

    def build(self):
        with patch.object(gate.platform, 'freedesktop_os_release', return_value={'ID':'ubuntu','VERSION_ID':'22.04'}), \
             patch.object(gate.platform, 'machine', return_value='x86_64'), \
             patch.object(gate, 'probe', return_value={'synthetic_test_observation': True}):
            gate.build(self.root, self.binary, self.package, EXPECTED)

    def rewrite_archive(self, mutate):
        archive = self.package / 'cloud-linux-amd64.tar.gz'
        with tarfile.open(archive, 'r:gz') as tar:
            members = [(m, tar.extractfile(m).read()) for m in tar.getmembers()]
        members = mutate(members)
        with tarfile.open(archive, 'w:gz') as tar:
            for member, data in members: tar.addfile(member, io.BytesIO(data))
        path = self.package / 'archive-receipt.json'; receipt = json.loads(path.read_text())
        receipt['archive'].update(size=archive.stat().st_size, sha256=gate.digest(archive))
        path.write_text(json.dumps(receipt))

    def test_exact_archive_and_binary_bytes_roundtrip(self):
        self.build(); manifest = gate.unpack(self.package, self.output, EXPECTED)
        self.assertFalse(manifest['publish_approved'])
        self.assertEqual(set(manifest['binaries']), set(gate.BINS))
        self.assertEqual({p.relative_to(self.output).as_posix() for p in self.output.rglob('*') if p.is_file()}, gate.MEMBERS)
        for name in gate.BINS: self.assertEqual((self.output / 'bin' / name).read_bytes(), self.elf_bytes)

    def test_elf_requires_64bit_amd64(self):
        path = self.binary / gate.BINS[0]; gate.elf(path)
        for value in (b'notelf', self.elf_bytes[:18]+b'\xb7\x00', b'\x7fELF\x01\x01'+self.elf_bytes[6:]):
            path.write_bytes(value)
            with self.assertRaises(ValueError): gate.elf(path)

    def test_archive_digest_and_source_version_mismatch_rejected(self):
        self.build()
        for key, value in [('source_sha', 'c'*40), ('product_version', '1.2.3-rc.9'), ('run_id', '999')]:
            with self.assertRaises(ValueError): gate.unpack(self.package, self.output, dict(EXPECTED, **{key:value}))
        archive = self.package / 'cloud-linux-amd64.tar.gz'; archive.write_bytes(archive.read_bytes()+b'changed')
        with self.assertRaises(ValueError): gate.unpack(self.package, self.output, EXPECTED)

    def test_archive_traversal_extra_and_duplicate_members_rejected(self):
        self.build()
        def extra(members):
            info = tarfile.TarInfo('../secret'); info.size=1; info.mode=0o644
            return members + [(info,b'x')]
        self.rewrite_archive(extra)
        with self.assertRaises(ValueError): gate.unpack(self.package, self.output, EXPECTED)
        self.assertFalse(self.output.exists())

    def test_symlink_member_rejected_before_writes(self):
        self.build()
        def link(members):
            member, data = members[0]; member.type=tarfile.SYMTYPE; member.linkname='/etc/passwd'
            return [(member,data),*members[1:]]
        self.rewrite_archive(link)
        with self.assertRaises(ValueError): gate.unpack(self.package, self.output, EXPECTED)
        self.assertFalse(self.output.exists())

    def test_inner_binary_digest_cannot_be_changed_with_outer_receipt(self):
        self.build()
        def change(members):
            return [(m, b'X'*len(data) if m.name.startswith('bin/') else data) for m,data in members]
        self.rewrite_archive(change)
        with self.assertRaises(ValueError): gate.unpack(self.package, self.output, EXPECTED)

    def test_inner_manifest_duplicate_or_boolean_schema_rejected(self):
        self.build()
        def change(members):
            result = []
            for member, data in members:
                if member.name == 'manifest.json':
                    data = data.replace(b'"schema": 1', b'"schema": true')
                    member.size = len(data)
                result.append((member, data))
            return result
        self.rewrite_archive(change)
        with self.assertRaises(ValueError): gate.unpack(self.package, self.output, EXPECTED)
        self.assertFalse(self.output.exists())

    def test_component_authority_does_not_bump_library_versions(self):
        for folder, name in [('cloud-gateway','coding-tools-cloud-gateway'),('cloud-agent','coding-tools-cloud-agent'),
                             ('local-agent','coding-tools-local-agent')]:
            directory=self.root/'services'/folder;directory.mkdir(parents=True)
            version=EXPECTED['component_versions'][name]
            (directory/'Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="{version}"\n')
            (directory/'Cargo.lock').write_text(f'[[package]]\nname="{name}"\nversion="{version}"\n')
        self.assertEqual(gate.versions(self.root, EXPECTED['product_version']), EXPECTED['component_versions'])
        with self.assertRaises(ValueError): gate.versions(self.root, '1.2.3-rc.9')
        (self.root/'services/cloud-agent/Cargo.lock').write_text('[[package]]\nname="coding-tools-cloud-agent"\nversion="0.2.0"')
        with self.assertRaises(ValueError): gate.versions(self.root, EXPECTED['product_version'])

    def test_all_actual_source_process_cases_required(self):
        source=Path(__file__).resolve().parents[1];evidence=self.root/'evidence';evidence.mkdir()
        for script,suite in [('run_service_http.py','standalone_process_http'),('run_agent_process.py','agent_process_wss')]:
            tree=ast.parse((source/'services/cloud-gateway/tests'/script).read_text())
            names=sorted({n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call)
                          and isinstance(n.func,ast.Name) and n.func.id=='passed' and n.args and isinstance(n.args[0],ast.Constant)})
            (evidence/(suite+'.json')).write_text(json.dumps(dict(suite=suite,result='PASS',passed=len(names),cases=names)))
        gate.smoke_reports(source,evidence)
        path=evidence/'agent_process_wss.json';value=json.loads(path.read_text());value['cases'].pop();path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):gate.smoke_reports(source,evidence)


if __name__ == '__main__':
    unittest.main()
