use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::sync::OnceLock;

#[cfg(target_os = "linux")]
fn log_path() -> Option<PathBuf> {
    let root = std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".local/state")))?;
    Some(root.join("coding-tools-mcp").join("bootstrap.log"))
}

#[cfg(not(target_os = "linux"))]
fn log_path() -> Option<PathBuf> {
    None
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StartupMode {
    pub safe_mode: bool,
    pub diagnose_startup: bool,
}

static STARTUP_MODE: OnceLock<StartupMode> = OnceLock::new();

fn mode_from_args(args: impl IntoIterator<Item = OsString>) -> StartupMode {
    let mut safe_mode = false;
    let mut diagnose_startup = false;
    for arg in args.into_iter().skip(1) {
        if arg == "--safe-mode" {
            safe_mode = true;
        } else if arg == "--diagnose-startup" {
            safe_mode = true;
            diagnose_startup = true;
        }
    }
    StartupMode { safe_mode, diagnose_startup }
}

pub fn startup_mode() -> StartupMode {
    *STARTUP_MODE.get_or_init(|| mode_from_args(std::env::args_os()))
}

pub fn safe_mode() -> bool {
    startup_mode().safe_mode
}

pub fn diagnose_startup() -> bool {
    startup_mode().diagnose_startup
}

/// Write only fixed phase identifiers. Never pass errors, environment values,
/// paths selected by the user, credentials, request bodies, or command text.
pub fn record(phase: &'static str) {
    let Some(path) = log_path() else { return; };
    let Some(parent) = path.parent() else { return; };
    let mut builder = fs::DirBuilder::new();
    builder.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    if builder.create(parent).is_err() { return; }
    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    if let Ok(mut file) = options.open(path) {
        let _ = writeln!(file, "phase={phase}");
    }
}

pub fn install_panic_marker() {
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        record("panic");
        previous(info);
    }));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phase_names_are_static_and_do_not_accept_runtime_payloads() {
        super::record("test-phase");
    }

    #[test]
    fn startup_flags_are_explicit_and_diagnose_implies_safe_mode() {
        let plain = mode_from_args([OsString::from("app")]);
        assert_eq!(plain, StartupMode { safe_mode: false, diagnose_startup: false });
        let safe = mode_from_args([OsString::from("app"), OsString::from("--safe-mode")]);
        assert_eq!(safe, StartupMode { safe_mode: true, diagnose_startup: false });
        let diagnose = mode_from_args([OsString::from("app"), OsString::from("--diagnose-startup")]);
        assert_eq!(diagnose, StartupMode { safe_mode: true, diagnose_startup: true });
    }
}
