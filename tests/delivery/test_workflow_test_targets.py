import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('workflow_test_targets', ROOT / 'tools/delivery/workflow_test_targets.py')
targets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(targets)


def repo(tmp, workflow, files=('svc/tests/real.rs',), cargo='[package]\nname = "svc"\n'):
    root = Path(tmp)
    (root / '.github/workflows').mkdir(parents=True)
    (root / '.github/workflows/ci.yml').write_text(workflow, encoding='utf-8')
    (root / 'svc').mkdir()
    (root / 'svc/Cargo.toml').write_text(cargo, encoding='utf-8')
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('', encoding='utf-8')
    return root


class WorkflowTestTargetTests(unittest.TestCase):
    def test_existing_target_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, 'run: cargo test --locked --manifest-path svc/Cargo.toml --lib --test real 2>&1 | tee x\n')
            self.assertEqual(targets.check(root), [])

    def test_missing_target_fails_with_location(self):
        # the v0.7.0 cloud-execution-bridge shape: `--test service_cli` with only service_contracts.rs
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, 'a: 1\nrun: cargo test --manifest-path svc/Cargo.toml --lib --test service_cli | tee x\n',
                        files=('svc/tests/service_contracts.rs',))
            problems = targets.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn('ci.yml:2', problems[0])
            self.assertIn('service_cli', problems[0])
            self.assertEqual(targets.main(['--root', str(root)]), 1)

    def test_target_in_other_crate_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, 'run: cargo test --manifest-path svc/Cargo.toml --test other\n',
                        files=('svc/tests/real.rs', 'other/tests/other.rs'))
            (root / 'other/Cargo.toml').write_text('[package]\nname = "other"\n', encoding='utf-8')
            self.assertEqual(len(targets.check(root)), 1)

    def test_main_rs_dir_cargo_test_section_continuation_and_equals_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow = ('run: |\n  cargo test --manifest-path=svc/Cargo.toml \\\n'
                        '    --test dir_suite --test=declared --test real\n')
            root = repo(tmp, workflow, files=('svc/tests/real.rs', 'svc/tests/dir_suite/main.rs'),
                        cargo='[package]\nname = "svc"\n[[test]]\nname = "declared"\npath = "t/d.rs"\n')
            self.assertEqual(targets.check(root), [])

    def test_libtest_args_and_node_test_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow = ('run: cargo test --manifest-path svc/Cargo.toml --test real -- --test-threads=1 --test nope\n'
                        'run: node --test tests/x.test.mjs\n')
            self.assertEqual(targets.check(repo(tmp, workflow)), [])

    def test_missing_manifest_and_unscoped_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            workflow = ('run: cargo test --manifest-path gone/Cargo.toml --test real\n'
                        'run: cargo test --test real\nrun: cargo test --test absent\n')
            problems = targets.check(repo(tmp, workflow))
            self.assertEqual(len(problems), 2)
            self.assertIn('gone/Cargo.toml does not exist', problems[0])
            self.assertIn('absent', problems[1])

    def test_repository_workflows_resolve_and_bridge_runs_the_check(self):
        self.assertEqual(targets.check(ROOT), [])
        source = (ROOT / '.github/workflows/cloud-execution-bridge.yml').read_text(encoding='utf-8')
        self.assertIn('python tools/delivery/workflow_test_targets.py\n', source)
        self.assertNotIn('--test service_cli', source)
        self.assertIn('--manifest-path services/cloud-gateway/Cargo.toml --lib 2>&1 | tee evidence/portable.txt', source)


if __name__ == '__main__':
    unittest.main()
