use super::*;
use crate::tools::{ToolContext, call_tool};
fn request(svc: &Arc<ChatAuthorizer>, profile: &str, session: &str) -> RemoteRequest {
    let token = super::super::principal::issue("https://mcp.example", "https://mcp.example", "fixture-key", "client", 3600).unwrap();
    let principal = super::super::principal::verify(&token, "fixture-key", "https://mcp.example", "https://mcp.example").unwrap();
    let mut req = RemoteRequest::verified(profile,"workspace",principal,&json!({"openai/session":session}),"fixture-key");
    req.service = svc.clone(); req
}
fn allow(req: &RemoteRequest, scopes: &[&str]) {
    let result = req.service.request(req,&json!({"scopes":scopes}));
    assert_eq!(result["ok"],true,"{result}");
    req.service.decide(&req.profile,result["authorization"]["id"].as_str().unwrap(),true,
        &scopes.iter().map(|s| (*s).to_string()).collect::<Vec<_>>()).unwrap();
}
#[test]
fn all_business_tools_are_denied_before_approval_including_dangerous_mode() {
    let root = tempfile::tempdir().unwrap(); let harness = tempfile::tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(),harness.path().into()).unwrap();
    ctx.policy.permission_mode = "dangerous".into(); ctx.permission_mode = "dangerous".into();
    ctx.remote_request = Some(request(&Arc::default(),"profile","A"));
    for (name,..) in crate::tools::registry::P0_TOOLS {
        let result = call_tool(&ctx,name,&json!({"confirm":true,"authorized":true,"grant_id":"pretend"}));
        assert_eq!(result["error"]["code"],"CHAT_AUTHORIZATION_REQUIRED","{name}: {result}");
    }
    assert_eq!(std::fs::read_dir(root.path()).unwrap().count(),0);
}
#[test]
fn model_supplied_identity_never_unlocks_missing_transport_context() {
    let root = tempfile::tempdir().unwrap(); let h = tempfile::tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(),h.path().into()).unwrap();
    ctx.remote_request = Some(RemoteRequest::unresolved("profile"));
    for tool in ["request_chat_authorization","read_file","exec_command"] {
        let v = call_tool(&ctx,tool,&json!({"_meta":{"openai/session":"A"},"oauth_sub":"owner","authorized":true}));
        assert_eq!(v["ok"],false,"{v}");
    }
}
#[test]
fn request_is_idempotent_and_approval_can_only_reduce_scopes() {
    let svc = Arc::new(ChatAuthorizer::default()); let req = request(&svc,"p","A");
    let first = svc.request(&req,&json!({"scopes":["files.read"]}));
    let retry = svc.request(&req,&json!({"scopes":["exec.run"]}));
    assert_eq!(first["authorization"],retry["authorization"]);
    let id = first["authorization"]["id"].as_str().unwrap();
    assert!(svc.decide("p",id,true,&["exec.run".into()]).is_err());
    assert!(svc.decide("wrong-profile",id,true,&["files.read".into()]).is_err());
    svc.decide("p",id,true,&["files.read".into()]).unwrap();
    assert!(svc.decide("p",id,true,&["files.read".into()]).is_err());
    assert!(svc.permit(&req,&["files.read"]).is_ok());
    assert!(svc.permit(&req,&["exec.run"]).is_err());
    assert!(svc.permit(&request(&svc,"p","B"),&["files.read"]).is_err());
    svc.revoke("p",Some(id)); assert!(svc.permit(&req,&["files.read"]).is_err());
}
#[test]
fn pending_idle_absolute_expiry_and_restart_all_fail_closed() {
    for age in [PENDING, IDLE, ABSOLUTE] {
        let svc = Arc::new(ChatAuthorizer::default()); let req = request(&svc,"p","A");
        let v = svc.request(&req,&json!({"scopes":["files.read"]})); let id = v["authorization"]["id"].as_str().unwrap();
        if age != PENDING { svc.decide("p",id,true,&["files.read".into()]).unwrap(); }
        {
            let mut state = svc.state.lock().unwrap(); let r = state.records.get_mut(req.binding.as_ref().unwrap()).unwrap();
            if age == IDLE { r.touched -= Duration::from_secs(age); } else { r.since -= Duration::from_secs(age); }
        }
        assert!(svc.permit(&req,&["files.read"]).is_err());
        assert_eq!(svc.status(&req)["authorization"]["status"],"expired");
        assert!(svc.decide("p",id,true,&["files.read".into()]).is_err());
    }
    let svc = Arc::new(ChatAuthorizer::default()); let req = request(&svc,"p","A"); allow(&req,&["files.read"]);
    assert!(ChatAuthorizer::default().permit(&req,&["files.read"]).is_err());
}
#[test]
fn exclusive_approval_is_atomic_and_does_not_revoke_other_workspaces() {
    let svc = Arc::new(ChatAuthorizer::default()); svc.set_exclusive("p",true);
    let a = request(&svc,"p","A"); let b = request(&svc,"p","B"); let other = request(&svc,"other","A");
    allow(&a,&["files.read"]); allow(&other,&["files.read"]); allow(&b,&["files.read"]);
    assert!(svc.permit(&a,&["files.read"]).is_err()); assert!(svc.permit(&b,&["files.read"]).is_ok());
    assert!(svc.permit(&other,&["files.read"]).is_ok());
    svc.revoke("p",None); assert!(svc.permit(&b,&["files.read"]).is_err()); assert!(svc.permit(&other,&["files.read"]).is_ok());
}
#[test]
fn metadata_limits_capacity_and_no_raw_identifiers_in_status() {
    let svc = Arc::new(ChatAuthorizer::default());
    for i in 0..MAX_RECORDS { assert_eq!(svc.request(&request(&svc,"p",&format!("session-{i}")),&json!({}))["ok"],true); }
    assert_eq!(svc.request(&request(&svc,"p","overflow"),&json!({}))["ok"],false);
    for session in ["".to_string(),"x".repeat(257),"bad\nvalue".into()] { assert!(request(&svc,"p",&session).identity().is_err()); }
    assert!(!svc.snapshot("p").to_string().contains("session-"));
    assert_eq!(svc.status(&request(&svc,"p","new-unapproved"))["authorization"]["status"],"unauthorized");
}
#[test]
fn runtime_cwd_sessions_jobs_harness_and_history_are_separate() {
    let root = tempfile::tempdir().unwrap(); let h = tempfile::tempdir().unwrap();
    std::fs::create_dir(root.path().join("a")).unwrap();
    let base = ToolContext::for_test(root.path().into(),h.path().into()).unwrap(); let svc = Arc::new(ChatAuthorizer::default());
    let a = request(&svc,"p","raw-conversation-A"); let b = request(&svc,"p","raw-conversation-B");
    allow(&a,SCOPES); allow(&b,SCOPES);
    let mut ca = base.background_snapshot(); ca.remote_request = Some(a.clone());
    let mut cb = base.background_snapshot(); cb.remote_request = Some(b.clone());
    let da = ca.chat_domains.scoped(&ca,&a).unwrap(); let db = cb.chat_domains.scoped(&cb,&b).unwrap();
    assert!(!Arc::ptr_eq(&da.sessions,&db.sessions)); assert!(!Arc::ptr_eq(&da.exec_tasks,&db.exec_tasks));
    assert_ne!(da.harness.store_root(),db.harness.store_root());
    da.set_default_cwd(root.path().join("a"));
    assert_eq!(ca.chat_domains.scoped(&ca,&a).unwrap().default_cwd_path(),root.path().join("a"));
    assert_eq!(db.default_cwd_path(),base.workspace.root());
    da.harness.start_task("A private task").unwrap(); assert!(db.harness.current_task().unwrap().is_none());
    let boot = call_tool(&ca,"history_session_bootstrap",&json!({"initial_user_input":"A private initial request"}));
    assert_eq!(boot["ok"],true,"{boot}");
    let other = call_tool(&cb,"history_session_read",&json!({"path":boot["current_path"]})); assert_eq!(other["ok"],false,"{other}");
    assert_eq!(call_tool(&cb,"history_session_search",&json!({"query":"private","history_dir":"docs/history-session"}))["ok"],false);
    assert!(!boot.to_string().contains("raw-conversation-A"));
    assert!(ExecTaskStoreCheck::contains(&da.exec_tasks,"p"));
}
struct ExecTaskStoreCheck;
impl ExecTaskStoreCheck {
    fn contains(expected: &Arc<crate::tools::exec_tasks::ExecTaskStore>, profile: &str) -> bool {
        crate::tools::exec_tasks::ExecTaskStore::live_for_profile(profile).iter().any(|s| Arc::ptr_eq(s,expected))
    }
}
#[test]
fn concurrent_exclusive_grants_have_exactly_one_winner() {
    let svc = Arc::new(ChatAuthorizer::default()); svc.set_exclusive("p",true);
    let barrier = Arc::new(std::sync::Barrier::new(8)); let mut threads = Vec::new();
    for n in 0..8 {
        let svc = svc.clone(); let barrier = barrier.clone();
        threads.push(std::thread::spawn(move || {
            let req = request(&svc,"p",&format!("C{n}"));
            let result = svc.request(&req,&json!({"scopes":["files.read"]}));
            barrier.wait(); svc.decide("p",result["authorization"]["id"].as_str().unwrap(),true,&["files.read".into()]).unwrap();
        }));
    }
    for thread in threads { thread.join().unwrap(); }
    assert_eq!(svc.snapshot("p")["records"].as_array().unwrap().iter().filter(|v|v["status"] == "active").count(),1);
}
