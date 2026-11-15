"""C13c: vendored-deepmerge mitigation path of rc_npm_audit_gate (capture v2, pinned digests, REVIEW_BY)."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rc_npm_audit_gate as module  # noqa: E402
from rc_npm_audit_gate_tests import ADVISORY, capture_for, encode, exempt, mitigated, report, no_clock  # noqa: E402

REPO = SCRIPTS.parent
NOW = datetime(2026, 11, 5, 6, 0, 0, tzinfo=timezone.utc)
DEC1 = datetime(2026, 12, 1, 0, 0, 0, tzinfo=timezone.utc)
REVIEW_DAY = datetime(2027, 2, 28, 23, 59, 59, tzinfo=timezone.utc)
AFTER_REVIEW = datetime(2027, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
SHAPES = dict(npm10=(mitigated, 1), npm11=(lambda: report({}), 0))


def v2(full, captured_at=NOW, mitigation=None, **override):
    data = encode(full)
    record = module.capture_record_v2(data, 1 if full["metadata"]["vulnerabilities"]["total"] else 0, report({}), 0,
                                      captured_at, dict(module.PINNED_MITIGATION) if mitigation is None else mitigation,
                                      "10.9.9", "v22.12.0")
    record.update(override)
    return data, record


class Fixture:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(REPO / name, root / name)
        shutil.copytree(REPO / module.VENDOR_DIR, root / module.VENDOR_DIR, symlinks=True)
        self.root = root
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()

    def edit_json(self, rel, change):
        path = self.root / rel
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value, indent=2) + "\n")

    def vendor(self, rel):
        return self.root / module.VENDOR_DIR / rel


def tamper_cjs(fx):
    path = fx.vendor("dist/cjs.js")
    path.write_bytes(path.read_bytes() + b"\n")


def comodify(fx):  # Grok proto-comodified: change cjs.js and re-hash it inside provenance
    tamper_cjs(fx)
    import hashlib
    digest = hashlib.sha256(fx.vendor("dist/cjs.js").read_bytes()).hexdigest()
    fx.edit_json(f"{module.VENDOR_DIR}/provenance.json", lambda v: v["vendored_files"].__setitem__("dist/cjs.js", digest))


def symlinked_file(fx):
    target = fx.vendor("readme.md")
    data = target.read_bytes()
    target.unlink()
    real = fx.root / "readme-real.md"
    real.write_bytes(data)
    target.symlink_to(real)


def node_modules_dir(fx):
    (fx.root / "node_modules" / "deepmerge").mkdir(parents=True)


def node_modules_wrong_link(fx):
    (fx.root / "node_modules").mkdir()
    other = fx.root / "elsewhere"
    other.mkdir()
    (fx.root / "node_modules" / "deepmerge").symlink_to(other)


TREE_FAULTS = {
    "provenance missing": lambda fx: fx.vendor("provenance.json").unlink(),
    "provenance invalid json": lambda fx: fx.vendor("provenance.json").write_text("{"),
    "cjs one byte": tamper_cjs,
    "cjs and provenance co-modified": comodify,
    "extra dist/umd.js": lambda fx: fx.vendor("dist/umd.js").write_text("x"),
    "extra index.js": lambda fx: fx.vendor("index.js").write_text("x"),
    "PATCHES.md edited": lambda fx: fx.vendor("PATCHES.md").write_text("x"),
    "vendored version 4.3.1": lambda fx: fx.edit_json(f"{module.VENDOR_DIR}/package.json", lambda v: v.update(version="4.3.1")),
    "provenance version": lambda fx: fx.edit_json(f"{module.VENDOR_DIR}/provenance.json", lambda v: v.update(version="4.3.1")),
    "vendored file symlink": symlinked_file,
    "lock registry resolved": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"].__setitem__(
        "node_modules/deepmerge", dict(version="4.3.1", resolved="https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz",
                                       integrity="sha512-x", dev=True))),
    "lock link missing": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"]["node_modules/deepmerge"].pop("link")),
    "lock vendor not dev": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"][module.VENDOR_DIR].pop("dev")),
    "lock vendor peer": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"][module.VENDOR_DIR].update(peer=True)),
    "lock nested copy": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"].__setitem__(
        "node_modules/x/node_modules/deepmerge", dict(version="4.3.1"))),
    "lock alias by name": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"].__setitem__(
        "node_modules/dm-alias", dict(name="deepmerge", version="4.3.1"))),
    "lock alias by resolved": lambda fx: fx.edit_json("package-lock.json", lambda v: v["packages"].__setitem__(
        "node_modules/dm2", dict(version="4.3.1", resolved="https://registry.npmjs.org/deepmerge/-/deepmerge-4.3.1.tgz"))),
    "devDependency ^4.3.1": lambda fx: fx.edit_json("package.json", lambda v: v["devDependencies"].update(deepmerge="^4.3.1")),
    "override missing": lambda fx: fx.edit_json("package.json", lambda v: v["overrides"].pop("deepmerge")),
    "deepmerge in dependencies": lambda fx: fx.edit_json("package.json", lambda v: v.setdefault("dependencies", {}).update(deepmerge="4.3.1")),
    "deepmerge in optionalDependencies": lambda fx: fx.edit_json("package.json", lambda v: v.setdefault("optionalDependencies", {}).update(deepmerge="4.3.1")),
    "deepmerge in peerDependencies": lambda fx: fx.edit_json("package.json", lambda v: v.setdefault("peerDependencies", {}).update(deepmerge="4.3.1")),
    "node_modules/deepmerge real dir": node_modules_dir,
    "node_modules/deepmerge wrong link": node_modules_wrong_link,
}


def report_fault(change):
    value = mitigated()
    change(value)
    return value


def _moderate(v):
    v["vulnerabilities"]["deepmerge"]["via"][0]["severity"] = "moderate"


def _all_moderate(v):
    for item in v["vulnerabilities"].values():
        item["severity"] = "moderate"
    v["metadata"]["vulnerabilities"].update(low=0, moderate=4)


def _fifth(v):
    v["vulnerabilities"]["vite"] = dict(v["vulnerabilities"]["@sveltejs/kit"], name="vite", via=["deepmerge"])
    v["metadata"]["vulnerabilities"].update(low=5, total=5)


REPORT_FAULTS = {
    "range changed": lambda v: v["vulnerabilities"]["deepmerge"]["via"][0].update(range=">=4.2.0 <4.3.2"),
    "second advisory": lambda v: v["vulnerabilities"]["deepmerge"]["via"].append(
        dict(ADVISORY, source=2, url="https://github.com/advisories/GHSA-xxxx-xxxx-xxxx")),
    "via severity moderate": _moderate,
    "all moderate": _all_moderate,
    "nodes missing node_modules": lambda v: v["vulnerabilities"]["deepmerge"].update(nodes=["vendor-js/deepmerge"]),
    "nodes other path": lambda v: v["vulnerabilities"]["deepmerge"].update(nodes=["node_modules/deepmerge", "node_modules/x/node_modules/deepmerge"]),
    "nodes duplicate": lambda v: v["vulnerabilities"]["deepmerge"].update(nodes=["node_modules/deepmerge", "vendor-js/deepmerge", "vendor-js/deepmerge"]),
    "via string on deepmerge": lambda v: v["vulnerabilities"]["deepmerge"].update(via=["@sveltejs/kit"]),
    "dict in chain via": lambda v: v["vulnerabilities"]["@sveltejs/kit"]["via"].append(dict(ADVISORY)),
    "fifth package": _fifth,
    "chain cycle": lambda v: v["vulnerabilities"]["@sveltejs/vite-plugin-svelte"].update(via=["@sveltejs/kit"]),
    # C13d negatives: exact chain nodes + via len==1 (no dedupe)
    "chain nodes evil": lambda v: v["vulnerabilities"]["@sveltejs/kit"].update(nodes=["evil"]),
    "chain nodes duplicate": lambda v: v["vulnerabilities"]["@sveltejs/kit"].update(
        nodes=["node_modules/@sveltejs/kit", "node_modules/@sveltejs/kit"]),
    "deepmerge via duplicate advisory": lambda v: v["vulnerabilities"]["deepmerge"]["via"].append(
        dict(v["vulnerabilities"]["deepmerge"]["via"][0])),
}


class MitigationVerifyTests(unittest.TestCase):
    def test_real_tree_matches_pins(self):
        self.assertEqual(module.verify_vendored_mitigation(REPO), module.PINNED_MITIGATION)
        with Fixture() as fx:
            self.assertEqual(module.verify_vendored_mitigation(fx.root), module.PINNED_MITIGATION)

    def test_valid_node_modules_symlink_accepted(self):
        with Fixture() as fx:
            (fx.root / "node_modules").mkdir()
            os.symlink(Path("..") / module.VENDOR_DIR, fx.root / "node_modules" / "deepmerge")
            module.verify_vendored_mitigation(fx.root)

    def test_tree_faults_fail_for_both_npm_shapes(self):
        for fault, apply in TREE_FAULTS.items():
            for shape, (make, code) in SHAPES.items():
                with self.subTest(fault=fault, shape=shape), Fixture() as fx:
                    apply(fx)
                    with self.assertRaises(module.GateError):
                        module.verify_vendored_mitigation(fx.root)
                    self.assertEqual(run_cli(fx.root, make(), code, NOW), 1)


class MitigatedJudgeTests(unittest.TestCase):
    def test_both_shapes_pass_now_dec1_and_review_day(self):
        for shape, (make, code) in SHAPES.items():
            for clock in (NOW, DEC1, REVIEW_DAY):
                with self.subTest(shape=shape, clock=clock):
                    self.assertTrue(module.check_mitigated(make(), code, clock.date())["mitigated"])
            with self.subTest(shape=shape, clock="review+1"), self.assertRaises(module.GateError):
                module.check_mitigated(make(), code, AFTER_REVIEW.date())

    def test_report_faults_fail(self):
        for fault, change in REPORT_FAULTS.items():
            with self.subTest(fault=fault), self.assertRaises(module.GateError):
                module.check_mitigated(report_fault(change), 1, NOW.date())

    def test_exact_count_and_exit_codes(self):
        value = mitigated()
        del value["vulnerabilities"]["@sveltejs/adapter-static"]
        value["metadata"]["vulnerabilities"].update(low=3, total=3)
        for bad, code in ((value, 1), (mitigated(), 0), (report({}), 1)):
            with self.assertRaises(module.GateError):
                module.check_mitigated(bad, code, NOW.date())

    def test_v1_exempt_shape_without_vendor_nodes_fails(self):
        with self.assertRaises(module.GateError):
            module.check_mitigated(exempt(), 1, NOW.date())


def run_cli(repo, full, code, clock, prod=None, prod_code=0, extra=(), capture=True):
    with tempfile.TemporaryDirectory() as directory:
        full_path, prod_path = Path(directory, "npm-audit.json"), Path(directory, "prod.json")
        full_path.write_bytes(encode(full))
        prod_path.write_text(json.dumps(report({}) if prod is None else prod))
        args = ["--repo", str(repo), "--full", str(full_path), "--full-exit-code", str(code),
                "--prod", str(prod_path), "--prod-exit-code", str(prod_code), *extra]
        if not any(a == "--npm-version" for a in extra):
            args += ["--npm-version", "10.9.9"]
        if not any(a == "--node-version" for a in extra):
            args += ["--node-version", "v22.12.0"]
        if not capture:
            args.append("--no-capture")
        with patch.object(module, "utc_now", return_value=clock):
            result = module.main(args)
        record = Path(directory, module.CAPTURE_NAME)
        if result == 0 and capture:
            data = json.loads(record.read_text())
            assert data["schema"] == module.CAPTURE_SCHEMA_V2, data
            assert module.check_recorded(full, full_path.read_bytes(), data)["mitigated"] is True
        assert result == 0 or not record.exists()
        assert capture or not record.exists()
        return result


class MitigationCliTests(unittest.TestCase):
    def test_cli_both_shapes_now_dec1_review(self):
        for shape, (make, code) in SHAPES.items():
            for clock, expect in ((NOW, 0), (DEC1, 0), (REVIEW_DAY, 0), (AFTER_REVIEW, 1)):
                with self.subTest(shape=shape, clock=clock):
                    self.assertEqual(run_cli(REPO, make(), code, clock), expect)

    def test_cli_no_capture(self):
        self.assertEqual(run_cli(REPO, mitigated(), 1, NOW, capture=False), 0)

    def test_cli_prod_must_be_strict_zero(self):
        self.assertEqual(run_cli(REPO, mitigated(), 1, NOW, prod=mitigated(), prod_code=1), 1)
        self.assertEqual(run_cli(REPO, mitigated(), 1, NOW, prod=report({}), prod_code=1), 1)

    def test_cli_requires_tool_versions(self):
        for flag in ("--npm-version", "--node-version"):
            with self.subTest(flag=flag):
                self.assertEqual(run_cli(REPO, mitigated(), 1, NOW, extra=(flag, "")), 1)

    def test_verify_only(self):
        with patch.object(module, "utc_now", return_value=NOW):
            self.assertEqual(module.main(["--verify-only", "--repo", str(REPO)]), 0)
        with patch.object(module, "utc_now", return_value=AFTER_REVIEW):
            self.assertEqual(module.main(["--verify-only", "--repo", str(REPO)]), 1)
        with Fixture() as fx, patch.object(module, "utc_now", return_value=NOW):
            tamper_cjs(fx)
            self.assertEqual(module.main(["--verify-only", "--repo", str(fx.root)]), 1)

    def test_zero_report_still_runs_verify(self):
        with Fixture() as fx:
            tamper_cjs(fx)
            self.assertEqual(run_cli(fx.root, report({}), 0, NOW), 1)

    def test_removal_hint_npm10_zero_only(self):
        import io
        for full, code, npm, expect in ((report({}), 0, "10.9.9", True), (report({}), 0, "11.6.2", False),
                                        (mitigated(), 1, "10.9.9", False)):
            with self.subTest(npm=npm, total=full["metadata"]["vulnerabilities"]["total"]), \
                    patch("sys.stderr", new_callable=io.StringIO) as err:
                self.assertEqual(run_cli(REPO, full, code, NOW, extra=("--npm-version", npm)), 0)
                self.assertEqual(module.REMOVAL_HINT in err.getvalue(), expect)


class RecordedV2Tests(unittest.TestCase):
    def test_v2_pass_and_review_by_by_capture_time(self):
        for shape, (make, _code) in SHAPES.items():
            for clock, ok in ((NOW, True), (DEC1, True), (REVIEW_DAY, True), (AFTER_REVIEW, False)):
                with self.subTest(shape=shape, clock=clock), patch.object(module, "utc_now", side_effect=no_clock):
                    data, record = v2(make(), captured_at=clock)
                    if ok:
                        self.assertTrue(module.check_recorded(make(), data, record)["mitigated"])
                    else:
                        with self.assertRaises(module.GateError):
                            module.check_recorded(make(), data, record)

    def test_v2_record_faults(self):
        full = mitigated()
        data, good = v2(full)
        forged = dict(good["mitigation"], cjs_sha256="0" * 64)
        cases = {
            "self-consistent forged digests": dict(good, mitigation=forged),
            "mitigation missing key": dict(good, mitigation={k: v for k, v in good["mitigation"].items() if k != "tree_sha256"}),
            "npm_version empty": dict(good, npm_version=""),
            "node_version not str": dict(good, node_version=None),
            "prod not zero": dict(good, prod_report=mitigated(), prod_exit_code=1),
            "wrong full sha": dict(good, full_sha256="0" * 64),
        }
        missing = dict(good)
        del missing["npm_version"]
        cases["npm_version missing"] = missing
        for name, record in cases.items():
            with self.subTest(case=name), self.assertRaises(module.GateError):
                module.check_recorded(full, data, record)
        with self.assertRaises(module.GateError):
            module.capture_record_v2(data, 1, report({}), 0, NOW, forged, "10.9.9", "v22")
        with self.assertRaises(module.GateError):
            module.check_recorded(report_fault(REPORT_FAULTS["range changed"]), encode(report_fault(REPORT_FAULTS["range changed"])),
                                  v2(report_fault(REPORT_FAULTS["range changed"]))[1])

    def test_v1_history_unchanged(self):
        # C13d: v1 with findings refused; all-zero v1 and no-capture unchanged; schema kept.
        before = capture_for(exempt())
        with self.assertRaises(module.GateError):
            module.check_recorded(exempt(), encode(exempt()), before)
        after = capture_for(exempt(), captured_at=DEC1)
        with self.assertRaises(module.GateError):
            module.check_recorded(exempt(), encode(exempt()), after)
        zero = report({})
        self.assertEqual(module.check_recorded(zero, encode(zero), capture_for(zero))["total"], 0)
        self.assertEqual(module.check_recorded(zero, encode(zero), None)["total"], 0)
        self.assertEqual(module.EXEMPTION_EXPIRES, date(2026, 11, 30))
        self.assertEqual(module.CAPTURE_SCHEMA, "rc-npm-audit-capture-v1")

    def test_c13d_chain_nodes_and_via_len_negatives(self):
        for fault in ("chain nodes evil", "chain nodes duplicate", "deepmerge via duplicate advisory"):
            with self.subTest(fault=fault), self.assertRaises(module.GateError):
                module.check_mitigated(report_fault(REPORT_FAULTS[fault]), 1, NOW.date())


LAST_V1_SECOND = datetime(2026, 11, 30, 23, 59, 59, tzinfo=timezone.utc)
DEC1_LATE = datetime(2026, 12, 1, 23, 59, 59, tzinfo=timezone.utc)


def no_v1_judge(*_args, **_kwargs):
    raise AssertionError("live gate must not reach the v1 check_findings / EXEMPTION_EXPIRES path")


class ClockPinnedDec1Tests(unittest.TestCase):
    """C41: the v1 exemption ends 2026-11-30; the live gate is governed by MITIGATION_REVIEW_BY only."""

    def test_dates_are_unchanged(self):
        self.assertEqual(module.EXEMPTION_EXPIRES, date(2026, 11, 30))
        self.assertEqual(module.MITIGATION_REVIEW_BY, date(2027, 2, 28))

    def test_live_verify_only_passes_with_clock_pinned_to_dec1(self):
        import io
        for clock in (DEC1, DEC1_LATE):
            with self.subTest(clock=clock), patch.object(module, "utc_now", return_value=clock), \
                    patch.object(module, "check_findings", side_effect=no_v1_judge), \
                    patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(module.main(["--verify-only", "--repo", str(REPO)]), 0)
                result = json.loads(out.getvalue())
                self.assertEqual((result["passed"], result["verify_only"], result["review_by"]),
                                 (True, True, "2027-02-28"))

    def test_live_mitigated_cli_passes_with_clock_pinned_to_dec1(self):
        for shape, (make, code) in SHAPES.items():
            for clock in (DEC1, DEC1_LATE):
                for capture in (False, True):  # --no-capture (vendor guard) and capture v2 (packaging)
                    with self.subTest(shape=shape, clock=clock, capture=capture), \
                            patch.object(module, "check_findings", side_effect=no_v1_judge):
                        self.assertEqual(run_cli(REPO, make(), code, clock, capture=capture), 0)

    def test_v1_nonzero_capture_after_nov30_is_rejected(self):
        for captured_at in (DEC1, DEC1_LATE, datetime(2027, 1, 15, tzinfo=timezone.utc)):
            with self.subTest(captured_at=captured_at), patch.object(module, "utc_now", side_effect=no_clock), \
                    self.assertRaises(module.GateError):
                module.check_recorded(exempt(), encode(exempt()), capture_for(exempt(), captured_at=captured_at))
        # The v1 judge itself also voids the exemption from 2026-12-01 (by the date it is given).
        with self.assertRaisesRegex(module.GateError, "expired after 2026-11-30"):
            module.check_full(exempt(), 1, DEC1.date())

    def test_v1_historical_records_on_or_before_nov30_still_pass(self):
        # Judged by the recorded capture time, never the (Dec 1) clock: no_clock proves it is not read.
        zero = report({})
        for captured_at in (datetime(2026, 10, 28, 7, 0, 1, tzinfo=timezone.utc), LAST_V1_SECOND):
            with self.subTest(captured_at=captured_at), patch.object(module, "utc_now", side_effect=no_clock):
                result = module.check_recorded(zero, encode(zero), capture_for(zero, captured_at=captured_at))
                self.assertEqual(result["captured_at"], captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"))
                self.assertEqual(result["total"], 0)
        with patch.object(module, "utc_now", side_effect=no_clock):
            self.assertEqual(module.check_recorded(zero, encode(zero), None)["total"], 0)
        # The v1 judge still accepts the exact exemption on its last valid day.
        self.assertEqual(module.check_full(exempt(), 1, LAST_V1_SECOND.date())["expires"], "2026-11-30")
        # C13d (unchanged): a v1 capture with findings is refused even on or before 2026-11-30.
        with patch.object(module, "utc_now", side_effect=no_clock), self.assertRaises(module.GateError):
            module.check_recorded(exempt(), encode(exempt()), capture_for(exempt(), captured_at=LAST_V1_SECOND))


if __name__ == "__main__":
    unittest.main()
