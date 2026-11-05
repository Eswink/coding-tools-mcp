"""Gateway lock must not retain unused sqlx-mysql / rsa (RUSTSEC-2023-0071).

Complements exact_build_audit / release_dependency_contract (which keep raw
findings visible and forbid --ignore). This suite asserts the packaging #85
gateway half: after B1 path-patch of sqlx / sqlx-macros-core, the lock text
itself omits rsa and sqlx-mysql. Does not claim Windows PASS/QUALIFIED/FINAL.
Does not close whole #85.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_LOCK = ROOT / 'services' / 'cloud-gateway' / 'Cargo.lock'
GATEWAY_TOML = ROOT / 'services' / 'cloud-gateway' / 'Cargo.toml'
WORKFLOWS = (
    ROOT / '.github' / 'workflows' / 'final-rc-packages.yml',
    ROOT / '.github' / 'workflows' / 'full-rc-cloud-binaries.yml',
    ROOT / '.github' / 'workflows' / 'issue85-exact-build-audit.yml',
)
SCRIPTS = (
    ROOT / 'scripts' / 'exact_build_audit.py',
    ROOT / 'scripts' / 'release_dependency_contract.py',
    ROOT / 'scripts' / 'release_dependency_capture.py',
)


def package_names(lock_text: str) -> set[str]:
    return set(re.findall(r'(?m)^name = "([^"]+)"$', lock_text))


class GatewayRsaAbsentLockTests(unittest.TestCase):
    def test_gateway_lock_omits_rsa_and_sqlx_mysql(self):
        text = GATEWAY_LOCK.read_text(encoding='utf-8')
        names = package_names(text)
        self.assertNotIn('rsa', names)
        self.assertNotIn('sqlx-mysql', names)
        self.assertNotIn('sqlx-sqlite', names)
        # still expect postgres path present
        self.assertIn('sqlx', names)
        self.assertIn('sqlx-postgres', names)

    def test_gateway_toml_stays_postgres_only_and_patches_sqlx(self):
        text = GATEWAY_TOML.read_text(encoding='utf-8')
        self.assertIn('postgres', text)
        self.assertNotRegex(text, r'features\s*=\s*\[[^\]]*mysql')
        self.assertIn('[patch.crates-io]', text)
        self.assertIn('patches/sqlx-0.8.6/crate', text)
        self.assertIn('patches/sqlx-macros-core-0.8.6/crate', text)

    def test_workflows_and_scripts_forbid_ignore_2023_0071(self):
        needle = '--ignore'
        advisory = 'RUSTSEC-2023-0071'
        for path in WORKFLOWS + SCRIPTS:
            with self.subTest(path=str(path.relative_to(ROOT))):
                text = path.read_text(encoding='utf-8')
                self.assertNotIn(needle, text)
                # scripts may mention the advisory id in comments/tests elsewhere;
                # workflows must not pair ignore with this id.
                if path in WORKFLOWS:
                    self.assertNotIn(f'{needle} {advisory}', text)
                    self.assertNotIn(f'{needle}={advisory}', text)

    def test_cargo_tree_reports_rsa_absent(self):
        # SHOULD: tree cannot resolve rsa after clear-lock (exit 101, no package).
        proc = subprocess.run(
            ['cargo', 'tree', '-i', 'rsa', '--locked'],
            cwd=GATEWAY_LOCK.parent,
            capture_output=True,
            text=True,
            timeout=120,
        )
        combined = (proc.stdout or '') + (proc.stderr or '')
        self.assertNotEqual(proc.returncode, 0, msg=combined)
        self.assertIn('did not match any packages', combined)


if __name__ == '__main__':
    unittest.main()
