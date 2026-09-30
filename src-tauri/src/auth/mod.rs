// The cloud adapter is crate-private until the owned sidecar supervisor is wired.
#[cfg_attr(not(test), allow(dead_code))]
pub(crate) mod cloud_context;
mod execution_fence;
#[cfg_attr(not(test), allow(dead_code))]
mod local_authority;
#[cfg_attr(not(test), allow(unused_imports))]
pub(crate) use local_authority::{
    LocalAdmissionPermit, LocalAdmissionTicket, LocalAuthorityPhase, LocalAuthoritySnapshot,
    LocalExecutionState,
};
pub(crate) mod chat_events;
mod exclusive_lease;
pub(crate) mod oauth_refresh;
mod oauth_scope;
#[path = "公网身份v2.rs"]
mod public_origin;
pub(crate) mod session_policy;
pub use public_origin::PublicOrigin;

mod bearer;
#[path = "聊天授权v1.rs"]
pub(crate) mod chat;
mod oauth;
mod oauth_flow;
#[path = "OAuth身份v1.rs"]
pub(crate) mod principal;

pub use bearer::verify_bearer_header;
pub use oauth::{authorization_server_metadata, external_base_url, protected_resource_metadata};
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

#[cfg(test)]
mod exclusive_refresh_http_tests;

#[cfg(test)]
mod offline_safe_privacy_tests;
