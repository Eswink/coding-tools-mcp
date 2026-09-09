#!/usr/bin/env bash
# Invoked inside Xvfb and an isolated D-Bus session, never a user's desktop session.
set -euo pipefail
script=$1 app=$2 driver=$3 kind=$4 output=$5
: "${DISPLAY:?Xvfb must start before D-Bus}"
: "${XAUTHORITY:?Xvfb authentication is required}"
: "${DBUS_SESSION_BUS_ADDRESS:?an isolated session bus is required}"
test "$(id -u)" -ne 0
test -f "$HOME/.ubuntu-ci-fixture-v1"
export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=x11
mkdir -p "$XDG_CONFIG_HOME/xdg-desktop-portal" "$output"
printf '[preferred]\ndefault=gtk\n' > "$XDG_CONFIG_HOME/xdg-desktop-portal/portals.conf"
# Explicit allowlist: do not copy CI tokens or the whole environment into activation.
dbus-update-activation-environment DISPLAY XAUTHORITY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE XDG_CONFIG_HOME XDG_DATA_HOME XDG_RUNTIME_DIR
printf '%s' 'isolated-ubuntu-native-v1' | gnome-keyring-daemon --unlock --components=secrets
timeout 25s gdbus introspect --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop > "$output/Portal接口v2.txt"
grep -q 'org.freedesktop.portal.FileChooser' "$output/Portal接口v2.txt"
gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus --method org.freedesktop.DBus.GetNameOwner org.freedesktop.impl.portal.desktop.gtk
exec python "$script" --executable "$app" --driver "$driver" --kind "$kind" --source "$GITHUB_SHA" --output "$output"
