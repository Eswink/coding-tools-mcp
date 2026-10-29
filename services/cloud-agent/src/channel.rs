//! Client wire codec, deliberately distinct from server authority objects.
use crate::{IdentityError, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
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
    Heartbeat {
        seq: i64,
    },
    ExecutionReady {
        seq: i64,
        version: u8,
    },
    ApprovalReady {
        seq: i64,
        version: u8,
    },
    ApprovalReply {
        seq: i64,
        reply: Box<crate::approval::ApprovalReply>,
    },
    ExecutionReply {
        seq: i64,
        reply: Box<crate::execution::ExecutionReply>,
    },
    ProjectionChallenge {
        seq: i64,
    },
    Projection {
        seq: i64,
        proof: SignedPayload,
    },
}
