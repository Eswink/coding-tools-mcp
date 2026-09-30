//! Device-signed projection wire assertions; native host state is the authority.
use crate::{IdentityError, Result};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
pub const MAX_SNAPSHOT_SECONDS: i64 = 60;
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ProjectionPhase {
    Free,
    Active,
    Draining,
    RecoveryRequired,
}
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionState {
    Online,
    Offline,
}
/// Original local grant. Heartbeats cannot change its ID, scope set or lifetime.
#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalLease {
    pub id: Uuid,
    pub conversation: String,
    pub issued_at: i64,
    pub expires_at: i64,
    pub scopes: Vec<String>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectionClaims {
    pub version: u32,
    pub issuer: String,
    pub resource: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub gateway_boot: Uuid,
    pub challenge: String,
    pub revision: i64,
    pub authority_epoch: i64,
    pub issued_at: i64,
    pub valid_until: i64,
    pub phase: ProjectionPhase,
    pub execution: ExecutionState,
    pub grant: Option<LocalLease>,
    pub drained_grant: Option<Uuid>,
}
pub fn projection_message(payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 8192 {
        return Err(IdentityError::InvalidProof);
    }
    let mut message = b"coding-tools-authority-projection-v1\0".to_vec();
    message.extend_from_slice(payload);
    Ok(message)
}
