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
        self.values.lock().unwrap().insert(id.into(), Zeroizing::new(value.to_vec()));
        Ok(())
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
        let message = AppError::startup_storage(StartupFailureReason::SecretServiceUnavailable).to_string();
        assert!(message.contains("原配置已保留"));
        assert!(!message.contains("BadEncoding"));
    }
}
