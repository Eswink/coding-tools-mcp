//! A Linux Secret Service transport owned by one durable-ledger scan.
//! Never retain keys, item handles, search results or decrypted documents.
use super::key_store::{KeyStore, SERVICE};
use crate::error::{AppError, AppResult, StartupFailureReason};
use dbus_secret_service::{EncryptionType, Error, Item, SecretService};
use std::{collections::HashMap, sync::Mutex};
use zeroize::Zeroizing;

#[derive(Default)]
pub(super) struct ScanKeys {
    // SecretService is Send, not Sync. The owning reader lives only for a scan;
    // this mutex satisfies the shared KeyStore boundary without global state.
    service: Mutex<Option<SecretService>>,
}

fn unavailable() -> AppError {
    AppError::startup_storage(StartupFailureReason::SecretServiceUnavailable)
}

fn backend_error(error: Error) -> AppError {
    // Backend errors can contain credential data. Export only bounded reasons.
    AppError::startup_storage(match error {
        Error::Locked | Error::Prompt => StartupFailureReason::SecretServiceLockedOrDenied,
        _ => StartupFailureReason::SecretServiceUnavailable,
    })
}

fn unique_secret(items: Vec<Item<'_>>) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
    if items.is_empty() {
        return Ok(None);
    }
    if items.len() != 1 {
        return Err(unavailable());
    }
    let item = &items[0];
    if item.is_locked().map_err(backend_error)? {
        return Err(AppError::startup_storage(
            StartupFailureReason::SecretServiceLockedOrDenied,
        ));
    }
    item.get_secret()
        .map(Zeroizing::new)
        .map(Some)
        .map_err(backend_error)
}

impl KeyStore for ScanKeys {
    fn get(&self, id: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
        #[cfg(feature = "native-state-timing")]
        let _timing = super::native_timing::key_read();
        let mut session = self.service.lock().map_err(|_| unavailable())?;
        if session.is_none() {
            // No plain transport or unlock prompt, including during fallback.
            *session = Some(
                SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, 0)
                    .map_err(backend_error)?,
            );
        }
        let service = session.as_ref().ok_or_else(unavailable)?;
        let search = service
            .search_items(HashMap::from([
                ("service", SERVICE),
                ("username", id),
                ("target", "default"),
            ]))
            .map_err(backend_error)?;
        // Locked results participate in uniqueness: never silently select an
        // unlocked duplicate or ask the service to unlock anything for a scan.
        if !search.locked.is_empty() {
            return Err(AppError::startup_storage(
                StartupFailureReason::SecretServiceLockedOrDenied,
            ));
        }
        if !search.unlocked.is_empty() {
            return unique_secret(search.unlocked);
        }
        // Match keyring 3.6.3's default-target compatibility search exactly:
        // only after no exact match, search service+username in default only.
        // A missing/unavailable collection is an error, never a new namespace.
        let collection = service.get_default_collection().map_err(backend_error)?;
        if collection.is_locked().map_err(backend_error)? {
            return Err(AppError::startup_storage(
                StartupFailureReason::SecretServiceLockedOrDenied,
            ));
        }
        unique_secret(
            collection
                .search_items(HashMap::from([("service", SERVICE), ("username", id)]))
                .map_err(backend_error)?,
        )
    }

    fn set(&self, _id: &str, _value: &[u8]) -> AppResult<()> {
        // Scans can never initialize, replace or repair a credential.
        Err(unavailable())
    }
}

#[cfg(all(test, feature = "native-keyring-tests"))]
#[path = "native_scan_keys_tests.rs"]
mod tests;
