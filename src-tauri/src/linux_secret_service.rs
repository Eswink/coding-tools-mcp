//! Linux Secret Service collection recovery.
//!
//! The keyring 3.6.x sync Secret Service backend falls back to a legacy search
//! in the default collection when a default-target item is absent. If the
//! Secret Service has no `default` alias at all, that fallback maps
//! `NoResult` to `NoStorageAccess`, which is indistinguishable from a locked or
//! dismissed prompt at the keyring API boundary.
//!
//! This module recovers only that bounded state. It never reads a password,
//! never stores a key itself, and never creates a collection when an existing
//! encrypted configuration is present. Collection creation is invoked only by
//! the explicit recovery action after the caller proves this is a fresh
//! configuration path. Any password UI is owned by the desktop Secret Service.

use dbus_secret_service::{EncryptionType, Error, SecretService};

use crate::error::{AppError, AppResult, StartupFailureReason};

const PROMPT_TIMEOUT_SECONDS: u64 = 90;
const DEFAULT_COLLECTION_LABEL: &str = "Login";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DefaultCollectionState {
    Present,
    Missing,
    Unknown,
}

impl DefaultCollectionState {
    pub(crate) const fn code(self) -> &'static str {
        match self {
            Self::Present => "present",
            Self::Missing => "missing",
            Self::Unknown => "unknown",
        }
    }
}

fn classify(error: &Error) -> StartupFailureReason {
    match error {
        Error::NoResult => StartupFailureReason::SecretServiceDefaultCollectionMissing,
        Error::Locked | Error::Prompt => StartupFailureReason::SecretServiceLockedOrDenied,
        Error::Unavailable | Error::Dbus(_) => StartupFailureReason::SecretServiceUnavailable,
        _ => StartupFailureReason::UnknownSecureStorageFailure,
    }
}

fn storage_error(error: &Error) -> AppError {
    // Never format the backend error. D-Bus/backend payloads are not part of
    // the stable recovery contract.
    AppError::startup_storage(classify(error))
}

/// Read-only bounded probe. Prompt timeout 0 ensures this cannot display a
/// dialog while merely classifying a keyring error or producing diagnostics.
pub(crate) fn default_collection_state() -> DefaultCollectionState {
    let Ok(service) = SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, 0) else {
        return DefaultCollectionState::Unknown;
    };
    match service.get_default_collection() {
        Ok(_) => DefaultCollectionState::Present,
        Err(Error::NoResult) => DefaultCollectionState::Missing,
        Err(_) => DefaultCollectionState::Unknown,
    }
}

/// Create the Secret Service `default` collection through the provider's own
/// secure prompt. The caller must enforce the fresh-install/no-config gate.
///
/// Returns true only if this call created the collection. A racing creator is
/// treated as success without changing any existing alias or key material.
pub(crate) fn initialize_default_collection() -> AppResult<bool> {
    let service =
        SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, PROMPT_TIMEOUT_SECONDS)
            .map_err(|error| storage_error(&error))?;

    match service.get_default_collection() {
        Ok(_) => return Ok(false),
        Err(Error::NoResult) => {}
        Err(error) => return Err(storage_error(&error)),
    }

    service
        .create_collection(DEFAULT_COLLECTION_LABEL, "default")
        .map_err(|error| storage_error(&error))?;

    service
        .get_default_collection()
        .map_err(|error| storage_error(&error))?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stable_state_codes_are_bounded() {
        assert_eq!(DefaultCollectionState::Present.code(), "present");
        assert_eq!(DefaultCollectionState::Missing.code(), "missing");
        assert_eq!(DefaultCollectionState::Unknown.code(), "unknown");
    }

    #[test]
    fn missing_default_is_not_misclassified_as_locked() {
        assert_eq!(
            classify(&Error::NoResult),
            StartupFailureReason::SecretServiceDefaultCollectionMissing
        );
        assert_eq!(
            classify(&Error::Prompt),
            StartupFailureReason::SecretServiceLockedOrDenied
        );
    }
}
