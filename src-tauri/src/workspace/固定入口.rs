//! Public identity and FRP routing are independent of the frps control address.
use serde::{Deserialize, Serialize};
use std::net::IpAddr;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct FrpRouteOptions {
    /// `subdomain` preserves old profiles; `custom` uses the full hostname.
    pub domain_mode: String,
    pub custom_domain: String,
    pub subdomain_host: String,
    pub public_port: u16,
    pub proxy_type: String,
    pub local_ip: String,
    /// None follows the workspace's MCP/Actions port.
    pub local_port: Option<u16>,
    pub https_mode: String,
    pub tls_cert_file: String,
    pub tls_key_file: String,
    pub use_compression: bool,
    /// These are connection-wide settings, not public HTTPS settings.
    pub tcp_mux: bool,
    pub tls_enable: bool,
}

impl Default for FrpRouteOptions {
    fn default() -> Self {
        Self {
            domain_mode: "subdomain".into(),
            custom_domain: String::new(),
            subdomain_host: String::new(),
            public_port: 443,
            proxy_type: "http".into(),
            local_ip: "127.0.0.1".into(),
            local_port: None,
            https_mode: "https2http".into(),
            tls_cert_file: String::new(),
            tls_key_file: String::new(),
            use_compression: false,
            tcp_mux: true,
            tls_enable: true,
        }
    }
}

impl FrpRouteOptions {
    pub fn hostname(&self, server: &str, subdomain: &str) -> Result<String, String> {
        match self.domain_mode.as_str() {
            "custom" => normalize_domain(&self.custom_domain),
            "subdomain" => {
                let prefix = subdomain.trim().to_ascii_lowercase();
                if !valid_label(&prefix) {
                    return Err("子域名前缀必须是 1–63 位字母、数字或连字符，不能以连字符开头或结尾。".into());
                }
                // Legacy DNS servers may supply the old suffix. Never use an IP.
                let suffix = if self.subdomain_host.trim().is_empty() {
                    normalize_domain(server).map_err(|_| {
                        "FRP 服务器是 IP 或不是有效的域名后缀：请填写独立子域名后缀，或选择完整自定义域名。".to_string()
                    })?
                } else {
                    normalize_domain(&self.subdomain_host)?
                };
                normalize_domain(&format!("{prefix}.{suffix}"))
            }
            _ => Err("未知 FRP 域名模式。".into()),
        }
    }

    pub fn public_origin(&self, server: &str, subdomain: &str) -> Result<String, String> {
        if self.public_port == 0 {
            return Err("公网 HTTPS 端口必须为 1–65535。".into());
        }
        let host = self.hostname(server, subdomain)?;
        if self.public_port == 443 {
            Ok(format!("https://{host}"))
        } else {
            Ok(format!("https://{host}:{}", self.public_port))
        }
    }

    pub fn target_port(&self, service_port: u16) -> u16 {
        self.local_port.unwrap_or(service_port)
    }

    pub fn target_address(&self, service_port: u16) -> String {
        let host = self.local_ip.trim().trim_start_matches('[').trim_end_matches(']');
        let port = self.target_port(service_port);
        if host.contains(':') {
            format!("[{host}]:{port}")
        } else {
            format!("{host}:{port}")
        }
    }

    pub fn validate_target(&self, service_port: u16) -> Result<(), String> {
        let normalized_host = normalize_server_host(&self.local_ip)?;
        if self.target_port(service_port) == 0 {
            return Err("本地目标端口必须为 1–65535。".into());
        }
        match self.proxy_type.as_str() {
            "http" => Ok(()),
            "https" => match self.https_mode.as_str() {
                "https2http" => {
                    if self.tls_cert_file.trim().is_empty() || self.tls_key_file.trim().is_empty() {
                        return Err("https2http 需要填写本地证书和私钥文件路径。".into());
                    }
                    if self.tls_cert_file.contains('\0') || self.tls_key_file.contains('\0') {
                        return Err("证书路径不能包含空字符。".into());
                    }
                    Ok(())
                }
                "local_tls" => {
                    if self.local_port.is_none() {
                        return Err("HTTPS 透传必须显式填写已有本地 HTTPS 服务的端口。".into());
                    }
                    let host = normalized_host.as_str();
                    if self.target_port(service_port) == service_port
                        && (host.eq_ignore_ascii_case("localhost")
                            || host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback() || ip.is_unspecified()))
                    {
                        return Err("内置 MCP/Actions 端口是普通 HTTP，不能直接作为 HTTPS 透传目标。".into());
                    }
                    Ok(())
                }
                _ => Err("未知 HTTPS 转发模式。".into()),
            },
            _ => Err("FRP 代理类型只支持 HTTP 或 HTTPS。".into()),
        }
    }
}

fn valid_label(label: &str) -> bool {
    !label.is_empty()
        && label.len() <= 63
        && !label.starts_with('-')
        && !label.ends_with('-')
        && label.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
}

/// Domain-only input: no scheme, path, port, wildcard or IP literal.
pub fn normalize_domain(value: &str) -> Result<String, String> {
    let domain = value.trim().trim_end_matches('.').to_ascii_lowercase();
    if domain.len() > 253
        || !domain.contains('.')
        || domain.parse::<IpAddr>().is_ok()
        || !domain.split('.').all(valid_label)
        || domain.rsplit('.').next().is_some_and(|label| label.bytes().all(|c| c.is_ascii_digit()))
    {
        return Err("请填写完整域名（例如 mcp.example.com），不要包含协议、端口、路径、通配符或 IP。".into());
    }
    Ok(domain)
}

/// Accept IPv4, bare/bracketed IPv6 or a DNS hostname; reject URL/host:port.
pub fn normalize_server_host(value: &str) -> Result<String, String> {
    let value = value.trim();
    let unbracketed = value.strip_prefix('[').and_then(|v| v.strip_suffix(']')).unwrap_or(value);
    if let Ok(ip) = unbracketed.parse::<IpAddr>() {
        return Ok(ip.to_string());
    }
    let host = value.trim_end_matches('.').to_ascii_lowercase();
    if host.is_empty() || host.len() > 253 || !host.split('.').all(valid_label) {
        return Err("服务器/本地目标地址只接受 IP 或主机名，不要附带协议、端口或路径。".into());
    }
    Ok(host)
}

/// Reject raw path syntax before URL normalization can erase `/a/..` or `\\`.
pub fn normalize_public_origin(value: &str) -> Result<String, String> {
    let value = value.trim();
    let invalid = || "公网地址必须是 HTTPS 根地址，例如 https://mcp.example.com；不要附带 /mcp、凭据、查询或片段。".to_string();
    if value.is_empty() || value.chars().any(|c| c.is_whitespace() || c.is_control())
        || value.contains(['\\', '?', '#'])
    {
        return Err(invalid());
    }
    let (_, rest) = value.split_once("://").ok_or_else(invalid)?;
    let (authority, path) = rest.split_once('/').unwrap_or((rest, ""));
    if authority.is_empty() || authority.contains('@') || !path.is_empty() {
        return Err(invalid());
    }
    let url = reqwest::Url::parse(value).map_err(|_| invalid())?;
    if url.scheme() != "https" || url.host_str().is_none()
        || !url.username().is_empty() || url.password().is_some()
        || url.port() == Some(0)
    {
        return Err(invalid());
    }
    Ok(url.origin().ascii_serialization())
}

pub fn is_quick_tunnel_origin(value: &str) -> bool {
    reqwest::Url::parse(value).ok().and_then(|url| url.host_str().map(str::to_string))
        .is_some_and(|host| {
            let host = host.trim_end_matches('.');
            host.eq_ignore_ascii_case("trycloudflare.com")
                || host.to_ascii_lowercase().ends_with(".trycloudflare.com")
        })
}

pub fn normalize_named_origin(value: &str) -> Result<String, String> {
    let origin = normalize_public_origin(value)?;
    if is_quick_tunnel_origin(&origin) {
        return Err("Named Tunnel 需要绑定自己的固定域名，不能使用 trycloudflare.com 临时地址。".into());
    }
    let mut url = reqwest::Url::parse(&origin).map_err(|e| e.to_string())?;
    let host = normalize_domain(url.host_str().unwrap_or_default())?;
    url.set_host(Some(&host)).map_err(|e| e.to_string())?;
    Ok(url.origin().ascii_serialization())
}

/// Validate only changed service configuration so unrelated edits can still
/// repair a legacy workspace. Credentials are neither read nor changed here.
pub fn normalize_profile_tunnels(
    current: &super::WorkspaceProfile,
    next: &mut super::WorkspaceProfile,
    settings: &crate::settings::AppSettings,
) -> Result<(), String> {
    let mcp_changed = serde_json::to_value(&current.tunnel).map_err(|e| e.to_string())?
        != serde_json::to_value(&next.tunnel).map_err(|e| e.to_string())?;
    if mcp_changed || current.runtime.local_port != next.runtime.local_port {
        let cfg = &next.tunnel;
        next.tunnel.public_url = validated_route_origin(
            &cfg.tunnel_type, &cfg.public_url, &cfg.frp_server, cfg.frp_server_port,
            &cfg.frp_profile_id, &cfg.frp_subdomain, &cfg.frp,
            &cfg.cloudflare_mode, next.runtime.local_port, settings,
        )?;
    }
    let before = &current.actions;
    let after = &next.actions;
    let actions_changed = before.public_url != after.public_url
        || before.tunnel_type != after.tunnel_type || before.frp != after.frp
        || before.frp_server != after.frp_server || before.frp_server_port != after.frp_server_port
        || before.frp_profile_id != after.frp_profile_id || before.frp_subdomain != after.frp_subdomain
        || before.cloudflare_mode != after.cloudflare_mode
        || before.cloudflare_http2 != after.cloudflare_http2 || before.use_proxy != after.use_proxy
        || before.local_port != after.local_port;
    if actions_changed {
        let cfg = &next.actions;
        next.actions.public_url = validated_route_origin(
            &cfg.tunnel_type, &cfg.public_url, &cfg.frp_server, cfg.frp_server_port,
            &cfg.frp_profile_id, &cfg.frp_subdomain, &cfg.frp,
            &cfg.cloudflare_mode, cfg.local_port, settings,
        )?;
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn validated_route_origin(
    provider: &str, public_url: &str, inline_server: &str, inline_port: u16,
    profile_id: &str, prefix: &str, options: &FrpRouteOptions,
    cloudflare_mode: &str, service_port: u16, settings: &crate::settings::AppSettings,
) -> Result<String, String> {
    if service_port == 0 { return Err("本地服务端口不能为 0。".into()); }
    match provider {
        "frp" => {
            if profile_id.is_empty() && inline_server.trim().is_empty() && prefix.trim().is_empty()
                && options == &FrpRouteOptions::default() {
                // A newly created workspace is allowed to remain unconfigured.
                return Ok(String::new());
            }
            let (server, port) = if profile_id.is_empty() {
                (inline_server, inline_port)
            } else {
                let profile = settings.find_frp_profile(profile_id)
                    .ok_or("所选 FRP 配置不存在，请重新选择。")?;
                (profile.server.as_str(), profile.server_port)
            };
            normalize_server_host(server)?;
            if port == 0 { return Err("FRPS 控制端口不能为 0。".into()); }
            options.validate_target(service_port)?;
            options.public_origin(server, prefix)
        }
        "cloudflare" => match cloudflare_mode {
            "named" => normalize_named_origin(public_url),
            "quick" => {
                if is_quick_tunnel_origin(public_url) { normalize_public_origin(public_url) }
                else { Ok(String::new()) }
            }
            _ => Err("未知 Cloudflare 模式。".into()),
        },
        "none" | "" => {
            if public_url.trim().is_empty() { Ok(String::new()) }
            else { normalize_public_origin(public_url) }
        }
        _ => Err("未知隧道类型。".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn old_profiles_keep_legacy_subdomain_defaults() {
        let options: FrpRouteOptions = serde_json::from_str("{}").unwrap();
        assert_eq!(options.public_origin("frp.example.com", "demo").unwrap(), "https://demo.frp.example.com");
        assert!(options.tcp_mux && options.tls_enable);
        assert!(!options.use_compression);
    }

    #[test]
    fn custom_domain_is_independent_of_ipv4_or_ipv6_server() {
        let options = FrpRouteOptions { domain_mode: "custom".into(), custom_domain: "MCP.Example.COM".into(), ..Default::default() };
        for server in ["203.0.113.10", "2001:db8::10"] {
            assert_eq!(options.public_origin(server, "").unwrap(), "https://mcp.example.com");
        }
    }

    #[test]
    fn ip_is_never_a_subdomain_suffix() {
        for server in ["203.0.113.10", "2001:db8::10", "[2001:db8::10]"] {
            assert!(FrpRouteOptions::default().public_origin(server, "demo").is_err());
        }
        let options = FrpRouteOptions { subdomain_host: "example.com".into(), ..Default::default() };
        assert_eq!(options.public_origin("203.0.113.10", "demo").unwrap(), "https://demo.example.com");
    }

    #[test]
    fn origin_validation_rejects_non_origin_inputs() {
        for value in ["http://example.com", "https://example.com/mcp", "https://example.com/a/..", "https://@example.com", "https://u:p@example.com", "https://example.com?", "https://example.com#x", "https://example.com:0", "https://exam\nple.com", "https://example.com\\mcp"] {
            assert!(normalize_public_origin(value).is_err(), "accepted {value:?}");
        }
        assert_eq!(normalize_public_origin(" https://EXAMPLE.com:443/ ").unwrap(), "https://example.com");
        assert_eq!(normalize_public_origin("https://example.com:8443").unwrap(), "https://example.com:8443");
    }

    #[test]
    fn named_rejects_quick_and_ip_endpoints() {
        for value in ["https://x.trycloudflare.com", "https://trycloudflare.com", "https://127.0.0.1"] {
            assert!(normalize_named_origin(value).is_err());
        }
        assert!(normalize_named_origin("https://mcp.example.com").is_ok());
        assert!(!is_quick_tunnel_origin("https://trycloudflare.com.example.com"));
    }

    #[test]
    fn https_cannot_silently_target_plain_http() {
        let mut options = FrpRouteOptions { proxy_type: "https".into(), https_mode: "local_tls".into(), ..Default::default() };
        assert!(options.validate_target(28766).is_err());
        options.local_port = Some(28766);
        assert!(options.validate_target(28766).is_err());
        options.local_port = Some(443);
        assert!(options.validate_target(28766).is_ok());
        options.https_mode = "https2http".into();
        assert!(options.validate_target(28766).is_err());
    }

    #[test]
    fn ipv6_target_and_server_are_normalized_separately() {
        assert_eq!(normalize_server_host("[2001:db8::1]").unwrap(), "2001:db8::1");
        let options = FrpRouteOptions { local_ip: "::1".into(), ..Default::default() };
        assert_eq!(options.target_address(28766), "[::1]:28766");
        assert!(normalize_server_host("https://example.com").is_err());
        assert!(normalize_server_host("example.com:7000").is_err());
    }
    #[test]
    fn whole_legacy_profile_roundtrips_without_rotating_client_identity() {
        let profile = super::super::WorkspaceProfile::new("/tmp/legacy".into(), None);
        let mut value = serde_json::to_value(&profile).unwrap();
        value["tunnel"].as_object_mut().unwrap().remove("frp");
        value["actions"].as_object_mut().unwrap().remove("frp");
        let loaded: super::super::WorkspaceProfile = serde_json::from_value(value).unwrap();
        assert_eq!(loaded.auth.oauth_client_id, profile.auth.oauth_client_id);
        assert_eq!(loaded.id, profile.id);
        assert_eq!(loaded.tunnel.frp, FrpRouteOptions::default());
        assert_eq!(loaded.actions.frp, FrpRouteOptions::default());
        let encoded = serde_json::to_string(&loaded).unwrap();
        let again: super::super::WorkspaceProfile = serde_json::from_str(&encoded).unwrap();
        assert_eq!(again.auth.oauth_client_id, profile.auth.oauth_client_id);
    }

    #[test]
    fn save_normalizes_named_root_and_rejects_temporary_hostname() {
        let before = super::super::WorkspaceProfile::new("/tmp/named".into(), None);
        let mut after = before.clone();
        after.tunnel.tunnel_type = "cloudflare".into();
        after.tunnel.cloudflare_mode = "named".into();
        after.tunnel.public_url = "https://MCP.EXAMPLE.COM:443/".into();
        let settings = crate::settings::AppSettings::default();
        normalize_profile_tunnels(&before, &mut after, &settings).unwrap();
        assert_eq!(after.tunnel.public_url, "https://mcp.example.com");
        after.tunnel.public_url = "https://temporary.trycloudflare.com".into();
        assert!(normalize_profile_tunnels(&before, &mut after, &settings).is_err());
    }

    #[test]
    fn actions_custom_origin_matches_all_published_urls() {
        let before = super::super::WorkspaceProfile::new("/tmp/actions".into(), None);
        let mut after = before.clone();
        after.actions.frp_server = "203.0.113.10".into();
        after.actions.frp.domain_mode = "custom".into();
        after.actions.frp.custom_domain = "actions.example.com".into();
        after.actions.frp.public_port = 8443;
        normalize_profile_tunnels(&before, &mut after, &crate::settings::AppSettings::default()).unwrap();
        assert_eq!(after.actions.public_url, "https://actions.example.com:8443");
        assert_eq!(after.actions_openapi_url(), "https://actions.example.com:8443/openapi.json");
        assert_eq!(after.actions_oauth_authorization_url(), "https://actions.example.com:8443/oauth/authorize");
        assert_eq!(after.actions_oauth_token_url(), "https://actions.example.com:8443/oauth/token");
    }

    #[test]
    fn unrelated_legacy_edit_is_not_blocked_by_incomplete_tunnel() {
        let before = super::super::WorkspaceProfile::new("/tmp/legacy".into(), None);
        let mut after = before.clone();
        after.name = "Renamed".into();
        normalize_profile_tunnels(&before, &mut after, &crate::settings::AppSettings::default()).unwrap();
        after.runtime.local_port += 1;
        normalize_profile_tunnels(&before, &mut after, &crate::settings::AppSettings::default()).unwrap();
    }

}
