use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;

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
    #[test]
    fn phase_names_are_static_and_do_not_accept_runtime_payloads() {
        super::record("test-phase");
    }
}
