//! Linux-only session-bus selection for the Secret Service boundary.
//!
//! Supported Ubuntu desktops normally expose the systemd user bus at
//! `$XDG_RUNTIME_DIR/bus`. A broken/mixed login environment can nevertheless
//! inherit a second session-bus address while the user service manager and
//! GNOME Keyring remain on the runtime user bus. In that split state, Secret
//! Service calls on the inherited bus can hang even though the real credential
//! service is healthy. We switch only when the inherited bus does not already
//! own Secret Service and the user-owned runtime bus proves that Secret Service
//! is owned or activatable there.

use std::fs;
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::Duration;

use dbus::blocking::Connection;

const DBUS_SERVICE: &str = "org.freedesktop.DBus";
const DBUS_PATH: &str = "/org/freedesktop/DBus";
const SECRET_SERVICE: &str = "org.freedesktop.secrets";
const PROBE_TIMEOUT: Duration = Duration::from_millis(750);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum SessionBusRoute {
    Inherited,
    RuntimeUserBus,
    Unavailable,
}

impl SessionBusRoute {
    pub(crate) const fn code(self) -> &'static str {
        match self {
            Self::Inherited => "inherited",
            Self::RuntimeUserBus => "runtime_user_bus",
            Self::Unavailable => "unavailable",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
struct BusProbe {
    reachable: bool,
    secret_service_owned: bool,
    secret_service_activatable: bool,
}

impl BusProbe {
    const fn secret_service_available(self) -> bool {
        self.secret_service_owned || self.secret_service_activatable
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct SessionBusState {
    pub(crate) original_configured: bool,
    pub(crate) inherited_reachable: bool,
    pub(crate) split_detected: bool,
    pub(crate) runtime_user_bus_reachable: bool,
    pub(crate) runtime_user_bus_secret_service_available: bool,
    pub(crate) route: SessionBusRoute,
}

impl SessionBusState {
    pub(crate) const fn selected_bus_reachable(self) -> bool {
        match self.route {
            SessionBusRoute::Inherited => self.inherited_reachable,
            SessionBusRoute::RuntimeUserBus => self.runtime_user_bus_reachable,
            SessionBusRoute::Unavailable => false,
        }
    }
}

impl Default for SessionBusState {
    fn default() -> Self {
        let original_configured = std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some();
        Self {
            original_configured,
            inherited_reachable: false,
            split_detected: false,
            runtime_user_bus_reachable: false,
            runtime_user_bus_secret_service_available: false,
            route: if original_configured {
                SessionBusRoute::Inherited
            } else {
                SessionBusRoute::Unavailable
            },
        }
    }
}

static STATE: OnceLock<SessionBusState> = OnceLock::new();

fn probe_bus(address: &str) -> BusProbe {
    let Ok(connection) = Connection::new_address(address) else {
        return BusProbe::default();
    };
    let proxy = connection.with_proxy(DBUS_SERVICE, DBUS_PATH, PROBE_TIMEOUT);
    let owned: Result<(bool,), dbus::Error> =
        proxy.method_call(DBUS_SERVICE, "NameHasOwner", (SECRET_SERVICE,));
    let Ok((secret_service_owned,)) = owned else {
        return BusProbe::default();
    };
    let secret_service_activatable = if secret_service_owned {
        true
    } else {
        let activatable: Result<(Vec<String>,), dbus::Error> =
            proxy.method_call(DBUS_SERVICE, "ListActivatableNames", ());
        activatable.ok().is_some_and(|(names,)| {
            names.iter().any(|name| name == SECRET_SERVICE)
        })
    };
    BusProbe {
        reachable: true,
        secret_service_owned,
        secret_service_activatable,
    }
}

fn runtime_user_bus_address() -> Option<String> {
    let runtime_dir = PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR")?);
    let uid = unsafe { libc::geteuid() };
    let directory = fs::symlink_metadata(&runtime_dir).ok()?;
    if !directory.file_type().is_dir() || directory.uid() != uid {
        return None;
    }
    let bus = runtime_dir.join("bus");
    let metadata = fs::symlink_metadata(&bus).ok()?;
    if !metadata.file_type().is_socket() || metadata.uid() != uid {
        return None;
    }
    let path = bus.to_str()?;
    // Avoid constructing an unescaped D-Bus address from an unusual runtime path.
    if path.bytes().any(|byte| matches!(byte, b',' | b';' | b'=')) {
        return None;
    }
    Some(format!("unix:path={path}"))
}

fn decide_route(
    original_configured: bool,
    inherited_matches_runtime: bool,
    inherited: BusProbe,
    runtime: BusProbe,
) -> SessionBusState {
    let split_detected = original_configured && !inherited_matches_runtime;
    let route = if inherited.secret_service_owned {
        SessionBusRoute::Inherited
    } else if runtime.secret_service_available() {
        SessionBusRoute::RuntimeUserBus
    } else if original_configured {
        SessionBusRoute::Inherited
    } else {
        SessionBusRoute::Unavailable
    };
    SessionBusState {
        original_configured,
        inherited_reachable: inherited.reachable,
        split_detected,
        runtime_user_bus_reachable: runtime.reachable,
        runtime_user_bus_secret_service_available: runtime.secret_service_available(),
        route,
    }
}

/// Select the secure-storage bus before Tauri creates plugins or background
/// threads. This never starts/stops a daemon and never changes key material.
///
/// On supported Ubuntu, `$XDG_RUNTIME_DIR/bus` is the canonical per-user bus.
/// We leave a healthy inherited bus untouched. If the inherited bus does not
/// own Secret Service, we redirect this process to the canonical user bus only
/// after proving that Secret Service is owned or activatable there. The original
/// and selected addresses are never logged or serialized.
pub(crate) fn prepare_secure_storage_bus() -> SessionBusState {
    *STATE.get_or_init(|| {
        let original_configured = std::env::var_os("DBUS_SESSION_BUS_ADDRESS").is_some();
        let inherited = std::env::var("DBUS_SESSION_BUS_ADDRESS")
            .ok()
            .filter(|value| !value.is_empty());
        let runtime = runtime_user_bus_address();
        let inherited_probe = inherited
            .as_deref()
            .map(probe_bus)
            .unwrap_or_default();
        let runtime_probe = runtime.as_deref().map(probe_bus).unwrap_or_default();
        let state = decide_route(
            original_configured,
            inherited.as_deref() == runtime.as_deref(),
            inherited_probe,
            runtime_probe,
        );
        if state.route == SessionBusRoute::RuntimeUserBus {
            if let Some(address) = runtime {
                // Called synchronously at process entry before Tauri starts any
                // plugins or background threads. No bus address is exposed.
                std::env::set_var("DBUS_SESSION_BUS_ADDRESS", address);
            }
        }
        state
    })
}

pub(crate) fn state() -> SessionBusState {
    STATE.get().copied().unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn probe(reachable: bool, owned: bool, activatable: bool) -> BusProbe {
        BusProbe {
            reachable,
            secret_service_owned: owned,
            secret_service_activatable: activatable,
        }
    }

    #[test]
    fn healthy_inherited_secret_service_is_never_replaced() {
        let state = decide_route(
            true,
            false,
            probe(true, true, true),
            probe(true, true, true),
        );
        assert_eq!(state.route, SessionBusRoute::Inherited);
        assert!(state.split_detected);
        assert!(state.selected_bus_reachable());
    }

    #[test]
    fn split_bus_uses_runtime_bus_only_when_secret_service_is_available_there() {
        let state = decide_route(
            true,
            false,
            probe(true, false, false),
            probe(true, true, true),
        );
        assert_eq!(state.route, SessionBusRoute::RuntimeUserBus);
        assert!(state.split_detected);
        assert!(state.runtime_user_bus_secret_service_available);
        assert!(state.selected_bus_reachable());
    }

    #[test]
    fn missing_inherited_bus_can_use_verified_runtime_user_bus() {
        let state = decide_route(
            false,
            false,
            BusProbe::default(),
            probe(true, true, true),
        );
        assert_eq!(state.route, SessionBusRoute::RuntimeUserBus);
        assert!(!state.split_detected);
        assert!(state.selected_bus_reachable());
    }

    #[test]
    fn split_without_runtime_secret_service_preserves_fail_closed_behavior() {
        let state = decide_route(
            true,
            false,
            probe(true, false, false),
            probe(true, false, false),
        );
        assert_eq!(state.route, SessionBusRoute::Inherited);
        assert!(state.split_detected);
        assert!(!state.runtime_user_bus_secret_service_available);
    }

    #[test]
    fn missing_or_unreachable_bus_is_not_reported_as_reachable() {
        let configured = decide_route(
            true,
            false,
            BusProbe::default(),
            BusProbe::default(),
        );
        assert_eq!(configured.route, SessionBusRoute::Inherited);
        assert!(!configured.selected_bus_reachable());

        let missing = decide_route(
            false,
            false,
            BusProbe::default(),
            BusProbe::default(),
        );
        assert_eq!(missing.route, SessionBusRoute::Unavailable);
        assert!(!missing.selected_bus_reachable());
    }
}
