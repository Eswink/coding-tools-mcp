"""Pure and actual Git evidence contracts; no network or token."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/delivery/dispatch.py"
spec = importlib.util.spec_from_file_location("delivery", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def task(key, **kwargs):
    return {"id": key, "issue": None, "title": "Test task", "lane": "agent-client", "state": "planned",
            "priority": 10, "depends_on": [], "paths": ["services/test"], "release_required": True, **kwargs}


def manifest(tasks):
    return {"version": 1, "repository": m.REPO, "integration_branch": m.BRANCH, "tasks": tasks,
            "release_gates": {g: "pending" for g in m.GATES}}


def verified(key, **kwargs):
    return task(key, state="verified", evidence={"revision": "a" * 40, "run_id": 1,
                "files": {"services/test/f.rs": "b" * 64}}, **kwargs)


class DispatchTests(unittest.TestCase):
    def result(self, tasks, checker=lambda *_: True, limit=3):
        return m.plan(manifest(tasks), Path.cwd(), limit, checker)

    def test_ready_packet_is_not_a_worker(self):
        r = self.result([task("agent-one", issue=47)])
        self.assertEqual(r["packets"][0]["action"], "queue_issue")
        self.assertFalse(r["packets"][0]["execution_started"])
        self.assertFalse(r["release_allowed"])

    def test_missing_issue_requests_creation_not_fake_number(self):
        self.assertEqual(self.result([task("agent-one")])["packets"][0]["action"], "create_issue")

    def test_dependency_order(self):
        r = self.result([verified("agent-one"), task("next-step", depends_on=["agent-one"])])
        self.assertEqual([p["id"] for p in r["packets"]], ["next-step"])

    def test_incomplete_dependency_not_ready(self):
        r = self.result([task("agent-one", state="blocked", reason="awaiting review"), task("next-step", depends_on=["agent-one"])])
        self.assertFalse(r["packets"])

    def test_source_staleness_propagates(self):
        r = self.result([verified("agent-one"), verified("next-step", depends_on=["agent-one"]), task("third-step", depends_on=["next-step"])], lambda *_: False)
        self.assertFalse(r["packets"])
        self.assertEqual(r["states"]["agent-one"], "stale_evidence")

    def test_active_resource_reserves_children(self):
        r = self.result([task("active-job", state="in_progress"), task("new-job", lane="packaging", paths=["services/test/new"])])
        self.assertFalse(r["packets"])

    def test_prefix_not_false_overlap(self):
        r = self.result([task("active-job", state="in_progress"), task("new-job", lane="packaging", paths=["services/testing"])])
        self.assertEqual(len(r["packets"]), 1)

    def test_one_packet_per_lane(self):
        self.assertEqual(len(self.result([task("aa"), task("bb", paths=["other"])])["packets"]), 1)

    def test_active_conflict_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", state="in_progress"), task("bb", state="in_progress", lane="packaging")])

    def test_order_is_stable(self):
        a, b = task("aa"), task("bb", lane="packaging", paths=["other"])
        self.assertEqual(self.result([a, b]), self.result([b, a]))

    def test_batch_limit(self):
        r = self.result([task("aa"), task("bb", lane="packaging", paths=["other"])], limit=1)
        self.assertEqual(len(r["packets"]), 1)

    def test_deferred_host_never_passes_release(self):
        d = manifest([verified("aa")])
        d["release_gates"] = {g: "pass" for g in m.GATES}
        d["release_gates"]["real-chatgpt"] = "deferred"
        r = m.plan(d, Path.cwd(), source_check=lambda *_: True)
        self.assertIn("gate:real-chatgpt", r["release_blockers"])
        self.assertFalse(r["release_eligible_for_review"])

    def test_all_verified_is_only_review_not_publish(self):
        d = manifest([verified("aa")])
        d["release_gates"] = {g: "pass" for g in m.GATES}
        r = m.plan(d, Path.cwd(), source_check=lambda *_: True)
        self.assertTrue(r["release_eligible_for_review"])
        self.assertFalse(r["release_allowed"])

    def test_cycle_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", depends_on=["bb"]), task("bb", depends_on=["aa"])])

    def test_missing_dependency_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", depends_on=["missing"])])

    def test_duplicate_id_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa"), task("aa")])

    def test_duplicate_issue_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", issue=47), task("bb", issue=47)])

    def test_boolean_issue_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", issue=True)])

    def test_missing_evidence_rejected(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", state="verified")])

    def test_unknown_fields_not_commands(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", command="run arbitrary code")])

    def test_missing_gate_rejected(self):
        d = manifest([task("aa")]); del d["release_gates"]["security-review"]
        with self.assertRaises(m.InvalidManifest):
            m.validate(d)

    def test_unsafe_paths(self):
        for p in ["../outside", "/etc", "a/../b", "a//b", "a\\b", "a/.git", "a\nfoo", "C:/foo"]:
            with self.subTest(path=p), self.assertRaises(m.InvalidManifest):
                self.result([task("aa", paths=[p])])

    def test_blocked_requires_reason(self):
        with self.assertRaises(m.InvalidManifest):
            self.result([task("aa", state="blocked")])

    def test_wrong_repo_rejected(self):
        d = manifest([task("aa")]); d["repository"] = "another/repo"
        with self.assertRaises(m.InvalidManifest):
            m.validate(d)

    def test_actual_git_source_and_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            subprocess.run(["git", "init", "-q", root], check=True)
            f = root / "services/test/f.rs"; f.parent.mkdir(parents=True); f.write_bytes(b"verified source\n")
            subprocess.run(["git", "-C", root, "add", "."], check=True)
            subprocess.run(["git", "-C", root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
            sha = m.git(root, "rev-parse", "HEAD").decode().strip()
            evidence = {"revision": sha, "run_id": 1, "files": {"services/test/f.rs": hashlib.sha256(f.read_bytes()).hexdigest()}}
            self.assertTrue(m.verify_sources(root, evidence))
            f.write_bytes(b"changed source\n")
            self.assertFalse(m.verify_sources(root, evidence))
            evidence["files"]["services/test/f.rs"] = hashlib.sha256(f.read_bytes()).hexdigest()
            self.assertFalse(m.verify_sources(root, evidence))


if __name__ == "__main__":
    unittest.main()
