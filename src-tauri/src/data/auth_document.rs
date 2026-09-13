//! One authenticated, bounded document per authorization namespace.
//! Callers serialize transactions. A stable process lock covers load and replace.
use std::path::{Path, PathBuf};
use std::time::Duration;
use serde::{de::DeserializeOwned, Serialize};
use zeroize::Zeroizing;
use crate::error::{AppError, AppResult};
use super::{config_lock::ConfigFileLock, encrypted_config, key_store, secure_file::Vault};

pub(crate) struct AuthDocument {
    path: PathBuf,
    key_id: String,
    initialized: bool,
    _owner: ConfigFileLock,
}
fn invalid() -> AppError {
    AppError::Message("授权存储不可用、损坏或版本不兼容；原文件已保留，未回退到明文。".into())
}
impl AuthDocument {
    pub(crate) fn open(root: &Path) -> AppResult<Self> {
        // Reject symlinks in existing ancestors, including the stable lock file.
        for path in root.ancestors() {
            if std::fs::symlink_metadata(path).is_ok_and(|m| m.file_type().is_symlink()) { return Err(invalid()); }
        }
        let mut builder = std::fs::DirBuilder::new();
        builder.recursive(true);
        #[cfg(unix)] { use std::os::unix::fs::DirBuilderExt; builder.mode(0o700); }
        builder.create(root)?;
        let lock = root.join("auth.lock");
        if std::fs::symlink_metadata(&lock).is_ok_and(|m| m.file_type().is_symlink()) { return Err(invalid()); }
        let owner = ConfigFileLock::acquire(&lock, Duration::ZERO)?;
        let path = root.join("auth.json");
        let initialized = match std::fs::symlink_metadata(&path) {
            Ok(m) if m.is_file() && !m.file_type().is_symlink() => true,
            Ok(_) => return Err(invalid()),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
            Err(e) => return Err(e.into()),
        };
        let key_id = encrypted_config::key_id_for_path(&path)?;
        Ok(Self { path, key_id, initialized, _owner: owner })
    }
    pub(crate) fn load<T: DeserializeOwned>(&self) -> AppResult<Option<T>> {
        if !self.initialized { return Ok(None); }
        let plain = Vault::new(key_store::default_keys()).read_scoped(&self.path, &self.key_id)?;
        serde_json::from_str(&plain).map(Some).map_err(|_| invalid())
    }
    pub(crate) fn save<T: Serialize>(&mut self, document: &T) -> AppResult<()> {
        let raw = Zeroizing::new(serde_json::to_string(document).map_err(|_| invalid())?);
        if raw.len() > 1_048_576 { return Err(invalid()); }
        // An externally removed file is not a fresh namespace; never create a replacement key.
        if self.initialized && !self.path.is_file() { return Err(invalid()); }
        Vault::new(key_store::default_keys()).write_scoped(&self.path, &raw, &self.key_id, !self.initialized)?;
        self.initialized = true;
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn encrypted_reopen_lock_and_corruption_fail_closed() {
        let dir = tempfile::tempdir().unwrap(); let path = dir.path();
        let mut doc = AuthDocument::open(path).unwrap();
        assert!(AuthDocument::open(path).is_err());
        doc.save(&serde_json::json!({"version":1,"secret_canary":"synthetic-auth-record"})).unwrap();
        assert!(!std::fs::read_to_string(path.join("auth.json")).unwrap().contains("synthetic-auth-record"));
        drop(doc);
        let doc = AuthDocument::open(path).unwrap();
        assert_eq!(doc.load::<serde_json::Value>().unwrap().unwrap()["version"], 1); drop(doc);
        std::fs::write(path.join("auth.json"), "corrupt").unwrap();
        let mut doc = AuthDocument::open(path).unwrap();
        assert!(doc.load::<serde_json::Value>().is_err());
        assert!(doc.save(&serde_json::json!({})).is_err());
        assert_eq!(std::fs::read_to_string(path.join("auth.json")).unwrap(), "corrupt");
    }
    #[test]
    fn missing_existing_key_never_recreates_credentials() {
        use super::super::key_store::KeyStore;
        let root = tempfile::tempdir().unwrap(); let mut doc = AuthDocument::open(root.path()).unwrap();
        doc.save(&serde_json::json!({"ok":true})).unwrap();
        let keys = super::super::key_store::MemoryKeys::default();
        // A different empty provider simulates a deleted OS credential.
        let vault = Vault::new(&keys);
        assert!(vault.read_scoped(&doc.path,&doc.key_id).is_err());
        assert!(vault.write_scoped(&doc.path,"{}",&doc.key_id,false).is_err());
        assert!(keys.get(&doc.key_id).unwrap().is_none());
    }
}
