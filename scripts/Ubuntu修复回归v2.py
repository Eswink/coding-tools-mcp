"""Offline repair regressions. Native desktop and Rust proof remain separate CI gates."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import zipfile
import Ubuntu原生验收v1 as native
import Ubuntu发布v1 as release
import Ubuntu发布回归v1 as fixtures


class UbuntuRepairTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.UbuntuReleaseTests("test_valid_package_digests")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def archive(self):
        f = self.fixture
        return release.compose(f.packages, f.evidence, f.output, fixtures.SOURCE, fixtures.ROOT)[2]

    def test_evidence_archive_ignores_download_mtime(self):
        before = self.archive().read_bytes()
        for root in (self.fixture.evidence, self.fixture.packages):
            for path in root.rglob("*"):
                if path.is_file():
                    os.utime(path, (1700000000, 1700000000))
        self.assertEqual(before, self.archive().read_bytes())

    def test_extra_candidate_artifact_cannot_change_release(self):
        before = self.archive().read_bytes()
        extra = self.fixture.evidence / "Ubuntu候选发布v1/不应公开v2.json"
        extra.parent.mkdir()
        extra.write_text('{"fixture":"must-not-be-published"}')
        self.assertEqual(before, self.archive().read_bytes())

    def test_unknown_file_inside_allowed_directory_is_excluded(self):
        extra = self.fixture.evidence / "Ubuntu原生验收v1-ubuntu-22.04/deb/不应公开v2.json"
        extra.write_text('{"fixture":"must-not-be-published"}')
        with zipfile.ZipFile(self.archive()) as archive:
            self.assertFalse(any("不应公开" in name for name in archive.namelist()))
            self.assertFalse(any(b"must-not-be-published" in archive.read(name) for name in archive.namelist()))

    def test_archive_has_fixed_metadata_and_no_duplicate_names(self):
        with zipfile.ZipFile(self.archive()) as archive:
            self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.external_attr >> 16, 0o100644)

    @staticmethod
    def immediate_wait(operation, predicate=bool, **kwargs):
        value = operation()
        if not predicate(value):
            raise AssertionError("fixture route/body mismatch")
        return value

    def test_navigation_clicks_native_sidebar_and_checks_url(self):
        session = Mock()
        session.call.return_value = "http://tauri.localhost/workspace/fixture-id"
        session.body.return_value = "Ubuntu桌面验收v1 异步任务"
        with patch.object(native, "wait_for", side_effect=self.immediate_wait):
            native.open_workspace(session, "fixture-id")
        session.click_text.assert_called_once_with("Ubuntu桌面验收v1")
        session.call.assert_called_once_with("url")
        self.assertEqual(session.mock_calls[0], unittest.mock.call.click_text("Ubuntu桌面验收v1"))

    def test_matching_sidebar_text_is_not_route_success(self):
        session = Mock()
        session.call.return_value = "http://tauri.localhost/"
        session.body.return_value = "Ubuntu桌面验收v1 异步任务"
        with patch.object(native, "wait_for", side_effect=self.immediate_wait):
            with self.assertRaises(AssertionError):
                native.open_workspace(session, "fixture-id")

    def test_wrong_workspace_route_is_rejected(self):
        session = Mock()
        session.call.return_value = "http://tauri.localhost/workspace/other-id"
        with patch.object(native, "wait_for", side_effect=self.immediate_wait):
            with self.assertRaises(AssertionError):
                native.open_workspace(session, "fixture-id")

    def test_task_locator_matches_request_span_not_whole_button(self):
        session = Mock()
        session.call.side_effect = [{"element-6066-11e4-a52e-4f735466cecf": "task-element"}, None]
        with patch.object(native, "wait_for", side_effect=self.immediate_wait):
            native.select_task(session, "Ubuntu-mcp-v1")
        selector = session.call.call_args_list[0].args[1]["value"]
        self.assertIn("@aria-label='任务列表'", selector)
        self.assertIn("button[span[normalize-space(.)='Ubuntu-mcp-v1']]", selector)
        session.call.assert_called_with("element/task-element/click", {})

    def test_display_is_created_before_session_bus(self):
        workflow = (fixtures.ROOT / ".github/workflows/Ubuntu桌面构建v1.yml").read_text(encoding="utf-8")
        self.assertNotIn("dbus-run-session -- xvfb-run", workflow)
        self.assertIn("xvfb-run -a -s '-screen 0 1280x900x24' dbus-run-session", workflow)

    def test_portal_environment_is_explicit_and_fail_closed(self):
        script = (fixtures.ROOT / "scripts/Ubuntu图形会话v2.sh").read_text(encoding="utf-8")
        self.assertIn("dbus-update-activation-environment DISPLAY XAUTHORITY", script)
        self.assertNotIn("--all", script)
        self.assertIn("org.freedesktop.portal.FileChooser", script)
        self.assertIn("set -euo pipefail", script)
        self.assertIn('exec python "$script"', script)

    def test_deb_uninstall_uses_verified_package_name(self):
        docs = (fixtures.ROOT / "docs/releases/Ubuntu安装说明v0.2.5.md").read_text(encoding="utf-8")
        self.assertIn("sudo apt remove coding-tools-mcp\n", docs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
