use super::*;
use crate::tunnel::frp::FrpProxyConfig;
use crate::workspace::endpoint::FrpRouteOptions;

fn custom_config() -> FrpServerConfig {
    FrpServerConfig { server_addr: "203.0.113.10".into(), server_port: 7000, token: Some("test-only".into()),
        proxy: FrpProxyConfig { proxy_name: "custom-test".into(), local_port: 28766, subdomain: String::new(),
            options: FrpRouteOptions { domain_mode: "custom".into(), custom_domain: "mcp.example.com".into(), ..Default::default() } } }
}

#[test]
fn launch_accepts_ip_server_and_full_custom_domain_without_prefix() {
    let config = custom_config();
    validate_frp_config(&config).unwrap();
    let text = build_frpc_toml_for_routes(&[config]);
    assert!(text.contains("customDomains = [\"mcp.example.com\"]"));
    assert!(!text.contains("subdomain ="));
}

#[test]
fn launch_rejects_missing_legacy_prefix_bad_domain_or_invalid_port() {
    let mut config = custom_config(); config.proxy.options.domain_mode = "subdomain".into();
    assert!(validate_frp_config(&config).is_err());
    let mut config = custom_config(); config.proxy.options.custom_domain = "https://wrong/path".into();
    assert!(validate_frp_config(&config).is_err());
    let mut config = custom_config(); config.server_port = 0;
    assert!(validate_frp_config(&config).is_err());
}

#[test]
fn launch_rejects_tls_passthrough_to_internal_http_listener() {
    let mut config = custom_config();
    config.proxy.options.proxy_type = "https".into();
    config.proxy.options.https_mode = "local_tls".into();
    config.proxy.options.local_port = Some(28766);
    assert!(validate_frp_config(&config).is_err());
}

#[cfg(feature = "frp-binary-tests")]
#[test]
fn generated_config_is_accepted_by_real_frpc_0612() {
    let binary = std::env::var("FRPC_TEST_BINARY").expect("FRPC_TEST_BINARY required for opt-in test");
    let output = std::process::Command::new(&binary).arg("--version").output().unwrap();
    assert!(output.status.success());
    assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), "0.61.2");
    let dir = tempfile::tempdir().unwrap();
    for case in 0..3 {
        let mut config = custom_config();
        if case == 1 { config.proxy.options.proxy_type = "https".into(); config.proxy.options.https_mode = "local_tls".into(); config.proxy.options.local_port = Some(443); }
        if case == 2 { config.proxy.options.domain_mode = "subdomain".into(); config.proxy.options.subdomain_host = "example.com".into(); config.proxy.subdomain = "legacy".into(); }
        validate_frp_config(&config).unwrap();
        let path = dir.path().join(format!("case-{case}.toml"));
        config_security::write_private_config(&path, &build_frpc_toml_for_routes(&[config])).unwrap();
        let result = std::process::Command::new(&binary).arg("verify").arg("-c").arg(path).output().unwrap();
        assert!(result.status.success(), "frpc verify case {case} failed: {}", String::from_utf8_lossy(&result.stderr));
    }
}
