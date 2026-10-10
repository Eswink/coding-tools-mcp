"""Terminal failures remain failures; withdrawal is exact, bounded and single-attempt."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import rc_artifact_consumer as consumer
import rc_consumer_finalize as finalize
from rc_consumer_fixtures import ConsumerFixture
from rc_consumer_io import PrivateRoot
import rc_consumer_plan_tests as fixtures
from rc_consumer_transport_tests import HOST, URL, Opener, Response


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = ConsumerFixture(self.temp.name)
        self.data = fixtures.zip_bytes(self.f.bundle)
        self.api = fixtures.API(self.f, self.data)
        self.original_close = PrivateRoot.close
        self.unlink = os.unlink
        self.rename = os.rename

    def invoke(self):
        with patch.object(consumer.snapshot, 'resolve_candidate', return_value=self.api.candidate), \
             patch.object(consumer.transport, 'TRUSTED_STORAGE_HOSTS', frozenset({HOST})):
            return consumer.consume(self.f.root, self.api.expected, {}, self.api,
                temporary_parent=self.temp.name,
                opener=Opener(Response(302, headers=[('Location', URL)]), Response(200, self.data)))

    def plans(self):
        return list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.json'))

    def close_failure(self, callback=None, prefix='rc-consumer-receipts-'):
        def close(root):
            self.original_close(root)
            if root.path.name.startswith(prefix):
                if callback:
                    callback(root)
                raise OSError('synthetic private error https://secret.invalid/?token=PRIVATE')
        return patch.object(PrivateRoot, 'close', close)

    def test_close_failure_withdraws_only_exact_owned_success_plan(self):
        unlinks = []
        def remove(name, *args, **kwargs):
            unlinks.append((name, kwargs))
            return self.unlink(name, *args, **kwargs)
        with self.close_failure(), patch.object(finalize.os, 'unlink', remove):
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
        error = caught.exception
        self.assertEqual(error.outcome, 'withdrawn')
        self.assertTrue(error.plan_absent_confirmed)
        self.assertIsInstance(error.__cause__, OSError)
        self.assertEqual(self.plans(), [])
        self.assertEqual(len(unlinks), 1)
        self.assertEqual(unlinks[0][0], 'rc-asset-plan.json')
        self.assertIn('dir_fd', unlinks[0][1])
        self.assertEqual(len(list(Path(self.temp.name).glob('rc-consumer-assets-*'))), 1)

    def test_close_ownership_cleared_before_one_potentially_failing_attempt(self):
        root = PrivateRoot(self.temp.name, source_root=self.f.root)
        fd, actual_close = root.fd, os.close
        try:
            with patch.object(os, 'close', side_effect=OSError('synthetic close error')) as close:
                with self.assertRaises(OSError):
                    root.close()
                self.assertIsNone(root.fd)
                root.close()
                close.assert_called_once_with(fd)
        finally:
            # This test knows its synthetic failure did not perform the syscall.
            actual_close(fd)

    def test_precommit_nonessential_cleanup_failure_never_creates_success_plan(self):
        with self.close_failure(prefix='rc-consumer-assets-'), \
             patch.object(consumer.snapshot, 'revalidate_snapshot') as fence:
            with self.assertRaises(OSError):
                self.invoke()
            fence.assert_not_called()
        self.assertEqual(self.plans(), [])
        self.assertTrue(list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.pending')))

    def test_withdrawal_failure_is_uncertain_and_never_retried(self):
        with self.close_failure(), patch.object(finalize.os, 'unlink', side_effect=PermissionError('synthetic')) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
        self.assertEqual(caught.exception.outcome, 'uncertain')
        self.assertFalse(caught.exception.plan_absent_confirmed)
        self.assertIsInstance(caught.exception.__cause__, OSError)
        self.assertIsInstance(caught.exception.withdrawal_error, PermissionError)
        unlink.assert_called_once()
        self.assertEqual(len(self.plans()), 1)
        plan = json.loads(self.plans()[0].read_text())
        self.assertFalse(plan['release_approved'])
        self.assertFalse(plan['publish_approved'])

    def test_wrong_content_is_left_untouched_and_uncertain(self):
        def change(root):
            (root.path / 'rc-asset-plan.json').write_bytes(b'foreign changed content')
        with self.close_failure(change), patch.object(finalize.os, 'unlink', wraps=self.unlink) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
            unlink.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'uncertain')
        self.assertEqual(self.plans()[0].read_bytes(), b'foreign changed content')

    def test_wrong_inode_is_left_untouched_and_uncertain(self):
        def change(root):
            path = root.path / 'rc-asset-plan.json'
            temp = root.path / 'replacement'
            temp.write_bytes(path.read_bytes())
            temp.chmod(0o600)
            os.replace(temp, path)
        with self.close_failure(change), patch.object(finalize.os, 'unlink', wraps=self.unlink) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
            unlink.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'uncertain')
        self.assertEqual(len(self.plans()), 1)

    def test_changed_root_is_not_adopted_or_removed(self):
        def change(root):
            self.rename(root.path, str(root.path) + '-original')
            root.path.mkdir(mode=0o700)
            (root.path / 'rc-asset-plan.json').write_bytes(b'other invocation')
        with self.close_failure(change), patch.object(finalize.os, 'unlink', wraps=self.unlink) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
            unlink.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'uncertain')
        self.assertEqual(len(self.plans()), 2)

    def test_symlink_success_target_never_followed_or_deleted(self):
        protected = self.f.root / 'package.json'
        original = protected.read_bytes()
        def change(root):
            path = root.path / 'rc-asset-plan.json'
            self.rename(path, root.path / 'held-original')
            path.symlink_to(protected)
        with self.close_failure(change), patch.object(finalize.os, 'unlink', wraps=self.unlink) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
            unlink.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'uncertain')
        self.assertEqual(protected.read_bytes(), original)
        self.assertTrue(self.plans()[0].is_symlink())

    def test_rename_failure_confirms_absence_without_claiming_deletion(self):
        with patch.object(finalize.os, 'rename', side_effect=OSError('synthetic')), \
             patch.object(finalize.os, 'unlink', wraps=self.unlink) as unlink:
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
            unlink.assert_not_called()
        self.assertEqual(caught.exception.outcome, 'absent')
        self.assertTrue(caught.exception.plan_absent_confirmed)
        self.assertEqual(self.plans(), [])

    def test_completed_rename_with_unconfirmed_return_is_withdrawn(self):
        def rename(*args, **kwargs):
            self.rename(*args, **kwargs)
            raise OSError('synthetic ambiguous return')
        with patch.object(finalize.os, 'rename', rename):
            with self.assertRaises(finalize.FinalizationFailure) as caught:
                self.invoke()
        self.assertEqual(caught.exception.outcome, 'withdrawn')
        self.assertEqual(self.plans(), [])

    def test_full_fence_follows_payload_staging_and_nonessential_closes(self):
        original_fence = consumer.snapshot.revalidate_snapshot
        closed = []
        def close(root):
            self.original_close(root)
            closed.append(root.path.name)
        def fence(*args):
            roots = list(Path(self.temp.name).glob('rc-consumer-assets-*'))
            self.assertEqual(len(roots), 1)
            self.assertEqual(len(list(roots[0].iterdir())), 6)
            self.assertTrue(list(Path(self.temp.name).glob('rc-consumer-receipts-*/rc-asset-plan.pending')))
            self.assertFalse(self.plans())
            for prefix in ('download', 'bundle', 'cloud', 'assets'):
                self.assertTrue(any(name.startswith('rc-consumer-' + prefix + '-') for name in closed))
            self.assertFalse(any(name.startswith('rc-consumer-receipts-') for name in closed))
            return original_fence(*args)
        with patch.object(PrivateRoot, 'close', close), \
             patch.object(consumer.snapshot, 'revalidate_snapshot', fence):
            result = self.invoke()
        self.assertFalse(result['plan']['publish_approved'])

    def test_cli_failure_report_preserves_safe_outcome_and_exit_failure(self):
        args = ['consumer'] + [part for k, v in self.api.expected.items()
                              for part in ('--' + k.replace('_', '-'), str(v))]
        for outcome in ('withdrawn', 'absent', 'uncertain'):
            error = finalize.FinalizationFailure(OSError('PRIVATE signed URL'), outcome)
            output = io.StringIO()
            with patch('sys.argv', args), patch.dict(os.environ, {'GH_TOKEN': 'fixture'}), \
                 patch.object(consumer, 'consume', side_effect=error), redirect_stdout(output):
                self.assertEqual(consumer.main(), 1)
            value = json.loads(output.getvalue())
            self.assertFalse(value['passed'])
            self.assertFalse(value['release_approved'])
            self.assertFalse(value['publish_approved'])
            self.assertEqual(value['plan_outcome'], outcome)
            self.assertEqual(value['plan_absent_confirmed'], outcome != 'uncertain')
            self.assertNotIn('PRIVATE', output.getvalue())
            self.assertNotIn('always()', (Path(__file__).parent.parent / '.github/workflows/rc-artifact-consumer.yml').read_text())


if __name__ == '__main__':
    unittest.main()
