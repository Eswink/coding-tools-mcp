//! The production provider never falls back to plaintext, environment variables,
//! or an in-memory store. Test doubles are compiled only for unit tests.
use crate::error::{AppError, AppResult};
use zeroize::Zeroizing;

pub(super) const SERVICE: &str = "coding-tools-mcp.config.v1";

pub(super) trait KeyStore: Send + Sync {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>>;
    fn set(&self, id: &str, value: &[u8]) -> AppResult<()>;
}

pub(super) struct NativeKeyStore;

fn unavailable() -> AppError {
    // Keyring errors may embed credential bytes (BadEncoding). Never format them.
    AppError::Message("系统凭据库不可用或未解锁；未回退到明文保存，原配置已保留。请解锁系统凭据库后重试。".into())
}

impl KeyStore for NativeKeyStore {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
        let entry = keyring::Entry::new(SERVICE, id).map_err(|_| unavailable())?;
        match entry.get_secret() {
            Ok(secret) => Ok(Some(Zeroizing::new(secret))),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(_) => Err(unavailable()),
        }
    }

    fn set(&self, id: &str, value: &[u8]) -> AppResult<()> {
        keyring::Entry::new(SERVICE, id)
            .and_then(|entry| entry.set_secret(value))
            .map_err(|_| unavailable())
    }
}

#[cfg(not(test))]
pub(super) fn default_keys() -> &'static dyn KeyStore {
    &NativeKeyStore
}

#[cfg(test)]
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
