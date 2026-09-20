//! Synthetic HTTP host, not a claim of real ChatGPT or installed notification acceptance.
use std::time::{Duration, Instant};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use super::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};

const PASSWORD: &str = "synthetic-owner-password";
const SECRET: &str = "synthetic-client-secret";
const REDIRECT: &str = "https://chatgpt.com/connector_platform_oauth_redirect";
const VERIFIER: &str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-verifier";
struct Server {
    root: tempfile::TempDir, profile: String, base: String, client: reqwest::Client,
    stop: Option<crate::mcp::ShutdownSender>,
}
impl Server {
    fn new() -> Self {
        let root=tempfile::tempdir().unwrap();let profile=uuid::Uuid::new_v4().to_string();
        let socket=std::net::TcpListener::bind("127.0.0.1:0").unwrap();let port=socket.local_addr().unwrap().port();drop(socket);
        let (stop,_task,_execution_gate)=crate::mcp::spawn_listener_with_origin(port,root.path().into(),profile.clone(),
            AuthConfig {oauth_client_id:"test-client".into(),..Default::default()},PublicOrigin::managed(fixture::ORIGIN).unwrap(),
            Some(SECRET.into()),Some(PASSWORD.into()),Some(fixture::KEY.into()),RuntimeConfig::default()).unwrap();
        let client=reqwest::Client::builder().no_proxy().redirect(reqwest::redirect::Policy::none()).timeout(Duration::from_secs(10)).build().unwrap();
        Self {root,profile,base:format!("http://127.0.0.1:{port}"),client,stop:Some(stop)}
    }
    async fn login(&self,scope:&str)->Value {
        let challenge=URL_SAFE_NO_PAD.encode(Sha256::digest(VERIFIER.as_bytes()));
        let resource=format!("{}/mcp",fixture::ORIGIN);
        let mut fields=vec![("response_type","code"),("client_id","test-client"),("redirect_uri",REDIRECT),
            ("code_challenge",challenge.as_str()),("code_challenge_method","S256"),("resource",resource.as_str()),("scope",scope),("state","synthetic-state")];
        let page=self.client.get(format!("{}/oauth/authorize",self.base)).query(&fields).send().await.unwrap();
        assert_eq!(page.status(),200);let html=page.text().await.unwrap();
        if scope.contains("offline_access"){assert!(html.contains("mcp offline_access"));assert!(html.contains("offline"));}
        fields.retain(|(k,_)|*k!="response_type");fields.push(("password",PASSWORD));
        let response=self.client.post(format!("{}/oauth/authorize",self.base)).form(&fields).send().await.unwrap();
        assert_eq!(response.status(),303);
        let location=reqwest::Url::parse(response.headers()["location"].to_str().unwrap()).unwrap();
        let code=location.query_pairs().find(|(k,_)|k=="code").unwrap().1.into_owned();
        let response=self.client.post(format!("{}/oauth/token",self.base)).form(&[
            ("grant_type","authorization_code"),("code",code.as_str()),("code_verifier",VERIFIER),
            ("client_id","test-client"),("client_secret",SECRET),("redirect_uri",REDIRECT),("resource",resource.as_str())]).send().await.unwrap();
        assert_eq!(response.status(),200);assert_eq!(response.headers()["cache-control"],"no-store");
        assert_eq!(response.headers()["pragma"],"no-cache");response.json().await.unwrap()
    }
    async fn rotate(&self,token:&str)->reqwest::Response {
        self.client.post(format!("{}/oauth/token",self.base)).form(&[("grant_type","refresh_token"),
            ("refresh_token",token),("client_id","test-client"),("client_secret",SECRET)]).send().await.unwrap()
    }
    async fn rpc(&self,token:&str,chat:&str,name:&str,args:Value)->Value {
        let response=self.client.post(format!("{}/mcp",self.base)).bearer_auth(token)
            .json(&fixture::request(name,args,chat)).send().await.unwrap();
        assert_eq!(response.status(),200);assert!(response.headers().get("www-authenticate").is_none());
        let body:Value=response.json().await.unwrap();body["result"]["structuredContent"].clone()
    }
    async fn approve(&self,token:&str,chat:&str)->Value {
        let grant=self.rpc(token,chat,"request_chat_authorization",json!({"scopes":super::chat::SCOPES})).await;
        super::chat::service().decide(&self.profile,grant["authorization"]["id"].as_str().unwrap(),true,
            &super::chat::SCOPES.iter().map(|s|(*s).to_owned()).collect::<Vec<_>>()).unwrap();
        self.rpc(token,chat,"auth_status",json!({})).await["authorization"].clone()
    }
}
impl Drop for Server {fn drop(&mut self){let _=std::fs::write(self.root.path().join("release"),"");if let Some(stop)=self.stop.take(){let _=stop.send(());}}}

#[tokio::test]
async fn http_refresh_preserves_owner_blocks_other_chat_and_revokes_replayed_family() {
    let s=Server::new();
    let meta:Value=s.client.get(format!("{}/.well-known/oauth-authorization-server",s.base)).send().await.unwrap().json().await.unwrap();
    assert_eq!(meta["grant_types_supported"],json!(["authorization_code","refresh_token"]));
    assert_eq!(meta["scopes_supported"],json!(["mcp","offline_access"]));
    let first=s.login("offline_access mcp mcp").await;
    assert_eq!(first["expires_in"],3600);assert_eq!(first["scope"],"mcp offline_access");
    let access=first["access_token"].as_str().unwrap();let old_refresh=first["refresh_token"].as_str().unwrap();
    let before=s.approve(access,"A").await;
    let renewed=s.rotate(old_refresh).await;assert_eq!(renewed.status(),200);
    let renewed:Value=renewed.json().await.unwrap();let next_access=renewed["access_token"].as_str().unwrap();
    assert_ne!(old_refresh,renewed["refresh_token"].as_str().unwrap());
    let after=s.rpc(next_access,"A","auth_status",json!({})).await;
    assert_eq!(after["authorization"]["id"],before["id"]);
    assert_eq!(after["authorization"]["fingerprint"],before["fingerprint"]);
    assert_eq!(after["authorization"]["expires_at"],before["expires_at"]);
    assert_eq!(s.rpc(next_access,"A","server_info",json!({})).await["ok"],true);
    let mut events=super::chat::service().subscribe();
    for _ in 0..100 {
        let denied=s.rpc(next_access,"B","request_chat_authorization",json!({})).await;
        assert_eq!(denied["error"]["code"],"EXCLUSIVE_CHAT_LOCKED");assert_eq!(denied["requires_local_action"],false);
        assert!(denied.get("authorization").is_none());
    }
    while let Ok(event)=events.try_recv(){assert_ne!(event.profile,s.profile,"blocked chat must emit no profile event");}
    assert_eq!(s.rpc(next_access,"B","server_info",json!({})).await["error"]["code"],"EXCLUSIVE_CHAT_LOCKED");
    let replay=s.rotate(old_refresh).await;assert_eq!(replay.status(),400);
    assert_eq!(replay.json::<Value>().await.unwrap()["error"],"invalid_grant");
    let rejected=s.client.post(format!("{}/mcp",s.base)).bearer_auth(next_access)
        .json(&fixture::request("server_info",json!({}),"A")).send().await.unwrap();
    assert_eq!(rejected.status(),401);
}
#[tokio::test]
async fn http_offline_consent_is_required_and_plain_scope_gets_access_only() {
    let s=Server::new();let result=s.login("mcp").await;
    assert!(result.get("refresh_token").is_none());assert_eq!(result["scope"],"mcp");
    let unknown=s.client.post(format!("{}/oauth/token",s.base)).form(&[("grant_type","password")]).send().await.unwrap();
    assert_eq!(unknown.status(),400);assert_eq!(unknown.json::<Value>().await.unwrap()["error"],"unsupported_grant_type");
    let too_large=s.client.post(format!("{}/oauth/token",s.base)).header("content-type","application/x-www-form-urlencoded")
        .body(format!("grant_type=refresh_token&refresh_token={}","a".repeat(9000))).send().await.unwrap();
    assert_eq!(too_large.status(),413);
}
#[tokio::test]
async fn http_revoked_owner_drains_actual_background_process_before_successor() {
    let s=Server::new();let first=s.login("mcp").await;let access=first["access_token"].as_str().unwrap();
    s.approve(access,"A").await;
    std::fs::write(s.root.path().join("hold.py"),"import pathlib, time\npathlib.Path('started').write_text('ready')\nwhile not pathlib.Path('release').exists():\n time.sleep(.05)\nprint('drained', flush=True)\n").unwrap();
    let python=if cfg!(windows){"python"}else{"python3"};
    let job=s.rpc(access,"A","start_exec_task",json!({"cmd":format!("{python} hold.py"),"request_id":"drain-http-job","timeout_ms":10000})).await;
    assert_eq!(job["ok"],true,"{job}");
    let started_at=Instant::now();let start_deadline=started_at+Duration::from_secs(8);
    // A trusted, read-only test observer verifies actual task termination after A
    // is revoked. Remote A/B remain denied; this grants neither conversation rights.
    let observer_root=tempfile::tempdir().unwrap();
    let mut observer=crate::tools::ToolContext::for_test(s.root.path().into(),observer_root.path().into()).unwrap();
    let query=json!({"job_id":job["job_id"],"limit":4096});
    let mut found=false;
    for store in crate::tools::exec_tasks::ExecTaskStore::live_for_profile(&s.profile) {
        observer.exec_tasks=store;
        if crate::tools::exec_tasks::get(&observer,&query).is_ok(){found=true;break;}
    }
    assert!(found,"submitted task must be registered before admission returns");
    let read_task=||crate::tools::exec_tasks::get(&observer,&query).expect("authoritative local task");
    while !s.root.path().join("started").exists() {
        let state=read_task();
        assert_ne!(state["terminal"],true,"worker terminated before readiness: {state}");
        assert!(Instant::now()<start_deadline,"worker must really start within original 8s gate: {state}");
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
    assert_eq!(std::fs::read_to_string(s.root.path().join("started")).unwrap(),"ready");
    eprintln!("drain-startup ready after {}ms",started_at.elapsed().as_millis());
    let service=super::chat::service();service.revoke(&s.profile,None);
    assert_eq!(service.snapshot(&s.profile)["lease_state"],"draining");
    assert_eq!(s.rpc(access,"B","request_chat_authorization",json!({})).await["error"]["code"],"CHAT_WORK_DRAINING");
    std::fs::write(s.root.path().join("release"),"").unwrap();
    // Startup and drainage are separate phases. Retain the actual 10s process
    // timeout, and never mistake its forced termination for a graceful release.
    let drain_deadline=Instant::now()+Duration::from_secs(8);
    let finished=loop {
        let state=read_task();
        if state["terminal"]==true{break state;}
        assert!(Instant::now()<drain_deadline,"draining must settle after actual child exit: {state}");
        tokio::time::sleep(Duration::from_millis(25)).await;
    };
    assert_eq!(finished["status"],"succeeded","{finished}");
    assert_eq!(finished["result"]["exit_code"],0,"{finished}");
    assert_eq!(finished["result"]["output_complete"],true,"{finished}");
    assert_eq!(finished["result"]["process_may_be_running"],false,"{finished}");
    assert!(finished["stdout"]["text"].as_str().unwrap().contains("drained"),"{finished}");
    while service.snapshot(&s.profile)["lease_state"]!="free" {
        assert!(Instant::now()<drain_deadline,"successful task must release the drain fence");
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
    assert_eq!(s.rpc(access,"B","request_chat_authorization",json!({})).await["authorization"]["status"],"pending");
}
