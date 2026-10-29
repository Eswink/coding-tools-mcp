import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('cargo_test_floor', ROOT / 'tools/delivery/cargo_test_floor.py')
floor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(floor)


def line(passed, failed=0, ignored=0, status='ok'):
    return (f'test result: {status}. {passed} passed; {failed} failed; {ignored} ignored; '
            '0 measured; 0 filtered out; finished in 1.00s\n')


class CargoTestFloorTests(unittest.TestCase):
    def test_growth_above_floor_passes(self):
        self.assertTrue(floor.check(line(142) + line(0), 88)[0])

    def test_total_below_floor_fails(self):
        ok, detail = floor.check(line(87) + line(0), 88)
        self.assertFalse(ok)
        self.assertIn('floor 88', detail)

    def test_no_summary_fails(self):
        self.assertFalse(floor.check('error[E0425]: cannot find value\n', 1)[0])

    def test_zero_selected_fails(self):
        self.assertFalse(floor.check(line(0), 13)[0])

    def test_any_failed_or_ignored_or_failed_status_fails(self):
        self.assertFalse(floor.check(line(142) + line(3, failed=1), 88)[0])
        self.assertFalse(floor.check(line(142, ignored=1), 88)[0])
        self.assertFalse(floor.check(line(142, status='FAILED'), 88)[0])

    def test_cli_exit_codes_and_floor_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'out.txt'
            log.write_text(line(16), encoding='utf-8')
            self.assertEqual(floor.main([str(log), '--min', '9']), 0)
            self.assertEqual(floor.main([str(log), '--min', '17']), 1)
            with self.assertRaises(SystemExit):
                floor.main([str(log), '--min', '0'])

    def test_workflow_uses_floors_not_exact_counts(self):
        source = (ROOT / '.github/workflows/cloud-execution-bridge.yml').read_text(encoding='utf-8')
        self.assertNotRegex(source, r"grep -F '\d+ passed")
        # portable has setup-python (`python`); postgres uses the system python3.
        for py, log, minimum in [('python', 'agent-full', 88), ('python', 'execution-unit', 13),
                                 ('python3', 'linearization', 3), ('python3', 'execution-postgres', 13),
                                 ('python3', 'managed-agent-wss', 5), ('python3', 'native-wss', 9)]:
            self.assertIn(f'{py} tools/delivery/cargo_test_floor.py evidence/{log}.txt --min {minimum}', source)


if __name__ == '__main__':
    unittest.main()
