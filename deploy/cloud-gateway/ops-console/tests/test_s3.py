#!/usr/bin/env python3
"""S3: invite output_rel must be under devices/."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ops_console.cli_wrap import (  # noqa: E402
    CliError,
    _require_invite_output_rel,
    invite_device,
)
from ops_console.paths import PathError, ensure_workspace_root  # noqa: E402


class RequireInviteOutputRelTests(unittest.TestCase):
    def test_accept_devices_invitation_json(self):
        self.assertEqual(
            _require_invite_output_rel("devices/invitation.json"),
            "devices/invitation.json",
        )

    def test_accept_devices_nested(self):
        self.assertEqual(
            _require_invite_output_rel("devices/foo/bar.json"),
            "devices/foo/bar.json",
        )

    def test_accept_backslash_normalized(self):
        self.assertEqual(
            _require_invite_output_rel("devices\\invitation.json"),
            "devices/invitation.json",
        )

    def test_reject_other_prefix(self):
        with self.assertRaises(PathError) as cm:
            _require_invite_output_rel("other/x.json")
        self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")

    def test_reject_devices_dotdot_escape(self):
        with self.assertRaises(PathError) as cm:
            _require_invite_output_rel("devices/../escape.json")
        self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")

    def test_reject_absolute_unix(self):
        with self.assertRaises(PathError) as cm:
            _require_invite_output_rel("/tmp/devices/invitation.json")
        self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")

    def test_reject_empty_after_prefix(self):
        with self.assertRaises(PathError) as cm:
            _require_invite_output_rel("devices/")
        self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")

    def test_reject_devices_alone(self):
        with self.assertRaises(PathError) as cm:
            _require_invite_output_rel("devices")
        self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")


class InviteDeviceOutputRelIntegrationTests(unittest.TestCase):
    """Rejects fail before gateway bin; accepts pass the devices gate (then miss bin)."""

    def test_invite_rejects_other_prefix_without_bin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            with self.assertRaises(PathError) as cm:
                invite_device(root, "config.json", "secrets.json", "other/x.json")
            self.assertEqual(cm.exception.code, "output_rel_must_be_under_devices")

    def test_invite_accept_reaches_bin_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = ensure_workspace_root(tmp)
            with self.assertRaises(CliError) as cm:
                invite_device(
                    root,
                    "config.json",
                    "secrets.json",
                    "devices/invitation.json",
                    gateway_bin="/nonexistent/coding-tools-gateway-s3-probe",
                )
            self.assertEqual(cm.exception.code, "gateway_bin_missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
