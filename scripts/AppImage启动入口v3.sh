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
# Python configuration, executable search PATH, arguments and cwd stay intact.
export LD_LIBRARY_PATH="$APPDIR/usr/lib:$APPDIR/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$app" "$@"
