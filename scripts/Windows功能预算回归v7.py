"""Guard the test-only functional budget; actual Windows execution remains a CI gate."""
from pathlib import Path
import hashlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src-tauri/src/tools/exec.rs'
FUNCTION = 'windows_workspace_scripts_and_python_unicode_execute_successfully'


class FunctionalBudgetTests(unittest.TestCase):
    def setUp(self):
        self.source = SOURCE.read_text(encoding='utf-8')
        self.function = self.source.split('fn ' + FUNCTION + '()', 1)[1].split(
            '\n    #[cfg(windows)]', 1)[0]

    def test_production_execution_implementation_is_unchanged(self):
        prefix = self.source.split('#[cfg(test)]\n#[allow(clippy::items_after_test_module)]', 1)[0]
        self.assertEqual(hashlib.sha256(prefix.encode()).hexdigest(),
                         'ebf48f5eb31b5465aae4e1a82704dd00780767bbba61a933a7b8be37e0db2fee')

    def test_functional_budget_and_wait_are_explicit_and_bounded(self):
        self.assertIn('const FUNCTIONAL_BUDGET_MS: u64 = 30_000;', self.function)
        self.assertEqual(self.function.count('"timeout_ms": FUNCTIONAL_BUDGET_MS'), 2)
        self.assertEqual(self.function.count('"yield_time_ms": FUNCTIONAL_BUDGET_MS'), 2)
        self.assertNotIn('10_000', self.function)

    def test_repetition_keeps_all_runners_and_checks_real_results(self):
        for value in ['for round in 1..=5', 'for _ in 0..10', 'any-name.cmd',
                      'any-name.ps1', 'powershell -NoProfile', '中文输出正常 ✅',
                      'output["exit_code"]', 'output["child_process"]',
                      'output["termination_reason"]', '.contains(expected)']:
            self.assertIn(value, self.function)
        self.assertNotIn('#[ignore]', self.function)

    def test_execution_deadline_regression_is_not_weakened(self):
        deadline = (ROOT / 'src-tauri/src/tools/异步命令回归v1.rs').read_text(encoding='utf-8')
        case = deadline.split('fn process_deadline_is_not_an_http_wait_timeout()', 1)[1].split('\n#[test]', 1)[0]
        self.assertIn('time.sleep(10)', case)
        self.assertIn(', 200)', case)
        self.assertIn('"timeout"', case)


if __name__ == '__main__':
    unittest.main(verbosity=2)
