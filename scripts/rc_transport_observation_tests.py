"""Hermetic transport/security tests; all URLs and credentials below are synthetic."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import rc_transport_observation as subject

TOKEN = "synthetic_test_token"
LOCATION = "https://Storage.Example.com/synthetic-private-path?signature=synthetic-secret"


class ObservationResponse:
    def __init__(self, payload=None, status=200, headers=None, raw=None):
        self.status = status
        self.headers = headers if headers is not None else [("Content-Type", "application/json")]
        self.raw = json.dumps(payload).encode() if raw is None else raw
        self.reads = []
        self.closed = False

    def getheaders(self):
        return self.headers

    def read(self, count):
        self.reads.append(count)
        if self.status == 302:
            raise AssertionError("redirect response body must never be read")
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw[:count]

    def close(self):
        self.closed = True


def observation_fixture():
    repo = {"id": subject.REPOSITORY_ID, "full_name": subject.REPOSITORY}
    run = {"id": subject.RUN_ID, "head_sha": subject.SOURCE_SHA, "status": "completed",
           "conclusion": "success", "repository": repo, "head_repository": repo}
    artifact = {"id": subject.ARTIFACT_ID, "size_in_bytes": subject.SIZE,
                "digest": subject.DIGEST, "expired": False,
                "workflow_run": {"id": subject.RUN_ID, "repository_id": subject.REPOSITORY_ID,
                                 "head_repository_id": subject.REPOSITORY_ID,
                                 "head_sha": subject.SOURCE_SHA}}
    return [copy.deepcopy(repo), copy.deepcopy(run),
            {"total_count": 1, "artifacts": [copy.deepcopy(artifact)]}, copy.deepcopy(artifact)]


class FixedObservationTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.connections = []
        self.responses = []
        self.network = patch.object(socket, "getaddrinfo", side_effect=AssertionError("real DNS forbidden"))
        self.network.start()
        self.addCleanup(self.network.stop)

    def run_fixture(self, metadata=None, responses=None, token=TOKEN, main=False):
        metadata = observation_fixture() if metadata is None else metadata
        queue = responses if responses is not None else [ObservationResponse(x) for x in metadata]
        if responses is None:
            queue.append(ObservationResponse(status=302, headers=[("Location", LOCATION)]))
        self.responses = queue[:]
        owner = self

        class FixedConnection:
            def __init__(self, host, port, timeout):
                owner.assertEqual((host, port, timeout), ("api.github.com", 443, 10))
                self.closed = False
                owner.connections.append(self)

            def request(self, method, path, headers):
                owner.calls.append((method, path, headers))
                owner.assertEqual(method, "GET")
                owner.assertEqual(path, subject.PATHS[len(owner.calls) - 1])
                owner.assertEqual(headers["Authorization"], "Bearer " + token)
                owner.assertEqual(headers["Accept-Encoding"], "identity")

            def getresponse(self):
                return queue.pop(0)

            def close(self):
                self.closed = True

        try:
            with patch.object(subject.http.client, "HTTPSConnection", FixedConnection):
                if main:
                    output, errors = io.StringIO(), io.StringIO()
                    with patch.dict(os.environ, {"GH_TOKEN": token}), patch.object(sys, "argv", ["probe"]):
                        with redirect_stdout(output), redirect_stderr(errors):
                            code = subject.observation_main()
                        self.assertNotIn("GH_TOKEN", os.environ)
                    self.assertEqual(errors.getvalue(), "")
                    return code, output.getvalue()
                return subject.observe_fixed_redirect(token)
        finally:
            self.assertTrue(all(c.closed for c in self.connections))
            self.assertTrue(all(r.closed for r in self.responses[:len(self.calls)]))

    def test_success_is_exact_typed_allowlist_and_get_only_without_storage_or_body(self):
        report = self.run_fixture()
        self.assertEqual(report, {"scope": subject.SCOPE, "repository_id": subject.REPOSITORY_ID,
                         "source_sha": subject.SOURCE_SHA, "run_id": subject.RUN_ID,
                         "artifact_id": subject.ARTIFACT_ID, "size_in_bytes": subject.SIZE,
                         "digest": subject.DIGEST, "expired": False, "http_status": 302,
                         "hostname": "storage.example.com", "release_approved": False,
                         "publish_approved": False})
        self.assertEqual(len(self.calls), 5)
        self.assertEqual(self.responses[-1].reads, [])
        self.assertTrue(all(r.reads == [subject.MAX_JSON + 1] for r in self.responses[:-1]))
        raw = json.dumps(report)
        for secret in (TOKEN, LOCATION, "synthetic-private-path", "signature", "synthetic-secret"):
            self.assertNotIn(secret, raw)

    def test_every_fixed_metadata_field_rejects_wrong_missing_and_wrong_type(self):
        base = observation_fixture()
        paths = [(0, ("id",)), (0, ("full_name",)), (1, ("id",)), (1, ("head_sha",)),
                 (1, ("status",)), (1, ("conclusion",))]
        for field in ("repository", "head_repository"):
            paths.extend([(1, (field, "id")), (1, (field, "full_name"))])
        for index, prefix in ((2, ("artifacts", 0)), (3, ())):
            paths.extend((index, prefix + (key,)) for key in ("id", "size_in_bytes", "digest", "expired"))
            paths.extend((index, prefix + ("workflow_run", key)) for key in
                         ("id", "repository_id", "head_repository_id", "head_sha"))
        for index, path in paths:
            for replacement in (None, True, False, "wrong", -1, 0, 912.0, [], {}):
                data = copy.deepcopy(base)
                target = data[index]
                for key in path[:-1]:
                    target = target[key]
                if type(target[path[-1]]) is type(replacement) and target[path[-1]] == replacement:
                    continue
                target[path[-1]] = replacement
                with self.subTest(index=index, field=path, value=replacement):
                    self.calls, self.connections = [], []
                    with self.assertRaises((ValueError, TypeError)):
                        self.run_fixture(metadata=data)
                    self.assertLess(len(self.calls), 5)

    def test_listing_is_complete_unique_bounded_and_targeted(self):
        target = observation_fixture()[3]
        invalid = [{"total_count": value, "artifacts": [target]} for value in (True, 0, 2, 101, "1", None)]
        invalid += [{"total_count": 1, "artifacts": value} for value in (None, {}, [], [None], [{"id": True}], [{"id": 3}])]
        invalid += [{"total_count": 2, "artifacts": [target, target]},
                    {"total_count": 1, "artifacts": [{"id": -1}]}]
        for listing in invalid:
            with self.subTest(listing=listing):
                self.calls, self.connections = [], []
                data = observation_fixture()
                data[2] = listing
                with self.assertRaises(ValueError):
                    self.run_fixture(metadata=data)
                self.assertLess(len(self.calls), 5)

    def test_json_rejects_duplicates_nonfinite_floats_oversize_and_malformed(self):
        invalid = [b'{"id":1,"id":2}', b'{"nested":{"x":1,"x":2}}', b'{"n":NaN}',
                   b'{"n":Infinity}', b'{"n":-Infinity}', b'{"n":1.0}', b'{"n":1e999}',
                   b'{"n":9223372036854775808}', b'{"n":-9223372036854775809}',
                   b'{"n":' + b'1' * 30 + b'}', b'{}junk', b'[]', b'null', b'\xff',
                   b'{}' + b' ' * subject.MAX_JSON, b'{']
        for raw in invalid:
            with self.subTest(raw=raw[:50]):
                self.calls, self.connections = [], []
                with self.assertRaises((ValueError, UnicodeError)):
                    self.run_fixture(responses=[ObservationResponse(raw=raw)])
                self.assertEqual(len(self.calls), 1)

    def test_api_redirects_and_http_failures_never_reach_followup_requests(self):
        for status in (201, 301, 302, 303, 307, 308, 401, 403, 404, 429, 500):
            with self.subTest(status=status):
                self.calls, self.connections = [], []
                with self.assertRaises(ValueError):
                    self.run_fixture(responses=[ObservationResponse(status=status, headers=[("Location", LOCATION)])])
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.responses[0].reads, [])

    def test_headers_reject_uncertain_pagination_compression_duplicates_and_size(self):
        valid = [("Content-Type", "application/json")]
        invalid = [[], [("Content-Type", "text/plain")], valid * 2,
                   valid + [("Link", '<https://api.github.com/next>; rel="next"')],
                   valid + [("Link", "")], valid + [("Location", LOCATION)],
                   valid + [("Content-Encoding", "gzip")],
                   valid + [("Content-Length", "131073")], valid + [("Content-Length", "1")],
                   valid + [("Content-Length", "2"), ("Content-Length", "2")],
                   valid + [("Content-Length", "-1")], valid + [("Content-Length", "2"), ("Transfer-Encoding", "chunked")],
                   valid + [("X-Oversize", "x" * subject.MAX_HEADERS)]]
        for headers in invalid:
            with self.subTest(headers=str(headers)[:70]):
                self.calls, self.connections = [], []
                with self.assertRaises(ValueError):
                    self.run_fixture(responses=[ObservationResponse(raw=b"{}", headers=headers)])

    def test_redirect_status_location_cardinality_and_size(self):
        redirects = [ObservationResponse(status=code, headers=[("Location", LOCATION)])
                     for code in (200, 301, 303, 307, 308, 403, 500)]
        redirects += [ObservationResponse(status=302, headers=headers) for headers in
                      ([], [("Location", LOCATION), ("location", LOCATION)],
                       [("Location", "https://example.com/" + "x" * 8192)])]
        for redirect in redirects:
            with self.subTest(status=redirect.status, headers=str(redirect.headers)[:70]):
                self.calls, self.connections = [], []
                with self.assertRaises(ValueError):
                    self.run_fixture(responses=[ObservationResponse(x) for x in observation_fixture()] + [redirect])
                self.assertEqual(redirect.reads, [])

    def test_hostname_parser_rejects_malformed_ip_userinfo_port_fragment_and_unicode(self):
        invalid = ["http://storage.example.com/x", "//storage.example.com", " https://storage.example.com",
                   "HTTPS://storage.example.com/x", "https://user:pass@storage.example.com/x",
                   "https://@storage.example.com", "https://storage.example.com:80", "https://storage.example.com:0443",
                   "https://storage.example.com:", "https://storage.example.com#", "https://storage.example.com/#fragment",
                   "https://127.0.0.1/x", "https://[::1]/x", "https://2130706433/", "https://0x7f.0x0.0x0.0x1/",
                   "https://0177.0.0.1/", "https://localhost/x", "https://a..com/x", "https://-a.example.com/x",
                   "https://a-.example.com/x", "https://a_b.example.com/x", "https://storage.example.com./x",
                   "https://störage.example.com/x", "https://%73torage.example.com/x", "https://storage.example.com\\@evil/x",
                   "https://storage.example.com/\nsecret", "https://storage.example.com/\x00", "https://storage.example.com/a b",
                   "https://" + "a" * 64 + ".com", "https://" + ("a" * 63 + ".") * 4 + "com"]
        for location in invalid:
            with self.subTest(location=location):
                with self.assertRaises(ValueError):
                    subject.observation_hostname(location)
        self.assertEqual(subject.observation_hostname("https://Storage.Example.com:443/x?q=y"), "storage.example.com")

    def test_failure_output_never_exposes_token_location_headers_body_or_exception(self):
        cases = [ObservationResponse(raw=(TOKEN + LOCATION).encode()),
                 ObservationResponse(raw=TimeoutError(TOKEN + LOCATION)),
                 ObservationResponse(raw=RuntimeError(TOKEN + LOCATION))]
        for response in cases:
            self.calls, self.connections = [], []
            code, output = self.run_fixture(responses=[response], main=True)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output), {"scope": subject.SCOPE, "error": "observation_failed",
                             "release_approved": False, "publish_approved": False,
                             "stage_id": 2, "predicate_id": 0, "http_status": 200})
            self.assertNotIn(TOKEN, output)
            self.assertNotIn(LOCATION, output)

    def test_success_main_keeps_alarm_bounded_and_cancels_it(self):
        with patch.object(signal, "setitimer", wraps=signal.setitimer) as timer:
            code, output = self.run_fixture(main=True)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["hostname"], "storage.example.com")
        self.assertEqual(timer.call_args_list[0].args, (signal.ITIMER_REAL, 40))
        self.assertEqual(timer.call_args_list[-1].args, (signal.ITIMER_REAL, 0))
        with self.assertRaises(TimeoutError):
            subject.observation_deadline(None, None)

    def test_production_rejects_arbitrary_arguments_tokens_and_paths_without_network(self):
        for token in ("", "a\nb", "a b", "é", "x" * 4097, None):
            with self.subTest(token=repr(token)[:30]), self.assertRaises(ValueError):
                self.run_fixture(token=token)
        with self.assertRaises(ValueError):
            subject.observation_get("https://evil.example/", TOKEN)
        with patch.object(sys, "argv", ["probe", "https://evil.example/"]), redirect_stdout(io.StringIO()):
            self.assertEqual(subject.observation_main(), 1)
        self.assertEqual(self.calls, [])

    def test_workflow_is_fixed_branch_no_inputs_read_only_and_sha_pinned(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/rc-transport-observation.yml").read_text()
        self.assertLessEqual(len(workflow.splitlines()), 100)
        self.assertLessEqual(len((root / "scripts/rc_transport_observation.py").read_text().splitlines()), 200)
        for text in ("branches: [ci/rc-transport-observation]", "workflow_dispatch:", "contents: read", "actions: read",
                     "github.repository_id == '1360355522'", "github.ref == 'refs/heads/ci/rc-transport-observation'",
                     "runs-on: ubuntu-24.04", "ref: ${{ github.sha }}", "persist-credentials: false",
                     "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                     "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065", "GH_TOKEN: ${{ github.token }}"):
            self.assertIn(text, workflow)
        for text in ("inputs:", "pull_request", "write", "environment:", "upload-artifact", "cache:", "secrets."):
            self.assertNotIn(text, workflow)

    def test_guard_conditions_match_original_8488272_ast_without_acceptance_changes(self):
        tree = ast.parse(Path(subject.__file__).read_text())
        guards = sorted([n for n in ast.walk(tree) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Name) and n.func.id == "observation_require"],
                        key=lambda n: (n.lineno, n.col_offset))
        self.assertEqual(len(guards), 31)
        self.assertEqual([n.args[1].value for n in guards], list(range(1, 32)))
        # Predicate 26 intentionally changes only to opaque RFC 6750 header syntax.
        approved = ast.parse('type(token) is str and 1 <= len(token) <= 4096 and '
                             're.fullmatch(r"[A-Za-z0-9._~+/\\-]+=*", token) is not None', mode="eval").body
        self.assertEqual(ast.dump(guards[25].args[0]), ast.dump(approved))
        conditions = [ast.dump(n.args[0], include_attributes=False) for n in guards]
        original = ast.parse('type(token) is str and re.fullmatch(r"[A-Za-z0-9_]{1,4096}", token) is not None', mode="eval").body
        conditions[25] = ast.dump(original, include_attributes=False)
        data = json.dumps(conditions, separators=(",", ":"))
        self.assertEqual(hashlib.sha256(data.encode()).hexdigest(),
                         "36845f1113d3857873ce86e84819ad1006904580d4dd9d2bee01e97d20c90c34")

    def test_rejected_tokens_report_identical_fixed_stage_and_predicate_without_details(self):
        expected = {"scope": subject.SCOPE, "error": "observation_failed", "release_approved": False,
                    "publish_approved": False, "stage_id": 1, "predicate_id": 26}
        for token in ("", "synthetic token", "synthetic=token", "x" * 4097, "synthetic\nsecret"):
            with self.subTest(case="synthetic invalid token"):
                code, output = self.run_fixture(token=token, main=True)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output), expected)
                self.assertEqual(self.calls, [])

    def test_fixed_stage_identifies_each_metadata_guard_without_returning_field_values(self):
        for index, stage, key in ((0, 2, "id"), (1, 3, "head_sha"), (2, 4, "total_count"), (3, 5, "digest")):
            with self.subTest(stage=stage):
                self.calls, self.connections = [], []
                metadata = observation_fixture()
                metadata[index][key] = "synthetic-private-value"
                code, output = self.run_fixture(metadata=metadata, main=True)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output), {"scope": subject.SCOPE, "error": "observation_failed",
                                 "release_approved": False, "publish_approved": False,
                                 "stage_id": stage, "predicate_id": 27 if index == 2 else 5,
                                 "http_status": 200})

    def test_http_failure_status_is_typed_and_does_not_disclose_headers(self):
        for status in (403, "403", True, 99, 600):
            with self.subTest(status=status):
                self.calls, self.connections = [], []
                response = ObservationResponse(status=status, headers=[("Location", LOCATION)])
                code, output = self.run_fixture(responses=[response], main=True)
                self.assertEqual(code, 1)
                expected = {"scope": subject.SCOPE, "error": "observation_failed", "release_approved": False,
                            "publish_approved": False, "stage_id": 2, "predicate_id": 17}
                if type(status) is int and 100 <= status <= 599:
                    expected["http_status"] = status
                self.assertEqual(json.loads(output), expected)
                self.assertEqual(response.reads, [])

    def test_redirect_failure_reports_only_fixed_ids_and_status_and_still_never_reads_body(self):
        for headers, predicate in (([("Location", LOCATION)] * 2, 16), ([("Location", "https://a.com:80/private?secret")], 10)):
            with self.subTest(predicate=predicate):
                self.calls, self.connections = [], []
                response = ObservationResponse(status=302, headers=headers)
                code, output = self.run_fixture(responses=[ObservationResponse(x) for x in observation_fixture()] + [response], main=True)
                self.assertEqual(code, 1)
                self.assertEqual(json.loads(output), {"scope": subject.SCOPE, "error": "observation_failed",
                                 "release_approved": False, "publish_approved": False,
                                 "stage_id": 6, "predicate_id": predicate, "http_status": 302})
                self.assertEqual(response.reads, [])

    def test_unexpected_and_tampered_error_metadata_never_escape_fixed_allowlists(self):
        secret = TOKEN + LOCATION
        for error in (RuntimeError(secret), subject.ObservationRejected(secret), subject.ObservationRejected(True),
                      subject.ObservationRejected(-1), subject.ObservationRejected(33)):
            def fail(_token):
                subject.OBSERVATION_STATE[:] = [secret, secret]
                raise error
            with patch.object(subject, "observe_fixed_redirect", fail):
                code, output = self.run_fixture(main=True)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(output), {"scope": subject.SCOPE, "error": "observation_failed",
                             "release_approved": False, "publish_approved": False,
                             "stage_id": 0, "predicate_id": 0})

    def test_json_noninteger_and_cli_rejection_have_fixed_predicate_ids(self):
        code, output = self.run_fixture(responses=[ObservationResponse(raw=b'{"n":NaN}')], main=True)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["predicate_id"], 32)
        output = io.StringIO()
        with patch.object(sys, "argv", ["probe", "synthetic-private-argument"]), redirect_stdout(output):
            self.assertEqual(subject.observation_main(), 1)
        self.assertEqual(json.loads(output.getvalue()), {"scope": subject.SCOPE, "error": "observation_failed",
                         "release_approved": False, "publish_approved": False, "stage_id": 0, "predicate_id": 31})

    def test_rfc6750_opaque_bearer_synthetic_formats_are_forwarded_without_parsing(self):
        baseline = self.run_fixture(main=True)[1]
        tokens = ("synthetic.segment.signature", "synthetic-with-hyphens", "opaque~+/==",
                  "ghs_12345_Not-A-JWT.NoPayload.ClaimsNotDecoded", "x", "x" * 4096)
        for index, token in enumerate(tokens):
            with self.subTest(synthetic_case=index):
                self.calls, self.connections = [], []
                code, output = self.run_fixture(token=token, main=True)
                self.assertEqual(code, 0)
                self.assertEqual(len(self.calls), 5)
                self.assertEqual(json.loads(output)["hostname"], "storage.example.com")
                self.assertEqual(self.responses[-1].reads, [])
                self.assertEqual(output, baseline)

    def test_bearer_header_rejects_all_controls_whitespace_unicode_and_bad_padding(self):
        invalid = ["a" + chr(c) + "b" for c in range(33)] + ["a\x7fb", "é", "a\u0085b", "a\u2028b",
                   "a\r\nAuthorization: x", "a=b", "=a", "=", "a:b", "a,b", 'a"b', "a\\b", "a;b",
                   "a@b", "a?b", "", "x" * 4097, b"bytes", None, True]
        for index, token in enumerate(invalid):
            with self.subTest(synthetic_case=index):
                with self.assertRaises(subject.ObservationRejected) as failure:
                    self.run_fixture(token=token)
                self.assertEqual(failure.exception.predicate_id, 26)
                self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
