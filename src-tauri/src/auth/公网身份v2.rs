//! One listener generation owns one shared identity; tunnel restarts publish to
//! that handle rather than rebuilding the listener or persisting a Quick URL.
use std::sync::{Arc, RwLock};

use axum::http::HeaderMap;

use crate::error::{AppError, AppResult};
use crate::workspace::endpoint::normalize_public_origin;

#[derive(Clone, Debug)]
pub struct PublicOrigin {
    value: Arc<RwLock<String>>,
    managed: bool,
}

impl PublicOrigin {
    pub fn managed(origin: &str) -> AppResult<Self> {
        let normalized = if origin.trim().is_empty() {
            String::new()
        } else {
            normalize_public_origin(origin).map_err(AppError::Message)?
        };
        Ok(Self { value: Arc::new(RwLock::new(normalized)), managed: true })
    }

    /// Returns an owned snapshot; no lock is held across network I/O or await.
    pub fn snapshot(&self) -> String {
        self.value.read().map(|value| value.clone()).unwrap_or_default()
    }

    pub fn publish(&self, origin: &str) -> AppResult<()> {
        // Validate before taking the write lock. A rejected update is non-mutating.
        let normalized = normalize_public_origin(origin).map_err(AppError::Message)?;
        let mut value = self.value.write()
            .map_err(|_| AppError::Message("公网身份状态不可用，请重启本地服务。".into()))?;
        *value = normalized;
        Ok(())
    }

    pub fn clear(&self) {
        if let Ok(mut value) = self.value.write() {
            value.clear();
        }
    }

    pub fn resolve(&self, headers: &HeaderMap, port: u16) -> String {
        let value = self.snapshot();
        if self.managed {
            // Before a managed tunnel is ready, do not derive issuer from an
            // untrusted Host/X-Forwarded-Host header or the previous Quick URL.
            if value.is_empty() { format!("http://127.0.0.1:{port}") } else { value }
        } else {
            // Preserve the standalone listener API used by the existing harness.
            super::external_base_url(headers, port, &value)
        }
    }
}

impl From<String> for PublicOrigin {
    fn from(value: String) -> Self {
        Self { value: Arc::new(RwLock::new(value.trim().trim_end_matches('/').to_string())), managed: false }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cloned_consumers_observe_a_single_validated_identity() {
        let origin = PublicOrigin::managed("").unwrap();
        let oauth = origin.clone();
        origin.publish("https://MCP.example.com:443/").unwrap();
        assert_eq!(oauth.snapshot(), "https://mcp.example.com");
    }

    #[test]
    fn rejected_update_preserves_last_good_identity() {
        let origin = PublicOrigin::managed("https://mcp.example.com").unwrap();
        for value in ["", "http://mcp.example.com", "https://mcp.example.com/mcp", "https://user:password@mcp.example.com"] {
            assert!(origin.publish(value).is_err());
            assert_eq!(origin.snapshot(), "https://mcp.example.com");
        }
    }

    #[test]
    fn old_generation_cannot_change_the_new_listener_identity() {
        let old = PublicOrigin::managed("").unwrap();
        let current = PublicOrigin::managed("https://current.example.com").unwrap();
        old.publish("https://late-result.example.com").unwrap();
        assert_eq!(current.snapshot(), "https://current.example.com");
    }

    #[test]
    fn pending_managed_identity_does_not_trust_forwarded_host() {
        let origin = PublicOrigin::managed("").unwrap();
        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-host", "attacker.example.com".parse().unwrap());
        assert_eq!(origin.resolve(&headers, 28766), "http://127.0.0.1:28766");
    }

    #[test]
    fn clearing_a_managed_tunnel_removes_stale_public_identity() {
        let origin = PublicOrigin::managed("https://previous.trycloudflare.com").unwrap();
        origin.clear();
        assert_eq!(origin.snapshot(), "");
        assert_eq!(origin.resolve(&HeaderMap::new(), 8787), "http://127.0.0.1:8787");
    }

    #[test]
    fn stable_configuration_produces_the_same_identity_after_restart() {
        let first = PublicOrigin::managed("https://mcp.example.com/").unwrap();
        let restarted = PublicOrigin::managed("https://mcp.example.com").unwrap();
        assert_eq!(first.snapshot(), restarted.snapshot());
    }
}
