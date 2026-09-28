import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/cloud-gateway/migration.py"
spec = importlib.util.spec_from_file_location("migration", SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

CONNECTOR = "00000000-0000-0000-0000-000000000001"
OTHER_CONNECTOR = "00000000-0000-0000-0000-000000000002"
ORIGIN = "https://research-system.eswlnk.com"


class MigrationContracts(unittest.TestCase):
    def plan(self, **overrides):
        values = {
            "current_origin": ORIGIN,
            "target_origin": ORIGIN,
            "connector": CONNECTOR,
            "target_connector": None,
            "current_prefix": "/coding-tools",
            "target_prefix": None,
            "upstream_port": 28880,
            "inventory": {},
        }
        values.update(overrides)
        return migration.migration_plan(**values)

    def test_canonical_origin_rejects_ambiguous_or_non_https_forms(self):
        invalid = [
            "http://research-system.eswlnk.com",
            "https://user@research-system.eswlnk.com",
            "https://research-system.eswlnk.com/path",
            "https://research-system.eswlnk.com?query=1",
            "https://research-system.eswlnk.com#fragment",
            "https://research-system.eswlnk.com:0443",
            "https://RESEARCH-SYSTEM.eswlnk.com",
            "https://research-system.eswlnk.com.",
            "https://127.0.0.1",
            "https://[::1]",
            "https://research-system.eswlnk.com\n",
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(migration.MigrationError):
                migration.canonical_origin(value)

        self.assertEqual(
            migration.canonical_origin("https://research-system.eswlnk.com:443"),
            {
                "scheme": "https",
                "host": "research-system.eswlnk.com",
                "effective_port": 443,
                "origin": ORIGIN,
            },
        )
        self.assertEqual(
            migration.canonical_origin("https://research-system.eswlnk.com:8443")["origin"],
            "https://research-system.eswlnk.com:8443",
        )

    def test_prefix_and_connector_are_canonical(self):
        for prefix in ["coding-tools", "/coding-tools/", "/coding-tools//x", "/../x", "/中文"]:
            with self.subTest(prefix=prefix), self.assertRaises(migration.MigrationError):
                migration.canonical_prefix(prefix)
        for connector in [
            "00000000-0000-0000-0000-000000000000",
            CONNECTOR.replace("-", ""),
            "../connector",
        ]:
            with self.subTest(connector=connector), self.assertRaises(migration.MigrationError):
                migration.canonical_connector(connector)

    def test_same_public_identity_is_the_only_continuity_mode(self):
        plan = self.plan()
        self.assertEqual(plan["mode"], "STABLE_ORIGIN_ROUTE_SWAP")
        self.assertTrue(plan["oauth_continuity"]["eligible"])
        self.assertEqual(plan["current"]["origin"], plan["target"]["origin"])
        self.assertEqual(plan["current"]["resource"], plan["target"]["resource"])
        self.assertEqual(plan["current"]["issuer"], plan["target"]["issuer"])
        self.assertEqual(plan["current"]["connector"], plan["target"]["connector"])
        self.assertFalse(plan["release_allowed"])
        self.assertFalse(plan["changes_applied"])

    def test_any_public_identity_change_requires_reconnect_and_reauth(self):
        variants = [
            {"target_origin": "https://new-research.eswlnk.com"},
            {"target_origin": "https://research-system.eswlnk.com:8443"},
            {"target_prefix": "/coding-tools-v2"},
            {"target_connector": OTHER_CONNECTOR},
        ]
        for change in variants:
            with self.subTest(change=change):
                plan = self.plan(**change)
                self.assertEqual(plan["mode"], "EXPLICIT_RECONNECT_REAUTH_REQUIRED")
                self.assertFalse(plan["oauth_continuity"]["eligible"])
                self.assertEqual(
                    plan["oauth_continuity"]["required_action"],
                    "explicit_connector_reconnect_and_reauthentication",
                )

    def test_rollback_is_routing_only_and_identity_is_monotonic(self):
        rollback = self.plan()["rollback"]
        self.assertTrue(rollback["routing_only"])
        self.assertTrue(rollback["preserve_current_identity_database"])
        self.assertTrue(rollback["preserve_revocations"])
        self.assertTrue(rollback["preserve_request_ledger_uncertainty"])
        self.assertTrue(rollback["keep_previous_route_until_host_acceptance"])
        self.assertFalse(rollback["restore_identity_database"])
        self.assertFalse(rollback["restore_oauth_state"])
        self.assertFalse(rollback["restore_revocation_epochs"])
        self.assertFalse(rollback["restore_consumed_authorization_state"])
        self.assertFalse(rollback["replay_unknown_requests"])

    def test_plan_has_typed_actions_not_executable_commands_or_secrets(self):
        plan = self.plan()
        serialized = json.dumps(plan, sort_keys=True).lower()
        for secret_key in [
            "access_token",
            "refresh_token",
            "authorization_code",
            "private_key",
            "database_url",
            "password",
            "cookie_value",
        ]:
            self.assertNotIn(secret_key, serialized)

        def walk(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertNotIn(key, {"command", "shell", "script", "exec", "argv"})
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)

        walk(plan)
        self.assertEqual(
            [phase["name"] for phase in plan["phases"]],
            ["preflight", "stage", "cutover", "verify", "rollback"],
        )

    def test_current_user_reported_inventory_stays_release_blocked(self):
        inventory = json.loads(
            (ROOT / "deploy/cloud-gateway/inventory.user-reported.json").read_text(encoding="utf-8")
        )
        plan = self.plan(inventory=inventory)
        evidence = {item["id"]: item["status"] for item in plan["required_evidence"]}
        self.assertEqual(evidence["supported_host"], "missing")
        self.assertEqual(evidence["docker_engine_isolation"], "missing")
        self.assertEqual(evidence["upstream_port_available"], "missing")
        self.assertEqual(evidence["tls_verified"], "missing")
        self.assertEqual(evidence["waf_protocol_verified"], "missing")
        self.assertEqual(evidence["real_chatgpt_acceptance"], "missing")
        self.assertFalse(plan["release_allowed"])

    def test_artifact_manifest_is_deterministic_sorted_and_detects_tamper(self):
        a = {"z.txt": b"z", "a.txt": b"alpha"}
        b = {"a.txt": b"alpha", "z.txt": b"z"}
        first = migration.artifact_manifest(a)
        second = migration.artifact_manifest(b)
        self.assertEqual(first, second)
        self.assertEqual([entry["path"] for entry in first["files"]], ["a.txt", "z.txt"])
        self.assertFalse(first["manifest_self_hashed"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, payload in a.items():
                (root / name).write_bytes(payload)
            migration.verify_artifact_manifest(root, first)
            (root / "a.txt").write_bytes(b"tampered")
            with self.assertRaises(migration.MigrationError):
                migration.verify_artifact_manifest(root, first)

    def test_cli_only_creates_fresh_review_package_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "migration-review"
            command = [
                sys.executable,
                str(SCRIPT),
                "--connector-id",
                CONNECTOR,
                "--inventory",
                str(ROOT / "deploy/cloud-gateway/inventory.user-reported.json"),
                "--output",
                str(output),
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=10, check=True
            )
            self.assertEqual(
                json.loads(completed.stdout),
                {
                    "applied": False,
                    "mode": "STABLE_ORIGIN_ROUTE_SWAP",
                    "release_allowed": False,
                    "rendered": True,
                },
            )
            plan = json.loads((output / "migration-plan.review.json").read_text(encoding="utf-8"))
            manifest = json.loads(
                (output / "artifact-manifest.review.json").read_text(encoding="utf-8")
            )
            migration.verify_artifact_manifest(output, manifest)
            self.assertFalse(plan["changes_applied"])
            self.assertFalse(plan["release_allowed"])
            before = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            again = subprocess.run(command, capture_output=True, timeout=10)
            self.assertNotEqual(again.returncode, 0)
            after = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_changed_domain_cli_stays_review_only_and_requires_reauth(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "changed-origin"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--connector-id",
                    CONNECTOR,
                    "--target-origin",
                    "https://new-research.eswlnk.com",
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            result = json.loads(completed.stdout)
            self.assertEqual(result["mode"], "EXPLICIT_RECONNECT_REAUTH_REQUIRED")
            self.assertFalse(result["release_allowed"])
            plan = json.loads((output / "migration-plan.review.json").read_text(encoding="utf-8"))
            self.assertFalse(plan["oauth_continuity"]["eligible"])


if __name__ == "__main__":
    unittest.main()
