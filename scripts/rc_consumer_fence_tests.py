"""Synthetic pagination/race and real isolated committed-source negative tests."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rc_consumer_snapshot as snapshot
from rc_consumer_snapshot_fixtures import API, TAG, candidate, environment, expectations, source_tree
from source_provenance_gate_tests import command, commit


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline, source = source_tree(root)
        original = snapshot.gate.reviewed.verify
        with patch.object(snapshot.gate.reviewed, 'verify', side_effect=lambda root, source:
                          original(root, source, baseline=baseline)):
            yield root, source, API(source)


class FenceTests(unittest.TestCase):
    def test_historical_unselected_rerun_does_not_replace_newest_first_attempt(self):
        api = API()
        page = api.data[api.runs_path(12)]
        page['workflow_runs'].append(dict(page['workflow_runs'][0], id=100, run_attempt=2))
        page['total_count'] = 2
        self.assertEqual(api.selection()['final_packaging']['run']['id'], 102)
        self.assertNotIn('/actions/runs/100', api.calls)

    def test_selected_failed_rerun_has_explicit_error_code(self):
        api = API()
        api.data['/actions/runs/102'].update(run_attempt=2, conclusion='failure')
        with self.assertRaisesRegex(snapshot.ConsumerError, '^unsupported_rerun_provenance$'):
            api.selection()

    def test_latest_relist_same_or_new_run_rerun_has_explicit_error(self):
        for new_id in (102, 103):
            api = API(); original = api.get
            def racing(path):
                value = original(path)
                if path == api.runs_path(12) and api.calls.count(path) == 2:
                    value['workflow_runs'] = [dict(value['workflow_runs'][0], id=new_id, run_attempt=2)]
                return value
            api.get = racing
            with self.subTest(new_id=new_id), self.assertRaisesRegex(snapshot.ConsumerError,
                    '^unsupported_rerun_provenance$'):
                api.selection()

    def test_cross_page_count_change_and_duplicate_identity_rejected(self):
        for duplicate in (False, True):
            api = API(); original = api.data['/actions/runs/102']
            first = api.runs_path(12)
            api.data[first] = dict(total_count=101, workflow_runs=[dict(original, id=1000+i) for i in range(100)])
            api.data[first.replace('&page=1', '&page=2')] = dict(
                total_count=101 if duplicate else 102,
                workflow_runs=[dict(original, id=1000 if duplicate else 1100)])
            with self.subTest(duplicate=duplicate), self.assertRaises(snapshot.ConsumerError): api.selection()

    def test_candidate_source_cannot_override_explicit_input(self):
        with self.assertRaisesRegex(snapshot.ConsumerError, '^candidate_source_mismatch$'):
            snapshot.select_source_runs(API(), candidate('b' * 40), expectations())

    def test_repository_metadata_redirect_is_not_followed_with_token(self):
        class Opener:
            def __init__(self, handlers): self.handlers = handlers
            def open(self, request, timeout):
                handler = self.handlers[0]()
                return handler.redirect_request(request, None, 302, 'Found', {},
                                                'https://untrusted.invalid/secret')
        with patch.object(snapshot.gate.urllib.request, 'build_opener', side_effect=lambda *h: Opener(h)):
            with self.assertRaisesRegex(snapshot.ConsumerError, '^unexpected_api_redirect$'):
                snapshot.GitHub('synthetic-token').get('/')

    def test_repository_metadata_nonobject_or_oversize_blocked(self):
        for raw in (b'[]', b'{}' + b' ' * snapshot.gate.MAX_RESPONSE_BYTES):
            class Opener:
                def open(self, request, timeout): return io.BytesIO(raw)
            with patch.object(snapshot.gate.urllib.request, 'build_opener', return_value=Opener()):
                with self.assertRaises(snapshot.ConsumerError): snapshot.GitHub('synthetic-token').get('/')

    def test_post_api_fence_rechecks_source_not_only_live_tag(self):
        with fixture() as (root, source, api):
            expected, env = expectations(source), environment(source)
            value = snapshot.resolve_candidate(root, expected, env, api)
            selection = snapshot.select_source_runs(api, value, expected)
            artifact = snapshot.authenticate_bundle_metadata(api, selection, 600)
            captured = dict(candidate=value, selection=selection, artifact=artifact,
                            producer=snapshot.derive_final_producer(value, selection, artifact))
            original = api.get
            def racing(path):
                record = original(path)
                if path == '/actions/artifacts/600' and api.calls.count(path) == 2:
                    (root / 'changed-during-api-fence').write_text('synthetic race')
                return record
            api.get = racing
            with self.assertRaisesRegex(snapshot.ConsumerError, '^untracked_source$'):
                snapshot.revalidate_snapshot(api, root, expected, env, captured)

    def test_committed_missing_or_invalid_reviewed_manifest_never_regenerated(self):
        for mutation in ('missing', 'schema_bool', 'version', 'entry_inventory'):
            with self.subTest(mutation=mutation), fixture() as (root, source, api):
                path = root / snapshot.gate.reviewed.MANIFEST
                value = json.loads(path.read_text())
                if mutation == 'missing': path.unlink()
                else:
                    if mutation == 'schema_bool': value['schema'] = True
                    elif mutation == 'version': value['version'] = '1.2.3-rc.5'
                    else:
                        (root / 'unreviewed.txt').write_text('committed but absent from frozen inventory')
                    path.write_text(json.dumps(value))
                source = commit(root); command(root, 'tag', '-f', TAG)
                expected_bytes = path.read_bytes() if path.exists() else None
                with self.assertRaises(snapshot.ConsumerError):
                    snapshot.resolve_candidate(root, expectations(source), environment(source), API(source))
                self.assertEqual(path.read_bytes() if path.exists() else None, expected_bytes)

    def test_checked_out_consumer_workflow_symlink_not_accepted(self):
        with fixture() as (root, source, api):
            path = root / snapshot.CONSUMER_WORKFLOW
            path.unlink(); path.symlink_to('../../package.json')
            source = commit(root); command(root, 'tag', '-f', TAG)
            with self.assertRaisesRegex(snapshot.ConsumerError, '^consumer_workflow_missing$'):
                snapshot.resolve_candidate(root, expectations(source), environment(source), API(source))


if __name__ == '__main__':
    unittest.main()
