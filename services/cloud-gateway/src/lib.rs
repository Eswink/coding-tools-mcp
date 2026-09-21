//! Durable identity primitives for the cloud Gateway. Not a public server yet.
//!
//! Code issuance and enrollment invitation creation require trusted operator
//! authorization at the caller. They are deliberately absent from the HTTP adapter.
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
