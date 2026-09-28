//! Exact bounded wire shapes. These data objects are not native authority.
use crate::{canonical::digest_json, LinkError, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

pub(crate) const SUBPROTOCOL: &str = "coding-tools-agent.v1";
pub(crate) const MAX_MESSAGE: usize = 16_384;
pub(crate) const MAX_ARGUMENTS: usize = 4096;
pub(crate) const MAX_RESULT: usize = 8192;
pub(crate) const SCOPES: &[&str] = &[
    "workspace.read", "files.read", "files.write", "exec.run", "task.read",
    "task.manage", "history.read", "history.write", "harness.write",
];
pub(crate) fn valid_digest(value: &str) -> bool {
    value.len() == 43 && URL_SAFE_NO_PAD.decode(value).is_ok_and(|v| v.len() == 32)
}
pub(crate) fn valid_scopes(scopes: &[String]) -> bool {
    !scopes.is_empty() && scopes.len() <= SCOPES.len()
        && scopes.iter().all(|s| SCOPES.contains(&s.as_str()))
        && scopes.iter().collect::<std::collections::BTreeSet<_>>().len() == scopes.len()
}

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
    pub(crate) fn validate(&self) -> Result<()> {
        if [self.connector, self.device, self.gateway_boot, self.channel_session]
            .iter().any(Uuid::is_nil) || self.device_epoch <= 0 || self.channel_generation <= 0 {
            return Err(LinkError::Protocol);
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
    pub(crate) fn validate_at(&self, at: i64) -> Result<()> {
        self.peer.validate()?;
        if self.request_id.is_nil() || self.grant_id.is_nil() || self.grant_revision <= 0
            || self.authority_epoch <= 0 || !valid_digest(&self.conversation)
            || !SCOPES.contains(&self.scope.as_str()) || self.tool.is_empty()
            || self.tool.len() > 128 || !self.tool.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b))
            || at < 0 || self.deadline <= at || self.deadline.checked_sub(at).is_none_or(|n| n > 300) {
            return Err(LinkError::Protocol);
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
    pub(crate) fn validate_at(&self, peer: &PeerBinding, at: i64) -> Result<()> {
        self.binding.validate_at(at)?;
        if &self.binding.peer != peer || !self.arguments.is_object()
            || digest_json(&self.arguments, MAX_ARGUMENTS)? != self.binding.arguments_hash {
            return Err(LinkError::Protocol);
        }
        Ok(())
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ExecutionReply { pub binding: ExecutionBinding, pub result: Value }

#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeGrant {
    pub id: Uuid,
    pub conversation: String,
    pub issued_at: i64,
    pub expires_at: i64,
    pub scopes: Vec<String>,
}
impl NativeGrant {
    pub(crate) fn valid(&self) -> bool {
        !self.id.is_nil() && valid_digest(&self.conversation) && self.issued_at >= 0
            && self.expires_at.checked_sub(self.issued_at).is_some_and(|n| (1..=30*86400).contains(&n))
            && valid_scopes(&self.scopes)
    }
}

#[derive(Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Phase { Free, Pending, Active, Draining, RecoveryRequired }
#[derive(Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum ExecutionState { Online, Offline }
#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Projected {
    pub phase: Phase,
    pub execution: ExecutionState,
    pub authority_epoch: i64,
    pub grant: Option<NativeGrant>,
    pub drained_grant: Option<Uuid>,
}
#[derive(Serialize)]
pub(crate) struct ProjectionClaims<'a> {
    pub version: u32,
    pub issuer: &'a str,
    pub resource: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub gateway_boot: Uuid,
    pub challenge: &'a str,
    pub revision: i64,
    pub issued_at: i64,
    pub valid_until: i64,
    #[serde(flatten)]
    pub state: &'a Projected,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ConnectChallenge {
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
#[derive(Serialize)]
pub(crate) struct ConnectClaims<'a> {
    pub version: u8,
    pub issuer: &'a str,
    pub resource: String,
    pub connector: Uuid,
    pub device: Uuid,
    pub device_epoch: i64,
    pub gateway_boot: Uuid,
    pub attempt: Uuid,
    pub nonce: &'a str,
    pub issued_at: i64,
    pub expires_at: i64,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SignedPayload { pub payload: String, pub signature: String }

#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ApprovalBinding {
    pub request_id: Uuid,
    pub peer: PeerBinding,
    pub conversation: String,
    pub arguments_hash: [u8; 32],
    pub deadline: i64,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ApprovalRequest {
    pub binding: ApprovalBinding,
    pub scopes: Vec<String>,
    pub status_only: bool,
}
impl ApprovalRequest {
    pub(crate) fn validate_at(&self, peer: &PeerBinding, at: i64) -> Result<()> {
        self.binding.peer.validate()?;
        if &self.binding.peer != peer || self.binding.request_id.is_nil()
            || !valid_digest(&self.binding.conversation) || self.binding.deadline <= at
            || self.binding.deadline.checked_sub(at).is_none_or(|n| n > 15)
            || (self.status_only && !self.scopes.is_empty())
            || (!self.status_only && !valid_scopes(&self.scopes))
            || digest_json(&serde_json::json!({"scopes":self.scopes,"status_only":self.status_only}),1024)? != self.binding.arguments_hash {
            return Err(LinkError::Protocol);
        }
        Ok(())
    }
}
#[derive(Serialize)]
pub(crate) struct ApprovalReply { pub binding: ApprovalBinding, pub result: Value }

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum ServerFrame {
    ConnectChallenge { challenge: ConnectChallenge },
    Connected { heartbeat_seconds: u64, lease_seconds: i64 },
    NativeReadyAck { seq: i64, peer: PeerBinding },
    HeartbeatAck { seq: i64 },
    ProjectionChallenge { seq: i64, gateway_boot: Uuid, nonce: String, expires_at: i64, snapshot_valid_until: i64 },
    ProjectionAck { seq: i64 },
    ExecutionRequest { request: ExecutionRequest },
    ExecutionReplyAck { seq: i64 },
    ApprovalRequest { request: ApprovalRequest },
    ApprovalReplyAck { seq: i64 },
}
impl ServerFrame {
    pub(crate) fn parse(text: &str) -> Result<Self> {
        if text.is_empty() || text.len() > MAX_MESSAGE { return Err(LinkError::Protocol); }
        serde_json::from_str(text).map_err(|_| LinkError::Protocol)
    }
}
#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub(crate) enum ClientFrame {
    NativeReady { seq: i64, version: u8 },
    Heartbeat { seq: i64 },
    ProjectionChallenge { seq: i64 },
    Projection { seq: i64, proof: SignedPayload },
    ExecutionReply { seq: i64, reply: ExecutionReply },
    ApprovalReply { seq: i64, reply: ApprovalReply },
}

macro_rules! redacted {
    ($($t:ty),+) => {$(impl std::fmt::Debug for $t {
        fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result {
            f.write_str(concat!(stringify!($t),"([REDACTED])"))
        }
    })+};
}
redacted!(PeerBinding, ExecutionBinding, ExecutionRequest, ExecutionReply, NativeGrant,
    Phase, ExecutionState, Projected, ApprovalBinding, ApprovalRequest, ApprovalReply);
