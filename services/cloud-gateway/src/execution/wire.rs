//! Wire assertions are not execution authority. Only the desktop can admit work.
use crate::{
    admission::canonical_digest, crypto::valid_digest, grant::LOCAL_SCOPES, IdentityError, Result,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

pub const MAX_EXECUTION_ARGUMENTS: usize = 4096;
pub const MAX_EXECUTION_RESULT: usize = 8192;
pub const EXECUTION_VERSION: u8 = 1;

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PeerBinding {
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub gateway_boot: Uuid,
    pub channel_session: Uuid,
    pub channel_generation: i64,
}
impl PeerBinding {
    pub fn validate(&self) -> Result<()> {
        if [
            self.connector,
            self.device,
            self.gateway_boot,
            self.channel_session,
        ]
        .iter()
        .any(Uuid::is_nil)
            || self.device_epoch <= 0
            || self.channel_generation <= 0
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
}
#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionBinding {
    pub request_id: Uuid,
    pub peer: PeerBinding,
    pub grant_id: Uuid,
    pub grant_revision: i64,
    pub authority_epoch: i64,
    pub conversation: String,
    pub scope: String,
    pub tool: String,
    pub arguments_hash: [u8; 32],
    pub deadline: i64,
}
impl ExecutionBinding {
    pub fn validate_at(&self, now: i64) -> Result<()> {
        self.peer.validate()?;
        if self.request_id.is_nil()
            || self.grant_id.is_nil()
            || self.grant_revision <= 0
            || self.authority_epoch <= 0
            || !valid_digest(&self.conversation)
            || !LOCAL_SCOPES.contains(&self.scope.as_str())
            || self.tool.is_empty()
            || self.tool.len() > 128
            || !self
                .tool
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.'))
            || now < 0
            || self.deadline <= now
            || self.deadline.checked_sub(now).is_none_or(|n| n > 300)
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionRequest {
    pub binding: ExecutionBinding,
    pub arguments: Value,
}
impl ExecutionRequest {
    pub fn validate_at(&self, peer: &PeerBinding, now: i64) -> Result<()> {
        self.binding.validate_at(now)?;
        if &self.binding.peer != peer
            || !self.arguments.is_object()
            || canonical_digest(&self.arguments, MAX_EXECUTION_ARGUMENTS)?
                != self.binding.arguments_hash
        {
            return Err(IdentityError::InvalidProof);
        }
        Ok(())
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionReply {
    pub binding: ExecutionBinding,
    pub result: Value,
}
impl ExecutionReply {
    pub fn validate_for(&self, expected: &ExecutionBinding, now: i64) -> Result<[u8; 32]> {
        self.binding.validate_at(now)?;
        if &self.binding != expected
            || !self.result.is_object()
            || self.result.get("ok").and_then(Value::as_bool).is_none()
        {
            return Err(IdentityError::InvalidProof);
        }
        canonical_digest(&self.result, MAX_EXECUTION_RESULT)
    }
}
macro_rules! redacted_debug {
    ($($t:ty),+) => {$ (
        impl std::fmt::Debug for $t {
            fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {f.write_str(concat!(stringify!($t),"([REDACTED])"))}
        }
    )+};
}
redacted_debug!(
    PeerBinding,
    ExecutionBinding,
    ExecutionRequest,
    ExecutionReply
);
