//! Persisted auto-start intent. It is only a note of what the user last chose
//! (start / stop); it is not a grant, never creates journals and carries no secrets.
use super::*;

const INTENT_FILE: &str = "auto-start.intent";

impl ConnectionStore {
    /// True only if the user's last explicit cloud action was "start" and nothing since
    /// has stopped it. A missing, redirected or hard-linked marker reads as "no".
    pub(crate) fn auto_start_intent(&self) -> bool {
        regular_file(&self.root.join(INTENT_FILE)).is_ok()
    }
    /// Manual start records the intent; manual stop clears it so the next application
    /// start does not undo the user's stop. Recording requires an existing private
    /// configuration directory; nothing here ever creates it.
    pub(crate) fn set_auto_start_intent(&self, enabled: bool) -> Result<(), ConfigurationError> {
        directory_chain(&self.root)?;
        let path = self.root.join(INTENT_FILE);
        if enabled {
            private_directory(&self.root)?;
            if self.auto_start_intent() {
                return Ok(());
            }
            fs::write(&path, b"1\n").map_err(|_| ConfigurationError::Unavailable)?;
        } else {
            // Clearing must also work for a workspace that was never configured.
            match fs::remove_file(&path) {
                Ok(()) => {}
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
                Err(_) => return Err(ConfigurationError::Unavailable),
            }
        }
        sync_directory(&self.root)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store(root: &Path, workspace: &Path) -> ConnectionStore {
        ConnectionStore::at(root.to_path_buf(), "profile", workspace).unwrap()
    }
    fn private_root(base: &Path) -> PathBuf {
        let root = base.join("connection");
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(&root).unwrap();
        root
    }

    #[test]
    fn intent_is_off_by_default_and_survives_a_restart_of_the_store() {
        let dir = tempfile::tempdir().unwrap();
        let workspace = dir.path().join("ws");
        fs::create_dir(&workspace).unwrap();
        let root = private_root(dir.path());
        assert!(!store(&root, &workspace).auto_start_intent());
        store(&root, &workspace)
            .set_auto_start_intent(true)
            .unwrap();
        // A brand new store object (the next application start) still sees it.
        assert!(store(&root, &workspace).auto_start_intent());
        store(&root, &workspace)
            .set_auto_start_intent(false)
            .unwrap();
        assert!(!store(&root, &workspace).auto_start_intent());
    }
    #[test]
    fn clearing_is_idempotent_and_never_creates_the_directory() {
        let dir = tempfile::tempdir().unwrap();
        let workspace = dir.path().join("ws");
        fs::create_dir(&workspace).unwrap();
        let root = private_root(dir.path());
        let s = store(&root, &workspace);
        s.set_auto_start_intent(false).unwrap();
        s.set_auto_start_intent(true).unwrap();
        s.set_auto_start_intent(true).unwrap();
        s.set_auto_start_intent(false).unwrap();
        s.set_auto_start_intent(false).unwrap();
        let missing = store(&dir.path().join("never-imported"), &workspace);
        assert!(missing.set_auto_start_intent(true).is_err());
        assert!(!dir.path().join("never-imported").exists());
        assert!(!missing.auto_start_intent());
        // Stopping a never-configured workspace is a harmless no-op, not an error.
        missing.set_auto_start_intent(false).unwrap();
        assert!(!dir.path().join("never-imported").exists());
    }
    #[cfg(unix)]
    #[test]
    fn a_symlinked_marker_is_not_an_intent() {
        let dir = tempfile::tempdir().unwrap();
        let workspace = dir.path().join("ws");
        fs::create_dir(&workspace).unwrap();
        let root = private_root(dir.path());
        let target = dir.path().join("elsewhere");
        fs::write(&target, "1").unwrap();
        std::os::unix::fs::symlink(&target, root.join(INTENT_FILE)).unwrap();
        assert!(!store(&root, &workspace).auto_start_intent());
    }
}
