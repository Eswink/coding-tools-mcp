"""Known gap (RC blocker follow-up 'authenticate before connect'); kept outside the pinned 48/85/300 inventories.

Current frozen02 behaviour: an owned mutation connects first (rc_publication_github.py:247) and only
then runs full _authenticate (stage revalidation, ~25 requests) and _authorize before sending.  When
that gap exceeds the server's idle bound the server closes the connection, sendall raises
BrokenPipeError, and the CreateDraft ends adapter_error / uncertain_remote_effect although no byte
of the request was sent.  This test pins the required behaviour (authentication completes before the
mutation connection is opened) and is an expectedFailure until the follow-up lands; it then reports an
unexpected success and the decorator must be removed.
"""
import sys
import time
import unittest
from unittest.mock import patch

import rc_publication_contract as core
import rc_publication_github as wire
import rc_publication_executor_cases as executor_cases


class AuthenticateBeforeConnectCases(unittest.TestCase):
    @unittest.expectedFailure  # follow-up: followup-issue-revalidate.md, "authenticate before connect"
    def test_slow_authentication_does_not_idle_out_mutation_connection(self):
        cases = executor_cases.ExecutorCases('test_pause_close_is_local_only_and_cannot_resume')
        observed = []
        with cases.session(idle_timeout=2) as (session, tls, _):
            modeled = wire._authenticate  # ExecutorCases' modeled gates, patched inside session()
            def slow_when_connected(*args, **kwargs):
                # Only the authentication inside an owned mutation request: a >2 s gap.
                frame = sys._getframe(1)
                while frame is not None and not (frame.f_code.co_name == '_request'
                                                 and frame.f_code.co_filename == wire.__file__):
                    frame = frame.f_back
                if frame is not None and frame.f_locals.get('op') is not None:
                    time.sleep(2.5)
                return modeled(*args, **kwargs)
            with patch.object(wire, '_authenticate', side_effect=slow_when_connected):
                pause = session.run_until_pause()
            observed.append((type(pause.action).__name__, pause.state.outcome, getattr(pause.state, 'code', None)))
            self.assertIsInstance(pause.action, core.AwaitPublishRequest, observed)
            self.assertEqual(len([r for r in tls.requests if r[0] == 'POST']), 7, observed)


if __name__ == '__main__':
    unittest.main()
