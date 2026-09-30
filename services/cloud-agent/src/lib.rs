//! Database-free live Agent runtime shared by the gateway integration tests and
//! the native desktop. Wire declarations are client-side protocol assertions,
//! never server grants or a source of local execution permission.
pub mod agent;
pub mod approval;
mod canonical;
pub mod catalog;
pub mod channel;
pub mod execution;
mod identity;
pub mod lifecycle;
pub mod managed;
pub mod projection;
#[cfg(unix)]
mod secure_io;
pub mod work;
pub use agent::host::{HostAgent, HostAuthoritySnapshot, HostFuture, LocalHost};
pub use agent::{AgentConfig, AgentError};
pub use identity::PublicIdentity;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtocolError {
    InvalidConfig,
    InvalidRequest,
    InvalidProof,
}
impl std::fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("agent_protocol_validation_failed")
    }
}
impl std::error::Error for ProtocolError {}
type IdentityError = ProtocolError;
type Result<T> = std::result::Result<T, ProtocolError>;

pub mod crypto {
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
    pub fn valid_digest(value: &str) -> bool {
        value.len() == 43 && URL_SAFE_NO_PAD.decode(value).is_ok_and(|v| v.len() == 32)
    }
}
pub mod grant {
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
}
