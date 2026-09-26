use super::*;
const IDLE:u64=1800;
const ABSOLUTE:u64=8*3600;
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
    let profile = "privacy-unapproved-profile";
    ctx.remote_request = Some(request(&Arc::default(),profile,"A"));
    ctx.execution_gate.pause().unwrap();
    let root_text = root.path().display().to_string();
    for (name,..) in crate::tools::registry::P0_TOOLS {
        let result = call_tool(&ctx,name,&json!({"confirm":true,"authorized":true,"grant_id":"pretend"}));
        assert_eq!(result["error"]["code"],"CHAT_AUTHORIZATION_REQUIRED","{name}: {result}");
        assert_ne!(result["error"]["code"],"WORKSPACE_OFFLINE","{name}: {result}");
        let text = result.to_string();
        assert!(!text.contains(profile),"{name}: {result}");
        assert!(!text.contains(&root_text),"{name}: {result}");
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
        let svc = Arc::new(ChatAuthorizer::default());
        svc.configure("p", &SessionPolicy {chat_lease_ttl_seconds:ABSOLUTE,chat_idle_timeout_seconds:IDLE,..Default::default()}).unwrap();
        let req = request(&svc,"p","A");
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
    allow(&a,&["files.read"]); allow(&other,&["files.read"]);
    assert_eq!(svc.request(&b,&json!({}))["error"]["code"],"EXCLUSIVE_CHAT_LOCKED");
    assert!(svc.permit(&a,&["files.read"]).is_ok()); assert!(svc.permit(&b,&["files.read"]).is_err());
    assert!(svc.permit(&other,&["files.read"]).is_ok());
    svc.revoke("p",None); allow(&b,&["files.read"]);
    assert!(svc.permit(&b,&["files.read"]).is_ok()); assert!(svc.permit(&other,&["files.read"]).is_ok());
}
#[test]
fn metadata_limits_capacity_and_no_raw_identifiers_in_status() {
    let svc = Arc::new(ChatAuthorizer::default()); svc.set_exclusive("p",false);
    for i in 0..MAX_RECORDS { assert_eq!(svc.request(&request(&svc,"p",&format!("session-{i}")),&json!({}))["ok"],true); }
    assert_eq!(svc.request(&request(&svc,"p","overflow"),&json!({}))["ok"],false);
    for session in ["".to_string(),"x".repeat(257),"bad\nvalue".into()] { assert!(request(&svc,"p",&session).identity().is_err()); }
    assert!(!svc.snapshot("p").to_string().contains("session-"));
    assert_eq!(svc.status(&request(&svc,"p","new-unapproved"))["authorization"]["status"],"unauthorized");
}
#[test]
fn offline_unapproved_authorization_request_is_suppressed_without_pending_noise_until_resume() {
    let root = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let svc = Arc::new(ChatAuthorizer::default());
    let req = request(&svc, "offline-auth-noise-profile", "C");
    let mut ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
    ctx.remote_request = Some(req.clone());

    let status = call_tool(&ctx, "auth_status", &json!({}));
    assert_eq!(status["authorization"]["status"], "unauthorized", "{status}");
    assert!(svc.snapshot(&req.profile)["records"].as_array().unwrap().is_empty());

    let mut events = svc.subscribe();
    ctx.execution_gate.pause().unwrap();

    let blocked = call_tool(&ctx, "request_chat_authorization", &json!({}));
    assert_eq!(blocked["error"]["code"], "CHAT_AUTHORIZATION_UNAVAILABLE", "{blocked}");
    assert_eq!(blocked["error"]["category"], "permission", "{blocked}");
    assert_eq!(blocked["error"]["retryable"], false, "{blocked}");
    assert_eq!(blocked["requires_local_action"], false, "{blocked}");
    let blocked_text = blocked.to_string().to_ascii_lowercase();
    assert!(!blocked_text.contains("offline"), "{blocked}");
    assert!(!blocked_text.contains("paused"), "{blocked}");
    assert!(svc.snapshot(&req.profile)["records"].as_array().unwrap().is_empty());
    while let Ok(event) = events.try_recv() {
        assert_ne!(event.profile, req.profile, "suppressed request emitted a profile event");
    }

    let business = call_tool(&ctx, "server_info", &json!({}));
    assert_eq!(business["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED", "{business}");
    assert_ne!(business["error"]["code"], "WORKSPACE_OFFLINE");

    ctx.execution_gate.resume().unwrap();
    let pending = call_tool(&ctx, "request_chat_authorization", &json!({}));
    assert_eq!(pending["authorization"]["status"], "pending", "{pending}");
    assert_eq!(svc.snapshot(&req.profile)["records"].as_array().unwrap().len(), 1);
    let event = events.try_recv().expect("resume should allow one pending event");
    assert_eq!(event.profile, req.profile);
    assert_eq!(event.kind, "pending");
    assert!(events.try_recv().is_err());
}

#[test]
fn offline_preserves_existing_pending_active_and_exclusive_ordering() {
    let root = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let svc = Arc::new(ChatAuthorizer::default());
    let a = request(&svc, "offline-auth-existing-profile", "A");
    let mut ctx_a = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
    ctx_a.remote_request = Some(a.clone());

    let pending = call_tool(&ctx_a, "request_chat_authorization", &json!({"scopes":["files.read"]}));
    assert_eq!(pending["authorization"]["status"], "pending", "{pending}");
    let id = pending["authorization"]["id"].as_str().unwrap().to_owned();
    let invalid_before_pause =
        call_tool(&ctx_a, "request_chat_authorization", &json!({"unexpected":true}));
    assert_eq!(invalid_before_pause["ok"], false, "{invalid_before_pause}");

    let mut events = svc.subscribe();
    ctx_a.execution_gate.pause().unwrap();

    let invalid_while_offline =
        call_tool(&ctx_a, "request_chat_authorization", &json!({"unexpected":true}));
    assert_eq!(
        invalid_while_offline,
        invalid_before_pause,
        "pause changed existing request-validation precedence"
    );
    assert!(events.try_recv().is_err(), "invalid retry emitted an authorization event");

    let pending_retry = call_tool(&ctx_a, "request_chat_authorization", &json!({"scopes":["exec.run"]}));
    assert_eq!(pending_retry["authorization"]["id"], id);
    assert_eq!(pending_retry["authorization"]["status"], "pending");
    assert!(events.try_recv().is_err(), "idempotent pending retry emitted a new event");

    svc.decide(&a.profile, &id, true, &["files.read".into()]).unwrap();
    while events.try_recv().is_ok() {}

    let active_retry = call_tool(&ctx_a, "request_chat_authorization", &json!({}));
    assert_eq!(active_retry["authorization"]["id"], id);
    assert_eq!(active_retry["authorization"]["status"], "active");
    assert!(events.try_recv().is_err(), "active retry emitted a new event");

    let b = request(&svc, &a.profile, "B");
    let mut ctx_b = ctx_a.background_snapshot();
    ctx_b.remote_request = Some(b);
    let foreign = call_tool(&ctx_b, "request_chat_authorization", &json!({}));
    assert_eq!(foreign["error"]["code"], "EXCLUSIVE_CHAT_LOCKED", "{foreign}");
    assert!(foreign.get("authorization").is_none());
    assert_eq!(svc.snapshot(&a.profile)["records"].as_array().unwrap().len(), 1);
    assert!(events.try_recv().is_err(), "foreign request emitted an authorization event");
}

#[test]
fn recovery_required_precedes_offline_authorization_suppression() {
    let root = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let fence_root = tempfile::tempdir().unwrap();
    let svc = Arc::new(ChatAuthorizer::default());
    let req = request(&svc, "offline-auth-recovery-profile", "R");
    let binding = req.binding.as_ref().unwrap().clone();

    let initial = super::super::execution_fence::ExecutionFence::open(fence_root.path()).unwrap();
    initial.mark(&binding).unwrap();
    drop(initial);
    let recovered = Arc::new(
        super::super::execution_fence::ExecutionFence::open(fence_root.path()).unwrap()
    );
    assert!(!recovered.ready());
    svc.fences.lock().unwrap().insert(req.profile.clone(), recovered);

    let mut ctx = ToolContext::for_test(root.path().into(), harness.path().into()).unwrap();
    ctx.remote_request = Some(req.clone());
    ctx.execution_gate.pause().unwrap();

    let blocked = call_tool(&ctx, "request_chat_authorization", &json!({}));
    assert_eq!(blocked["error"]["code"], "CHAT_RECOVERY_REQUIRED", "{blocked}");
    assert_ne!(blocked["error"]["code"], "CHAT_AUTHORIZATION_UNAVAILABLE");
    assert!(svc.snapshot(&req.profile)["records"].as_array().unwrap().is_empty());
}

#[test]
fn runtime_cwd_sessions_jobs_harness_and_history_are_separate() {
    let root = tempfile::tempdir().unwrap(); let h = tempfile::tempdir().unwrap();
    std::fs::create_dir(root.path().join("a")).unwrap();
    let base = ToolContext::for_test(root.path().into(),h.path().into()).unwrap(); let svc = Arc::new(ChatAuthorizer::default());
    svc.set_exclusive("p",false);
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
            let req = request(&svc,"p",&format!("C{n}")); barrier.wait();
            let result = svc.request(&req,&json!({"scopes":["files.read"]}));
            if result["ok"] == true {
                svc.decide("p",result["authorization"]["id"].as_str().unwrap(),true,&["files.read".into()]).unwrap();
            } else { assert_eq!(result["error"]["code"],"EXCLUSIVE_CHAT_LOCKED"); }
        }));
    }
    for thread in threads { thread.join().unwrap(); }
    assert_eq!(svc.snapshot("p")["records"].as_array().unwrap().iter().filter(|v|v["status"] == "active").count(),1);
}

#[test]
fn local_authority_export_is_local_grant_only_and_tracks_offline_state() {
    use crate::auth::{LocalAuthorityPhase, LocalExecutionState};
    let svc = Arc::new(ChatAuthorizer::default());
    let storage = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let profile = "local-authority-export";
    svc.attach_storage(profile, storage.path(), harness.path())
        .unwrap();
    let req = request(&svc, profile, "owner-A");
    allow(&req, &["files.read", "exec.run"]);
    let gate = crate::runtime::WorkspaceExecutionGate::shared();

    let active = svc.local_authority_snapshot(&req, &gate).unwrap();
    assert_eq!(active.phase(), LocalAuthorityPhase::Active);
    assert_eq!(active.execution_state(), LocalExecutionState::Online);
    assert!(active.scopes().contains("files.read"));
    assert!(active.scopes().contains("exec.run"));
    assert_eq!(active.authority_epoch(), 1);
    assert!(active.authority_revision() > 0);

    gate.pause().unwrap();
    let offline = svc.local_authority_snapshot(&req, &gate).unwrap();
    assert_eq!(offline.phase(), LocalAuthorityPhase::Active);
    assert_eq!(offline.execution_state(), LocalExecutionState::Offline);
    assert_eq!(offline.authority_epoch(), active.authority_epoch());

    let foreign = request(&svc, profile, "foreign-B");
    assert_eq!(
        svc.local_authority_snapshot(&foreign, &gate).unwrap_err(),
        "EXCLUSIVE_CHAT_LOCKED"
    );
}

#[test]
fn local_authority_export_preserves_draining_owner_without_enabling_execution() {
    use crate::auth::{LocalAuthorityPhase, LocalExecutionState};
    let svc = Arc::new(ChatAuthorizer::default());
    let storage = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let profile = "local-authority-draining";
    svc.attach_storage(profile, storage.path(), harness.path())
        .unwrap();
    let req = request(&svc, profile, "owner-A");
    allow(&req, &["files.read"]);
    let gate = crate::runtime::WorkspaceExecutionGate::shared();
    let id = svc.snapshot(profile)["records"][0]["id"]
        .as_str()
        .unwrap()
        .to_owned();
    let in_flight = svc.admit(&req, &["files.read"]).unwrap();

    svc.revoke(profile, Some(&id));
    let draining = svc.local_authority_snapshot(&req, &gate).unwrap();
    assert_eq!(draining.phase(), LocalAuthorityPhase::Draining);
    assert_eq!(draining.execution_state(), LocalExecutionState::Offline);

    drop(in_flight);
    assert!(svc.local_authority_snapshot(&req, &gate).is_err());
    assert_eq!(svc.snapshot(profile)["lease_state"], "free");
}

#[test]
fn local_admission_ticket_is_one_handoff_and_fails_after_pause_or_revoke() {
    let svc = Arc::new(ChatAuthorizer::default());
    let storage = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let profile = "local-admission-fences";
    svc.attach_storage(profile, storage.path(), harness.path())
        .unwrap();
    let req = request(&svc, profile, "owner-A");
    allow(&req, &["files.read"]);
    let gate = crate::runtime::WorkspaceExecutionGate::shared();

    let stale_gate = svc
        .issue_local_admission_ticket(&req, &["files.read"], &gate)
        .unwrap();
    gate.pause().unwrap();
    gate.resume().unwrap();
    assert_eq!(
        svc.commit_local_admission(&req, &gate, stale_gate)
            .err().unwrap(),
        "WORKSPACE_EXECUTION_CHANGED"
    );

    let stale_grant = svc
        .issue_local_admission_ticket(&req, &["files.read"], &gate)
        .unwrap();
    let id = svc.snapshot(profile)["records"][0]["id"]
        .as_str()
        .unwrap()
        .to_owned();
    svc.revoke(profile, Some(&id));
    assert!(svc
        .commit_local_admission(&req, &gate, stale_grant)
        .is_err());
}

#[test]
fn committed_local_admission_uses_existing_in_flight_drain_semantics() {
    let svc = Arc::new(ChatAuthorizer::default());
    let storage = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let profile = "local-admission-commit";
    svc.attach_storage(profile, storage.path(), harness.path())
        .unwrap();
    let req = request(&svc, profile, "owner-A");
    allow(&req, &["files.read"]);
    let gate = crate::runtime::WorkspaceExecutionGate::shared();
    let id = svc.snapshot(profile)["records"][0]["id"]
        .as_str()
        .unwrap()
        .to_owned();

    let ticket = svc
        .issue_local_admission_ticket(&req, &["files.read"], &gate)
        .unwrap();
    let permit = svc
        .commit_local_admission(&req, &gate, ticket)
        .expect("local admission commit");
    assert_eq!(gate.snapshot().in_flight, 1);

    svc.revoke(profile, Some(&id));
    assert_eq!(svc.snapshot(profile)["lease_state"], "draining");
    drop(permit);
    assert_eq!(gate.snapshot().in_flight, 0);
    assert_eq!(svc.snapshot(profile)["lease_state"], "free");
}

#[test]
fn local_admission_ticket_is_bounded_and_cannot_expand_scope() {
    let svc = Arc::new(ChatAuthorizer::default());
    let storage = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let profile = "local-admission-bounds";
    svc.attach_storage(profile, storage.path(), harness.path())
        .unwrap();
    let req = request(&svc, profile, "owner-A");
    allow(&req, &["files.read"]);
    let gate = crate::runtime::WorkspaceExecutionGate::shared();

    assert!(svc.issue_local_admission_ticket(&req, &[], &gate).is_err());
    assert_eq!(
        svc.issue_local_admission_ticket(&req, &["exec.run"], &gate)
            .err().unwrap(),
        "INSUFFICIENT_CHAT_SCOPE"
    );
    let mut expired = svc
        .issue_local_admission_ticket(&req, &["files.read"], &gate)
        .unwrap();
    expired.expire_for_test();
    assert_eq!(
        svc.commit_local_admission(&req, &gate, expired)
            .err().unwrap(),
        "LOCAL_ADMISSION_EXPIRED"
    );
}
