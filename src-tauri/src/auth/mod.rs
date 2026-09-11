#[path = "公网身份v2.rs"]
mod public_origin;
pub use public_origin::PublicOrigin;

#[path = "聊天授权v1.rs"]
pub(crate) mod chat;
#[path = "OAuth身份v1.rs"]
pub(crate) mod principal;
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
#[path = "聊天HTTP夹具v1.rs"]
pub(crate) mod chat_fixture;
#[cfg(test)]
#[path = "聊天HTTP回归v1.rs"]
mod chat_http_tests;

#[cfg(test)]
#[path = "身份联调v2.rs"]
mod identity_tests;

#[cfg(test)]
mod oauth_discovery_tests;
