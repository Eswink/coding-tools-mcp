"""Negative guard kept outside the pinned 48/85/300 inventories: unowned mutations never reach the wire."""
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_github as wire
from rc_publication_https_fixture import HTTPSFixture
import rc_publication_github_cases as gc  # module only: borrow the read-step driver, not its tests


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

    step = gc.GitHubCases.step
    until = gc.GitHubCases.until

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
