use super::*;
use serde_json::{json, Value};
use crate::auth::{chat, principal};

struct Fixture { state: AppState, profile: WorkspaceProfile, _root: tempfile::TempDir, client: reqwest::Client }
impl Fixture {
    fn new() -> Self {
        let state = AppState::new().unwrap();
        let root = tempfile::tempdir().unwrap();
        let mut profile = WorkspaceProfile::new(root.path().display().to_string(), Some("OAuth reload fixture".into()));
        profile.tunnel.tunnel_type = "none".into();
        profile.tunnel.public_url = "https://oauth-reload.example".into();
        profile.actions.tunnel_type = "none".into();
        profile.auth.auth_type = "noauth".into();
        let mcp_port = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let actions_port = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        profile.runtime.local_port = mcp_port.local_addr().unwrap().port();
        profile.actions.local_port = actions_port.local_addr().unwrap().port();
        state.with_data(|store| {
            store.init_workspace_secrets(&profile.id)?;
            store.add(profile.clone())
        }).unwrap();
        Self { state, profile, _root: root, client: reqwest::Client::builder().no_proxy()
            .redirect(reqwest::redirect::Policy::none()).timeout(std::time::Duration::from_secs(8)).build().unwrap() }
    }
    fn base(&self) -> String { format!("http://127.0.0.1:{}", self.profile.runtime.local_port) }
    async fn metadata(&self) -> Value {
        let response = self.client.get(format!("{}/.well-known/oauth-authorization-server", self.base())).send().await.unwrap();
        assert_eq!(response.status(), 200);
        response.json().await.unwrap()
    }
    async fn token_request(&self, secret: &str) -> Value {
        self.client.post(format!("{}/oauth/token", self.base())).basic_auth(&self.profile.auth.oauth_client_id, Some(secret))
            .form(&[("grant_type", "authorization_code"), ("code", "missing-fixture-code"),
                ("redirect_uri", "https://chatgpt.com/connector_platform_oauth_redirect"), ("code_verifier", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
                ("resource", "https://oauth-reload.example/mcp")]).send().await.unwrap().json().await.unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        chat::service().revoke(&self.profile.id, None);
        let _ = self.state.with_runtime(|r| { r.drop_workspace(&self.profile); Ok(()) });
        let _ = self.state.with_data(|s| { s.remove(&self.profile.id)?; Ok(()) });
    }
}

#[test]
fn config_diff_selects_only_affected_services() {
    let old = WorkspaceProfile::new("fixture".into(), None);
    let mut next = old.clone(); next.name = "renamed".into();
    assert!(changed_services(&old, &next).unwrap().is_empty());
    next.auth.auth_type = "noauth".into();
    assert_eq!(changed_services(&old, &next).unwrap(), vec![ServiceKind::Mcp]);
    next = old.clone(); next.actions.auth_type = "oauth".into();
    assert_eq!(changed_services(&old, &next).unwrap(), vec![ServiceKind::Actions]);
    next = old.clone(); next.path = "another".into();
    assert_eq!(changed_services(&old, &next).unwrap(), vec![ServiceKind::Mcp, ServiceKind::Actions]);
}

#[tokio::test]
async fn stopped_profile_save_and_secret_change_never_start_a_service() {
    let mut f = Fixture::new(); f.profile.auth.auth_type = "oauth".into();
    update(&f.state, f.profile.clone()).await.unwrap();
    write_secret(&f.state, Some(&f.profile.id), "oauth_client_secret", Some("fixture-stopped-secret")).await.unwrap();
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Mcp))).unwrap());
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Actions))).unwrap());
}

#[tokio::test]
async fn running_auth_save_loads_secret_and_rotation_revokes_existing_grants() {
    let mut f = Fixture::new();
    runtime::start_mcp_service(&f.state, &f.profile.id).await.unwrap();
    let response = f.client.get(format!("{}/.well-known/oauth-protected-resource", f.base())).send().await.unwrap();
    assert_eq!(response.status(), 404);
    f.profile.auth.auth_type = "oauth".into();
    update(&f.state, f.profile.clone()).await.unwrap();
    assert_eq!(f.metadata().await["token_endpoint_auth_methods_supported"], json!(["client_secret_post", "client_secret_basic"]));
    let original = f.state.with_data(|s| s.get_workspace_secret(&f.profile.id, "oauth_client_secret")).unwrap().unwrap();
    assert_eq!(f.token_request("wrong-fixture-secret").await["error"], "invalid_client");
    assert_eq!(f.token_request(&original).await["error"], "invalid_grant");
    let identity = principal::VerifiedPrincipal { issuer: "https://oauth-reload.example".into(), subject: "desktop-owner".into(),
        client_id: f.profile.auth.oauth_client_id.clone(), expires_at: chat::unix_now() + 60 };
    let req = chat::RemoteRequest::verified(&f.profile.id, &f.profile.path, identity, &json!({"openai/session":"fixture-chat"}), "binding-fixture");
    let authorizer = chat::service(); let pending = authorizer.request(&req, &json!({"scopes":["files.read"]}));
    authorizer.decide(&f.profile.id, pending["authorization"]["id"].as_str().unwrap(), true, &["files.read".into()]).unwrap();
    assert!(authorizer.permit(&req, &["files.read"]).is_ok());
    write_secret(&f.state, Some(&f.profile.id), "oauth_client_secret", Some("rotated-fixture-secret")).await.unwrap();
    assert!(authorizer.permit(&req, &["files.read"]).is_err());
    assert_eq!(f.token_request(&original).await["error"], "invalid_client");
    assert_eq!(f.token_request("rotated-fixture-secret").await["error"], "invalid_grant");
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Actions))).unwrap());
    // Explicit empty workspace secret is a public PKCE client, never an advertised secret.
    write_secret(&f.state, Some(&f.profile.id), "oauth_client_secret", Some("")).await.unwrap();
    assert_eq!(f.metadata().await["token_endpoint_auth_methods_supported"], json!(["none"]));
}

#[tokio::test]
async fn persistence_failure_stops_old_listener_and_returns_failure() {
    let f = Fixture::new();
    let _gate = RESTART_GATE.lock().await;
    runtime::start_mcp_service(&f.state, &f.profile.id).await.unwrap();
    let result: AppResult<()> = apply(&f.state, &[(f.profile.clone(), ServiceKind::Mcp)], || Err(AppError::Message("injected persistence failure".into()))).await;
    assert!(result.is_err());
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Mcp))).unwrap());
    assert!(f.client.get(format!("{}/mcp", f.base())).send().await.is_err());
}

#[tokio::test]
async fn failed_restart_does_not_report_a_successful_config_application() {
    let mut f = Fixture::new();
    runtime::start_mcp_service(&f.state, &f.profile.id).await.unwrap();
    f.profile.path = f._root.path().join("missing-directory").display().to_string();
    let result = update(&f.state, f.profile.clone()).await;
    assert!(result.is_err(), "missing workspace must not be reported as running");
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Mcp))).unwrap());
}

#[tokio::test]
async fn concurrent_secret_writes_complete_before_returning_with_one_consistent_listener() {
    let mut f = Fixture::new(); f.profile.auth.auth_type = "oauth".into();
    update(&f.state, f.profile.clone()).await.unwrap();
    runtime::start_mcp_service(&f.state, &f.profile.id).await.unwrap();
    let (first, second) = tokio::join!(
        write_secret(&f.state, Some(&f.profile.id), "oauth_client_secret", Some("parallel-fixture-one")),
        write_secret(&f.state, Some(&f.profile.id), "oauth_client_secret", Some("parallel-fixture-two")));
    first.unwrap(); second.unwrap();
    let saved = f.state.with_data(|s| s.get_workspace_secret(&f.profile.id, "oauth_client_secret")).unwrap().unwrap();
    assert_eq!(f.token_request(&saved).await["error"], "invalid_grant");
    let stale = if saved == "parallel-fixture-one" { "parallel-fixture-two" } else { "parallel-fixture-one" };
    assert_eq!(f.token_request(stale).await["error"], "invalid_client");
    assert!(f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Mcp))).unwrap());
}

#[tokio::test]
async fn shared_credential_update_reloads_only_running_shared_consumers() {
    let mut f = Fixture::new(); f.profile.auth.auth_type = "oauth".into();
    f.profile.auth.use_shared_secrets = true;
    update(&f.state, f.profile.clone()).await.unwrap();
    let other_root = tempfile::tempdir().unwrap();
    let mut stopped = WorkspaceProfile::new(other_root.path().display().to_string(), Some("stopped shared consumer".into()));
    stopped.tunnel.tunnel_type = "none".into(); stopped.actions.tunnel_type = "none".into();
    stopped.auth.use_shared_secrets = true;
    f.state.with_data(|s| { crate::workspace::resources::assign_free_workspace_ports(s.list(), &mut stopped)?;
        s.init_workspace_secrets(&stopped.id)?; s.add(stopped.clone()) }).unwrap();
    runtime::start_mcp_service(&f.state, &f.profile.id).await.unwrap();
    // A dedicated AppState owns only this test's listeners; all credentials are test-store fixtures.
    let old = f.state.with_data(|s| Ok(s.get_shared_secret("oauth_client_secret"))).unwrap().unwrap();
    let client_id = f.state.with_data(|s| Ok(s.get_shared_secret("oauth_client_id"))).unwrap().unwrap();
    f.profile.auth.oauth_client_id = client_id;
    write_secret(&f.state, None, "oauth_client_secret", Some("shared-rotated-fixture")).await.unwrap();
    assert_eq!(f.token_request(&old).await["error"], "invalid_client");
    assert_eq!(f.token_request("shared-rotated-fixture").await["error"], "invalid_grant");
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&stopped.id, ServiceKind::Mcp))).unwrap());
    assert!(!f.state.with_runtime(|r| Ok(r.is_running(&f.profile.id, ServiceKind::Actions))).unwrap());
    f.state.with_data(|s| { s.remove(&stopped.id)?; s.remove_workspace_secrets(&stopped.id) }).unwrap();
}
