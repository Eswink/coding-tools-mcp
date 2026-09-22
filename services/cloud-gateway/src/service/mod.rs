//! Identity-only executable boundary. Local workspace execution is never authorized here.
mod cli;
mod input;
mod lifecycle;
mod runtime;

pub use cli::run;
pub use input::{read_protected, GatewayConfig};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServiceError {
    Arguments,
    Configuration,
    Input,
    FileProtection,
    FileAclUnsupported,
    Store,
    Identity,
    Provisioning,
    NotReady,
    Bind,
    Shutdown,
}
impl std::fmt::Display for ServiceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Arguments => "invalid_arguments",
            Self::Configuration => "invalid_service_configuration",
            Self::Input => "invalid_secret_input",
            Self::FileProtection => "file_protection_failed",
            Self::FileAclUnsupported => "secret_file_acl_unverified_use_stdin",
            Self::Store => "identity_store_unavailable",
            Self::Identity => "identity_configuration_mismatch",
            Self::Provisioning => "provisioning_rejected",
            Self::NotReady => "provisioning_not_ready",
            Self::Bind => "listener_unavailable",
            Self::Shutdown => "shutdown_incomplete",
        })
    }
}
impl std::error::Error for ServiceError {}
pub type Result<T> = std::result::Result<T, ServiceError>;

mod control_cli;
mod control_selection;
pub use control_cli::run_control;
