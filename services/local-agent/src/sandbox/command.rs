//! Adapter for an already-authorized host command. No authority is minted here.
use super::{LinuxSandbox, SandboxError, SandboxErrorKind};
use std::path::Path;
use tokio::process::Command;

impl LinuxSandbox {
    /// Install the same mandatory boundary used by the process/PTY managers.
    ///
    /// The trusted host must finish local admission and command policy checks,
    /// configure stdio, and spawn this command without changing its program/cwd.
    /// All fallible preparation happens in the parent. Failure must not be
    /// retried on an unsandboxed path.
    pub fn configure_command(&self, command: &mut Command) -> Result<(), SandboxError> {
        let program = Path::new(command.as_std().get_program());
        if !program.is_absolute() {
            return Err(SandboxError {
                kind: SandboxErrorKind::InvalidExecutable,
            });
        }
        let cwd = command.as_std().get_current_dir().ok_or(SandboxError {
            kind: SandboxErrorKind::InvalidWorkingDirectory,
        })?;
        let prepared = self.prepare(program, cwd)?;
        // Do not leak host credentials, preload variables or runtime search
        // paths. These values are chosen locally, never supplied by the model.
        command
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("HOME", &self.root.path)
            .env("TMPDIR", &self.root.path)
            .env("LANG", "C.UTF-8")
            .env("PYTHONUTF8", "1")
            .kill_on_drop(true);
        // SAFETY: PreparedSandbox::apply only performs async-signal-safe
        // syscalls, uses owned prepared descriptors, and never allocates/locks.
        unsafe {
            command.pre_exec(move || prepared.apply());
        }
        Ok(())
    }
}

#[cfg(all(test, target_arch = "x86_64"))]
mod tests {
    use super::*;

    #[test]
    fn host_command_requires_explicit_absolute_executable_and_cwd() {
        let root = std::env::temp_dir();
        let policy = LinuxSandbox::new(&root).unwrap();
        let mut relative = Command::new("sh");
        relative.current_dir(&root);
        assert_eq!(
            policy.configure_command(&mut relative).unwrap_err().kind,
            SandboxErrorKind::InvalidExecutable
        );
        let mut missing_cwd = Command::new("/bin/sh");
        assert_eq!(
            policy.configure_command(&mut missing_cwd).unwrap_err().kind,
            SandboxErrorKind::InvalidWorkingDirectory
        );
    }
}
