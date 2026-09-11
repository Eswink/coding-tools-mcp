//! Verified OAuth identities never originate in tool arguments or OpenAI subject hints.
use jsonwebtoken::{decode, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use super::chat::unix_now;
#[derive(Clone)]
pub(crate) struct VerifiedPrincipal {
    pub issuer: String,
    pub subject: String,
    pub client_id: String,
    pub expires_at: u64,
}
impl VerifiedPrincipal {
    pub fn is_current(&self) -> bool { unix_now() < self.expires_at }
}
#[derive(Serialize, Deserialize)]
struct Claims {
    iss: String, aud: String, sub: String, client_id: String,
    iat: u64, nbf: u64, exp: u64, scope: String, jti: String,
}
pub(crate) fn verify(token: &str, secret: &str, issuer: &str, resource: &str) -> Option<VerifiedPrincipal> {
    if secret.is_empty() || token.len() > 8192 { return None; }
    let issuer = issuer.trim_end_matches('/');
    let mut v = Validation::new(Algorithm::HS256);
    v.set_issuer(&[issuer]); v.set_audience(&[resource]); v.leeway = 0; v.validate_nbf = true;
    v.set_required_spec_claims(&["exp","iss","aud","sub","nbf"]);
    let c = decode::<Claims>(token, &DecodingKey::from_secret(secret.as_bytes()), &v).ok()?.claims;
    if c.sub != "desktop-owner" || c.client_id.is_empty() || c.client_id.len() > 256
        || c.iat > unix_now() || c.exp <= unix_now() || c.exp <= c.iat
        || c.exp - c.iat > 8 * 3600 || !c.scope.split_whitespace().eq(["mcp"])
        || c.jti.is_empty() { return None; }
    Some(VerifiedPrincipal { issuer: c.iss, subject: c.sub, client_id: c.client_id, expires_at: c.exp })
}
pub(crate) fn issue(issuer: &str, resource: &str, secret: &str, client_id: &str, ttl: i64) -> Result<String, ()> {
    if secret.is_empty() || client_id.is_empty() || client_id.len() > 256 || ttl <= 0 || ttl > 8 * 3600 { return Err(()); }
    let now = unix_now();
    let claims = Claims { iss: issuer.into(), aud: resource.into(), sub: "desktop-owner".into(),
        client_id: client_id.into(), iat: now, nbf: now, exp: now + ttl as u64, scope: "mcp".into(),
        jti: uuid::Uuid::new_v4().to_string() };
    encode(&Header::new(Algorithm::HS256), &claims, &EncodingKey::from_secret(secret.as_bytes())).map_err(|_| ())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_wrong_issuer_audience_scope_identity_time_and_signature() {
        let token = issue("https://host", "https://host", "test-secret", "client", 3600).unwrap();
        assert!(verify(&token,"test-secret","https://host","https://host").is_some());
        assert!(verify(&token,"wrong-secret","https://host","https://host").is_none());
        assert!(verify(&token,"test-secret","https://other","https://other").is_none());
        for field in ["aud", "iss", "scope", "sub", "exp", "nbf", "iat", "client_id"] {
            let mut v = Validation::new(Algorithm::HS256); v.validate_aud = false;
            let mut c = decode::<serde_json::Value>(&token,&DecodingKey::from_secret(b"test-secret"),&v).unwrap().claims;
            c[field] = match field { "exp" => 1.into(), "nbf" | "iat" => (unix_now()+3600).into(), "client_id" => "".into(), _ => "wrong".into() };
            let bad = encode(&Header::default(),&c,&EncodingKey::from_secret(b"test-secret")).unwrap();
            assert!(verify(&bad,"test-secret","https://host","https://host").is_none(),"{field}");
        }
    }
    #[test]
    fn rejects_unknown_extra_scopes_and_empty_token_identity() {
        let token = issue("https://host", "https://host", "test-secret", "client", 3600).unwrap();
        let mut validation = Validation::new(Algorithm::HS256);
        validation.validate_aud = false;
        let claims = decode::<serde_json::Value>(&token, &DecodingKey::from_secret(b"test-secret"), &validation).unwrap().claims;
        for scope in ["", "mcp admin", "mcp files.write", "admin mcp", "mcp mcp"] {
            let mut bad = claims.clone();
            bad["scope"] = scope.into();
            let token = encode(&Header::default(), &bad, &EncodingKey::from_secret(b"test-secret")).unwrap();
            assert!(verify(&token, "test-secret", "https://host", "https://host").is_none(), "{scope}");
        }
        let mut bad = claims;
        bad["jti"] = "".into();
        let token = encode(&Header::default(), &bad, &EncodingKey::from_secret(b"test-secret")).unwrap();
        assert!(verify(&token, "test-secret", "https://host", "https://host").is_none());
        assert!(issue("https://host", "https://host", "test-secret", &"c".repeat(257), 3600).is_err());
    }

}
