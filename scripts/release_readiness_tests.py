"""Failure-first contracts for complete TAP evidence and version-matched guides."""
import importlib
from pathlib import Path
import tempfile
import unittest

m = importlib.import_module("聊天授权发布v26")
fixtures = importlib.import_module("聊天授权发布回归v26")
ROOT = Path(__file__).resolve().parents[1]


def tap(count=3):
    return "TAP version 13\n" + "".join(f"ok {i} - fixture {i}\n" for i in range(1, count + 1)) + (
        f"1..{count}\n# tests {count}\n# suites 0\n# pass {count}\n"
        "# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 1.0\n")


class ReleaseReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.guide = fixtures.fixture(self.root)
        self.front = self.root / "聊天授权前端-ubuntu-latest-v4/前端回归v4.txt"

    def tearDown(self):
        self.temporary.cleanup()

    def rejected(self, source):
        self.front.write_text(source, encoding="utf-8")
        with self.assertRaises(ValueError):
            m.baseline(self.root, fixtures.SOURCE)

    def test_fail_zero_alone_is_not_evidence(self):
        self.rejected("# fail 0\n")

    def test_zero_tests_are_not_evidence(self):
        self.rejected(tap(0))

    def test_missing_or_duplicate_summaries_are_rejected(self):
        for source in (tap().replace("# pass 3\n", ""), tap() + "# pass 3\n"):
            self.rejected(source)

    def test_nonzero_cancel_skip_and_todo_are_rejected(self):
        for name in ("cancelled", "skipped", "todo"):
            self.rejected(tap().replace(f"# {name} 0", f"# {name} 1"))

    def test_counts_and_plan_must_match_real_result_lines(self):
        for source in (tap().replace("# pass 3", "# pass 2"), tap().replace("1..3", "1..4"),
                       tap().replace("ok 2 - fixture 2\n", "")):
            self.rejected(source)

    def test_huge_plan_is_rejected_without_allocating_reported_size(self):
        self.rejected(tap().replace("1..3", "1..999999999999999999"))

    def test_skip_directives_and_nested_failures_are_rejected(self):
        self.rejected(tap().replace("ok 2 - fixture 2", "ok 2 - fixture 2 # SKIP disabled"))
        self.rejected(tap() + "    not ok 1 - nested failure\n")

    def test_complete_flat_report_is_accepted(self):
        self.front.write_text(tap(), encoding="utf-8")
        result = m.baseline(self.root, fixtures.SOURCE)
        self.assertEqual(result["ubuntu-latest"]["frontend_test_count"], 3)

    def test_complete_nested_suite_is_accepted(self):
        report = ("TAP version 13\n    ok 1 - child A\n    ok 2 - child B\n"
                  "    1..2\nok 1 - suite\n1..1\n# tests 2\n# suites 1\n# pass 2\n"
                  "# fail 0\n# cancelled 0\n# skipped 0\n# todo 0\n# duration_ms 1.0\n")
        self.front.write_text(report, encoding="utf-8")
        self.assertEqual(m.baseline(self.root, fixtures.SOURCE)["ubuntu-latest"]["frontend_test_count"], 2)

    def test_english_guide_is_preferred_only_for_exact_version(self):
        folder = self.root / "docs/releases"; folder.mkdir(parents=True)
        english = folder / "verification-v0.3.2.md"; english.write_text("English-named exact-version guide.")
        (folder / "聊天授权安装与本地核验v0.3.2.md").write_text("Historical naming.")
        self.assertEqual(m.release_guide(self.root, "0.3.2"), english)

    def test_historical_same_version_name_remains_supported(self):
        folder = self.root / "docs/releases"; folder.mkdir(parents=True)
        legacy = folder / "聊天授权安装与本地核验v0.3.1.md"; legacy.write_text("Exact historical version.")
        self.assertEqual(m.release_guide(self.root, "0.3.1"), legacy)
        with self.assertRaises(ValueError): m.release_guide(self.root, "0.3.2")

    def test_empty_guide_and_invalid_version_fail_closed(self):
        folder = self.root / "docs/releases"; folder.mkdir(parents=True)
        (folder / "verification-v0.3.2.md").write_text("   ")
        for version in ("0.3.2", "../0.3.1", "03.2.1"):
            with self.assertRaises(ValueError): m.release_guide(self.root, version)

    def test_actual_candidate_guide_exists_before_build(self):
        version = importlib.import_module("发布版本校验v4").project_versions(ROOT)[0]
        guide = m.release_guide(ROOT, version)
        self.assertIn(version, guide.name)
        for name in ("oauth-native-acceptance.yml", "聊天授权发布v26.yml"):
            source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("python scripts/release_preflight.py", source)
            self.assertIn("python scripts/release_readiness_tests.py", source)


if __name__ == "__main__":
    unittest.main()
