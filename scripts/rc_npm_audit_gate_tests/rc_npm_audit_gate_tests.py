"""Gate, evidence-verifier and consumer-site tests for the time-boxed npm audit exemption."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# Kept in a subdirectory so the frozen top-level scripts/*.py inventory of
# Windows标准用户验收v22.py stays within its 300-entry cap; the modules under test
# remain top-level in scripts/ and are imported from there explicitly.
SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import rc_npm_audit_gate as module  # noqa: E402

TODAY = date(2026, 10, 28)
ADVISORY = dict(source=1243505, name="deepmerge", dependency="deepmerge",
                title="deepmerge mergeObject() allows prototype poisoning of returned objects",
                url="https://github.com/advisories/GHSA-gcqx-w48m-w2h4", severity="low",
                cwe=["CWE-1321"], range=">=4.2.0 <=4.3.1")


def entry(name, via, direct=True):
    return dict(name=name, severity="low", isDirect=direct, via=via, effects=[], range="*",
                nodes=["node_modules/" + name], fixAvailable=dict(name="@sveltejs/kit", version="0.0.30", isSemVerMajor=True))


def report(vulnerabilities):
    totals = dict(info=0, low=0, moderate=0, high=0, critical=0)
    for value in vulnerabilities.values():
        totals[value["severity"]] += 1
    totals["total"] = len(vulnerabilities)
    return dict(auditReportVersion=2, vulnerabilities=vulnerabilities, metadata=dict(vulnerabilities=totals))


def exempt():
    return report({
        "deepmerge": entry("deepmerge", [dict(ADVISORY)], direct=False),
        "@sveltejs/vite-plugin-svelte": entry("@sveltejs/vite-plugin-svelte", ["deepmerge"]),
        "@sveltejs/kit": entry("@sveltejs/kit", ["@sveltejs/vite-plugin-svelte"]),
        "@sveltejs/adapter-static": entry("@sveltejs/adapter-static", ["@sveltejs/kit"]),
    })


class RcNpmAuditGateTests(unittest.TestCase):
    def rejects(self, value, code=1, today=TODAY):
        with self.assertRaises(module.GateError):
            module.check_full(value, code, today)

    def test_only_exempt_advisory_passes(self):
        result = module.check_full(exempt(), 1, TODAY)
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["advisory"], "https://github.com/advisories/GHSA-gcqx-w48m-w2h4")

    def test_extra_advisory_fails(self):
        value = exempt()
        value["vulnerabilities"]["deepmerge"]["via"].append(dict(ADVISORY, source=1, url="https://github.com/advisories/GHSA-xxxx-xxxx-xxxx"))
        self.rejects(value)
        value = exempt()
        value["vulnerabilities"]["vite"] = entry("vite", [dict(ADVISORY, name="vite", dependency="vite", url="https://github.com/advisories/GHSA-yyyy-yyyy-yyyy")])
        value["metadata"]["vulnerabilities"].update(low=5, total=5)
        self.rejects(value)

    def test_same_advisory_with_moderate_severity_fails(self):
        value = exempt()
        value["vulnerabilities"]["deepmerge"]["via"][0]["severity"] = "moderate"
        self.rejects(value)
        value = exempt()
        for item in value["vulnerabilities"].values():
            item["severity"] = "moderate"
        value["metadata"]["vulnerabilities"].update(low=0, moderate=4)
        self.rejects(value)

    def test_chain_must_resolve_only_to_advisory(self):
        value = exempt()
        value["vulnerabilities"]["@sveltejs/kit"]["via"].append(dict(ADVISORY))
        self.rejects(value)
        value = exempt()
        value["vulnerabilities"]["@sveltejs/vite-plugin-svelte"]["via"] = ["@sveltejs/kit"]
        self.rejects(value)
        value = exempt()
        del value["vulnerabilities"]["@sveltejs/adapter-static"]
        value["metadata"]["vulnerabilities"].update(low=3, total=3)
        self.rejects(value)

    def test_expiry_and_exit_codes(self):
        module.check_full(exempt(), 1, date(2026, 11, 30))
        self.rejects(exempt(), today=date(2026, 12, 1))
        self.rejects(exempt(), code=0)
        self.rejects(dict(exempt(), error=dict(code="ENOLOCK")))
        zero = report({})
        self.assertEqual(module.check_full(zero, 0, date(2027, 1, 1)), dict(total=0, exempted=[]))
        self.rejects(zero, code=1)

    def test_malformed_counts_fail(self):
        value = exempt()
        value["metadata"]["vulnerabilities"]["total"] = True
        self.rejects(value)
        value = exempt()
        value["metadata"]["vulnerabilities"]["low"] = 3
        self.rejects(value)

    def test_prod_requires_zero(self):
        self.assertEqual(module.check_prod(report({}), 0), dict(total=0))
        with self.assertRaises(module.GateError):
            module.check_prod(exempt(), 1)
        with self.assertRaises(module.GateError):
            module.check_prod(report({}), 1)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            full, prod = Path(directory, "full.json"), Path(directory, "prod.json")
            full.write_text(json.dumps(report({})))
            prod.write_text(json.dumps(report({})))
            self.assertEqual(module.main(["--full", str(full), "--full-exit-code", "0",
                                          "--prod", str(prod), "--prod-exit-code", "0"]), 0)
            prod.write_text(json.dumps(exempt()))
            self.assertEqual(module.main(["--full", str(full), "--full-exit-code", "0",
                                          "--prod", str(prod), "--prod-exit-code", "1"]), 1)

    def test_cli_writes_capture_record_next_to_full_report(self):
        with tempfile.TemporaryDirectory() as directory:
            full, prod = Path(directory, "npm-audit.json"), Path(directory, "prod.json")
            full.write_text(json.dumps(exempt()))
            prod.write_text(json.dumps(report({})))
            clock = datetime(2026, 10, 28, 7, 0, 1, tzinfo=timezone.utc)
            with patch.object(module, "utc_now", return_value=clock):
                self.assertEqual(module.main(["--full", str(full), "--full-exit-code", "1",
                                              "--prod", str(prod), "--prod-exit-code", "0"]), 0)
            capture = json.loads(Path(directory, module.CAPTURE_NAME).read_text())
            self.assertEqual(capture["captured_at"], "2026-10-28T07:00:01Z")
            self.assertEqual(capture["full_sha256"], hashlib.sha256(full.read_bytes()).hexdigest())
            self.assertEqual(module.check_recorded(exempt(), full.read_bytes(), capture)["captured_at"],
                             "2026-10-28T07:00:01Z")
            with patch.object(module, "utc_now", return_value=datetime(2026, 12, 1, tzinfo=timezone.utc)):
                Path(directory, module.CAPTURE_NAME).unlink()
                self.assertEqual(module.main(["--full", str(full), "--full-exit-code", "1",
                                              "--prod", str(prod), "--prod-exit-code", "0"]), 1)
            self.assertFalse(Path(directory, module.CAPTURE_NAME).exists())


# rc.2 packaging run 40428267551 (bdc4aeb5), artifact rc-package-contracts/npm-audit.json, byte-exact.
# Its sha256 equals the npm-audit.json digest recorded in that run's identity.json evidence_inventory.
RC2_NPM_AUDIT = (b'{\n  "auditReportVersion": 2,\n  "vulnerabilities": {},\n  "metadata": {\n'
                 b'    "vulnerabilities": {\n      "info": 0,\n      "low": 0,\n      "moderate": 0,\n'
                 b'      "high": 0,\n      "critical": 0,\n      "total": 0\n    },\n    "dependencies": {\n'
                 b'      "prod": 23,\n      "dev": 111,\n      "optional": 67,\n      "peer": 0,\n'
                 b'      "peerOptional": 0,\n      "total": 133\n    }\n  }\n}\n')
RC2_NPM_AUDIT_SHA256 = "f09d5ea0fad78e79db7624fcba6e67734fa6a95bb5efc40fcc036c95b316dc3f"
BEFORE = datetime(2026, 11, 29, 23, 59, 59, tzinfo=timezone.utc)
AFTER = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
LATE_CLOCK = datetime(2027, 6, 1, tzinfo=timezone.utc)


def encode(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def capture_for(full, captured_at=BEFORE, prod=None, prod_code=0, full_code=None):
    data = full if type(full) is bytes else encode(full)
    total = json.loads(data)["metadata"]["vulnerabilities"]["total"]
    return module.capture_record(data, (1 if total else 0) if full_code is None else full_code,
                                 report({}) if prod is None else prod, prod_code, captured_at)


def different_advisory():
    value = exempt()
    value["vulnerabilities"]["deepmerge"]["via"][0]["url"] = "https://github.com/advisories/GHSA-zzzz-zzzz-zzzz"
    return value


def moderate():
    value = exempt()
    for item in value["vulnerabilities"].values():
        item["severity"] = "moderate"
    value["vulnerabilities"]["deepmerge"]["via"][0]["severity"] = "moderate"
    value["metadata"]["vulnerabilities"].update(low=0, moderate=4)
    return value


def extra_package():
    value = exempt()
    value["vulnerabilities"]["vite"] = entry("vite", ["deepmerge"])
    value["metadata"]["vulnerabilities"].update(low=5, total=5)
    return value


def no_clock():
    raise AssertionError("evidence verification must not read the clock")


class Site:
    """One verification site: returns normally on pass, raises ValueError on fail."""
    name = ""

    def verify(self, full, capture):
        raise NotImplementedError


class GateSite(Site):
    name = "rc_npm_audit_gate.check_recorded"

    def __init__(self, base):
        pass

    def verify(self, full, capture):
        data = full if type(full) is bytes else encode(full)
        return module.check_recorded(json.loads(data), data, capture)


class EvidenceSite(Site):
    """scripts/final_rc_evidence.py audits() and dependency_contract() (both use npm_audit())."""

    def __init__(self, base, mode):
        import final_rc_evidence as final
        self.final, self.mode, self.name = final, mode, "final_rc_evidence." + mode
        self.directory = Path(base, "contracts")
        self.directory.mkdir()
        for name in final.LOCKS:
            (self.directory / f"rust-audit-{name}.json").write_text(json.dumps(dict(
                database=dict(commit="c" * 40), lockfile=dict(dependency_count=1),
                vulnerabilities=dict(found=False, count=0))))
        self.cloud = Path(base, "cloud")
        (self.cloud / "exact-build").mkdir(parents=True)
        (self.cloud / "exact-build/raw-audit.json").write_bytes(
            (self.directory / "rust-audit-cloud-gateway.json").read_bytes())

    def verify(self, full, capture):
        (self.directory / "npm-audit.json").write_bytes(full if type(full) is bytes else encode(full))
        path = self.directory / module.CAPTURE_NAME
        if path.exists():
            path.unlink()
        if capture is not None:
            path.write_text(json.dumps(capture))
        if self.mode == "audits":
            return self.final.audits(self.directory)
        dependency = self.final.dependency
        proof = dict(artifact_kind="release-cloud", archive_to_build_verified=True)
        with patch.object(dependency, "verify_archive", return_value=proof), \
             patch.object(dependency, "verify_noncloud_audits", return_value={}):
            return self.final.dependency_contract(self.directory, self.cloud, Path(self.cloud, "unpacked"),
                                                  Path("."), dict(version="0", source_sha="a" * 40), {})


class ConsumerSite(Site):
    """scripts/rc_consumer_contracts.py verify_consumed_bundle()."""
    name = "rc_consumer_contracts.verify_consumed_bundle"

    def __init__(self, base):
        from rc_consumer_fixtures import ConsumerFixture
        self.fixture = ConsumerFixture(base)

    def verify(self, full, capture):
        contracts = self.fixture.contracts
        (contracts / "npm-audit.json").write_bytes(full if type(full) is bytes else encode(full))
        path = contracts / module.CAPTURE_NAME
        if path.exists():
            path.unlink()
        if capture is not None:
            path.write_text(json.dumps(capture))
        self.fixture.refresh_inventory()
        return self.fixture.verify()


class RecordedEvidenceSites(unittest.TestCase):
    """Every site imports module.check_recorded and the module's exemption constants."""

    def sites(self):
        for factory in (GateSite, lambda b: EvidenceSite(b, "audits"),
                        lambda b: EvidenceSite(b, "dependency_contract"), ConsumerSite):
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            yield factory(temp.name)

    def passes(self, site, full, capture):
        with self.subTest(site=site.name, expect="pass"), patch.object(module, "utc_now", side_effect=no_clock):
            site.verify(full, capture)

    def fails(self, site, full, capture, why, reason):
        with self.subTest(site=site.name, expect="fail", why=why), \
             patch.object(module, "utc_now", side_effect=no_clock):
            with self.assertRaises(ValueError) as caught:
                site.verify(full, capture)
            error = caught.exception
            if isinstance(site, ConsumerSite):  # public boundary exposes only the fixed code
                self.assertEqual(str(error), "invalid_npm_zero_audit")
            chain = str(error) + " | " + str(error.__context__ or "")
            self.assertRegex(chain, reason)

    def test_sites_share_the_gate_function_and_constants(self):
        import final_rc_evidence as final
        import rc_consumer_contracts as consumer
        self.assertIs(final.npm_gate, module)
        self.assertIs(consumer.npm_gate, module)
        for path in ("final_rc_evidence.py", "rc_consumer_contracts.py"):
            text = (SCRIPTS / path).read_text(encoding="utf-8")
            self.assertIn("npm_gate.check_recorded(", text)
            for literal in ("GHSA-gcqx-w48m-w2h4", "deepmerge", "2026", "vite-plugin-svelte", "adapter-static"):
                self.assertNotIn(literal, text, f"copied allowlist literal {literal!r} in {path}")

    def test_rc2_actual_zero_audit_keeps_its_pass_verdict(self):
        self.assertEqual(hashlib.sha256(RC2_NPM_AUDIT).hexdigest(), RC2_NPM_AUDIT_SHA256)
        for site in self.sites():
            self.passes(site, RC2_NPM_AUDIT, None)  # historical evidence has no capture record
            self.passes(site, RC2_NPM_AUDIT, capture_for(RC2_NPM_AUDIT, captured_at=LATE_CLOCK))
            self.passes(site, dict(metadata=dict(vulnerabilities=dict(total=0))), None)  # legacy fixture shape
            self.fails(site, RC2_NPM_AUDIT, capture_for(RC2_NPM_AUDIT, full_code=1), "zero report, exit 1", "exit code 1 with zero findings")

    def test_capture_before_expiry_passes_with_simulated_clock_after_expiry(self):
        for site in self.sites():
            with patch.object(module, "utc_now", return_value=LATE_CLOCK):
                self.passes(site, exempt(), capture_for(exempt(), captured_at=BEFORE))
                self.passes(site, exempt(), capture_for(exempt(), captured_at=datetime(
                    2026, 11, 30, 23, 59, 59, tzinfo=timezone.utc)))

    def test_capture_after_expiry_fails(self):
        for site in self.sites():
            self.fails(site, exempt(), capture_for(exempt(), captured_at=AFTER), "captured after expiry", "expired after 2026-11-30")

    def test_negative_cases_at_every_site(self):
        for site in self.sites():
            self.passes(site, exempt(), capture_for(exempt()))
            self.fails(site, exempt(), None, "findings without capture record", "npm audit missing or vulnerable")
            self.fails(site, exempt(), capture_for(exempt(), prod=exempt(), prod_code=1), "prod not zero", "production npm audit is not zero")
            self.fails(site, exempt(), capture_for(exempt(), prod=report({}), prod_code=1), "prod exit 1", "production npm audit is not zero")
            self.fails(site, different_advisory(), capture_for(different_advisory()), "different advisory", "advisory outside the exemption")
            self.fails(site, moderate(), capture_for(moderate()), "moderate severity", "outside the exemption")
            self.fails(site, extra_package(), capture_for(extra_package()), "extra package", "packages outside the exemption")
            self.fails(site, exempt(), capture_for(extra_package()), "capture binds another report", "does not bind the recorded report")
            stale = capture_for(exempt())
            stale["captured_at"] = "2026-11-29"
            self.fails(site, exempt(), stale, "malformed capture time", "invalid npm audit capture time")
            extra_key = dict(capture_for(exempt()), now="2026-11-29T00:00:00Z")
            self.fails(site, exempt(), extra_key, "unknown capture key", "capture record invalid")
            self.fails(site, dict(metadata=dict(vulnerabilities=dict(total=0, low=1))), None, "inconsistent zero", "npm audit missing or vulnerable")


if __name__ == "__main__":
    unittest.main()
