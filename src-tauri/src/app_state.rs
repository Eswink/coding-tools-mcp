use std::sync::Mutex;

use serde::Serialize;

use crate::data::DataStore;
use crate::error::{AppError, AppResult, StartupFailureReason};
use crate::runtime::RuntimeSupervisor;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct StartupStatus {
    pub state: String,
    pub ready: bool,
    pub recoverable: bool,
    pub reason_code: Option<String>,
    pub message: String,
    pub platform: String,
    pub safe_mode: bool,
}

pub struct AppState {
    data: Mutex<Option<DataStore>>,
    startup_reason: Mutex<Option<StartupFailureReason>>,
    pub runtime: Mutex<RuntimeSupervisor>,
}

impl AppState {
    pub fn new() -> AppResult<Self> {
        Ok(Self::from_store_result(Self::load_store()))
    }

    fn load_store() -> AppResult<DataStore> {
        let mut store = DataStore::load()?;
        store.init_shared_secrets()?;
        Ok(store)
    }

    fn from_store_result(result: AppResult<DataStore>) -> Self {
        let (data, startup_reason) = match result {
            Ok(store) => (Some(store), None),
            Err(error) => (None, Some(error.startup_failure_reason())),
        };
        Self {
            data: Mutex::new(data),
            startup_reason: Mutex::new(startup_reason),
            runtime: Mutex::new(RuntimeSupervisor::default()),
        }
    }

    pub fn is_ready(&self) -> bool {
        self.data
            .lock()
            .map(|guard| guard.is_some())
            .unwrap_or(false)
    }

    fn current_startup_reason(&self) -> StartupFailureReason {
        self.startup_reason
            .lock()
            .ok()
            .and_then(|guard| *guard)
            .unwrap_or(StartupFailureReason::UnknownSecureStorageFailure)
    }

    pub fn startup_status(&self) -> StartupStatus {
        let ready = self.is_ready();
        let reason = if ready { None } else { Some(self.current_startup_reason()) };
        StartupStatus {
            state: if ready { "ready" } else { "locked" }.into(),
            ready,
            recoverable: !ready,
            reason_code: reason.map(|value| value.code().to_string()),
            message: reason.map(|value| value.user_message().to_string()).unwrap_or_default(),
            platform: crate::platform::platform().os_name().into(),
            safe_mode: crate::bootstrap::safe_mode(),
        }
    }

    /// Retry only the local encrypted configuration boundary. A failed retry
    /// keeps the previous locked state and never fabricates a replacement key.
    /// Returns true only for the locked -> ready transition.
    pub fn retry_data(&self) -> AppResult<bool> {
        let mut guard = self
            .data
            .lock()
            .map_err(|_| AppError::Message("data store poisoned".into()))?;
        if guard.is_some() {
            return Ok(false);
        }
        match Self::load_store() {
            Ok(store) => {
                *guard = Some(store);
                if let Ok(mut reason) = self.startup_reason.lock() {
                    *reason = None;
                }
                Ok(true)
            }
            Err(error) => {
                let reason = error.startup_failure_reason();
                if let Ok(mut current) = self.startup_reason.lock() {
                    *current = Some(reason);
                }
                Err(AppError::startup_storage(reason))
            }
        }
    }

    pub fn with_data<R>(&self, f: impl FnOnce(&mut DataStore) -> AppResult<R>) -> AppResult<R> {
        let mut guard = self
            .data
            .lock()
            .map_err(|_| AppError::Message("data store poisoned".into()))?;
        let store = guard
            .as_mut()
            .ok_or_else(|| AppError::startup_storage(self.current_startup_reason()))?;
        store.refresh()?;
        f(store)
    }

    pub fn with_workspaces<R>(&self, f: impl FnOnce(&mut DataStore) -> AppResult<R>) -> AppResult<R> {
        self.with_data(f)
    }

    pub fn with_settings<R>(&self, f: impl FnOnce(&mut DataStore) -> AppResult<R>) -> AppResult<R> {
        self.with_data(f)
    }

    pub fn with_runtime<R>(&self, f: impl FnOnce(&mut RuntimeSupervisor) -> AppResult<R>) -> AppResult<R> {
        let mut guard = self
            .runtime
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        f(&mut guard)
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self::new().expect("failed to initialize app state wrapper")
    }
}

pub fn bootstrap_workspace(store: &mut DataStore, profile_id: &str) -> AppResult<()> {
    store.init_workspace_secrets(profile_id)
}

pub fn teardown_workspace(store: &mut DataStore, profile_id: &str) -> AppResult<()> {
    store.remove_workspace_secrets(profile_id)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn storage_failure_enters_recoverable_locked_state_instead_of_panicking() {
        let state = AppState::from_store_result(Err(AppError::Message("fixture-secret-must-not-leak".into())));
        let status = state.startup_status();
        assert_eq!(status.state, "locked");
        assert!(!status.ready);
        assert!(status.recoverable);
        assert_eq!(status.reason_code.as_deref(), Some("unknown_secure_storage_failure"));
        assert!(!status.message.contains("fixture-secret-must-not-leak"));
        assert!(state.with_data(|_| Ok(())).is_err());
    }

    #[test]
    fn typed_storage_failure_reaches_the_status_without_backend_payloads() {
        let state = AppState::from_store_result(Err(AppError::startup_storage(
            StartupFailureReason::SecretServiceLockedOrDenied,
        )));
        let status = state.startup_status();
        assert_eq!(status.reason_code.as_deref(), Some("secret_service_locked_or_denied"));
        assert!(status.message.contains("系统凭据库"));
        assert!(!status.message.contains("BadEncoding"));
    }

    #[test]
    fn healthy_store_remains_ready() {
        let state = AppState::new().expect("state wrapper");
        let status = state.startup_status();
        assert!(status.ready);
        assert!(status.reason_code.is_none());
    }
}
