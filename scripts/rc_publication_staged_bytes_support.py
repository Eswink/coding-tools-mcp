"""Test-only boundary observation; delegates real IO and retirement."""
from contextlib import ExitStack, contextmanager
import time
from types import SimpleNamespace
from unittest.mock import patch
import rc_consumer_archive_budget_support as observation
import rc_consumer_io as safe
import rc_publication_executor as executor


def boundary(self, action, selected, cancelled=True, *, expected=None):
    budget, triggered = observation.Budget(cancelled), []
    def hook(event):
        if not triggered and selected(event):
            budget.stopped = True
            triggered.append(len(trace.events))
    with self.trace_calls(hook, budget) as trace, patch.object(safe, 'time', SimpleNamespace(monotonic=budget.now)):
        self.failure(lambda: action(budget.controls), expected or budget.code)
    self.assertEqual(len(triggered), 1)
    self.no_later_bytes(trace, triggered[0])
    self.assertTrue(all(stream.closed for stream in trace.streams))
    return trace


def failed_activation(self, phase, cancelled, *, handle_failure=False, **faults):
    with self.padded_session(**faults) as (session, tls, _, seen):
        stopped = []
        def now():
            return session._deadline if stopped and not cancelled else time.monotonic()
        def hook(event):
            boundary_kind = {'receipts': 'zip.read', 'copy': 'raw.read',
                             'output_hash': 'raw.read', 'revalidate': 'binary.read'}[phase]
            if not stopped and event.phase == phase and event.kind == boundary_kind:
                stopped.append(len(trace.events))
                if cancelled: session.cancel()
        code = 'adapter_error' if faults or handle_failure else 'cancelled' if cancelled else 'timeout'
        retired = []
        with self.trace_calls(hook) as trace, patch.object(safe, 'time', SimpleNamespace(monotonic=now)), patch.object(executor, 'time', SimpleNamespace(monotonic=now)), ExitStack() as patches:
            opened = safe.PrivateRoot.open
            @contextmanager
            def closed_handle(root, name, mode='rb'):
                try:
                    with opened(root, name, mode) as stream:
                        yield stream
                finally:
                    if mode == 'rb' and seen.stage is not None and stream in seen.stage._handles:
                        retired.append(stream)
                        if len(retired) == 1:
                            raise OSError('injected retained-handle failure after real closure')
            if handle_failure:
                patches.enter_context(patch.object(safe.PrivateRoot, 'open', closed_handle))
            self.failed_run(session, code)
        self.assertEqual(len(stopped), 1)
        self.no_later_bytes(trace, stopped[0])
        self.activation_failed(session, tls, seen, code, 1 if phase == 'receipts' else 2, sticky=bool(faults) or handle_failure)
        self.assertTrue(all(stream.closed for stream in trace.streams))
        if handle_failure:
            self.assertEqual(retired, list(reversed(seen.stage._handles)))
            self.assertEqual(len(set(map(id, retired))), 6)
