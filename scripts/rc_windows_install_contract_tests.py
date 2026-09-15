"""Contract tests for the RC-only Windows installed acceptance boundary."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rc_windows_install.ps1"


class RcWindowsInstallContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_never_reads_or_deletes_runneradmin_application_state(self) -> None:
        for forbidden in (
            "GetFolderPath('ApplicationData')",
            'GetFolderPath("ApplicationData")',
            "$configRoot",
            "Remove-Item",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_application_runs_only_through_owned_standard_user_fixture(self) -> None:
        smoke = self.text.index("Windows启动对照v17.py")
        native = self.text.index("Windows标准用户验收v22.py --scenario exclusive")
        gate = self.text.index("scripts/rc_native_gate.py")
        self.assertLess(smoke, native)
        self.assertLess(native, gate)
        self.assertIn("--kind nsis", self.text)
        self.assertNotIn("--fixture-root", self.text)

    def test_rc_gate_remains_non_publishing(self) -> None:
        self.assertIn("release_candidate=$true", self.text)
        self.assertIn("publish_approved=$false", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
