"""Unit checks for the native harness; these are not native GUI acceptance."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("native_auth_v6", Path(__file__).with_name("聊天授权原生验收v6.py"))
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


class NativeHarnessTests(unittest.TestCase):
    def test_callback_is_never_followed(self):
        self.assertIsNone(auth.NoRedirect().redirect_request(None, None, 303, "See Other", {}, "https://chatgpt.com/connector/oauth/fixture"))

    def test_host_metadata_stays_separate_from_model_arguments(self):
        calls = []
        def exchange(url, data, **kwargs):
            calls.append(data)
            return 200, {}, json.dumps({"result": {"structuredContent": {"ok": False}}}).encode()
        with patch.object(auth, "exchange", side_effect=exchange):
            auth.rpc("http://127.0.0.1:1234", "test-token", "B", "server_info", {"_meta": {"openai/session": "A"}})
            auth.rpc("http://127.0.0.1:1234", "test-token", None, "server_info", {})
        self.assertEqual(calls[0]["params"]["_meta"]["openai/session"], "B")
        self.assertEqual(calls[0]["params"]["arguments"]["_meta"]["openai/session"], "A")
        self.assertNotIn("_meta", calls[1]["params"])

    def test_missing_structured_response_is_not_counted_as_denial(self):
        with patch.object(auth, "exchange", return_value=(200, {}, b'{"result":{}}')):
            with self.assertRaises(AssertionError):
                auth.rpc("http://127.0.0.1:1234", "test-token", "A", "server_info", {})

    def test_denial_assertion_rejects_data_leak_and_false_success(self):
        denied = {"ok": False, "error": {"code": "CHAT_AUTHORIZATION_REQUIRED"}}
        auth.denied(denied, "/private-workspace")
        for value in [{**denied, "ok": True}, {**denied, "message": "/private-workspace"}, {**denied, "output": "chat-A-only-v6"}]:
            with self.assertRaises(AssertionError):
                auth.denied(value, "/private-workspace")


class NativeOAuthMigrationTests(unittest.TestCase):
    BASE = "http://127.0.0.1:1234"
    CALLBACK = "https://chatgpt.com/connector/oauth/native-fixture-v6"

    def exchange(self, transform=lambda url, status, headers, data: (status, headers, data)):
        calls = []
        def invoke(url, data=None, **kwargs):
            calls.append((url, data, kwargs))
            headers = {"Cache-Control": "no-store"}
            if "/.well-known/oauth-protected-resource" in url:
                body = {"resource": self.BASE + "/mcp", "authorization_servers": [self.BASE]}
                status = 200
            elif url.endswith("/.well-known/oauth-authorization-server"):
                body = {"issuer": self.BASE, "authorization_endpoint": self.BASE + "/oauth/authorize",
                        "token_endpoint": self.BASE + "/oauth/token", "code_challenge_methods_supported": ["S256"],
                        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"]}
                status = 200
            elif "/oauth/authorize?" in url:
                body, status = b"fixture login form", 200
            elif url.endswith("/oauth/authorize"):
                self.assertEqual(data["resource"], self.BASE + "/mcp")
                headers["Location"] = self.CALLBACK + "?code=fixture-code&state=" + data["state"]
                body, status = b"", 303
            elif url.endswith("/oauth/token"):
                self.assertEqual(data["resource"], self.BASE + "/mcp")
                if data.get("client_secret") != "fixture-client-secret":
                    headers["WWW-Authenticate"] = 'Basic realm="oauth"'
                    body, status = {"error": "invalid_client"}, 401
                else:
                    body, status = {"access_token": "fixture-token-not-real"}, 200
            else:
                raise AssertionError("unexpected fixture route")
            status, headers, body = transform(url, status, headers, body)
            return status, headers, json.dumps(body).encode() if isinstance(body, dict) else body
        return invoke, calls

    def token(self):
        return auth.oauth_token(self.BASE, "fixture-client", "fixture-password", self.CALLBACK,
                                "/private-fixture", client_secret="fixture-client-secret")

    def test_discovery_and_confidential_exchange_match_current_protocol(self):
        exchange, calls = self.exchange()
        with patch.object(auth, "exchange", side_effect=exchange):
            self.assertEqual(self.token(), "fixture-token-not-real")
        urls = [item[0] for item in calls]
        self.assertIn(self.BASE + "/.well-known/oauth-protected-resource/mcp", urls)
        self.assertIn(self.BASE + "/.well-known/oauth-protected-resource", urls)
        self.assertIn(self.BASE + "/.well-known/oauth-authorization-server", urls)
        forms = [item[1] for item in calls if item[0].endswith("/oauth/token")]
        self.assertEqual(len(forms), 3)
        self.assertNotIn("client_secret", forms[0])
        self.assertNotEqual(forms[1]["client_secret"], "fixture-client-secret")
        self.assertEqual(forms[2]["client_secret"], "fixture-client-secret")

    def test_origin_only_resource_is_rejected(self):
        def alter(url, status, headers, body):
            if isinstance(body, dict) and "resource" in body: body["resource"] = self.BASE
            return status, headers, body
        exchange, _ = self.exchange(alter)
        with patch.object(auth, "exchange", side_effect=exchange), self.assertRaises(AssertionError): self.token()

    def test_cross_issuer_and_disagreeing_aliases_are_rejected(self):
        for broken in ("issuer", "alias"):
            def alter(url, status, headers, body):
                if broken == "issuer" and isinstance(body, dict) and "issuer" in body: body["issuer"] = "https://other.invalid"
                if broken == "alias" and url.endswith("oauth-protected-resource"): body["resource"] += "/other"
                return status, headers, body
            exchange, _ = self.exchange(alter)
            with patch.object(auth, "exchange", side_effect=exchange), self.assertRaises(AssertionError): self.token()

    def test_unauthenticated_token_success_is_never_accepted(self):
        def alter(url, status, headers, body):
            if status == 401: return 200, headers, {"access_token": "unexpected"}
            return status, headers, body
        exchange, _ = self.exchange(alter)
        with patch.object(auth, "exchange", side_effect=exchange), self.assertRaises(AssertionError): self.token()

    def test_secret_exposure_on_login_and_error_is_rejected(self):
        for broken in ("login", "error"):
            def alter(url, status, headers, body):
                if broken == "login" and "/oauth/authorize?" in url: body = b"fixture-client-secret"
                if broken == "error" and status == 401: body["detail"] = "fixture-client-secret"
                return status, headers, body
            exchange, _ = self.exchange(alter)
            with patch.object(auth, "exchange", side_effect=exchange), self.assertRaises(AssertionError): self.token()

    def test_fixture_setup_persists_random_secret_and_exact_challenge(self):
        source = Path(__file__).with_name("聊天授权原生验收v6.py").read_text(encoding="utf-8")
        self.assertIn('("oauth_client_secret", client_secret)', source)
        self.assertIn('client_secret = secrets.token_urlsafe(32)', source)
        self.assertIn('client_secret=client_secret', source)
        self.assertIn('Bearer resource_metadata=', source)
        self.assertIn('/.well-known/oauth-protected-resource/mcp', source)


if __name__ == "__main__":
    unittest.main()
