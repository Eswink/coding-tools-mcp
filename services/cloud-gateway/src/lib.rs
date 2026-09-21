//! Cloud Gateway identity and local-authority components; no local executor.
//!
//! Code issuance and enrollment invitation creation require trusted operator
//! authorization at the caller. Browser consent is the only HTTP code-issuance
//! path; direct operator shortcuts and enrollment invitations remain unexposed.
pub mod browser;
pub mod config;
pub mod crypto;
pub mod device;
pub mod error;
pub mod grant;
pub mod http;
pub mod oauth;
pub mod store;

pub use config::PublicIdentity;
pub use crypto::{Secret, SecretKey};
pub use error::{IdentityError, Result};
pub use oauth::{AuthorizationRequest, ClientCredential, OAuthPrincipal, TokenPair};
pub use store::{IdentityStore, Lifetimes};

/// Standalone identity service and trusted local operator adapter. Not an MCP executor.
pub mod service;

/// Internal-only device-owned authorization projection; not an execution permit.
pub mod projection;
