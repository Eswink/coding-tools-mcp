//! Outbound native link. Transport authentication is never local authority.
mod canonical;
mod config;
mod journal;
mod projection;
mod transport;
mod wire;

pub use config::{DeviceConfig, DeviceKey};
pub use journal::{ClaimOutcome, Journal};
pub use transport::NativeLink;
pub use wire::{ExecutionBinding, ExecutionRequest, NativeGrant, PeerBinding};

use futures_util::future::BoxFuture;
use serde_json::Value;
use std::sync::{atomic::{AtomicBool, AtomicI64, Ordering}, Arc};
use thiserror::Error;

pub type Result<T> = std::result::Result<T, LinkError>;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Error)]
pub enum LinkError {
    #[error("native link configuration rejected")]
    Configuration,
    #[error("native device credentials rejected")]
    Credentials,
    #[error("native link protocol rejected")]
    Protocol,
    #[error("configured gateway TLS identity rejected")]
    Tls,
    #[error("native link transport unavailable")]
    Transport,
    #[error("native link stopped")]
    Stopped,
    #[error("local durable execution journal requires recovery")]
    Journal,
    #[error("local execution capacity exhausted")]
    Capacity,
    #[error("current local approval is required")]
    NotApproved,
    #[error("request identity conflicts with durable history")]
    ReplayConflict,
    #[error("request has already been durably claimed; execution is not replayed")]
    AlreadyRecorded,
    #[error("tool output exceeded the transport bound")]
    OutputTooLarge,
}

pub(crate) fn now() -> Result<i64> {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .ok().and_then(|d| i64::try_from(d.as_secs()).ok()).ok_or(LinkError::Protocol)
}

/// Created only after WSS identity verification and enrolled-device authentication.
/// There is intentionally no Deserialize or public constructor for this capability.
#[derive(Clone)]
pub struct Session(Arc<SessionInner>);
struct SessionInner {
    issuer: String,
    peer: PeerBinding,
    live: AtomicBool,
    lease_until: AtomicI64,
    absolute_until: i64,
}
impl Session {
    pub fn issuer(&self) -> &str { &self.0.issuer }
    pub fn peer(&self) -> &PeerBinding { &self.0.peer }
    pub fn is_current(&self) -> bool {
        now().is_ok_and(|at| self.0.live.load(Ordering::Acquire)
            && at < self.0.lease_until.load(Ordering::Acquire)
            && at < self.0.absolute_until)
    }
    pub fn expires_at(&self) -> i64 {
        self.0.lease_until.load(Ordering::Acquire).min(self.0.absolute_until)
    }
    pub(crate) fn established(issuer: String, peer: PeerBinding, at: i64) -> Result<Self> {
        peer.validate()?;
        Ok(Self(Arc::new(SessionInner { issuer, peer, live: AtomicBool::new(true),
            lease_until: AtomicI64::new(at.checked_add(30).ok_or(LinkError::Protocol)?),
            absolute_until: at.checked_add(3600).ok_or(LinkError::Protocol)? })))
    }
    pub(crate) fn renew(&self, heartbeat_sent_at: i64) -> Result<()> {
        if !self.is_current() { return Err(LinkError::Protocol); }
        let until = heartbeat_sent_at.checked_add(30).ok_or(LinkError::Protocol)?
            .min(self.0.absolute_until);
        self.0.lease_until.fetch_max(until, Ordering::AcqRel);
        Ok(())
    }
    pub(crate) fn close(&self) { self.0.live.store(false, Ordering::Release); }
}
impl std::fmt::Debug for Session {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Session([REDACTED])")
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LocalPhase { Free, Pending, Active, Draining, RecoveryRequired }

/// Read only from the native authorizer. It cannot be deserialized from the wire.
/// Proof is an opaque native snapshot, never constructed from a cloud request.
#[derive(Clone)]
pub struct Observation<P> {
    pub phase: LocalPhase,
    pub native_epoch: u64,
    pub native_revision: u64,
    pub execution_generation: u64,
    pub execution_enabled: bool,
    pub recovery_ready: bool,
    pub drain_safe: bool,
    pub grant: Option<NativeGrant>,
    pub proof: Option<P>,
}

/// A validated control request may request a local pending decision, not approve it.
pub struct ApprovalCall {
    pub(crate) session: Session,
    pub(crate) request: wire::ApprovalRequest,
}
impl ApprovalCall {
    pub fn session(&self) -> &Session { &self.session }
    pub fn conversation(&self) -> &str { &self.request.binding.conversation }
    pub fn scopes(&self) -> &[String] { &self.request.scopes }
    pub fn status_only(&self) -> bool { self.request.status_only }
    pub fn deadline(&self) -> i64 { self.request.binding.deadline }
}

/// A locally generated proof is paired with an exact wire request after signature,
/// generation, digest, scope and lifetime validation. Host MUST still perform its
/// final local-authority check immediately before the real tool side effect.
pub struct ExecutionCall<P> {
    pub(crate) session: Session,
    pub(crate) request: ExecutionRequest,
    pub(crate) proof: P,
}
impl<P> ExecutionCall<P> {
    pub fn session(&self) -> &Session { &self.session }
    pub fn request(&self) -> &ExecutionRequest { &self.request }
    pub fn proof(&self) -> &P { &self.proof }
    pub fn into_parts(self) -> (Session, ExecutionRequest, P) {
        (self.session, self.request, self.proof)
    }
}

/// Implemented by the actual desktop authorizer/runtime, not a cloud principal.
pub trait NativeHost: Send + Sync + 'static {
    type Proof: Clone + Send + Sync + 'static;
    fn connected(&self, session: &Session) -> Result<()>;
    fn observe<'a>(&'a self, session: &'a Session) -> BoxFuture<'a, Result<Observation<Self::Proof>>>;
    fn approval(&self, call: ApprovalCall) -> BoxFuture<'_, Result<Value>>;
    fn execute(&self, call: ExecutionCall<Self::Proof>) -> BoxFuture<'_, Result<Value>>;
}

pub(crate) fn tool_error(code: &'static str) -> Value {
    serde_json::json!({"ok":false,"error":{"code":code,"category":"execution",
        "retryable":false,"message":"Local execution was not accepted or its outcome requires reconciliation."}})
}
