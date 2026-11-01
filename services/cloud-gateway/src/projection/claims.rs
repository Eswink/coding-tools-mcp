use crate::{crypto::valid_digest, device::EnrolledDevice, grant::LOCAL_SCOPES};
use crate::{IdentityError, PublicIdentity, Result};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub const MAX_SNAPSHOT_SECONDS: i64 = 60;
/// A1 C7 (SPEC §3.3): one signed projection revision carries at most this many workers.
pub const MAX_PROJECTED_WORKERS: usize = 8;
const DOMAIN_V1: &[u8] = b"coding-tools-authority-projection-v1\0";
const DOMAIN_V2: &[u8] = b"coding-tools-authority-projection-v2\0";
const MAX_GRANT_SECONDS: i64 = 30 * 86400;
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
/// A1 C7 (SPEC §3.3): a worker of the CURRENT grant's conversation. A pre-filter for
/// the gateway only; the native host repeats the authoritative owner check.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct WorkerClaim {
    pub id: String,
    pub conversation: String,
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
    /// Version 2 only (absent = empty, so a v1 payload never carries workers).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub workers: Vec<WorkerClaim>,
}
pub struct VerifiedSnapshot(pub(super) ProjectionClaims);
impl std::fmt::Debug for VerifiedSnapshot {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("VerifiedSnapshot([REDACTED])")
    }
}
/// Sign the returned bytes, not a reparsed/reserialized representation.
/// Version 1 domain: still accepted for one transition version (no workers).
pub fn projection_message(payload: &[u8]) -> Result<Vec<u8>> {
    domain_message(DOMAIN_V1, payload)
}
/// A1 C7: version 2 domain (claims `version: 2`, may carry `workers`).
pub fn projection_message_v2(payload: &[u8]) -> Result<Vec<u8>> {
    domain_message(DOMAIN_V2, payload)
}
fn domain_message(domain: &[u8], payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 8192 {
        return Err(IdentityError::InvalidProof);
    }
    let mut message = domain.to_vec();
    message.extend_from_slice(payload);
    Ok(message)
}
pub fn verify_snapshot(
    identity: &PublicIdentity,
    device: &EnrolledDevice,
    payload: &[u8],
    signature: &[u8],
    at: i64,
) -> Result<VerifiedSnapshot> {
    // The signed domain fixes the version: a v1 signature cannot vouch for a v2 payload.
    let key = UnparsedPublicKey::new(&ED25519, &device.public_key);
    let version = if key
        .verify(&projection_message_v2(payload)?, signature)
        .is_ok()
    {
        2
    } else {
        key.verify(&projection_message(payload)?, signature)
            .map_err(|_| IdentityError::InvalidProof)?;
        1
    };
    let c: ProjectionClaims =
        serde_json::from_slice(payload).map_err(|_| IdentityError::InvalidProof)?;
    if c.version != version
        || (version == 1 && !c.workers.is_empty())
        || c.issuer != identity.issuer()
        || c.resource != identity.resource()
        || c.connector != identity.connector()
        || c.connector != device.connector
        || c.device != device.id
        || c.device_epoch != device.epoch
        || c.device_epoch <= 0
        || c.gateway_boot.is_nil()
        || !valid_digest(&c.challenge)
        || c.revision <= 0
        || c.authority_epoch <= 0
    {
        return Err(IdentityError::InvalidProof);
    }
    c.validate_time(at)?;
    c.state().validate_shape()?;
    if c.drained_grant.is_some_and(|g| g.is_nil())
        || (c.drained_grant.is_some() && c.phase != ProjectionPhase::Free)
    {
        return Err(IdentityError::InvalidProof);
    }
    Ok(VerifiedSnapshot(c))
}
impl ProjectionClaims {
    pub(super) fn validate_time(&self, at: i64) -> Result<()> {
        if self.issued_at < 0
            || self.issued_at > at
            || self.valid_until <= at
            || !self
                .valid_until
                .checked_sub(self.issued_at)
                .is_some_and(|n| (1..=MAX_SNAPSHOT_SECONDS).contains(&n))
            || (self.phase == ProjectionPhase::Active
                && self
                    .grant
                    .as_ref()
                    .is_none_or(|g| g.expires_at <= at || g.issued_at > at))
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
    pub(super) fn state(&self) -> ProjectedState {
        ProjectedState {
            phase: self.phase,
            execution: self.execution,
            authority_epoch: self.authority_epoch,
            grant: self.grant.clone(),
            last_drained_grant: self.drained_grant,
            workers: self.workers.clone(),
        }
    }
}
/// The only snapshot fields persisted. No signature payload, challenge or raw session.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ProjectedState {
    pub phase: ProjectionPhase,
    pub execution: ExecutionState,
    pub authority_epoch: i64,
    pub grant: Option<LocalLease>,
    // Minimal receipt, not an authorization. Retained so a lost acknowledgement
    // can be reconciled with a fresh signed proof without inventing a new grant.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub last_drained_grant: Option<Uuid>,
    // A1 C7: absent = no workers, so a state without workers stays byte-identical
    // to the pre-C7 encoding. A pre-C7 gateway rejects a persisted non-empty list
    // (deny_unknown_fields) until the next v1 projection overwrites it.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub workers: Vec<WorkerClaim>,
}
impl ProjectedState {
    pub fn validate_shape(&self) -> Result<()> {
        if self.authority_epoch <= 0
            || self
                .last_drained_grant
                .is_some_and(|id| id.is_nil() || self.phase != ProjectionPhase::Free)
            || (self.phase != ProjectionPhase::Active && self.execution != ExecutionState::Offline)
            || (self.phase == ProjectionPhase::Free && self.grant.is_some())
            || (matches!(
                self.phase,
                ProjectionPhase::Active | ProjectionPhase::Draining
            ) && self.grant.is_none())
        {
            return Err(IdentityError::InvalidProof);
        }
        if let Some(g) = &self.grant {
            if g.id.is_nil()
                || !valid_digest(&g.conversation)
                || g.issued_at < 0
                || !g
                    .expires_at
                    .checked_sub(g.issued_at)
                    .is_some_and(|n| (1..=MAX_GRANT_SECONDS).contains(&n))
                || g.scopes.is_empty()
                || g.scopes.len() > LOCAL_SCOPES.len()
                || g.scopes.iter().any(|s| !LOCAL_SCOPES.contains(&s.as_str()))
                || g.scopes
                    .iter()
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != g.scopes.len()
            {
                return Err(IdentityError::InvalidProof);
            }
        }
        if !self.workers.is_empty() {
            let Some(g) = &self.grant else {
                return Err(IdentityError::InvalidProof);
            };
            if self.workers.len() > MAX_PROJECTED_WORKERS
                || self
                    .workers
                    .iter()
                    .any(|w| !valid_worker_id(&w.id) || w.conversation != g.conversation)
                || self
                    .workers
                    .iter()
                    .map(|w| w.id.as_str())
                    .collect::<std::collections::BTreeSet<_>>()
                    .len()
                    != self.workers.len()
            {
                return Err(IdentityError::InvalidProof);
            }
        }
        Ok(())
    }
    /// A1 C7: whether `(worker, conversation)` is in this projection. A pre-filter only.
    pub fn owns_worker(&self, conversation: &str, worker: &str) -> bool {
        self.grant
            .as_ref()
            .is_some_and(|g| g.conversation == conversation)
            && self
                .workers
                .iter()
                .any(|w| w.id == worker && w.conversation == conversation)
    }
}
/// 32 lowercase hex (the native WorkerStore id format).
pub fn valid_worker_id(id: &str) -> bool {
    id.len() == 32 && id.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}
/// Enforce the durable drain barrier, independent of transport availability/time.
pub(super) fn transition(
    previous: Option<&ProjectedState>,
    next: &ProjectionClaims,
    floor: i64,
) -> Result<i64> {
    use ProjectionPhase::*;
    let state = next.state();
    state.validate_shape()?;
    if state.grant.is_some() && state.authority_epoch <= floor {
        return Err(IdentityError::InvalidProof);
    }
    if let Some(p) = previous {
        if state.authority_epoch < p.authority_epoch {
            return Err(IdentityError::InvalidProof);
        }
        match p.phase {
            Free => {
                if next.drained_grant.is_some()
                    && !(state.phase == Free
                        && state.authority_epoch == p.authority_epoch
                        && next.drained_grant == p.last_drained_grant)
                {
                    return Err(IdentityError::InvalidProof);
                }
            }
            Active | Draining | RecoveryRequired => {
                let free_from_drain = p.phase == Draining
                    && state.phase == Free
                    && next.drained_grant == p.grant.as_ref().map(|g| g.id)
                    && state.authority_epoch == p.authority_epoch;
                let free_from_empty_recovery = p.phase == RecoveryRequired
                    && p.grant.is_none()
                    && state.phase == Free
                    && next.drained_grant.is_none();
                let retaining = state.phase != Free
                    && next.drained_grant.is_none()
                    && state.grant == p.grant
                    && state.authority_epoch == p.authority_epoch
                    && !(p.phase != Active && state.phase == Active);
                if !(free_from_drain || free_from_empty_recovery || retaining) {
                    return Err(IdentityError::InvalidProof);
                }
            }
        }
    } else if next.drained_grant.is_some() {
        return Err(IdentityError::InvalidProof);
    }
    Ok(if state.phase == Free {
        floor.max(state.authority_epoch)
    } else {
        floor
    })
}

#[cfg(test)]
mod c7_tests {
    use super::*;
    fn state(workers: Vec<WorkerClaim>) -> ProjectedState {
        ProjectedState {
            phase: ProjectionPhase::Active,
            execution: ExecutionState::Online,
            authority_epoch: 3,
            grant: Some(LocalLease {
                id: Uuid::from_u128(5),
                conversation: "A".repeat(43),
                issued_at: 1,
                expires_at: 100,
                scopes: vec!["agents.manage".into()],
            }),
            last_drained_grant: None,
            workers,
        }
    }
    fn w(id: &str, conversation: &str) -> WorkerClaim {
        WorkerClaim {
            id: id.into(),
            conversation: conversation.into(),
        }
    }
    #[test]
    fn c7_state_without_workers_is_byte_identical_to_the_pre_c7_encoding() {
        let text = serde_json::to_string(&state(vec![])).unwrap();
        assert_eq!(
            text,
            r#"{"phase":"active","execution":"online","authority_epoch":3,"grant":{"id":"00000000-0000-0000-0000-000000000005","conversation":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","issued_at":1,"expires_at":100,"scopes":["agents.manage"]}}"#
        );
        let back: ProjectedState = serde_json::from_str(&text).unwrap();
        assert!(back.workers.is_empty());
    }
    #[test]
    fn c7_owns_worker_requires_the_grant_conversation_and_a_listed_id() {
        let conv = "A".repeat(43);
        let id = "ab".repeat(16);
        let s = state(vec![w(&id, &conv)]);
        assert!(s.validate_shape().is_ok());
        assert!(s.owns_worker(&conv, &id));
        assert!(!s.owns_worker(&conv, &"cd".repeat(16)));
        assert!(!s.owns_worker(&"B".repeat(43), &id));
        let mut free = state(vec![]);
        free.grant = None;
        assert!(!free.owns_worker(&conv, &id));
        // A persisted foreign-conversation entry is a shape violation, not ownership.
        assert!(state(vec![w(&id, &"B".repeat(43))])
            .validate_shape()
            .is_err());
    }
    #[test]
    fn c7_valid_worker_id_is_exactly_32_lowercase_hex() {
        assert!(valid_worker_id(&"0123456789abcdef".repeat(2)));
        for bad in [
            "",
            "ABCDEF0123456789ABCDEF0123456789",
            "0123456789abcdef0123456789abcde",
        ] {
            assert!(!valid_worker_id(bad));
        }
        assert!(!valid_worker_id(&"0".repeat(33)));
    }
}
