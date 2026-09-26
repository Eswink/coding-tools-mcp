use crate::{IdentityError, Result};
use serde_json::{json, Value};
use url::Url;
use uuid::Uuid;

#[derive(Clone, Debug)]
pub struct PublicIdentity {
    origin: String,
    authority: String,
    prefix: String,
    connector: Uuid,
}
impl PublicIdentity {
    pub fn new(origin: &str, prefix: &str, connector: Uuid) -> Result<Self> {
        let url = Url::parse(origin).map_err(|_| IdentityError::InvalidConfig)?;
        if url.scheme() != "https"
            || url.host_str().is_none()
            || !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
            || url.path() != "/"
            || origin.trim() != origin
            || connector.is_nil()
            || prefix.len() > 64
            || !prefix.starts_with('/')
            || prefix.ends_with('/')
            || !prefix[1..]
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        {
            return Err(IdentityError::InvalidConfig);
        }
        let canonical = url.origin().ascii_serialization();
        // No silent normalization of configured OAuth identity.
        if origin != canonical {
            return Err(IdentityError::InvalidConfig);
        }
        Ok(Self {
            authority: canonical.trim_start_matches("https://").into(),
            origin: canonical,
            prefix: prefix.into(),
            connector,
        })
    }
    pub fn origin(&self) -> &str {
        &self.origin
    }
    pub fn authority(&self) -> &str {
        &self.authority
    }
    pub fn prefix(&self) -> &str {
        &self.prefix
    }
    pub fn connector(&self) -> Uuid {
        self.connector
    }
    pub fn issuer(&self) -> String {
        format!("{}{}/oauth", self.origin, self.prefix)
    }
    pub fn resource(&self) -> String {
        format!("{}{}", self.origin, self.resource_path())
    }
    pub fn resource_path(&self) -> String {
        format!("{}/mcp/{}", self.prefix, self.connector)
    }
    pub fn token_path(&self) -> String {
        format!("{}/oauth/token", self.prefix)
    }
    pub fn resource_metadata_path(&self) -> String {
        format!(
            "/.well-known/oauth-protected-resource{}",
            self.resource_path()
        )
    }
    pub fn server_metadata_path(&self) -> String {
        format!(
            "/.well-known/oauth-authorization-server{}/oauth",
            self.prefix
        )
    }
    pub fn resource_metadata(&self) -> Value {
        json!({"resource":self.resource(),
        "authorization_servers":[self.issuer()],"scopes_supported":["mcp"],
        "bearer_methods_supported":["header"]})
    }
    pub fn server_metadata(&self) -> Value {
        json!({"issuer":self.issuer(),
        "authorization_endpoint":format!("{}/authorize",self.issuer()),
        "token_endpoint":format!("{}/token",self.issuer()),
        "response_types_supported":["code"],"grant_types_supported":["authorization_code","refresh_token"],
        "code_challenge_methods_supported":["S256"],"scopes_supported":["mcp"],
        "token_endpoint_auth_methods_supported":["client_secret_post","none"]})
    }
    pub(crate) fn allow_origin(&self, raw: &str) -> bool {
        let Ok(u) = Url::parse(raw) else {
            return false;
        };
        u.scheme() == "https"
            && u.username().is_empty()
            && u.password().is_none()
            && u.query().is_none()
            && u.fragment().is_none()
            && u.path() == "/"
            && raw.trim() == raw
            && !raw.ends_with('/')
            && u.origin().ascii_serialization() == self.origin
            // URL parsers repair backslashes and missing authority separators.
            // An Origin header must already be a serialized origin, not a URL
            // that merely normalizes to the configured identity.
            && (raw.eq_ignore_ascii_case(&self.origin)
                || (u.port_or_known_default() == Some(443)
                    && raw.eq_ignore_ascii_case(&format!("{}:443", self.origin))))
    }
}
pub(crate) fn validate_client(id: &str, redirect: &str) -> Result<()> {
    let u = Url::parse(redirect).map_err(|_| IdentityError::InvalidRequest)?;
    if id.is_empty()
        || id.len() > 128
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
        || redirect.len() > 2048
        || redirect.trim() != redirect
        || u.scheme() != "https"
        || u.host_str().is_none()
        || !u.username().is_empty()
        || u.password().is_some()
        || u.fragment().is_some()
        || u.query_pairs()
            .any(|(k, _)| ["code", "state", "iss", "error"].contains(&k.as_ref()))
    {
        return Err(IdentityError::InvalidRequest);
    }
    Ok(())
}
