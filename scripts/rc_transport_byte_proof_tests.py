"""Hermetic fixed-byte proof tests. Every credential, URL and payload is synthetic."""
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch
import rc_transport_byte_proof as proof
import rc_transport_observation as observation
from rc_transport_observation_tests import ObservationResponse, observation_fixture

TOKEN = "synthetic.header-payload.signature"
PAYLOAD = b"B" * 912
DIGEST = "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()
LOCATION = "https://" + proof.HOST + "/synthetic%2Fprivate?sig=synthetic%2Bsecret&x="


class ByteProofTests(unittest.TestCase):
    def setUp(self):
        self.calls, self.connections, self.returned = [], [], []
        self.addCleanup(observation.urlsplit.cache_clear)
        self.dns = patch.object(socket, "getaddrinfo", side_effect=AssertionError("real DNS forbidden"))
        self.dns.start()
        self.addCleanup(self.dns.stop)

    def responses(self, before=None, after=None, body=PAYLOAD, location=LOCATION):
        before = observation_fixture() if before is None else before
        after = copy.deepcopy(before) if after is None else after
        return ([ObservationResponse(x) for x in before]
                + [ObservationResponse(status=302, headers=[("Location", location), ("Set-Cookie", "api-secret")])]
                + [ObservationResponse(raw=body, headers=[("Content-Length", "912")])]
                + [ObservationResponse(x) for x in after])

    def invoke(self, modify=None, body=PAYLOAD, location=LOCATION, token=TOKEN, after_response=None):
        owner = self
        self.calls, self.connections, self.returned = [], [], []
        with patch.object(observation, "DIGEST", DIGEST):
            responses = self.responses(body=body, location=location)
            if modify:
                modify(responses)
            queue = responses[:]

            class Connection:
                def __init__(self, host, port, timeout):
                    owner.assertIn(host, ("api.github.com", proof.HOST))
                    owner.assertEqual((port, timeout), (443, 10))
                    self.host, self.closed = host, False
                    owner.connections.append(self)

                def request(self, method, path, headers):
                    owner.assertEqual(method, "GET")
                    owner.assertLess(len(owner.calls), 10)
                    index = len(owner.calls)
                    if self.host == proof.HOST:
                        owner.assertEqual(index, 5)
                        owner.assertEqual(headers, {"Accept-Encoding": "identity", "Connection": "close"})
                        owner.assertTrue(path.startswith("/") and not path.startswith("//"))
                    else:
                        owner.assertEqual(path, observation.PATHS[index if index < 5 else index - 6])
                        owner.assertEqual(headers["Authorization"], "Bearer " + token)
                    owner.calls.append((self.host, method, path, headers))

                def getresponse(self):
                    response = queue.pop(0)
                    if isinstance(response, Exception):
                        raise response
                    owner.returned.append(response)
                    if after_response:
                        after_response(len(owner.calls))
                    return response

                def close(self):
                    self.closed = True

            output, errors = io.StringIO(), io.StringIO()
            with patch.object(proof.http.client, "HTTPSConnection", Connection), patch.object(sys, "argv", ["probe"]):
                with patch.dict(os.environ, {"GH_TOKEN": token, "HTTPS_PROXY": "https://synthetic-proxy.invalid/secret"}):
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = proof.proof_main()
            self.assertEqual(errors.getvalue(), "")
            self.assertTrue(all(c.closed for c in self.connections))
            self.assertTrue(all(r.closed for r in self.returned))
            return code, json.loads(output.getvalue()), responses

    def assert_failure(self, result, stage=None, predicate=None):
        code, report, _ = result
        self.assertEqual(code, 1)
        self.assertEqual(report["scope"], proof.SCOPE)
        self.assertEqual(report["error"], "byte_transport_failed")
        self.assertIs(report["release_approved"], False)
        self.assertIs(report["publish_approved"], False)
        self.assertLessEqual(set(report), {"scope", "error", "stage_id", "predicate_id", "http_status",
                                          "release_approved", "publish_approved"})
        if stage is not None:
            self.assertEqual(report["stage_id"], stage)
        if predicate is not None:
            self.assertEqual(report["predicate_id"], predicate)
        raw = json.dumps(report)
        for value in (TOKEN, LOCATION, "synthetic-secret", "api-secret", "private"):
            self.assertNotIn(value, raw)

    def test_success_has_ten_gets_one_storage_read_and_exact_typed_report(self):
        code, report, responses = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report, {"scope": proof.SCOPE, "repository_id": observation.REPOSITORY_ID,
                         "source_sha": observation.SOURCE_SHA, "run_id": observation.RUN_ID,
                         "artifact_id": observation.ARTIFACT_ID, "hostname": proof.HOST,
                         "redirect_http_status": 302, "storage_http_status": 200, "size_in_bytes": 912,
                         "digest": DIGEST, "byte_proof_verified": True, "metadata_rechecked": True,
                         "snapshot_atomic": False, "release_approved": False, "publish_approved": False})
        self.assertEqual(len(self.calls), 10)
        self.assertEqual(len(self.connections), 10)
        self.assertEqual(responses[4].reads, [])
        self.assertEqual(responses[5].reads, [913])
        self.assertEqual(sum(c[0] == proof.HOST for c in self.calls), 1)
        self.assertEqual(observation.urlsplit.cache_info().currsize, 0)

    def test_pre_metadata_identity_bounds_digest_and_pagination_fail_before_storage(self):
        mutations = [(0, lambda x: x.update(id=1)), (1, lambda x: x.update(head_sha="wrong")),
                     (1, lambda x: x["head_repository"].update(id=1)),
                     (2, lambda x: x.update(total_count=2)),
                     (2, lambda x: x["artifacts"][0].update(expired=True)),
                     (2, lambda x: x["artifacts"][0].update(digest="wrong")),
                     (3, lambda x: x.update(size_in_bytes=913)),
                     (3, lambda x: x["workflow_run"].update(id=1))]
        for index, mutate in mutations:
            def modify(responses):
                value = json.loads(responses[index].raw)
                mutate(value)
                responses[index].raw = json.dumps(value).encode()
            with self.subTest(index=index):
                self.assert_failure(self.invoke(modify=modify), stage=2)
                self.assertLessEqual(len(self.calls), 4)
        for raw in (b'{"id":1,"id":2}', b'{"id":NaN}', b'{"id":1.0}', b'x' * 131073):
            self.assert_failure(self.invoke(modify=lambda r: setattr(r[0], "raw", raw)), stage=2)
        self.assert_failure(self.invoke(modify=lambda r: r[2].headers.append(("Link", "synthetic-secret"))), stage=2)

    def test_redirect_validation_rejects_other_hosts_and_clears_url_cache(self):
        bad = ["https://other.blob.core.windows.net/x?sig=synthetic-secret", "https://" + proof.HOST + ".evil.invalid/x",
               "https://evil" + proof.HOST + "/x", "https://127.0.0.1/x", "http://" + proof.HOST + "/x",
               "https://user@" + proof.HOST + "/x", "https://" + proof.HOST + ":444/x",
               "https://" + proof.HOST + "/x#secret", "https://" + proof.HOST + "/x\nsecret",
               "https://" + proof.HOST + "//x", "https://" + proof.HOST + "/é", "https://" + proof.HOST + "/" + "x" * 8192]
        for location in bad:
            with self.subTest(synthetic_case=bad.index(location)):
                self.assert_failure(self.invoke(location=location), stage=3)
                self.assertEqual(len(self.calls), 5)
                self.assertEqual(observation.urlsplit.cache_info().currsize, 0)
        for headers in ([], [("Location", LOCATION)] * 2):
            self.assert_failure(self.invoke(modify=lambda r: setattr(r[4], "headers", headers)), stage=3, predicate=42)

    def test_storage_http_shape_rejections_never_read_body_or_follow_redirects(self):
        for status in (201, 206, 301, 302, 303, 307, 308, 403, 404, 500):
            with self.subTest(status=status):
                result = self.invoke(modify=lambda r: setattr(r[5], "status", status))
                self.assert_failure(result, stage=4, predicate=45)
                self.assertEqual(result[2][5].reads, [])
                self.assertEqual(len(self.calls), 6)
        invalid = [[], [("Content-Length", "911")], [("Content-Length", "913")], [("Content-Length", "0912")],
                   [("Content-Length", "912")] * 2, [("Content-Length", " 912")]]
        invalid += [[("Content-Length", "912"), extra] for extra in
                    (("Location", LOCATION), ("Transfer-Encoding", "chunked"), ("Content-Range", "bytes 0-911/912"),
                     ("Content-Encoding", "gzip"), ("X-Large", "x" * 16384))]
        invalid += [[("Content-Length", "912"), ("Content-Encoding", "identity"), ("Content-Encoding", "identity")]]
        for index, headers in enumerate(invalid):
            with self.subTest(case=index):
                result = self.invoke(modify=lambda r: setattr(r[5], "headers", headers))
                self.assert_failure(result, stage=4)
                self.assertEqual(result[2][5].reads, [])

    def test_bounded_body_and_digest_rejections_stop_before_postcheck(self):
        for body in (b"", b"x" * 911, b"x" * 913, b"x" * 2000, b"x" * 912,
                     TimeoutError(TOKEN + LOCATION), proof.http.client.IncompleteRead(b"synthetic-secret")):
            with self.subTest(kind=type(body).__name__):
                result = self.invoke(body=body)
                self.assert_failure(result)
                self.assertEqual(result[2][5].reads, [913])
                self.assertEqual(len(self.calls), 6)

    def test_postcheck_rejects_every_target_field_and_changed_inventory_without_redownload(self):
        with patch.object(observation, "DIGEST", DIGEST):
            base = observation_fixture()
        paths = [(0, ("id",)), (0, ("full_name",)), (1, ("id",)), (1, ("head_sha",)),
                 (1, ("status",)), (1, ("conclusion",)), (1, ("repository", "id")),
                 (1, ("head_repository", "id")), (2, ("total_count",))]
        for index, prefix in ((2, ("artifacts", 0)), (3, ())):
            paths += [(index, prefix + (key,)) for key in ("id", "size_in_bytes", "digest", "expired")]
            paths += [(index, prefix + ("workflow_run", key)) for key in ("id", "repository_id", "head_repository_id", "head_sha")]
        for index, path in paths:
            def modify(responses):
                value = copy.deepcopy(base[index])
                item = value
                for key in path[:-1]:
                    item = item[key]
                item[path[-1]] = None
                responses[6 + index].raw = json.dumps(value).encode()
            with self.subTest(path=path):
                self.assert_failure(self.invoke(modify=modify), stage=6)
                self.assertEqual(sum(c[0] == proof.HOST for c in self.calls), 1)
        def changed_inventory(responses):
            value = json.loads(responses[8].raw)
            value["artifacts"].append({"id": 2})
            value["total_count"] = 2
            responses[8].raw = json.dumps(value).encode()
        self.assert_failure(self.invoke(modify=changed_inventory), stage=6, predicate=51)
        self.assert_failure(self.invoke(modify=lambda r: setattr(r[9], "status", 404)), stage=6)

    def test_monotonic_expiry_after_blocking_calls_prevents_next_request_and_success(self):
        for stop in (1, 5, 6, 10):
            clock = [0.0]
            def elapsed(count):
                if count == stop:
                    clock[0] = 41.0
            with self.subTest(stop=stop), patch.object(proof.time, "monotonic", side_effect=lambda: clock[0]):
                self.assert_failure(self.invoke(after_response=elapsed), predicate=40)
                self.assertEqual(len(self.calls), stop)

    def test_cleanup_cache_and_timer_errors_withhold_success_and_hide_exception_text(self):
        for position in (4, 5, 9):
            def modify(responses):
                original = responses[position].close
                def fail_close():
                    original()
                    raise RuntimeError(TOKEN + LOCATION)
                responses[position].close = fail_close
            self.assert_failure(self.invoke(modify=modify))
        clear = proof.urlsplit.cache_clear
        count = [0]
        def fail_clear_once():
            count[0] += 1
            if count[0] == 2:
                raise RuntimeError(TOKEN + LOCATION)
            clear()
        with patch.object(proof.urlsplit, "cache_clear", side_effect=fail_clear_once):
            self.assert_failure(self.invoke(), stage=3)
        self.assertEqual(observation.urlsplit.cache_info().currsize, 0)
        for method, fail_at in (("signal", 1), ("signal", 2), ("setitimer", 1), ("setitimer", 2)):
            original, old = getattr(signal, method), signal.getsignal(signal.SIGALRM)
            count = [0]
            def fail_timer(*args):
                count[0] += 1
                if count[0] == fail_at:
                    raise RuntimeError(TOKEN + LOCATION)
                return original(*args)
            try:
                with self.subTest(method=method, call=fail_at), patch.object(signal, method, side_effect=fail_timer):
                    self.assert_failure(self.invoke())
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old)

    def test_real_http_serializer_preserves_target_and_never_forwards_api_headers(self):
        for location in (LOCATION, "https://" + proof.HOST + "/synthetic?"):
            with patch.object(observation, "DIGEST", DIGEST):
                responses = self.responses(location=location)
                wire, sockets = [], []
                class WireSocket:
                    def __init__(self, raw):
                        self.raw, self.closed = raw, False
                    def sendall(self, data):
                        wire.append(data)
                    def makefile(self, *_args):
                        return io.BytesIO(self.raw)
                    def close(self):
                        self.closed = True
                owner = self
                def connect(connection):
                    index = len(sockets)
                    owner.assertEqual(connection.host, proof.HOST if index == 5 else "api.github.com")
                    owner.assertTrue(connection._context.check_hostname)
                    owner.assertEqual(connection._context.verify_mode, ssl.CERT_REQUIRED)
                    response = responses[index]
                    headers = response.headers[:]
                    if not any(k.lower() == "content-length" for k, _ in headers):
                        headers.append(("Content-Length", str(len(response.raw))))
                    raw = (f"HTTP/1.1 {response.status} Synthetic\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers) + "\r\n").encode() + response.raw
                    connection.sock = WireSocket(raw)
                    sockets.append(connection.sock)
                output = io.StringIO()
                with patch.object(proof.http.client.HTTPSConnection, "connect", connect), patch.object(sys, "argv", ["probe"]):
                    with patch.dict(os.environ, {"GH_TOKEN": TOKEN, "HTTPS_PROXY": "http://synthetic-proxy.invalid"}), redirect_stdout(output):
                        self.assertEqual(proof.proof_main(), 0)
                self.assertEqual(len(wire), 10)
                self.assertTrue(all(s.closed for s in sockets))
                storage = wire[5].decode("ascii")
                self.assertEqual(storage.split("\r\n")[0], "GET " + location.removeprefix("https://" + proof.HOST) + " HTTP/1.1")
                headers = dict(line.split(": ", 1) for line in storage.split("\r\n")[1:] if line)
                self.assertEqual(headers, {"Host": proof.HOST, "Accept-Encoding": "identity", "Connection": "close"})
                self.assertNotIn(TOKEN, storage)
                self.assertTrue(all((TOKEN.encode() in request) == (index != 5) for index, request in enumerate(wire)))
                self.assertEqual(observation.urlsplit.cache_info().currsize, 0)

    def test_source_workflow_and_production_constants_remain_narrow(self):
        root = Path(__file__).resolve().parents[1]
        source = Path(proof.__file__).read_text()
        workflow = (root / ".github/workflows/rc-artifact-byte-proof.yml").read_text()
        self.assertLessEqual(len(source.splitlines()), 200)
        self.assertLessEqual(len(workflow.splitlines()), 100)
        self.assertEqual((observation.SIZE, observation.ARTIFACT_ID, observation.RUN_ID, observation.REPOSITORY_ID),
                         (912, 11134440327, 36796834637, 1360355522))
        self.assertEqual(observation.DIGEST, "sha256:dcc70362712162e99d6884942f0720934bc16c7d6a817361ffbfd1602601fa60")
        self.assertEqual(proof.HOST, "productionresultssa5.blob.core.windows.net")
        tree = ast.parse(source)
        imports = {n.names[0].name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))}
        self.assertTrue(imports.isdisjoint({"zipfile", "tarfile", "subprocess", "zlib", "gzip", "requests"}))
        for text in ("open(", "write_bytes", "write_text", "exec(", "eval(", "urlopen", "extract", "set_debuglevel"):
            self.assertNotIn(text, source)
        for text in ("branches: [ci/rc-artifact-byte-proof]", "github.repository_id == '1360355522'",
                     "github.ref == 'refs/heads/ci/rc-artifact-byte-proof'", "contents: read", "actions: read",
                     "python-version: '3.12.14'", "persist-credentials: false", "ref: ${{ github.sha }}",
                     "timeout --signal=KILL 45s python scripts/rc_transport_byte_proof.py",
                     "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
                     "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"):
            self.assertIn(text, workflow)
        for text in ("inputs:", "write", "upload-artifact", "cache:", "environment:", "secrets.", "pull_request"):
            self.assertNotIn(text, workflow)

    def test_token_safety_and_arbitrary_cli_input_reject_before_requests(self):
        for token in ("", "a\r\nb", "a b", "é", "x" * 4097, "a=b"):
            self.assert_failure(self.invoke(token=token), stage=1, predicate=26)
            self.assertEqual(self.calls, [])
        self.assertEqual(self.invoke(token="x" * 4096)[0], 0)
        output = io.StringIO()
        with patch.dict(os.environ, {"GH_TOKEN": TOKEN}), patch.object(sys, "argv", ["probe", "synthetic-input"]):
            with redirect_stdout(output):
                self.assertEqual(proof.proof_main(), 1)
            self.assertNotIn("GH_TOKEN", os.environ)
        self.assertEqual(json.loads(output.getvalue())["predicate_id"], 31)

    def test_forged_error_state_remains_typed_and_never_discloses_private_values(self):
        for state in ([TOKEN, LOCATION], [], [6, None]):
            def fail(_token):
                proof.STATE[:] = state
                observation.OBSERVATION_STATE[:] = []
                raise observation.ObservationRejected(LOCATION)
            with patch.object(proof, "proof_run", side_effect=fail):
                self.assert_failure(self.invoke(), predicate=0)
        observation.OBSERVATION_STATE[:] = [0, None]


if __name__ == "__main__":
    unittest.main()
