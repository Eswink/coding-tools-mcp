//! Exact-byte proof and bounded control wire types; no execution payloads.
use crate::{
    crypto::valid_digest, device::EnrolledDevice, IdentityError, PublicIdentity, Result, Secret,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::signature::{UnparsedPublicKey, ED25519};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub const SUBPROTOCOL: &str = "coding-tools-agent.v1";
pub const MAX_MESSAGE: usize = 16_384;
pub const LEASE_SECONDS: i64 = 30;
pub const AUTH_SECONDS: i64 = 10;
pub const MAX_AGE_SECONDS: i64 = 3600;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConnectChallenge {
    pub version: u8,
    pub issuer: String,
    pub resource: String,
    pub connector: Uuid,
    pub gateway_boot: Uuid,
    pub attempt: Uuid,
    pub nonce: String,
    pub issued_at: i64,
    pub expires_at: i64,
}
impl ConnectChallenge {
    pub(crate) fn fresh(identity: &PublicIdentity, boot: Uuid, at: i64) -> Result<Self> {
        Ok(Self {
            version: 1,
            issuer: identity.issuer(),
            resource: identity.resource(),
            connector: identity.connector(),
            gateway_boot: boot,
            attempt: Uuid::new_v4(),
            nonce: Secret::random()?.expose().into(),
            issued_at: at,
            expires_at: at
                .checked_add(AUTH_SECONDS)
                .ok_or(IdentityError::InvalidProof)?,
        })
    }
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConnectClaims {
    pub version: u8,
    pub issuer: String,
    pub resource: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub gateway_boot: Uuid,
    pub attempt: Uuid,
    pub nonce: String,
    pub issued_at: i64,
    pub expires_at: i64,
}
/// Use only after the local client checks the configured WSS endpoint/identity.
/// This signs connection presence, never a grant or cloud-supplied execution request.
pub fn connect_message(payload: &[u8]) -> Result<Vec<u8>> {
    if payload.is_empty() || payload.len() > 4096 {
        return Err(IdentityError::InvalidProof);
    }
    let mut msg = b"coding-tools-agent-connect-v1\0".to_vec();
    msg.extend_from_slice(payload);
    Ok(msg)
}
pub fn verify_connect(
    identity: &PublicIdentity,
    registered: &EnrolledDevice,
    challenge: &ConnectChallenge,
    payload: &[u8],
    signature: &[u8],
    at: i64,
) -> Result<()> {
    let msg = connect_message(payload)?;
    if signature.len() != 64 {
        return Err(IdentityError::InvalidProof);
    }
    UnparsedPublicKey::new(&ED25519, &registered.public_key)
        .verify(&msg, signature)
        .map_err(|_| IdentityError::InvalidProof)?;
    let c: ConnectClaims =
        serde_json::from_slice(payload).map_err(|_| IdentityError::InvalidProof)?;
    if c.version != 1
        || challenge.version != 1
        || c.issuer != identity.issuer()
        || c.resource != identity.resource()
        || c.issuer != challenge.issuer
        || c.resource != challenge.resource
        || c.connector != identity.connector()
        || c.connector != registered.connector
        || c.connector != challenge.connector
        || c.device != registered.id
        || c.device.is_nil()
        || c.device_epoch != registered.epoch
        || c.device_epoch <= 0
        || c.gateway_boot != challenge.gateway_boot
        || c.gateway_boot.is_nil()
        || c.attempt != challenge.attempt
        || c.attempt.is_nil()
        || !valid_digest(&c.nonce)
        || c.nonce != challenge.nonce
        || c.issued_at != challenge.issued_at
        || c.expires_at != challenge.expires_at
        || c.issued_at < 0
        || c.issued_at > at
        || c.expires_at <= at
        || c.expires_at.checked_sub(c.issued_at) != Some(AUTH_SECONDS)
    {
        return Err(IdentityError::InvalidProof);
    }
    Ok(())
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SignedPayload {
    pub payload: String,
    pub signature: String,
}
impl SignedPayload {
    pub fn decode(&self, max: usize) -> Result<(Vec<u8>, Vec<u8>)> {
        if self.payload.len() > max * 4 / 3 + 4 || self.signature.len() != 86 {
            return Err(IdentityError::InvalidProof);
        }
        let bytes = URL_SAFE_NO_PAD
            .decode(&self.payload)
            .map_err(|_| IdentityError::InvalidProof)?;
        let sig = URL_SAFE_NO_PAD
            .decode(&self.signature)
            .map_err(|_| IdentityError::InvalidProof)?;
        if bytes.is_empty() || bytes.len() > max || sig.len() != 64 {
            return Err(IdentityError::InvalidProof);
        }
        Ok((bytes, sig))
    }
}
#[derive(Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum ControlMessage {
    Heartbeat { seq: i64 },
    ProjectionChallenge { seq: i64 },
    Projection { seq: i64, proof: SignedPayload },
}
impl ControlMessage {
    pub(crate) fn sequence(&self) -> i64 {
        match self {
            Self::Heartbeat { seq }
            | Self::ProjectionChallenge { seq }
            | Self::Projection { seq, .. } => *seq,
        }
    }
}
