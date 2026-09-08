//! Small encrypted task documents. The lifetime sidecar lock prevents two app
//! processes from independently accepting the same request key.
use std::path::{Path, PathBuf};
use std::collections::HashMap;
use sha2::{Digest, Sha256};
use std::sync::{Mutex, atomic::{AtomicBool, Ordering}};
use std::time::Duration;
use serde_json::Value;
use crate::error::{AppError, AppResult};
use super::{config_lock::ConfigFileLock, encrypted_config, key_store, secure_file::Vault};

pub(crate) struct TaskArchive {
    root: PathBuf,
    _owner: ConfigFileLock,
    io: Mutex<HashMap<String, [u8; 32]>>,
    key_id: String,
    key_initialized: AtomicBool,
}

impl TaskArchive {
    pub(crate) fn open(root: &Path) -> AppResult<Self> {
        if std::fs::symlink_metadata(root).is_ok_and(|m| m.file_type().is_symlink()) {
            return Err(invalid());
        }
        std::fs::create_dir_all(root)?;
        let lock = root.join("owner.lock");
        if std::fs::symlink_metadata(&lock).is_ok_and(|m| m.file_type().is_symlink()) {
            return Err(invalid());
        }
        let owner = ConfigFileLock::acquire(&lock, Duration::ZERO)?;
        let has_records = std::fs::read_dir(root)?.try_fold(false, |found, entry| {
            Ok::<_, std::io::Error>(found || entry?.path().extension().and_then(|s| s.to_str()) == Some("json"))
        })?;
        let key_id = encrypted_config::key_id_for_path(&root.join("archive-key-v2"))?;
        Ok(Self { root: root.to_path_buf(), _owner: owner, io: Mutex::new(HashMap::new()),
            key_id, key_initialized: AtomicBool::new(has_records) })
    }

    fn path(&self, id: &str) -> AppResult<PathBuf> {
        let uuid = uuid::Uuid::parse_str(id).map_err(|_| invalid())?;
        if uuid.to_string() != id { return Err(invalid()); }
        Ok(self.root.join(format!("{id}.json")))
    }

    pub(crate) fn load(&self) -> AppResult<Vec<Value>> {
        let _io = self.io.lock().map_err(|_| invalid())?;
        let mut records = Vec::new();
        for entry in std::fs::read_dir(&self.root)? {
            let path = entry?.path();
            if path.extension().and_then(|s| s.to_str()) != Some("json") { continue; }
            if records.len() >= 32 { return Err(invalid()); }
            let id = path.file_stem().and_then(|s| s.to_str()).ok_or_else(invalid)?;
            if self.path(id)? != path { return Err(invalid()); }
            let plain = Vault::new(key_store::default_keys()).read_scoped(&path, &self.key_id)?;
            let value: Value = serde_json::from_str(&plain).map_err(|_| invalid())?;
            if value.get("id").and_then(Value::as_str) != Some(id) { return Err(invalid()); }
            records.push(value);
        }
        Ok(records)
    }

    /// Generate the current snapshot AFTER acquiring the write lock: an older
    /// checkpoint cannot overwrite a more recent terminal/cancel transition.
    pub(crate) fn save(&self, id: &str, snapshot: impl FnOnce() -> Value) -> AppResult<()> {
        let mut saved = self.io.lock().map_err(|_| invalid())?;
        let value = snapshot();
        let raw = zeroize::Zeroizing::new(serde_json::to_string(&value).map_err(|_| invalid())?);
        // A quiet long-running process must not rewrite MiB-sized encrypted logs
        // every two seconds merely because elapsed time advanced. Output/state
        // changes and every terminal transition still force a fresh snapshot.
        let mut identity = value;
        if identity.get("completed_at").is_some_and(Value::is_null) {
            if let Some(object) = identity.as_object_mut() { object.remove("elapsed_ms"); }
        }
        let identity_bytes = zeroize::Zeroizing::new(serde_json::to_vec(&identity).map_err(|_| invalid())?);
        let digest: [u8; 32] = Sha256::digest(&*identity_bytes).into();
        let path = self.path(id)?;
        if saved.get(id) == Some(&digest) && path.is_file() { return Ok(()); }
        Vault::new(key_store::default_keys()).write_scoped(&path, &raw, &self.key_id,
            !self.key_initialized.load(Ordering::Acquire))?;
        self.key_initialized.store(true, Ordering::Release);
        saved.insert(id.to_owned(), digest);
        Ok(())
    }

    pub(crate) fn remove(&self, id: &str) -> AppResult<()> {
        let mut saved = self.io.lock().map_err(|_| invalid())?;
        // Authenticate before deletion too. Never erase an unreadable record.
        let path = self.path(id)?;
        let _verified = Vault::new(key_store::default_keys()).read_scoped(&path, &self.key_id)?;
        std::fs::remove_file(path)?;
        saved.remove(id);
        Ok(())
    }
}

fn invalid() -> AppError {
    AppError::Message("任务记录损坏、版本不兼容或路径无效；原记录已保留，禁止自动重试命令。".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn one_namespace_reuses_one_key_and_rejects_cross_namespace_documents() {
        let a = tempfile::tempdir().unwrap(); let b = tempfile::tempdir().unwrap();
        let left = TaskArchive::open(a.path()).unwrap();
        let right = TaskArchive::open(b.path()).unwrap();
        let one = uuid::Uuid::new_v4().to_string(); let two = uuid::Uuid::new_v4().to_string();
        left.save(&one, || serde_json::json!({"id":one})).unwrap();
        left.save(&two, || serde_json::json!({"id":two})).unwrap();
        for id in [&one, &two] {
            let raw = std::fs::read_to_string(left.path(id).unwrap()).unwrap();
            let envelope = encrypted_config::parse_envelope(&raw).unwrap().unwrap();
            assert_eq!(envelope.key_id, left.key_id);
        }
        std::fs::copy(left.path(&one).unwrap(), right.path(&one).unwrap()).unwrap();
        assert!(right.load().is_err());
        assert!(right.path(&one).unwrap().exists());
    }
}

#[cfg(test)]
mod checkpoint_tests {
    use super::*;
    #[test]
    fn quiet_progress_does_not_rewrite_ciphertext_but_output_and_terminal_do() {
        let root = tempfile::tempdir().unwrap();
        let archive = TaskArchive::open(root.path()).unwrap();
        let id = uuid::Uuid::new_v4().to_string();
        let mut value = serde_json::json!({"id":id,"completed_at":null,"elapsed_ms":1,"stdout":""});
        archive.save(&id, || value.clone()).unwrap();
        let file = archive.path(&id).unwrap();
        let first = std::fs::read(&file).unwrap();
        value["elapsed_ms"] = serde_json::json!(9999);
        archive.save(&id, || value.clone()).unwrap();
        assert_eq!(std::fs::read(&file).unwrap(), first);
        value["stdout"] = serde_json::json!("output");
        archive.save(&id, || value.clone()).unwrap();
        let output = std::fs::read(&file).unwrap();
        assert_ne!(output, first);
        value["completed_at"] = serde_json::json!(10000);
        archive.save(&id, || value.clone()).unwrap();
        assert_ne!(std::fs::read(&file).unwrap(), output);
        assert_eq!(archive.load().unwrap()[0], value);
    }
}
