//! Native recovery-only control Agent. No shell, file tools, grant or remote signing API.
mod cli;
mod client;
mod config;
mod journal;
mod signer;
mod wire;

pub use cli::run;
pub use config::AgentConfig;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentError {
    Arguments,
    Configuration,
    Credentials,
    Journal,
    Protocol,
    Authentication,
    Tls,
    Transport,
    Exhausted,
    Cancelled,
}
impl std::fmt::Display for AgentError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::Arguments => "agent_invalid_arguments",
            Self::Configuration => "agent_invalid_configuration",
            Self::Credentials => "agent_credentials_rejected",
            Self::Journal => "agent_journal_requires_local_review",
            Self::Protocol => "agent_protocol_rejected",
            Self::Authentication => "agent_authentication_rejected",
            Self::Tls => "agent_tls_rejected",
            Self::Transport => "agent_transport_interrupted",
            Self::Exhausted => "agent_retry_budget_exhausted",
            Self::Cancelled => "agent_cancelled",
        })
    }
}
impl std::error::Error for AgentError {}
type Result<T> = std::result::Result<T, AgentError>;

#[cfg(test)]
mod tests;
