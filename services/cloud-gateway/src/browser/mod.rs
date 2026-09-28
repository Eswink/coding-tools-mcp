//! Browser owner identity is NOT a local workspace/chat approval.
mod credentials;
mod envelope;
mod flows;
mod html;
pub(crate) mod http;

use crate::{IdentityError, IdentityStore, Secret};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::Semaphore;

pub const FLOW_SECONDS: i64 = 300;
pub const MAX_FLOWS: i64 = 128;
pub const COOKIE_NAME: &str = "__Host-ctm-browser";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserError {
    Rejected,
    LoginRejected,
    RateLimited,
    StoreUnavailable,
    InvalidConfig,
}
pub type Result<T> = std::result::Result<T, BrowserError>;
impl From<IdentityError> for BrowserError {
    fn from(e: IdentityError) -> Self {
        match e {
            IdentityError::StoreUnavailable => Self::StoreUnavailable,
            IdentityError::InvalidConfig | IdentityError::IdentityMismatch => Self::InvalidConfig,
            _ => Self::Rejected,
        }
    }
}
impl From<sqlx::Error> for BrowserError {
    fn from(_: sqlx::Error) -> Self {
        Self::StoreUnavailable
    }
}
impl std::fmt::Display for BrowserError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Rejected => "browser_request_rejected",
            Self::LoginRejected => "login_rejected",
            Self::RateLimited => "try_later",
            Self::StoreUnavailable => "temporarily_unavailable",
            Self::InvalidConfig => "owner_configuration_unavailable",
        })
    }
}
impl std::error::Error for BrowserError {}

// Deliberately no Debug: OAuth state may contain private client data.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BrowserRequest {
    pub client_id: String,
    pub redirect_uri: String,
    pub resource: String,
    pub code_challenge: String,
    pub state: String,
}
/// Secrets have explicitly redacted Debug; no automatic serialization.
pub struct BrowserPage {
    pub cookie: Secret,
    pub csrf: Secret,
    pub authenticated: bool,
    pub remaining_seconds: i64,
    pub(crate) request: BrowserRequest,
}
#[derive(Clone)]
pub struct BrowserAuth {
    pub(crate) store: IdentityStore,
    password_work: Arc<Semaphore>,
}
impl BrowserAuth {
    pub fn new(store: IdentityStore) -> Self {
        Self {
            store,
            password_work: Arc::new(Semaphore::new(2)),
        }
    }
}
