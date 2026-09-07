#[path = "公网身份v2.rs"]
mod public_origin;
pub use public_origin::PublicOrigin;

mod bearer;
mod oauth;
mod oauth_flow;

pub use bearer::verify_bearer_header;
pub use oauth::{
    authorization_server_metadata, external_base_url, protected_resource_metadata,
};
pub use oauth_flow::{
    authorize_get, authorize_post, token_exchange, verify_oauth_bearer_header, AuthorizeForm,
    AuthorizeParams, OAuthRuntime, TokenForm,
};

#[cfg(test)]
#[path = "身份联调v2.rs"]
mod identity_tests;
