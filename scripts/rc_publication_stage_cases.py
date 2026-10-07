"""Synthetic authenticated shapes and real source/archive validators; no live authority."""
from contextlib import contextmanager
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import rc_artifact_consumer as consumer
from rc_consumer_fixtures import ConsumerFixture, write_json, write_lock
from rc_consumer_io import ConsumerError, PrivateRoot
from rc_consumer_plan_tests import API, zip_bytes
from rc_pretag_types import SourceIdentity, InvocationIdentity, REPOSITORY_ID
import rc_publication_contract as core
import rc_pretag_composition_tests as c
import rc_publication_stage as stage
from rc_publication_https_fixture import stable_identity

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), '-c', 'core.hooksPath=/dev/null',
        '-c', 'core.fsmonitor=false', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false', *args],
        stderr=subprocess.DEVNULL, env=c.git_environment(), timeout=30).decode().strip()


class SourceFixture(ConsumerFixture):
    def commit_source(self):
        gate = consumer.snapshot.gate
        overlay = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        git(self.root, 'init', '-q')
        git(self.root, 'fetch', '--quiet', '--no-tags', '--depth=1', str(ROOT), gate.reviewed.BASE)
        git(self.root, 'read-tree', gate.reviewed.BASE)
        git(self.root, 'checkout-index', '--all', '--force')
        for path, data in overlay.items():
            (self.root / path).write_bytes(data)
        name = gate.rc.PACKAGE
        write_json(self.root / 'package.json', dict(name=name, version=self.version))
        lock = json.loads((self.root / 'package-lock.json').read_text())
        lock.update(name=name, version=self.version)
        lock['packages'][''] = dict(name=name, version=self.version)
        write_json(self.root / 'package-lock.json', lock)
        write_json(self.root / 'src-tauri/tauri.conf.json', dict(version=self.version))
        (self.root / 'src-tauri/Cargo.toml').write_text(f'[package]\nname="{name}"\nversion="{self.version}"\n')
        self.noncloud_locks['desktop']['package'].append(dict(name=name, version=self.version))
        write_lock(self.root / 'src-tauri/Cargo.lock', self.noncloud_locks['desktop'])
        for path in (gate.FINAL_WORKFLOW, gate.final.WORKFLOW, consumer.snapshot.CONSUMER_WORKFLOW):
            target = self.root / path
            target.parent.mkdir(exist_ok=True, parents=True)
            target.write_bytes((ROOT / path).read_bytes())
        git(self.root, 'add', '.')
        tree = git(self.root, 'write-tree')
        parts = git(self.root, 'diff', '--name-status', '--no-renames', gate.reviewed.BASE, tree).splitlines()
        entries = []
        for line in parts:
            status, path = line.split('\t')
            if path != gate.reviewed.MANIFEST:
                entries.append(dict(path=path, status=status, before=gate.reviewed.blob(self.root, gate.reviewed.BASE, path),
                                    after=gate.reviewed.blob(self.root, tree, path)))
        write_json(self.root / gate.reviewed.MANIFEST, dict(schema=1, base_commit=gate.reviewed.BASE,
            version=self.version, review_reference='Synthetic publisher fixture, not approval', entries=sorted(entries, key=lambda x: x['path'])))
        git(self.root, 'update-ref', 'HEAD', gate.reviewed.BASE)
        git(self.root, 'add', '.')
        git(self.root, '-c', 'user.name=Synthetic publisher fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '-qm', 'Synthetic publisher fixture, not release evidence')
        self.sha, self.tree = (c._git('rev-parse', ref, root=self.root).decode().strip() for ref in ('HEAD', 'HEAD^{tree}'))
        git(self.root, 'tag', 'v' + self.version)


@contextmanager
def publisher_fixture():
    with tempfile.TemporaryDirectory(prefix='publisher-case-') as parent, patch.dict(os.environ, c.git_environment(), clear=True):
        f = SourceFixture(parent)
        f.producer.repository_id = REPOSITORY_ID
        f.sign_cloud(); f.build_noncloud(); f.refresh_reports()
        final_bytes = zip_bytes(f.bundle)
        api = API(f, final_bytes)
        for run_id in (123, 456):
            run = api.data[f'/actions/runs/{run_id}']
            for key in ('repository', 'head_repository'):
                run[key]['id'] = REPOSITORY_ID
            api.data[f'/actions/runs/{run_id}/attempts/{run["run_attempt"]}'] = copy.deepcopy(run)
        api.data['/']['id'] = REPOSITORY_ID
        api.data['/actions/artifacts/13']['workflow_run'].update(repository_id=REPOSITORY_ID, head_repository_id=REPOSITORY_ID)
        cpath = consumer.snapshot.CONSUMER_WORKFLOW
        crun = dict(copy.deepcopy(api.data['/actions/runs/123']), id=999, workflow_id=19, path=cpath,
                    event='workflow_dispatch', run_started_at='2026-10-01T00:03:00Z', updated_at='2026-10-01T00:10:00Z')
        cjob = dict(id=9991, run_id=999, run_attempt=1, name=stage.CONSUME_JOB, head_sha=f.sha,
                    status='completed', conclusion='success', started_at='2026-10-01T00:03:01Z', completed_at='2026-10-01T00:09:59Z')
        api.data.update({'/actions/workflows/' + Path(cpath).name: dict(id=19, path=cpath),
            '/actions/runs/999': crun, '/actions/runs/999/attempts/1': copy.deepcopy(crun),
            '/actions/runs/999/attempts/1/jobs?per_page=100&page=1': dict(total_count=1, jobs=[cjob])})
        source = SourceIdentity(consumer.snapshot.REPOSITORY, REPOSITORY_ID, f.sha, f.tree, f.version)
        invocations, ids = [], []
        for role, ident in (('final', 123), ('integration', 456), ('consumer', 999)):
            run = api.data[f'/actions/runs/{ident}']
            ref = 'refs/heads/' + run['head_branch']
            invocations.append(InvocationIdentity(role, source, ident, run['run_attempt'], run['workflow_id'],
                run['path'], source.repository + '/' + run['path'] + '@' + ref, f.sha,
                consumer.snapshot.gate.reviewed.blob(f.root, f.sha, run['path'])['blob_sha'], run['event'], ref))
            ids.append(tuple(j['id'] for j in api.data[f'/actions/runs/{ident}/attempts/{run["run_attempt"]}/jobs?per_page=100&page=1']['jobs']))
        runs = consumer.snapshot._select_source_runs_for_identity(api, f.sha, REPOSITORY_ID, api.expected)
        metadata = consumer.snapshot.authenticate_bundle_metadata(api, runs, 13)
        producer = consumer.snapshot.derive_final_producer(api.candidate, runs, metadata)
        api.candidate['consumer'].update(repository_id=REPOSITORY_ID, workflow_ref=invocations[2].workflow_ref)
        with PrivateRoot(parent, source_root=f.root) as output, PrivateRoot(parent, source_root=f.root) as receipts:
            plan = consumer.make_asset_plan(dict(candidate=api.candidate, selection=runs, producer=producer),
                                            f.verify(), SimpleNamespace(path=f.bundle), output, receipts)
            # Prepare historical receipts once; the stage must never reconstruct their clock.
            provenance = {k: v for k, v in plan.items() if k != 'assets'}
            provenance['verified_at'] = '2026-10-01T00:08:00Z'
            payloads = {p.name: p.read_bytes() for p in output.path.iterdir()}
            payloads['RC_PROVENANCE.json'] = consumer.encode(provenance)
            cname = f'SHA256SUMS_{f.version}.txt'
            payloads[cname] = ''.join(f'{hashlib.sha256(payloads[n]).hexdigest()}  {n}\n' for n in sorted(payloads) if n != cname).encode()
            rows = [dict(r, size=len(payloads[r['name']]), sha256=hashlib.sha256(payloads[r['name']]).hexdigest()) for r in plan['assets']]
            plan_bytes = consumer.encode(dict(provenance, assets=rows))
        subject = core.PublicationSubject(source, 'v' + f.version, f.sha, tuple(invocations), tuple(ids), 13,
            len(final_bytes), hashlib.sha256(final_bytes).hexdigest(), hashlib.sha256(plan_bytes).hexdigest(),
            ('a' * 64,) * len(core.GATE_IDS), stable_identity())
        value = SimpleNamespace(root=f.root, parent=parent, temporary_parent=parent, api=api, source=f, plan=core.AssetPlanView(tuple(core.Asset(**r) for r in rows)),
            plan_bytes=plan_bytes, provenance_bytes=payloads['RC_PROVENANCE.json'], payloads=payloads, archives={13: final_bytes})
        value.selection = stage.Selection(subject, 14, 1, '0' * 64)
        set_receipts(value)
        yield value


def set_receipts(f, members=None):
    members = members or [('rc-consumer-receipts-fixture/' + n, data) for n, data in
                         (('RC_PROVENANCE.json', f.provenance_bytes), ('rc-asset-plan.json', f.plan_bytes))]
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in members:
            z.writestr(name, data)
    data = output.getvalue()
    f.archives[14] = data
    f.selection = replace(f.selection, consumer_artifact_size=len(data), consumer_artifact_sha256=hashlib.sha256(data).hexdigest())
    artifact = dict(f.api.data['/actions/artifacts/13'], id=14, name='rc-artifact-consumer-sanitized-999-1',
        size_in_bytes=len(data), digest='sha256:' + hashlib.sha256(data).hexdigest(), created_at='2026-10-01T00:09:00Z',
        updated_at='2026-10-01T00:09:01Z', workflow_run=dict(f.api.data['/actions/artifacts/13']['workflow_run'], id=999))
    f.api.data['/actions/artifacts/14'] = artifact
    f.api.data['/actions/runs/999/artifacts?per_page=100&page=1'] = dict(total_count=1, artifacts=[artifact])


def artifact_route(f, method, path, headers, body):
    prefix = '/repos/' + consumer.snapshot.REPOSITORY
    if method != 'GET':
        return None
    suffix = '/' if path == prefix else path.removeprefix(prefix)
    if suffix in f.api.data:
        return 200, {}, json.dumps(f.api.get(suffix)).encode()
    if suffix.startswith('/actions/artifacts/') and suffix.endswith('/zip'):
        ident = int(suffix.split('/')[-2])
        return 302, {'Location': f'https://productionresultssa5.blob.core.windows.net/fixture-artifact/{ident}'}, b''
    if path.startswith('/fixture-artifact/'):
        return 200, {}, f.archives[int(path.rsplit('/', 1)[1])]
    return None


@contextmanager
def artifact_worker(f, server=None):
    """Patch only private worker launch source; retain production IPC and byte checks."""
    script = Path(f.parent) / 'fixture-worker.py'
    script.write_text('import sys, io, json, ssl, socket, http.client\nfrom email.message import Message\n'
        'from urllib.parse import urlsplit\nfrom pathlib import Path\n'
        f'sys.path.insert(0, {str(ROOT / "scripts")!r})\nimport rc_consumer_transport_worker as wire\n'
        + (f'PORT={server.port}\nCA={str(server.ca)!r}\n' if server else 'PORT=None\n') +
        f'BASE={f.parent!r}\nclass Opener:\n def open(self, request, timeout):\n'
        '  parsed=urlsplit(request.full_url)\n  if PORT:\n'
        '   connection=http.client.HTTPSConnection(parsed.hostname,timeout=timeout,context=ssl.create_default_context(cafile=CA))\n'
        '   connection.sock=connection._context.wrap_socket(socket.create_connection(("127.0.0.1",PORT),timeout),server_hostname=parsed.hostname)\n'
        '   connection.request("GET",parsed.path,headers=dict(request.header_items()))\n'
        '   response=connection.getresponse();response.code=response.status\n'
        '   close=response.close\n   def cleanup():\n    close();connection.close()\n'
        '   response.close=cleanup\n   return response\n'
        '  ident=int(parsed.path.split("/")[-2] if parsed.path.endswith("/zip") else parsed.path.rsplit("/",1)[1])\n'
        '  response=io.BytesIO(b"" if parsed.path.endswith("/zip") else Path(BASE,f"archive-{ident}.zip").read_bytes())\n'
        '  response.code=302 if parsed.path.endswith("/zip") else 200\n  response.headers=Message()\n'
        '  response.headers["Location"]=f"https://productionresultssa5.blob.core.windows.net/fixture-artifact/{ident}"\n'
        '  response.read1=response.read\n  return response\nsys.exit(wire.main(Opener()))\n')
    for ident, data in f.archives.items():
        (Path(f.parent) / f'archive-{ident}.zip').write_bytes(data)
    with patch.object(consumer.transport, 'WORKER', script):
        yield


class StageCases(unittest.TestCase):
    def setUp(self):
        context = publisher_fixture()
        self.f = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def open_stage(self):
        worker = artifact_worker(self.f)
        worker.__enter__(); self.addCleanup(worker.__exit__, None, None, None)
        owner = stage.stage_selected(self.f.root, self.f.selection, self.f.api, temporary_parent=self.f.parent)
        self.addCleanup(owner.close)
        return owner.__enter__()

    def test_exact_selected_consumer_run_job_and_receipt_artifact(self):
        owner = self.open_stage()
        self.assertEqual(owner.subject, self.f.selection.subject)
        self.assertEqual(owner.revalidate(), self.f.plan.assets)
        for path in ('/actions/runs/999', '/actions/runs/999/attempts/1', '/actions/artifacts/14'):
            self.assertGreaterEqual(self.f.api.calls.count(path), 2)

    def test_receipt_zip_layout_and_original_bytes_are_bound(self):
        original = [('rc-consumer-receipts-fixture/' + n, d) for n, d in
                    (('RC_PROVENANCE.json', self.f.provenance_bytes), ('rc-asset-plan.json', self.f.plan_bytes))]
        for members in ([('rc-asset-plan.json', self.f.plan_bytes)], original + [('foreign', b'x')],
                        [(n.replace('fixture', str(i)), d) for i, (n, d) in enumerate(original)], original + [original[0]]):
            with self.subTest(members=[m[0] for m in members]):
                set_receipts(self.f, members)
                with self.assertRaises((ConsumerError, ValueError)):
                    self.open_stage()
        link = zipfile.ZipInfo('rc-consumer-receipts-fixture/RC_PROVENANCE.json')
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        set_receipts(self.f, [(link, self.f.provenance_bytes), original[1]])
        with self.assertRaises(ConsumerError): self.open_stage()
        set_receipts(self.f, original + [('rc-consumer-receipts-fixture/', b'')])
        self.assertEqual(self.open_stage().plan_bytes, self.f.plan_bytes)

    def test_missing_foreign_or_mutated_selection_rejects(self):
        original = copy.deepcopy(self.f.api.data)
        mutations = [('/actions/runs/999', 'event', 'push'), ('/actions/runs/999', 'run_attempt', 2),
            ('/actions/artifacts/14', 'digest', 'sha256:' + 'e' * 64), ('/actions/artifacts/14', 'expired', True),
            ('/actions/artifacts/13', 'size_in_bytes', 1),
            ('/actions/runs/999', 'workflow_id', 11), ('/actions/runs/999', 'head_sha', 'f' * 40),
            ('/actions/runs/999', 'status', 'queued'), ('/actions/artifacts/14', 'created_at', '2026-09-01T00:00:00Z'),
            ('/actions/artifacts/14', 'size_in_bytes', True), ('/actions/artifacts/14', 'id', True)]
        for path, key, value in mutations:
            self.f.api.data = copy.deepcopy(original); self.f.api.data[path][key] = value
            with self.subTest(path=path, key=key), self.assertRaises(ConsumerError): self.open_stage()
        self.f.api.data = original
        owner = self.open_stage()
        self.f.api.data['/actions/runs/999/attempts/1/jobs?per_page=100&page=1']['jobs'][0]['id'] += 1
        with self.assertRaises(ConsumerError): owner.revalidate()

    def test_exact_final_archive_reuses_existing_validation(self):
        with patch.object(consumer, '_verify_bundle_bytes', wraps=consumer._verify_bundle_bytes) as verified:
            self.open_stage(); self.assertEqual(verified.call_count, 1)
        self.f.archives[13] = self.f.archives[13][:-1] + b'X'
        with self.assertRaises(ConsumerError): self.open_stage()

    def test_original_plan_and_provenance_survive_clock_change(self):
        with patch.object(consumer, 'make_asset_plan', side_effect=AssertionError('must not regenerate')), \
             patch.object(consumer, 'write_sanitized_provenance', side_effect=AssertionError('must not regenerate')):
            owner = self.open_stage()
        self.assertEqual(owner.plan_bytes, self.f.plan_bytes)
        self.assertEqual(owner.provenance_bytes, self.f.provenance_bytes)
        self.assertEqual(json.loads(owner.provenance_bytes)['verified_at'], '2026-10-01T00:08:00Z')
        original = json.loads(self.f.provenance_bytes)
        for key, value in (('release_approved', True), ('schema', True), ('limitations', []),
                           ('verified_at', '2026-11-01T00:00:00Z'), ('foreign', 'extra')):
            self.f.provenance_bytes = consumer.encode(dict(original, **{key: value}))
            set_receipts(self.f)
            with self.subTest(key=key), self.assertRaises(ConsumerError): self.open_stage()

    def test_six_fixed_rows_and_checksum_bytes_match_plan(self):
        owner = self.open_stage()
        self.assertEqual(len(owner.revalidate()), 6)
        for ordinal, row in enumerate(owner.plan.assets):
            self.assertEqual(owner.stream(ordinal).read(), self.f.payloads[row.name])
        self.assertNotIn('rc-asset-plan.json', owner._output.files())
        original = json.loads(self.f.plan_bytes)
        for key, value in (('size', 1), ('sha256', '0' * 64), ('family', 'foreign')):
            changed = copy.deepcopy(original); changed['assets'][0][key] = value
            self.f.plan_bytes = consumer.encode(changed)
            self.f.selection = replace(self.f.selection, subject=replace(self.f.selection.subject,
                plan_sha256=hashlib.sha256(self.f.plan_bytes).hexdigest()))
            set_receipts(self.f)
            with self.subTest(key=key), self.assertRaises(ConsumerError): self.open_stage()

    def test_owned_handles_survive_pause_and_upload_without_reopen(self):
        owner = self.open_stage(); handles = tuple(owner.stream(i) for i in range(6))
        with patch.object(PrivateRoot, 'open', side_effect=AssertionError('stream must lend retained handle')):
            for i, handle in enumerate(handles):
                self.assertIs(owner.stream(i), handle); self.assertEqual(handle.tell(), 0)
        for value in (-1, 6, True, '0'):
            with self.assertRaises(ConsumerError): owner.stream(value)

    def test_file_replacement_link_and_inventory_changes_reject(self):
        for mode in ('replace', 'symlink', 'hardlink', 'extra', 'root'):
            with self.subTest(mode=mode):
                owner = self.open_stage(); path = owner._output.path / owner.plan.assets[0].name
                if mode == 'replace':
                    other = path.with_name('other'); other.write_bytes(path.read_bytes()); other.chmod(0o600); os.replace(other, path)
                elif mode == 'symlink':
                    path.unlink(); path.symlink_to(self.f.source.bundle / path.name)
                elif mode == 'hardlink': os.link(path, Path(self.f.parent) / ('hard-' + path.parent.name))
                elif mode == 'extra': (path.parent / 'extra').write_bytes(b'x')
                else: path.parent.rename(str(path.parent) + '-moved'); path.parent.mkdir(mode=0o700)
                with self.assertRaises(ConsumerError): owner.revalidate()
                if mode != 'extra':
                    with self.assertRaises(ConsumerError): owner.stream(0)

    def test_inplace_size_and_hash_drift_rejects(self):
        for data in (b'x', None):
            owner = self.open_stage(); path = owner._output.path / owner.plan.assets[0].name
            raw = path.read_bytes(); path.write_bytes(data or bytes([raw[0] ^ 1]) + raw[1:])
            with self.assertRaises(ConsumerError): owner.revalidate()

    def test_no_source_path_or_closed_consumer_ownership_transfer(self):
        with self.assertRaises(ConsumerError):
            with stage.stage_selected(self.f.root, self.f.selection, self.f.api, temporary_parent=self.f.root): pass
        with patch.object(consumer, 'consume', side_effect=AssertionError('closed paths are not authority')):
            owner = self.open_stage()
        self.assertNotEqual(owner._output.path, self.f.source.bundle)
        (self.f.root / 'untracked').write_text('new source')
        with self.assertRaises(ConsumerError): owner.revalidate()

    def test_closure_on_success_failure_and_cancel(self):
        owner = self.open_stage(); handles = list(owner._handles); roots = list(owner._roots)
        owner.close(); owner.close()
        self.assertTrue(all(h.closed for h in handles)); self.assertTrue(all(r.fd is None for r in roots))
        with self.assertRaises(ConsumerError): owner.stream(0)
        observed, original = [], PrivateRoot.close
        def closing(root): observed.append(root); original(root)
        self.f.archives[13] = b'broken'
        with patch.object(PrivateRoot, 'close', closing), self.assertRaises(ConsumerError): self.open_stage()
        self.assertEqual(len(observed), 6); self.assertTrue(all(r.fd is None for r in observed))

    def test_mutable_selection_and_ambient_invocation_cannot_reselect(self):
        with self.assertRaises(FrozenInstanceError): self.f.selection.consumer_artifact_id = 88
        with patch.dict(os.environ, {'GITHUB_RUN_ID': '88', 'GITHUB_SHA': 'f' * 40}, clear=True):
            owner = self.open_stage()
        self.assertEqual(owner.subject.runs[2].run_id, 999)
        final, integration, consumed = self.f.selection.subject.runs
        ref = 'refs/pull/36/merge'
        integration = replace(integration, event='pull_request', ref=ref,
            workflow_ref=integration.source.repository + '/' + integration.workflow_path + '@' + ref)
        self.f.selection = replace(self.f.selection, subject=replace(self.f.selection.subject, runs=(final, integration, consumed)))
        self.f.api.data['/actions/runs/456']['event'] = 'pull_request'
        with self.assertRaisesRegex(ConsumerError, 'selected_ref_mismatch'): self.open_stage()
        for value in (True, 0, -1, 2**63):
            with self.assertRaises(ConsumerError): replace(self.f.selection, consumer_artifact_id=value)


if __name__ == '__main__':
    unittest.main()
