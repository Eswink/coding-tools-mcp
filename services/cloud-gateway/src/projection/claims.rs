use crate::{crypto::valid_digest, device::EnrolledDevice, grant::LOCAL_SCOPES};
use crate::{IdentityError, PublicIdentity, Result};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub const MAX_SNAPSHOT_SECONDS: i64 = 60;
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
pub struct VerifiedSnapshot(pub(super) ProjectionClaims);
impl std::fmt::Debug for VerifiedSnapshot {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("VerifiedSnapshot([REDACTED])")
    }
}
/// Sign the returned bytes, not a reparsed/reserialized representation.
pub fn projection_message(payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 8192 {
        return Err(IdentityError::InvalidProof);
    }
    let mut message = b"coding-tools-authority-projection-v1\0".to_vec();
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
    let message = projection_message(payload)?;
    UnparsedPublicKey::new(&ED25519, &device.public_key)
        .verify(&message, signature)
        .map_err(|_| IdentityError::InvalidProof)?;
    let c: ProjectionClaims =
        serde_json::from_slice(payload).map_err(|_| IdentityError::InvalidProof)?;
    if c.version != 1
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
}
impl ProjectedState {
    pub fn validate_shape(&self) -> Result<()> {
        if self.authority_epoch <= 0
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
        Ok(())
    }
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
                if next.drained_grant.is_some() {
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
