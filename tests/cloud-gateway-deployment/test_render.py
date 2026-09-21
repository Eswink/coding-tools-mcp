import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/cloud-gateway/render.py"
spec = importlib.util.spec_from_file_location("render", SCRIPT)
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)
CONNECTOR = "00000000-0000-0000-0000-000000000001"


class DeploymentContracts(unittest.TestCase):
    def blueprint(self):
        return render.compose_blueprint(render.DEFAULT_DOMAIN, CONNECTOR, 28880)

    def test_injection_and_noncanonical_hosts_are_rejected(self):
        for host in ["example.com;return 200;", "example.com\n", "$host", "https://example.com",
                     "example.com/path", "example.com:443", "EXAMPLE.com", "x..com", "a-.com", "例子.com"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                render.validate(host, CONNECTOR, 28880)

    def test_connector_id_is_validated(self):
        for value in ["../a", "00000000-0000-0000-0000-000000000000", CONNECTOR.replace("-", "")]:
            with self.assertRaises(ValueError):
                render.validate(render.DEFAULT_DOMAIN, value, 28880)

    def test_port_must_not_take_over_443(self):
        for port in [443, 80, 0, 65536, True]:
            with self.assertRaises(ValueError):
                render.validate(render.DEFAULT_DOMAIN, CONNECTOR, port)

    def test_gateway_only_publishes_loopback(self):
        config = self.blueprint()
        ports = config["services"]["gateway"]["ports"]
        self.assertEqual(ports, [{"target": 8080, "published": "28880", "host_ip": "127.0.0.1", "protocol": "tcp"}])
        self.assertNotIn("ports", config["services"]["postgres"])
        self.assertTrue(config["networks"]["database"]["internal"])

    def test_no_default_runnable_service_or_fake_release(self):
        config = self.blueprint()
        for service in config["services"].values():
            self.assertEqual(service["profiles"], ["integration-pending"])
            self.assertIn(":?", service["image"])
        self.assertEqual(config["x-delivery-state"], "NOT_DEPLOYABLE_IDENTITY_LIBRARY_ONLY")

    def test_secrets_are_files_not_values(self):
        config = self.blueprint()
        for entry in config["secrets"].values():
            self.assertIn(":?", entry["file"])
        env = config["services"]["gateway"]["environment"]
        self.assertNotIn("DATABASE_URL", env)
        self.assertNotIn("IDENTITY_KEY", env)
        self.assertIn("/run/secrets/", env["IDENTITY_KEY_FILE"])

    def test_gateway_is_nonroot_and_unprivileged(self):
        service = self.blueprint()["services"]["gateway"]
        self.assertEqual(service["user"], "65532:65532")
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertNotIn("privileged", service)
        self.assertNotIn("network_mode", service)
        self.assertNotIn("docker.sock", json.dumps(service))

    def test_nginx_never_replaces_tls_or_root_site(self):
        text = render.nginx_locations(render.DEFAULT_DOMAIN, CONNECTOR, 28880)
        for forbidden in ["listen 443", "ssl_certificate", "location / {", "server {", "waf off"]:
            self.assertNotIn(forbidden, text)
        self.assertIn("proxy_pass http://127.0.0.1:28880;", text)
        self.assertNotIn("http://127.0.0.1:28880/;", text)
        self.assertIn("oauth-protected-resource/coding-tools/mcp/" + CONNECTOR, text)
        self.assertIn("oauth-authorization-server/coding-tools/oauth", text)

    def test_headers_and_streams_are_not_reinterpreted(self):
        text = render.nginx_locations(render.DEFAULT_DOMAIN, CONNECTOR, 28880)
        for directive in ["proxy_buffering off;", "proxy_intercept_errors off;", "proxy_cache off;",
                          'proxy_set_header X-Forwarded-Host "";', 'proxy_set_header Forwarded "";',
                          "proxy_set_header Host research-system.eswlnk.com;", "access_log off;", "return 421;"]:
            self.assertIn(directive, text)
        self.assertEqual(text.count('proxy_set_header Connection "upgrade";'), 1)

    def test_report_does_not_assume_compose_is_docker_engine(self):
        data = json.loads((ROOT / "deploy/cloud-gateway/inventory.user-reported.json").read_text())
        report = render.assess_inventory(data)
        self.assertIn("HOST_OS_EOL_CENTOS_STREAM_8", report["blockers"])
        self.assertIn("DOCKER_ENGINE_VERSION_UNVERIFIED", report["blockers"])
        self.assertFalse(report["changes_applied"])

    def test_old_engine_has_separate_loopback_risk(self):
        report = render.assess_inventory({"docker_engine_version": "27.5.1"})
        self.assertIn("DOCKER_LOOPBACK_PUBLISH_L2_RISK", report["blockers"])

    def test_no_inventory_can_turn_library_into_a_release(self):
        report = render.assess_inventory({"docker_engine_version": "28.0.0", "os_security_support_verified": True})
        self.assertEqual(report["status"], "BLOCKED_FOR_PRODUCTION")
        self.assertIn("GATEWAY_APPLICATION_INTEGRATION_PENDING", report["blockers"])

    def test_cli_only_writes_new_review_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "review"
            cmd = [sys.executable, str(SCRIPT), "--connector-id", CONNECTOR, "--output", str(target)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True)
            self.assertEqual(json.loads(result.stdout), {"rendered": True, "applied": False, "deployable": False})
            before = (target / "compose.blueprint.json").read_bytes()
            again = subprocess.run(cmd, capture_output=True, timeout=10)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((target / "compose.blueprint.json").read_bytes(), before)
            self.assertTrue((target / "NOT_DEPLOYABLE.txt").exists())


if __name__ == "__main__":
    unittest.main()
