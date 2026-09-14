use std::sync::Mutex;

use serde::Serialize;

use crate::data::DataStore;
use crate::error::{AppError, AppResult};
use crate::runtime::RuntimeSupervisor;

const LOCKED_MESSAGE: &str = "配置存储暂不可用；应用已进入受限恢复模式。请解锁系统凭据库或修复原配置后重试。原配置不会被重置或降级为明文。";

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct StartupStatus {
    pub state: String,
    pub ready: bool,
    pub recoverable: bool,
    pub message: String,
    pub platform: String,
    pub safe_mode: bool,
}

pub struct AppState {
    data: Mutex<Option<DataStore>>,
    startup_error: Mutex<Option<String>>,
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
        let (data, startup_error) = match result {
            Ok(store) => (Some(store), None),
            Err(_) => (None, Some(LOCKED_MESSAGE.to_string())),
        };
        Self {
            data: Mutex::new(data),
            startup_error: Mutex::new(startup_error),
            runtime: Mutex::new(RuntimeSupervisor::default()),
        }
    }

    pub fn is_ready(&self) -> bool {
        self.data
            .lock()
            .map(|guard| guard.is_some())
            .unwrap_or(false)
    }

    pub fn startup_status(&self) -> StartupStatus {
        let ready = self.is_ready();
        let message = if ready {
            String::new()
        } else {
            self.startup_error
                .lock()
                .ok()
                .and_then(|guard| guard.clone())
                .unwrap_or_else(|| LOCKED_MESSAGE.to_string())
        };
        StartupStatus {
            state: if ready { "ready" } else { "locked" }.into(),
            ready,
            recoverable: !ready,
            message,
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
                if let Ok(mut error) = self.startup_error.lock() {
                    *error = None;
                }
                Ok(true)
            }
            Err(_) => {
                if let Ok(mut error) = self.startup_error.lock() {
                    *error = Some(LOCKED_MESSAGE.to_string());
                }
                Err(AppError::Message(LOCKED_MESSAGE.into()))
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
            .ok_or_else(|| AppError::Message(LOCKED_MESSAGE.into()))?;
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
        assert!(!status.message.contains("fixture-secret-must-not-leak"));
        assert!(state.with_data(|_| Ok(())).is_err());
    }

    #[test]
    fn healthy_store_remains_ready() {
        let state = AppState::new().expect("state wrapper");
        assert!(state.startup_status().ready);
    }
}
