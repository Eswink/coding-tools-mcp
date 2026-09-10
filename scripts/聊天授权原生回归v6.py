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


if __name__ == "__main__":
    unittest.main()
