use std::fmt;

/// Fixed classes only. Never put database URLs, SQL parameters or credentials in errors.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IdentityError {
    InvalidConfig,
    StoreUnavailable,
    IdentityMismatch,
    InvalidRequest,
    InvalidClient,
    InvalidGrant,
    InvalidToken,
    Conflict,
    InvalidProof,
}
pub type Result<T> = std::result::Result<T, IdentityError>;
impl fmt::Display for IdentityError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}",
            match self {
                Self::InvalidConfig => "invalid_configuration",
                Self::StoreUnavailable => "identity_store_unavailable",
                Self::IdentityMismatch => "identity_store_configuration_mismatch",
                Self::InvalidRequest => "invalid_request",
                Self::InvalidClient => "invalid_client",
                Self::InvalidGrant => "invalid_grant",
                Self::InvalidToken => "invalid_token",
                Self::Conflict => "identity_conflict",
                Self::InvalidProof => "invalid_proof",
            }
        )
    }
}
impl std::error::Error for IdentityError {}
impl From<sqlx::Error> for IdentityError {
    fn from(_: sqlx::Error) -> Self {
        Self::StoreUnavailable
    }
}
