//! Device-owned signed approval primitive. Not a complete distributed grant store.
use crate::{crypto::valid_digest, device::EnrolledDevice, IdentityError, PublicIdentity, Result};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub const LOCAL_SCOPES: &[&str] = &[
    "workspace.read",
    "files.read",
    "files.write",
    "exec.run",
    "task.read",
    "task.manage",
    "history.read",
    "history.write",
    "harness.write",
];
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GrantClaims {
    pub issuer: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub conversation: String,
    pub epoch: i64,
    pub issued_at: i64,
    pub expires_at: i64,
    pub scopes: Vec<String>,
}
pub struct VerifiedGrant {
    claims: GrantClaims,
}
impl VerifiedGrant {
    pub fn allows(&self, scope: &str, conversation: &str, local_epoch: i64, now: i64) -> bool {
        self.claims.conversation == conversation
            && self.claims.epoch == local_epoch
            && now >= self.claims.issued_at
            && now < self.claims.expires_at
            && self.claims.scopes.iter().any(|s| s == scope)
    }
}
pub fn grant_message(payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 4096 {
        return Err(IdentityError::InvalidProof);
    }
    let mut msg = b"coding-tools-local-grant-v1\0".to_vec();
    msg.extend_from_slice(payload);
    Ok(msg)
}
/// registered must be freshly read from the device registry, never reconstructed from claims.
/// The Agent must still compare with its own active local grant, epoch, scopes and execution gate.
pub fn verify_grant(
    identity: &PublicIdentity,
    registered: &EnrolledDevice,
    payload: &[u8],
    signature: &[u8],
    now: i64,
) -> Result<VerifiedGrant> {
    let msg = grant_message(payload)?;
    UnparsedPublicKey::new(&ED25519, &registered.public_key)
        .verify(&msg, signature)
        .map_err(|_| IdentityError::InvalidProof)?;
    let c: GrantClaims =
        serde_json::from_slice(payload).map_err(|_| IdentityError::InvalidProof)?;
    if c.issuer != identity.issuer()
        || c.connector != identity.connector()
        || c.connector != registered.connector
        || c.device != registered.id
        || c.epoch != registered.epoch
        || !valid_digest(&c.conversation)
        || c.issued_at < 0
        || c.issued_at > now
        || c.expires_at <= now
        || c.expires_at <= c.issued_at
        || c.expires_at - c.issued_at > 30 * 86400
        || c.scopes.is_empty()
        || c.scopes.len() > LOCAL_SCOPES.len()
        || c.scopes.iter().any(|s| !LOCAL_SCOPES.contains(&s.as_str()))
        || c.scopes
            .iter()
            .collect::<std::collections::BTreeSet<_>>()
            .len()
            != c.scopes.len()
    {
        return Err(IdentityError::InvalidProof);
    }
    Ok(VerifiedGrant { claims: c })
}
