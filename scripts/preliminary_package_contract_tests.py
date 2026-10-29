"""Engineering evidence may proceed independently; failed required tests stay failed."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def workflow(platform):
    return (ROOT / f'.github/workflows/{platform}-rc-packages.yml').read_text()


def step(text, identity):
    blocks = re.split(r'(?m)^      - ', text)[1:]
    matches = [block for block in blocks if f'        id: {identity}\n' in block]
    if len(matches) != 1:
        raise AssertionError(f'exactly one step required: {identity}')
    return matches[0]


class EngineeringContracts(unittest.TestCase):
    def test_required_regression_cannot_be_suppressed(self):
        for platform in ('linux', 'windows'):
            text = workflow(platform)
            self.assertNotIn('continue-on-error', text)
            regression = step(text, 'regression')
            self.assertIn('cargo test --no-fail-fast --manifest-path src-tauri/Cargo.toml --locked', regression)
            self.assertNotIn('        if:', regression)
            self.assertNotIn('|| true', regression)
            if platform == 'windows':
                self.assertIn("throw 'Windows Rust regression failed'", regression)
            else:
                self.assertIn('set -euo pipefail', regression)
                self.assertIn('dbus-run-session -- bash -euo pipefail', regression)

    def test_diagnostic_build_requires_real_prerequisite_success(self):
        for platform in ('linux', 'windows'):
            text = workflow(platform)
            prerequisites = step(text, 'prerequisites')
            self.assertIn('rc_version_gate.py --expect-version', prerequisites)
            self.assertIn('npm run check', prerequisites)
            build = step(text, 'package_build')
            self.assertIn("if: always() && steps.prerequisites.outcome == 'success'", build)
            self.assertNotIn('steps.regression', build)
            if platform == 'linux':
                import linux_package_provenance_contract as provenance
                self.assertIn('desktop_glib_build_evidence.py collect-linux', build)
                self.assertEqual(provenance.tauri_command('/source'), ['npm', 'run', 'tauri', '--',
                    '--verbose', 'build', '--config', 'src-tauri/Ubuntu桌面v1.json', '--bundles',
                    'deb,appimage', '--target', 'x86_64-unknown-linux-gnu', '--runner',
                    str(Path('/source') / 'scripts' / 'desktop_glib_build_evidence.py'), '--', '--locked', '--message-format=json'])
            else:
                self.assertIn('npm run tauri -- build', build)
            self.assertIn('git diff --exit-code', build)

    def test_failed_build_cannot_feed_native_installation(self):
        windows = workflow('windows')
        self.assertIn("if: always() && steps.package_build.outcome == 'success' && steps.driver.outcome == 'success'", windows)
        self.assertIn("if: always() && steps.build_receipt.outcome == 'success'", windows)
        linux = workflow('linux')
        self.assertIn("packages_ready: ${{ steps.package_upload.outcome == 'success' && steps.driver_upload.outcome == 'success' }}", linux)
        self.assertIn("if: always() && needs.build.outputs.packages_ready == 'true'", linux)
        self.assertIn("if: always() && steps.package_build.outcome == 'success'", step(linux, 'package_upload'))
        self.assertIn("if: always() && steps.driver.outcome == 'success'", step(linux, 'driver_upload'))

    def test_raw_builds_are_never_accepted_or_publishable(self):
        for platform in ('linux', 'windows'):
            text = workflow(platform)
            self.assertIn('NOT_FINAL-NOT_PUBLISHABLE', text)
            self.assertIn("native_acceptance='NOT_EXECUTED'", text)
            self.assertIn('accepted=$false' if platform == 'windows' else 'accepted=False', text)
            self.assertIn('publish_approved=$false' if platform == 'windows' else 'publish_approved=False', text)
            self.assertIn("'ci/preliminary-packages-*'", text)
            self.assertNotIn('release/full-rc-candidate-', text)
            self.assertIn('rc_native_gate.py' if platform == 'linux' else 'rc_windows_install.ps1', text)

    def test_linux_regression_has_private_secret_service_and_system_python(self):
        text = workflow('linux')
        regression = step(text, 'regression')
        self.assertIn('export PATH="/usr/bin:$PATH"', regression)
        self.assertIn('gnome-keyring-daemon --unlock --components=secrets', regression)
        self.assertIn('chmod 700 "$XDG_RUNTIME_DIR"', regression)
        self.assertIn('PATH="/usr/bin:/bin:$PATH" exec xvfb-run', text)
        parser = text.index("with environment({'PATH':'/usr/bin:/bin', 'LANG':'C', 'LC_ALL':'C'}):")
        self.assertLess(text.index('sudo apt-get install -y build-essential'), parser)
        self.assertLess(parser, text.index('name: Required source and frontend prerequisites'))
        self.assertLess(parser, text.index('id: regression'))
        self.assertEqual(text.count('print(json.dumps(parser_identity(), sort_keys=True))'), 1)


if __name__ == '__main__':
    unittest.main()
