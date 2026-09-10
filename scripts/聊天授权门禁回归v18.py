"""Strict gate regressions use synthetic evidence, never claim a real GUI run."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("native_gate_v18", Path(__file__).with_name("聊天授权证据门禁v18.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(source="a" * 40, run_id="123456", version="0.3.0", kind="nsis", binary_sha256="b" * 64)
        self.data = dict(passed=True, source_sha=self.expected["source"], run_id="123456", version="0.3.0",
            package_kind="nsis", build_kind="release-installed", binary_sha256=self.expected["binary_sha256"],
            real_native_webview=True, real_oauth_http=True, real_local_ipc=True,
            cleanup_completed=True, cleanup_failed=False, sandbox_disabled=False,
            synthetic_conversation_metadata=True, real_chatgpt_verified=False,
            tests=[dict(name=name, passed=True) for name in gate.TEST_NAMES])

    def test_complete_fixture_is_not_release_approval(self):
        proof = gate.verify(self.data, **self.expected)
        self.assertIs(proof["passed"], True)
        self.assertIs(proof["publish_approved"], False)
        self.assertIs(proof["real_chatgpt_verified"], False)

    def test_zero_of_eight_cannot_pass_even_with_prefilled_flags(self):
        self.data["tests"] = []
        with self.assertRaises(ValueError): gate.verify(self.data, **self.expected)

    def test_duplicate_or_incomplete_stages_rejected(self):
        variants = ([self.data["tests"][0]] * 8, self.data["tests"][:-1], self.data["tests"][::-1])
        for tests in variants:
            with self.subTest(tests=tests), self.assertRaises(ValueError):
                gate.verify({**self.data, "tests": tests}, **self.expected)

    def test_each_stage_requires_actual_boolean_true(self):
        for index in range(8):
            for wrong in (False, 1, "true", None):
                value = copy.deepcopy(self.data)
                value["tests"][index]["passed"] = wrong
                with self.subTest(index=index, wrong=wrong), self.assertRaises(ValueError):
                    gate.verify(value, **self.expected)

    def test_wrong_source_run_version_binary_and_package_rejected(self):
        for key in ("source_sha", "run_id", "version", "binary_sha256", "package_kind", "build_kind"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.verify({**self.data, key: "other"}, **self.expected)

    def test_observation_cleanup_and_metadata_boundaries_enforced(self):
        for key in ("real_native_webview", "real_oauth_http", "real_local_ipc", "cleanup_completed", "passed"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.verify({**self.data, key: False}, **self.expected)
        for key in ("sandbox_disabled", "cleanup_failed", "real_chatgpt_verified"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.verify({**self.data, key: True}, **self.expected)

    def test_failure_metadata_cannot_be_hidden_by_passed_true(self):
        for key in ("failure_type", "cleanup_failure_type", "host_exit_code"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.verify({**self.data, key: None}, **self.expected)

    def test_json_duplicates_nonfinite_and_bad_shapes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "证据.json"
            for raw in ('{"passed":false,"passed":true}', '{"x":NaN}', '[]', '', '{"tests":[{"passed":true,"passed":false}]}'):
                path.write_text(raw, encoding="utf-8")
                with self.subTest(raw=raw), self.assertRaises(ValueError): gate.load(path)
            path.write_text(json.dumps(self.data), encoding="utf-8-sig")
            self.assertEqual(gate.load(path), self.data)

    def test_oversized_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "证据.json"
            path.write_bytes(b" " * (gate.LIMIT + 1))
            with self.assertRaises(ValueError): gate.load(path)

    def test_gate_stage_names_match_actual_harness_calls(self):
        tree = ast.parse(Path(__file__).with_name("聊天授权原生验收v6.py").read_text(encoding="utf-8"))
        names = [n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "passed" and n.args
                 and isinstance(n.args[0], ast.Constant)]
        self.assertEqual(names, list(gate.TEST_NAMES))


if __name__ == "__main__":
    unittest.main()
