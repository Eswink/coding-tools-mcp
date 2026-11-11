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
/// A1 C7 (SPEC §3.3): at most this many workers per signed projection revision.
pub const MAX_PROJECTED_WORKERS: usize = 8;
/// A1 C7: a live worker of the current grant's conversation (gateway pre-filter only).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerClaim {
    pub id: String,
    pub conversation: String,
}
/// 32 lowercase hex (the native WorkerStore id format).
pub fn valid_worker_id(id: &str) -> bool {
    id.len() == 32 && id.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
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
    /// Version 2 only; absent when empty so v1 payloads stay byte-identical.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub workers: Vec<WorkerClaim>,
}
pub fn projection_message(payload: &[u8]) -> Result<Vec<u8>> {
    domain_message(b"coding-tools-authority-projection-v1\0", payload)
}
/// A1 C7: the version 2 domain (claims carry `version: 2` and may list workers).
pub fn projection_message_v2(payload: &[u8]) -> Result<Vec<u8>> {
    domain_message(b"coding-tools-authority-projection-v2\0", payload)
}
fn domain_message(domain: &[u8], payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 8192 {
        return Err(IdentityError::InvalidProof);
    }
    let mut message = domain.to_vec();
    message.extend_from_slice(payload);
    Ok(message)
}
