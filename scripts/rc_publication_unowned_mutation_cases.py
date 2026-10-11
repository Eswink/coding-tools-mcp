"""Negative guard kept outside the pinned 48/85/300 inventories: unowned mutations never reach the wire."""
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_github as wire
from rc_publication_https_fixture import HTTPSFixture
import io
from rc_publication_https_fixture import authorities, gates


class UnownedMutationCases(unittest.TestCase):
    def setUp(self):
        self.fixture = HTTPSFixture().__enter__()
        self.addCleanup(self.fixture.close)
        connection = patch.object(wire, '_connect', side_effect=self.fixture.connect)
        connection.start()
        self.addCleanup(connection.stop)
        self.api = wire.GitHub('fixture-private-token', self.fixture.selection)
        self.addCleanup(self.api.close)
        self.transition = core.start(self.fixture.subject, self.fixture.plan)
        self.trace, self.attempts = [], []

    def step(self):
        state, op = self.transition.state, self.transition.action
        self.trace.append(op.kind)
        fields = {}
        if op.kind in ('ObserveFence', 'ObserveDraft', 'VerifyPublished'):
            rows, visibility = gates(self.fixture.selection)
            fields['observation'] = self.api.observe(state, staged=state.plan.assets, gates=rows,
                                                      draft_visibility=visibility)
        elif op.kind in ('CreateDraft', 'PublishPrerelease'):
            method = self.api.create_draft if op.kind == 'CreateDraft' else self.api.publish_prerelease
            fields['release_id'] = method(op, before_write=lambda: self.attempts.append(op.operation_id),
                                          check_active=lambda: None)
        elif op.kind == 'UploadAsset':
            fields['asset'] = self.api.upload_asset(op, io.BytesIO(self.fixture.payloads[op.asset.name]),
                before_write=lambda: self.attempts.append(op.operation_id), check_active=lambda: None)
            fields['release_id'] = op.release_id
        else:
            fields.update(asset=self.api.verify_asset(op), release_id=op.release_id)
        result = core.OperationResult(core.RESULT_KINDS[core.OPERATION_KINDS.index(op.kind)],
            op.operation_id, op.subject_digest, op.kind, 'confirmed' if op.kind in core.MUTATIONS else 'none', **fields)
        self.transition = core.advance(state, result)
        return self.transition

    def until(self, kind, ordinal=None):
        while self.transition.action is not None:
            action = self.transition.action
            if type(action) is core.AwaitPublishRequest:
                if kind == 'AwaitPublishRequest':
                    return action
                self.transition = core.request_publish(self.transition.state,
                    core.PublicationRequest('request', 'fixture-owner', action.release_id, action.subject_digest))
                continue
            if action.kind == kind and (ordinal is None or action.asset_ordinal == ordinal):
                return action
            self.step()
        self.fail('unexpected terminal outcome: ' + str(self.transition.state.outcome))


    def test_unowned_mutation_rejected_before_write(self):
        op = self.until('CreateDraft')
        self.assertEqual(self.attempts, [])
        writes = []
        with self.assertRaises(wire.WireFailure) as caught:
            self.api.create_draft(op, before_write=lambda: writes.append(op.operation_id),
                                  check_active=lambda: None, scope=None)
        self.assertEqual(caught.exception.code, 'invalid_request')
        self.assertEqual(caught.exception.effect, 'none')
        self.assertEqual(writes, [])
        self.assertEqual([row for row in self.fixture.requests if row[0] in ('POST', 'PATCH', 'DELETE')], [])
        self.assertNotIn('fixture-private-token', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
