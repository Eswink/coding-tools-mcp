//! Cooperative cross-process lock on a stable sidecar, not the atomically
//! replaced profiles.json inode. Never unlink the sidecar after releasing it.
use std::fs::{File, OpenOptions};
use std::path::Path;
use std::time::{Duration, Instant};

use crate::error::{AppError, AppResult};

pub(super) struct ConfigFileLock(File);

impl ConfigFileLock {
    pub(super) fn acquire(path: &Path, timeout: Duration) -> AppResult<Self> {
        if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
            std::fs::create_dir_all(parent)?;
        }
        let mut options = OpenOptions::new();
        options.read(true).write(true).create(true).truncate(false);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        let file = options.open(path)?;
        let start = Instant::now();
        loop {
            match fs2::FileExt::try_lock_exclusive(&file) {
                Ok(()) => return Ok(Self(file)),
                Err(error) if error.raw_os_error() == fs2::lock_contended_error().raw_os_error()
                    || error.kind() == std::io::ErrorKind::WouldBlock => {
                    if start.elapsed() >= timeout {
                        return Err(AppError::Message("另一应用实例正在读写配置，等待超时；本次未写入，请重试。".into()));
                    }
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(error) => return Err(error.into()),
            }
        }
    }
}

impl Drop for ConfigFileLock {
    fn drop(&mut self) {
        let _ = fs2::FileExt::unlock(&self.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exclusive_lock_is_released_without_unlinking_the_sidecar() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.lock");
        let first = ConfigFileLock::acquire(&path, Duration::ZERO).unwrap();
        assert!(ConfigFileLock::acquire(&path, Duration::ZERO).is_err());
        drop(first);
        assert!(path.exists());
        assert!(ConfigFileLock::acquire(&path, Duration::ZERO).is_ok());
    }

    #[test]
    fn contention_timeout_is_bounded_and_does_not_change_the_lock_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.lock");
        std::fs::write(&path, "unchanged").unwrap();
        let first = ConfigFileLock::acquire(&path, Duration::ZERO).unwrap();
        let start = Instant::now();
        assert!(ConfigFileLock::acquire(&path, Duration::from_millis(40)).is_err());
        assert!(start.elapsed() < Duration::from_secs(3));
        drop(first);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "unchanged");
    }

    #[test]
    fn independent_files_do_not_block_each_other() {
        let dir = tempfile::tempdir().unwrap();
        let first = ConfigFileLock::acquire(&dir.path().join("first.lock"), Duration::ZERO).unwrap();
        let second = ConfigFileLock::acquire(&dir.path().join("second.lock"), Duration::ZERO).unwrap();
        drop((first, second));
    }

    #[test]
    fn child_lock_probe() {
        let Ok(path) = std::env::var("MCP_TEST_CONFIG_LOCK_PATH") else { return; };
        let expected = std::env::var("MCP_TEST_CONFIG_LOCK_AVAILABLE").unwrap() == "1";
        assert_eq!(ConfigFileLock::acquire(Path::new(&path), Duration::ZERO).is_ok(), expected);
    }

    #[test]
    fn another_process_observes_contention_then_release() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("profiles.lock");
        let probe = |available: bool| {
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "data::config_lock::tests::child_lock_probe", "--nocapture"])
                .env("MCP_TEST_CONFIG_LOCK_PATH", &path)
                .env("MCP_TEST_CONFIG_LOCK_AVAILABLE", if available { "1" } else { "0" })
                .output().unwrap();
            assert!(output.status.success(), "{}", String::from_utf8_lossy(&output.stderr));
            assert!(String::from_utf8_lossy(&output.stdout).contains("1 passed"));
        };
        let lock = ConfigFileLock::acquire(&path, Duration::ZERO).unwrap();
        probe(false);
        drop(lock);
        probe(true);
    }
}
