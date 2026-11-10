//! The production provider never falls back to plaintext, environment variables,
//! or an in-memory store. Test doubles are compiled only for unit tests.
use crate::error::{classify_keyring_error, AppError, AppResult};
use zeroize::Zeroizing;

pub(super) const SERVICE: &str = "coding-tools-mcp.config.v1";

pub(super) trait KeyStore: Send + Sync {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>>;
    fn set(&self, id: &str, value: &[u8]) -> AppResult<()>;
}

pub(super) struct NativeKeyStore;

fn unavailable(error: &keyring::Error) -> AppError {
    // Never format or serialize the platform error: variants may carry credential bytes.
    AppError::startup_storage(classify_keyring_error(error))
}

impl KeyStore for NativeKeyStore {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
        #[cfg(feature = "native-state-timing")]
        let _timing = super::native_timing::key_read();
        let entry = keyring::Entry::new(SERVICE, id).map_err(|error| unavailable(&error))?;
        match entry.get_secret() {
            Ok(secret) => Ok(Some(Zeroizing::new(secret))),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(error) => Err(unavailable(&error)),
        }
    }

    fn set(&self, id: &str, value: &[u8]) -> AppResult<()> {
        keyring::Entry::new(SERVICE, id)
            .and_then(|entry| entry.set_secret(value))
            .map_err(|error| unavailable(&error))
    }
}

#[cfg(any(not(test), feature = "native-keyring-tests"))]
pub(super) fn default_keys() -> &'static dyn KeyStore {
    &NativeKeyStore
}

#[cfg(all(test, not(feature = "native-keyring-tests")))]
pub(super) fn default_keys() -> &'static dyn KeyStore {
    static KEYS: std::sync::OnceLock<MemoryKeys> = std::sync::OnceLock::new();
    KEYS.get_or_init(MemoryKeys::default)
}

#[cfg(test)]
#[derive(Default)]
pub(super) struct MemoryKeys {
    values: std::sync::Mutex<std::collections::HashMap<String, Zeroizing<Vec<u8>>>>,
}

#[cfg(test)]
impl KeyStore for MemoryKeys {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
        Ok(self.values.lock().unwrap().get(id).cloned())
    }
    fn set(&self, id: &str, value: &[u8]) -> AppResult<()> {
        if FAIL_KEY_WRITES.with(std::cell::Cell::get) {
            return Err(AppError::startup_storage(
                crate::error::StartupFailureReason::SecretServiceUnavailable,
            ));
        }
        self.values
            .lock()
            .unwrap()
            .insert(id.into(), Zeroizing::new(value.to_vec()));
        Ok(())
    }
}

// A1 C38 (G1-RE6): a per-thread locked/lost provider. Only the calling test's
// thread sees failed key writes; parallel tests sharing MemoryKeys are unaffected.
#[cfg(test)]
thread_local! {
    static FAIL_KEY_WRITES: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

#[cfg(all(test, not(feature = "native-keyring-tests")))]
mod root_work_reclaim_tests {
    use crate::tools::root_work::RootWorkTracker;
    use sha2::{Digest, Sha256};

    fn namespace_for(root: &std::path::Path) -> std::path::PathBuf {
        // The native store itself may not exist yet; its process tempdir does.
        let native = crate::harness::Harness::default_root().unwrap();
        let store = native
            .parent()
            .unwrap()
            .canonicalize()
            .unwrap()
            .join(native.file_name().unwrap());
        let root = root.canonicalize().unwrap();
        store.join("native-root-work-v1").join(format!(
            "{:x}",
            Sha256::digest(root.to_string_lossy().as_bytes())
        ))
    }

    #[test]
    fn failed_first_key_write_leaves_no_namespace_and_recovers_for_every_root() {
        // Workspace directories outlive the process ledger (inode identities).
        let temp = Box::leak(Box::new(tempfile::tempdir().unwrap()));
        let root = temp.path().join("first");
        let unrelated = temp.path().join("unrelated");
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir(&unrelated).unwrap();
        let namespace = namespace_for(&root);

        super::FAIL_KEY_WRITES.with(|fail| fail.set(true));
        let failed = RootWorkTracker::for_workspace(&root);
        super::FAIL_KEY_WRITES.with(|fail| fail.set(false));
        assert!(failed.is_err(), "a lost provider must fail closed");
        assert!(
            std::fs::symlink_metadata(&namespace).is_err(),
            "no half-initialized namespace may remain after a failed first write"
        );

        let same = RootWorkTracker::for_workspace(&root).expect("same root after recovery");
        assert!(namespace.join("auth.json").is_file());
        drop(same.register().expect("same root admits work"));
        let other = RootWorkTracker::for_workspace(&unrelated).expect("unrelated root");
        drop(other.register().expect("unrelated root admits work"));
    }
}

#[cfg(test)]
mod provider_contract_tests {
    use super::*;
    use crate::error::StartupFailureReason;

    #[test]
    fn native_adapter_is_available_without_calling_the_users_keyring() {
        let _provider: &dyn KeyStore = &NativeKeyStore;
        assert_eq!(SERVICE, "coding-tools-mcp.config.v1");
        let message =
            AppError::startup_storage(StartupFailureReason::SecretServiceUnavailable).to_string();
        assert!(message.contains("原配置已保留"));
        assert!(!message.contains("BadEncoding"));
    }
}
