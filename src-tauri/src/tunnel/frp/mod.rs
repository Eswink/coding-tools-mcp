mod client;
#[path = "配置校验v1.rs"]
mod config_check;
pub(crate) use config_check::verify_frpc_configs;

use crate::settings::AppSettings;
#[allow(unused_imports)]
use crate::settings::FrpProfile;
use crate::workspace::WorkspaceProfile;
use crate::workspace::endpoint::{normalize_server_host, FrpRouteOptions};
use crate::error::{AppError, AppResult};
use std::collections::HashSet;

use super::TunnelServiceKind;

pub(crate) use client::{
    acquire_frpc_operation_lock, clear_managed_frpc_pid, frpc_log_name, frpc_reconnect_loop_detected,
    managed_frpc_config_matches, probe_host_network_available, probe_local_actions_ok,
    probe_local_mcp_ok, probe_public_mcp_endpoint, read_frpc_log_tail,
    stop_recorded_frpc_instance, PublicMcpProbe,
};
pub(crate) use client::{cached_frpc_path, download_frpc_to_cache};
pub use client::{resolve_frpc, spawn_frpc};

const FRP_VERSION: &str = "0.61.2";
pub(crate) const VERSION: &str = FRP_VERSION;

#[allow(dead_code)]
pub(crate) fn frp_version() -> &'static str {
    FRP_VERSION
}

/// FRP proxy snippet for the MCP listener (`profile.tunnel` + `profile.runtime`).
#[allow(dead_code)]
pub fn mcp_frp_snippet(profile: &WorkspaceProfile, settings: &AppSettings) -> String {
    frp_snippet(profile, TunnelServiceKind::Mcp, settings)
}

/// FRP proxy snippet for the Actions listener (`profile.actions`).
#[allow(dead_code)]
pub fn actions_frp_snippet(profile: &WorkspaceProfile, settings: &AppSettings) -> String {
    frp_snippet(profile, TunnelServiceKind::Actions, settings)
}

pub fn frp_snippet(
    profile: &WorkspaceProfile,
    kind: TunnelServiceKind,
    settings: &AppSettings,
) -> String {
    // Do not load or export a credential for a UI preview.
    let mut config = frp_server_config(profile, kind, settings, Some(String::new()));
    config.token = Some("<REDACTED>".into());
    build_frpc_toml(&config)
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct FrpProxyConfig {
    pub proxy_name: String,
    pub local_port: u16,
    pub subdomain: String,
    pub options: FrpRouteOptions,
}

#[derive(Clone, PartialEq, Eq)]
pub(crate) struct FrpServerConfig {
    pub server_addr: String,
    pub server_port: u16,
    pub token: Option<String>,
    pub proxy: FrpProxyConfig,
}

#[allow(dead_code)]
pub fn frp_public_url(
    profile: &WorkspaceProfile,
    kind: TunnelServiceKind,
    settings: &AppSettings,
) -> String {
    match kind {
        TunnelServiceKind::Mcp => profile.effective_public_url_with(settings),
        TunnelServiceKind::Actions => profile.actions_effective_public_url_with(settings),
    }
}

pub fn frp_server_config(
    profile: &WorkspaceProfile,
    kind: TunnelServiceKind,
    settings: &AppSettings,
    token_override: Option<String>,
) -> FrpServerConfig {
    let proxy = frp_proxy_config(profile, kind);
    let (profile_id, server_addr, server_port) = match kind {
        TunnelServiceKind::Mcp => (
            profile.tunnel.frp_profile_id.as_str(),
            profile.tunnel.frp_server.clone(),
            profile.tunnel.frp_server_port,
        ),
        TunnelServiceKind::Actions => (
            profile.actions.frp_profile_id.as_str(),
            profile.actions.frp_server.clone(),
            profile.actions.frp_server_port,
        ),
    };

    let (server_addr, server_port) =
        if let Some(frp_profile) = settings.find_frp_profile(profile_id) {
            (frp_profile.server.clone(), frp_profile.server_port)
        } else {
            (server_addr, server_port)
        };

    let token = token_override.or_else(|| resolve_frp_token(profile_id, profile, kind, settings));

    FrpServerConfig {
        server_addr: normalize_server_host(&server_addr).unwrap_or_else(|_| server_addr.trim().to_string()),
        server_port,
        token,
        proxy,
    }
}

fn resolve_frp_token(
    profile_id: &str,
    workspace: &WorkspaceProfile,
    kind: TunnelServiceKind,
    settings: &AppSettings,
) -> Option<String> {
    if !profile_id.trim().is_empty() {
        if let Ok(Some(token)) =
            crate::secret::SecretStore::get_app("frp_profile_token", profile_id)
        {
            if !token.trim().is_empty() {
                return Some(token);
            }
        }
    }

    let workspace_key = match kind {
        TunnelServiceKind::Mcp => "frp_token",
        TunnelServiceKind::Actions => "actions_frp_token",
    };
    if let Ok(Some(token)) = crate::secret::SecretStore::get(&workspace.id, workspace_key) {
        if !token.trim().is_empty() {
            return Some(token);
        }
    }

    // Manual inline server: reuse token from a global profile with the same host.
    let inline_server = match kind {
        TunnelServiceKind::Mcp => workspace.tunnel.frp_server.as_str(),
        TunnelServiceKind::Actions => workspace.actions.frp_server.as_str(),
    };
    let inline_server = inline_server.trim();
    if !inline_server.is_empty() {
        for profile in &settings.frp_profiles {
            if profile.server.trim().eq_ignore_ascii_case(inline_server) {
                if let Ok(Some(token)) =
                    crate::secret::SecretStore::get_app("frp_profile_token", &profile.id)
                {
                    if !token.trim().is_empty() {
                        return Some(token);
                    }
                }
            }
        }
    }

    None
}

#[allow(dead_code)]
pub fn build_frpc_toml(config: &FrpServerConfig) -> String {
    let mut lines = vec![
        format!("serverAddr = {}", toml_string(config.server_addr.trim())),
        format!("serverPort = {}", config.server_port),
        String::new(),
    ];
    if let Some(token) = config.token.as_ref().filter(|t| !t.trim().is_empty()) {
        lines.push("auth.method = \"token\"".to_string());
        lines.push(format!("auth.token = {}", toml_string(token.trim())));
        lines.push(String::new());
    }
    append_frpc_transport_settings(&mut lines, &config.proxy.options);
    lines.push(build_proxy_snippet(&config.proxy));
    lines.join("\n")
}

/// Build one frpc configuration containing all active proxies.
///
/// A single frpc process can serve multiple workspaces, but all proxies must
/// share the same server connection. The supervisor validates that invariant
/// before calling this function.
pub(crate) fn build_frpc_toml_for_routes(configs: &[FrpServerConfig]) -> String {
    let Some(first) = configs.first() else {
        return String::new();
    };

    let mut lines = vec![
        format!("serverAddr = {}", toml_string(first.server_addr.trim())),
        format!("serverPort = {}", first.server_port),
        String::new(),
    ];
    if let Some(token) = first.token.as_ref().filter(|t| !t.trim().is_empty()) {
        lines.push("auth.method = \"token\"".to_string());
        lines.push(format!("auth.token = {}", toml_string(token.trim())));
        lines.push(String::new());
    }
    append_frpc_transport_settings(&mut lines, &first.proxy.options);

    let mut used_names = HashSet::new();
    for config in configs {
        let mut proxy = config.proxy.clone();
        let base_name = proxy.proxy_name.clone();
        let mut name = base_name.clone();
        let mut suffix = 2;
        while !used_names.insert(name.clone()) {
            name = format!("{base_name}-{suffix}");
            suffix += 1;
        }
        proxy.proxy_name = name;
        lines.push(build_proxy_snippet(&proxy));
        lines.push(String::new());
    }

    lines.pop();
    lines.join("\n")
}

pub(crate) fn build_frpc_toml_for_route_refs(
    routes: &[(&WorkspaceProfile, TunnelServiceKind)],
    settings: &AppSettings,
) -> String {
    let configs: Vec<FrpServerConfig> = routes
        .iter()
        .map(|(profile, kind)| frp_server_config(profile, *kind, settings, None))
        .collect();
    build_frpc_toml_for_routes(&configs)
}

fn frp_proxy_config(profile: &WorkspaceProfile, kind: TunnelServiceKind) -> FrpProxyConfig {
    let prefix = workspace_proxy_prefix(&profile.id);
    match kind {
        TunnelServiceKind::Mcp => FrpProxyConfig {
            proxy_name: format!("{prefix}-mcp"),
            local_port: profile.runtime.local_port,
            subdomain: profile.tunnel.frp_subdomain.trim().to_ascii_lowercase(),
            options: profile.tunnel.frp.clone(),
        },
        TunnelServiceKind::Actions => FrpProxyConfig {
            proxy_name: format!("{prefix}-actions"),
            local_port: profile.actions.local_port,
            subdomain: profile.actions.frp_subdomain.trim().to_ascii_lowercase(),
            options: profile.actions.frp.clone(),
        },
    }
}

fn append_frpc_transport_settings(lines: &mut Vec<String>, options: &FrpRouteOptions) {
    lines.push(format!("transport.tcpMux = {}", options.tcp_mux));
    lines.push(format!("transport.tls.enable = {}", options.tls_enable));
    // Keep retrying through overnight router outages instead of exiting once.
    lines.push("loginFailExit = false".to_string());
    lines.push("transport.heartbeatInterval = 30".to_string());
    lines.push("transport.heartbeatTimeout = 90".to_string());
    lines.push(String::new());
}

fn build_proxy_snippet(proxy: &FrpProxyConfig) -> String {
    let options = &proxy.options;
    let mut lines = vec![
        "[[proxies]]".to_string(),
        format!("name = {}", toml_string(&proxy.proxy_name)),
        format!("type = {}", toml_string(&options.proxy_type)),
        format!("transport.useCompression = {}", options.use_compression),
    ];
    if options.domain_mode == "custom" {
        let domain = options.custom_domain.trim().trim_end_matches('.').to_ascii_lowercase();
        lines.push(format!("customDomains = [{}]", toml_string(&domain)));
    } else {
        lines.push(format!("subdomain = {}", toml_string(proxy.subdomain.trim())));
    }
    if options.proxy_type == "https" && options.https_mode == "https2http" {
        lines.push("plugin.type = \"https2http\"".into());
        lines.push(format!("plugin.localAddr = {}", toml_string(&options.target_address(proxy.local_port))));
        lines.push(format!("plugin.crtPath = {}", toml_string(options.tls_cert_file.trim())));
        lines.push(format!("plugin.keyPath = {}", toml_string(options.tls_key_file.trim())));
    } else {
        let host = normalize_server_host(&options.local_ip).unwrap_or_else(|_| options.local_ip.clone());
        lines.push(format!("localIP = {}", toml_string(&host)));
        lines.push(format!("localPort = {}", options.target_port(proxy.local_port)));
    }
    lines.join("\n")
}

/// TOML basic-string quoting, including Windows paths and C0/DEL controls.
fn toml_string(value: &str) -> String {
    let mut quoted = String::from("\"");
    for ch in value.chars() {
        match ch {
            '"' => quoted.push_str("\\\""),
            '\\' => quoted.push_str("\\\\"),
            '\n' => quoted.push_str("\\n"),
            '\r' => quoted.push_str("\\r"),
            '\t' => quoted.push_str("\\t"),
            c if c <= '\u{1f}' || c == '\u{7f}' => quoted.push_str(&format!("\\u{:04X}", c as u32)),
            c => quoted.push(c),
        }
    }
    quoted.push('"');
    quoted
}

pub(crate) fn route_hostname(config: &FrpServerConfig) -> String {
    config.proxy.options.hostname(&config.server_addr, &config.proxy.subdomain).unwrap_or_default()
}

pub(crate) fn same_route(a: &FrpServerConfig, b: &FrpServerConfig) -> bool {
    let host = route_hostname(a);
    !host.is_empty() && host == route_hostname(b)
        && a.server_addr.eq_ignore_ascii_case(&b.server_addr)
        && a.server_port == b.server_port
        && a.proxy.options.proxy_type == b.proxy.options.proxy_type
}

pub(crate) fn same_connection(a: &FrpServerConfig, b: &FrpServerConfig) -> bool {
    a.server_addr.eq_ignore_ascii_case(&b.server_addr)
        && a.server_port == b.server_port && a.token == b.token
        && a.proxy.options.tcp_mux == b.proxy.options.tcp_mux
        && a.proxy.options.tls_enable == b.proxy.options.tls_enable
}

pub(crate) fn validate_frp_config(profile: &WorkspaceProfile, kind: TunnelServiceKind, settings: &AppSettings) -> AppResult<()> {
    let profile_id = match kind {
        TunnelServiceKind::Mcp => &profile.tunnel.frp_profile_id,
        TunnelServiceKind::Actions => &profile.actions.frp_profile_id,
    };
    if !profile_id.is_empty() && settings.find_frp_profile(profile_id).is_none() {
        return Err(AppError::Message("所选 FRP 配置不存在，请重新选择。".into()));
    }
    let config = frp_server_config(profile, kind, settings, Some(String::new()));
    normalize_server_host(&config.server_addr).map_err(AppError::Message)?;
    if config.server_port == 0 {
        return Err(AppError::Message("FRP 控制端口必须为 1–65535。".into()));
    }
    config.proxy.options.public_origin(&config.server_addr, &config.proxy.subdomain).map_err(AppError::Message)?;
    config.proxy.options.validate_target(config.proxy.local_port).map_err(AppError::Message)?;
    Ok(())
}


fn workspace_proxy_prefix(workspace_id: &str) -> String {
    let stable_id: String = workspace_id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .take(12)
        .collect();
    if stable_id.is_empty() {
        "workspace".to_string()
    } else {
        format!("ws-{}", stable_id.to_ascii_lowercase())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::FrpProfile;
    use crate::workspace::WorkspaceProfile;

    #[test]
    fn mcp_snippet_uses_tunnel_subdomain() {
        let mut profile = WorkspaceProfile::new("/tmp/demo".into(), Some("Demo WS".into()));
        profile.tunnel.frp_subdomain = "demo-mcp".into();
        profile.runtime.local_port = 28766;
        let settings = AppSettings {
            frp_profiles: vec![FrpProfile {
                id: "p1".into(),
                name: "Main".into(),
                server: "frp.example.com".into(),
                server_port: 7000,
            }],
            ..AppSettings::default()
        };
        profile.tunnel.frp_profile_id = "p1".into();

        let snippet = mcp_frp_snippet(&profile, &settings);
        let proxy_name = frp_server_config(&profile, TunnelServiceKind::Mcp, &settings, None)
            .proxy
            .proxy_name;
        assert!(snippet.contains(&format!("name = \"{proxy_name}\"")));
        assert!(snippet.contains("localPort = 28766"));
        assert!(snippet.contains("subdomain = \"demo-mcp\""));
    }

    #[test]
    fn build_frpc_toml_uses_global_profile_server() {
        let mut profile = WorkspaceProfile::new("/tmp/demo".into(), Some("Demo".into()));
        profile.tunnel.frp_subdomain = "demo".into();
        profile.tunnel.frp_profile_id = "p1".into();
        let settings = AppSettings {
            frp_profiles: vec![FrpProfile {
                id: "p1".into(),
                name: "Main".into(),
                server: "frp.example.com".into(),
                server_port: 7000,
            }],
            ..AppSettings::default()
        };
        let config = frp_server_config(
            &profile,
            TunnelServiceKind::Mcp,
            &settings,
            Some("secret".into()),
        );
        let toml = build_frpc_toml(&config);
        assert!(toml.contains("serverAddr = \"frp.example.com\""));
        assert!(toml.contains("auth.token = \"secret\""));
        assert!(toml.contains("loginFailExit = false"));
        assert!(toml.contains("transport.heartbeatInterval = 30"));
        assert!(toml.contains("transport.heartbeatTimeout = 90"));
    }

    #[test]
    fn build_frpc_toml_for_routes_contains_all_proxies() {
        let mut first = WorkspaceProfile::new("/tmp/first".into(), Some("First".into()));
        first.tunnel.frp_server = "frp.example.com".into();
        first.tunnel.frp_server_port = 7000;
        first.tunnel.frp_subdomain = "first".into();
        first.runtime.local_port = 28766;

        let mut second = WorkspaceProfile::new("/tmp/second".into(), Some("Second".into()));
        second.tunnel.frp_server = "frp.example.com".into();
        second.tunnel.frp_server_port = 7000;
        second.tunnel.frp_subdomain = "second".into();
        second.runtime.local_port = 28767;

        let settings = AppSettings::default();
        let configs = vec![
            frp_server_config(&first, TunnelServiceKind::Mcp, &settings, None),
            frp_server_config(&second, TunnelServiceKind::Mcp, &settings, None),
        ];
        let first_name = configs[0].proxy.proxy_name.clone();
        let second_name = configs[1].proxy.proxy_name.clone();
        let toml = build_frpc_toml_for_routes(&configs);

        assert_eq!(toml.matches("[[proxies]]").count(), 2);
        assert!(toml.contains("serverAddr = \"frp.example.com\""));
        assert!(toml.contains(&format!("name = \"{first_name}\"")));
        assert!(toml.contains(&format!("name = \"{second_name}\"")));
        assert!(toml.contains("localPort = 28766"));
        assert!(toml.contains("localPort = 28767"));
    }

    #[test]
    fn build_frpc_toml_for_routes_supports_mcp_and_actions_together() {
        let mut mcp = WorkspaceProfile::new("/tmp/mcp".into(), Some("MCP".into()));
        mcp.tunnel.frp_server = "frp.example.com".into();
        mcp.tunnel.frp_server_port = 7000;
        mcp.tunnel.frp_subdomain = "mcp".into();
        mcp.runtime.local_port = 28766;

        let mut actions = WorkspaceProfile::new("/tmp/actions".into(), Some("Actions".into()));
        actions.actions.frp_server = "frp.example.com".into();
        actions.actions.frp_server_port = 7000;
        actions.actions.frp_subdomain = "actions".into();
        actions.actions.local_port = 8787;

        let settings = AppSettings::default();
        let configs = vec![
            frp_server_config(&mcp, TunnelServiceKind::Mcp, &settings, None),
            frp_server_config(&actions, TunnelServiceKind::Actions, &settings, None),
        ];
        let mcp_name = configs[0].proxy.proxy_name.clone();
        let actions_name = configs[1].proxy.proxy_name.clone();
        let toml = build_frpc_toml_for_routes(&configs);

        assert_eq!(toml.matches("[[proxies]]").count(), 2);
        assert!(toml.contains(&format!("name = \"{mcp_name}\"")));
        assert!(toml.contains(&format!("name = \"{actions_name}\"")));
        assert!(toml.contains("localPort = 28766"));
        assert!(toml.contains("localPort = 8787"));
    }

    #[test]
    fn build_frpc_toml_for_routes_keeps_workspace_proxy_names_unique() {
        let mut first = WorkspaceProfile::new("/tmp/first".into(), Some("Same Name".into()));
        first.tunnel.frp_server = "frp.example.com".into();
        first.tunnel.frp_server_port = 7000;
        first.tunnel.frp_subdomain = "first".into();

        let mut second = WorkspaceProfile::new("/tmp/second".into(), Some("Same Name".into()));
        second.tunnel.frp_server = "frp.example.com".into();
        second.tunnel.frp_server_port = 7000;
        second.tunnel.frp_subdomain = "second".into();

        let settings = AppSettings::default();
        let configs = vec![
            frp_server_config(&first, TunnelServiceKind::Mcp, &settings, None),
            frp_server_config(&second, TunnelServiceKind::Mcp, &settings, None),
        ];
        let first_name = configs[0].proxy.proxy_name.clone();
        let second_name = configs[1].proxy.proxy_name.clone();
        let toml = build_frpc_toml_for_routes(&configs);

        assert_ne!(first_name, second_name);
        assert!(toml.contains(&format!("name = \"{first_name}\"")));
        assert!(toml.contains(&format!("name = \"{second_name}\"")));
    }

    #[test]
    fn build_frpc_toml_for_routes_returns_empty_for_no_routes() {
        assert!(build_frpc_toml_for_routes(&[]).is_empty());
    }

    #[test]
    fn same_name_workspaces_receive_distinct_proxy_names() {
        let first = WorkspaceProfile::new("/tmp/first".into(), Some("Same Name".into()));
        let second = WorkspaceProfile::new("/tmp/second".into(), Some("Same Name".into()));
        let settings = AppSettings::default();

        let first_config = frp_server_config(&first, TunnelServiceKind::Mcp, &settings, None);
        let second_config = frp_server_config(&second, TunnelServiceKind::Mcp, &settings, None);

        assert_ne!(
            first_config.proxy.proxy_name,
            second_config.proxy.proxy_name
        );
    }

    #[test]
    fn proxy_name_is_stable_when_workspace_is_renamed() {
        let original = WorkspaceProfile::new("/tmp/demo".into(), Some("Before".into()));
        let mut renamed = original.clone();
        renamed.name = "After".into();
        let settings = AppSettings::default();

        let before = frp_server_config(&original, TunnelServiceKind::Mcp, &settings, None);
        let after = frp_server_config(&renamed, TunnelServiceKind::Mcp, &settings, None);

        assert_eq!(before.proxy.proxy_name, after.proxy.proxy_name);
    }

    #[test]
    fn resolve_token_from_matching_global_profile_when_manual_server() {
        let mut profile = WorkspaceProfile::new("/tmp/demo".into(), Some("Demo".into()));
        profile.tunnel.frp_server = "frp.example.com".into();
        profile.tunnel.frp_subdomain = "demo".into();
        let settings = AppSettings {
            frp_profiles: vec![FrpProfile {
                id: "p1".into(),
                name: "Main".into(),
                server: "frp.example.com".into(),
                server_port: 7000,
            }],
            ..AppSettings::default()
        };
        crate::secret::SecretStore::set_app("frp_profile_token", "p1", "shared-token").unwrap();
        let config = frp_server_config(&profile, TunnelServiceKind::Mcp, &settings, None);
        assert_eq!(config.token.as_deref(), Some("shared-token"));
    }
    #[test]
    fn ip_with_custom_domain_generates_a_real_custom_domains_route() {
        let mut profile = WorkspaceProfile::new("/tmp/custom".into(), Some("Custom".into()));
        profile.tunnel.frp_server = "203.0.113.10".into();
        profile.tunnel.frp.domain_mode = "custom".into();
        profile.tunnel.frp.custom_domain = "MCP.Example.COM.".into();
        let settings = AppSettings::default();
        assert!(validate_frp_config(&profile, TunnelServiceKind::Mcp, &settings).is_ok());
        let config = frp_server_config(&profile, TunnelServiceKind::Mcp, &settings, Some("canary".into()));
        let text = build_frpc_toml(&config);
        assert!(text.contains("customDomains = [\"mcp.example.com\"]"));
        assert!(!text.contains("subdomain ="));
        assert!(text.contains("serverAddr = \"203.0.113.10\""));
        assert_eq!(frp_public_url(&profile, TunnelServiceKind::Mcp, &settings), "https://mcp.example.com");
        assert_eq!(profile.public_endpoint(), "https://mcp.example.com/mcp");
        assert!(!frp_snippet(&profile, TunnelServiceKind::Mcp, &settings).contains("canary"));
    }

    #[test]
    fn actions_https_plugin_uses_its_actual_service_port() {
        let mut profile = WorkspaceProfile::new("/tmp/actions".into(), None);
        profile.actions.frp_server = "2001:db8::1".into();
        profile.actions.frp.domain_mode = "custom".into();
        profile.actions.frp.custom_domain = "actions.example.com".into();
        profile.actions.frp.proxy_type = "https".into();
        profile.actions.frp.local_ip = "::1".into();
        profile.actions.frp.tls_cert_file = r"C:\certs\fullchain.pem".into();
        profile.actions.frp.tls_key_file = r"C:\certs\private.key".into();
        profile.actions.frp.use_compression = true;
        profile.actions.local_port = 8999;
        let settings = AppSettings::default();
        let config = frp_server_config(&profile, TunnelServiceKind::Actions, &settings, Some(String::new()));
        let text = build_frpc_toml(&config);
        assert!(text.contains("plugin.type = \"https2http\""));
        assert!(text.contains("plugin.localAddr = \"[::1]:8999\""));
        assert!(text.contains(r#"plugin.crtPath = "C:\\certs\\fullchain.pem""#));
        assert!(text.contains("transport.useCompression = true"));
        assert!(!text.contains("localPort ="));
    }

    #[test]
    fn shared_connection_includes_multiplexing_and_transport_tls() {
        let profile = WorkspaceProfile::new("/tmp/shared".into(), None);
        let settings = AppSettings::default();
        let first = frp_server_config(&profile, TunnelServiceKind::Mcp, &settings, Some(String::new()));
        let mut next = first.clone();
        assert!(same_connection(&first, &next));
        next.proxy.options.tcp_mux = !first.proxy.options.tcp_mux;
        assert!(!same_connection(&first, &next));
        next = first.clone();
        next.proxy.options.tls_enable = !first.proxy.options.tls_enable;
        assert!(!same_connection(&first, &next));
    }

    #[test]
    fn strings_cannot_inject_additional_toml_lines() {
        assert_eq!(toml_string("x\"\nserverPort=1\u{7f}"), "\"x\\\"\\nserverPort=1\\u007F\"");
        assert_eq!(toml_string(r"C:\certs\key.pem"), r#""C:\\certs\\key.pem""#);
    }

}
