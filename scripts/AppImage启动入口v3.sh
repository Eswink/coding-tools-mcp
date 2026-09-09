#!/usr/bin/env bash
# Coding Tools MCP AppImage entry. linuxdeploy supplies the outer GTK hook.
# Do not emulate the generic AppRun's PYTHONHOME/PYTHONPATH/Qt/PATH injection:
# this Rust desktop launches the user's host tools, it does not bundle Python.
set -euo pipefail
app_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
export APPDIR="$app_dir"
app="$APPDIR/usr/bin/coding-tools-mcp-desktop"
if [[ ! -f "$app" || ! -x "$app" ]]; then
  printf '%s\n' 'AppImage payload is missing or not executable' >&2
  exit 126
fi
# GUI/WebKit helpers need the bundled libraries. Keep the user's suffix;
# Python configuration, executable search PATH and arguments stay intact.
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Use the bundled GIO ABI, including its real GnuTLS module. EXTRA alone
# would still load newer host modules against the bundled older GLib.
export GIO_MODULE_DIR="$APPDIR/usr/lib/x86_64-linux-gnu/gio/modules"
export GIO_EXTRA_MODULES="$GIO_MODULE_DIR"
# Release WebKit ignores WEBKIT_EXEC_PATH and linuxdeploy rewrites its helper
# paths relative to usr. Retain the original AppRun GUI cwd contract; tool
# execution still selects the workspace cwd explicitly in the Rust engine.
cd -- "$APPDIR/usr"
exec "$app" "$@"
