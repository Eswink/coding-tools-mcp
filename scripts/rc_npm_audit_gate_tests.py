from __future__ import annotations

import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).with_name("rc_npm_audit_gate.py")
spec = importlib.util.spec_from_file_location("rc_npm_audit_gate", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)

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


if __name__ == "__main__":
    unittest.main()
