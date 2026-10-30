use super::*;
use crate::auth::{
    chat::{ChatAuthorizer, RemoteRequest},
    principal::VerifiedPrincipal,
};
use crate::tools::call_tool;
use std::{
    fs,
    process::Command,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: tempfile::TempDir,
    _state: tempfile::TempDir,
    _auth: tempfile::TempDir,
    ctx: ToolContext,
    request: RemoteRequest,
}
impl Fixture {
    fn new(remote: bool) -> Self {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        let auth = tempfile::tempdir().unwrap();
        for args in [
            &["init", "-q"][..],
            &["config", "user.name", "Fixture"],
            &["config", "user.email", "fixture@example.invalid"],
        ] {
            assert!(Command::new("git")
                .current_dir(root.path())
                .args(args)
                .output()
                .unwrap()
                .status
                .success());
        }
        fs::write(root.path().join("fixture.txt"), "original\n").unwrap();
        for args in [&["add", "."][..], &["commit", "-qm", "fixture"]] {
            assert!(Command::new("git")
                .current_dir(root.path())
                .args(args)
                .output()
                .unwrap()
                .status
                .success());
        }
        let mut ctx = ToolContext::for_test(root.path().into(), state.path().into()).unwrap();
        let service = Arc::new(ChatAuthorizer::default());
        let profile = uuid::Uuid::new_v4().to_string();
        service
            .attach_storage(&profile, auth.path(), state.path())
            .unwrap();
        let mut request = RemoteRequest::verified(
            &profile,
            "fixture-workspace",
            VerifiedPrincipal {
                issuer: "https://fixture.example.invalid".into(),
                subject: "local-owner".into(),
                client_id: "fixture".into(),
                expires_at: SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs()
                    + 3600,
                family_id: None,
            },
            &json!({"openai/session":"fixture-conversation"}),
            "synthetic-fixture-secret",
        );
        request.service = service;
        if remote {
            ctx.remote_request = Some(request.clone());
        }
        Self {
            root,
            _state: state,
            _auth: auth,
            ctx,
            request,
        }
    }
    fn approve(&self, scopes: &[&str]) {
        let result = self
            .request
            .service
            .request(&self.request, &json!({"scopes":scopes}));
        assert_eq!(result["ok"], true, "{result}");
        self.request
            .service
            .decide(
                &self.request.profile,
                result["authorization"]["id"].as_str().unwrap(),
                true,
                &scopes.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            )
            .unwrap();
    }
}

#[test]
fn public_dispatch_create_list_remove_is_idempotent_and_preserves_original() {
    let f = Fixture::new(false);
    let result = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(result["ok"], true, "{result}");
    let id = result["worktree"]["id"].as_str().unwrap();
    let result = call_tool(&f.ctx, "worktree_list", &json!({}));
    assert_eq!(result["worktrees"].as_array().unwrap().len(), 1, "{result}");
    for _ in 0..2 {
        let result = call_tool(&f.ctx, "worktree_remove", &json!({"id":id}));
        assert_eq!(result["ok"], true, "{result}");
    }
    assert_eq!(
        fs::read_to_string(f.root.path().join("fixture.txt")).unwrap(),
        "original\n"
    );
}

#[test]
fn public_dispatch_denies_unapproved_and_read_only_remote_mutations() {
    // #70 grants only workspace.read for listing and files.write for mutations.
    // Keep this independent of catalog annotations, which are not authority.
    for (name, scope) in [
        ("worktree_list", "workspace.read"),
        ("worktree_create", "files.write"),
        ("worktree_remove", "files.write"),
    ] {
        assert_eq!(
            crate::tools::chat_domain::required(name, &json!({})),
            Some(&[scope][..])
        );
    }
    let f = Fixture::new(true);
    for name in ["worktree_create", "worktree_list", "worktree_remove"] {
        let args = if name == "worktree_remove" {
            json!({"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
        } else {
            json!({})
        };
        let result = call_tool(&f.ctx, name, &args);
        assert_eq!(result["ok"], false, "{result}");
    }
    f.approve(&["workspace.read"]);
    let list = call_tool(&f.ctx, "worktree_list", &json!({}));
    assert_eq!(list["ok"], true, "{list}");
    let create = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(create["ok"], false, "{create}");
    let remove = call_tool(
        &f.ctx,
        "worktree_remove",
        &json!({"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}),
    );
    assert_eq!(remove["ok"], false, "{remove}");
    assert!(!f.root.path().join(".git/worktrees").exists());
}

#[test]
fn locally_approved_remote_dispatch_scopes_and_revocation_are_enforced() {
    let f = Fixture::new(true);
    f.approve(&["workspace.read", "files.write"]);
    let result = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(result["ok"], true, "{result}");
    let id = result["worktree"]["id"].as_str().unwrap();
    let list = call_tool(&f.ctx, "worktree_list", &json!({}));
    assert_eq!(list["worktrees"].as_array().unwrap().len(), 1, "{list}");
    f.request.service.revoke(&f.request.profile, None);
    let removed = call_tool(&f.ctx, "worktree_remove", &json!({"id":id}));
    assert_eq!(removed["ok"], false, "{removed}");
    assert!(f.root.path().join(".git/worktrees").join(id).exists());
}

#[test]
fn public_dispatch_rejects_paths_git_options_and_wrong_id_types() {
    let f = Fixture::new(false);
    for args in [
        json!({"path":"/outside"}),
        json!({"root":"/outside"}),
        json!({"env":{"GIT_DIR":"/outside"}}),
        json!({"ref":"main"}),
    ] {
        let result = call_tool(&f.ctx, "worktree_create", &args);
        assert_eq!(result["ok"], false, "{result}");
    }
    for args in [
        json!({"id":"../outside"}),
        json!({"id":1}),
        json!({"id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","force":true}),
    ] {
        assert_eq!(call_tool(&f.ctx, "worktree_remove", &args)["ok"], false);
    }
    assert!(!f.root.path().join(".git/worktrees").exists());
}

#[test]
fn public_worktree_errors_never_run_ambient_git_diagnostics() {
    let f = Fixture::new(false);
    fs::write(
        f.root.path().join(".git/config"),
        "INTENTIONALLY INVALID CONFIG\n",
    )
    .unwrap();
    let invalid = call_tool(&f.ctx, "worktree_create", &json!({"path":"outside"}));
    assert_eq!(invalid["ok"], false);
    assert!(
        invalid.get("harness").is_none(),
        "worktree errors must not invoke ambient diagnostics"
    );
    let created = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(created["ok"], true, "{created}");
    let removed = call_tool(
        &f.ctx,
        "worktree_remove",
        &json!({"id":created["worktree"]["id"]}),
    );
    assert_eq!(removed["ok"], true, "{removed}");
}

#[test]
fn compatibility_annotations_do_not_mislabel_new_worktree_mutations() {
    let tools = crate::tools::registry::list_tools_for_profile("compat-readonly-all");
    for name in ["worktree_create", "worktree_remove"] {
        let tool = tools.iter().find(|tool| tool["name"] == name).unwrap();
        assert_eq!(tool["annotations"]["readOnlyHint"], false);
    }
    let remove = tools
        .iter()
        .find(|tool| tool["name"] == "worktree_remove")
        .unwrap();
    assert_eq!(remove["annotations"]["destructiveHint"], true);
}

#[test]
fn public_worktree_broker_refuses_another_active_source_writer() {
    let f = Fixture::new(false);
    let tracker = f.ctx.root_work.as_ref().unwrap();
    let mut writer = tracker.register().unwrap();
    writer.begin().unwrap();
    let blocked = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(
        blocked["error"]["code"], "NATIVE_ROOT_UNAVAILABLE",
        "{blocked}"
    );
    assert!(!f.root.path().join(".git/worktrees").exists());
    writer.complete();
    let created = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(created["ok"], true, "{created}");
}

#[test]
fn public_worktree_broker_refuses_overlapping_child_root_writer() {
    let f = Fixture::new(false);
    let child = f.root.path().join("nested");
    fs::create_dir(&child).unwrap();
    let state = tempfile::tempdir().unwrap();
    let child_ctx = ToolContext::for_test(child, state.path().into()).unwrap();
    let mut writer = child_ctx.root_work.as_ref().unwrap().register().unwrap();
    writer.begin().unwrap();
    let blocked = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(
        blocked["error"]["code"], "NATIVE_ROOT_UNAVAILABLE",
        "{blocked}"
    );
    assert!(!f.root.path().join(".git/worktrees").exists());
    writer.complete();
}

#[test]
fn unscoped_helper_cannot_invent_source_exclusivity_from_trusted_policy() {
    let f = Fixture::new(false);
    let error = super::call(&f.ctx, "worktree_create", &json!({})).unwrap_err();
    assert!(error
        .to_string()
        .contains("Source workspace writers are not proven quiescent"));
    assert!(!f.root.path().join(".git/worktrees").exists());
    assert!(!f.ctx.harness.store_root().join("worktrees-v1").exists());
}

// ---------------------------------------------------------------------------
// A1 C2b (C1-b, C2-b, C2-c): remote sessions share the device slot pool, and
// subagent_* / worker_id calls need agents.manage before any worker state.
// ---------------------------------------------------------------------------
impl Fixture {
    /// Two concurrent conversations: exclusive mode would refuse the second.
    /// Must run before any grant (toggling the policy resets grants).
    fn shared(remote: bool) -> Self {
        let f = Self::new(remote);
        f.request.service.set_exclusive(&f.request.profile, false);
        f
    }
    /// Another conversation of the same profile, approved for `scopes`.
    fn session(&self, conversation: &str, scopes: &[&str]) -> ToolContext {
        let mut request = RemoteRequest::verified(
            &self.request.profile,
            "fixture-workspace",
            VerifiedPrincipal {
                issuer: "https://fixture.example.invalid".into(),
                subject: "local-owner".into(),
                client_id: "fixture".into(),
                expires_at: SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_secs()
                    + 3600,
                family_id: None,
            },
            &json!({"openai/session": conversation}),
            "synthetic-fixture-secret",
        );
        request.service = self.request.service.clone();
        let result = request.service.request(&request, &json!({"scopes":scopes}));
        assert_eq!(result["ok"], true, "{result}");
        request
            .service
            .decide(
                &request.profile,
                result["authorization"]["id"].as_str().unwrap(),
                true,
                &scopes.iter().map(|s| s.to_string()).collect::<Vec<_>>(),
            )
            .unwrap();
        let mut ctx = self.ctx.background_snapshot();
        ctx.remote_request = Some(request);
        ctx
    }
}

#[test]
fn remote_sessions_share_the_eight_device_slots_for_worktree_create() {
    // C1-b: worktree tools build their manager on the main root, so two chat
    // sessions draw from the same 8-slot pool as workers and local callers.
    let f = Fixture::shared(false);
    let a = f.session("conversation-a", &["files.write", "workspace.read"]);
    let b = f.session("conversation-b", &["files.write", "workspace.read"]);
    for n in 0..5 {
        let out = call_tool(&a, "worktree_create", &json!({}));
        assert_eq!(out["ok"], true, "a{n}: {out}");
    }
    for n in 0..3 {
        let out = call_tool(&b, "worktree_create", &json!({}));
        assert_eq!(out["ok"], true, "b{n}: {out}");
    }
    for ctx in [&a, &b, &f.ctx] {
        let out = call_tool(ctx, "worktree_create", &json!({}));
        assert_eq!(out["error"]["code"], "CAPACITY", "{out}");
    }
    let listed = call_tool(&a, "worktree_list", &json!({}));
    assert_eq!(listed["worktrees"].as_array().unwrap().len(), 8, "{listed}");
}

#[test]
fn remote_calls_without_agents_manage_are_rejected_before_any_worker_state() {
    // C2-b: the coarse scope check precedes worker resolution; the main-root
    // WorkerStore is never opened, locked or registered.
    use super::workers::WorkerStore;
    let f = Fixture::shared(false);
    let ctx = f.session(
        "conversation-a",
        &["files.read", "files.write", "task.manage"],
    );
    let calls = [
        ("subagent_spawn", json!({"request_id":"r1"})),
        ("subagent_status", json!({})),
        (
            "subagent_discard",
            json!({"worker_id":"0123456789abcdef0123456789abcdef"}),
        ),
        (
            "read_file",
            json!({"path":"fixture.txt","worker_id":"0123456789abcdef0123456789abcdef"}),
        ),
    ];
    for (name, args) in calls {
        let out = call_tool(&ctx, name, &args);
        assert_eq!(
            out["error"]["message"], "INSUFFICIENT_CHAT_SCOPE",
            "{name} {args}: {out}"
        );
    }
    // A malformed id is refused as an argument error, still before any state.
    let bad = call_tool(
        &ctx,
        "read_file",
        &json!({"path":"fixture.txt","worker_id":"NOT-HEX"}),
    );
    assert_eq!(bad["error"]["message"], "INVALID_ARGUMENT", "{bad}");
    assert!(!WorkerStore::registered_for_test(&f.ctx.host));
    assert!(!f.ctx.host.store_root.join("agents-v1").exists());
}

#[test]
fn remote_subagent_lifecycle_runs_through_the_chat_permit_once_agents_manage_is_granted() {
    // C2-c: end to end through the permit. The schemas are exposed, the call is
    // denied without agents.manage and allowed once the (pending) scope is held.
    let tools = crate::tools::list_tools();
    let spawn = tools
        .iter()
        .find(|t| t["name"] == "subagent_spawn")
        .expect("subagent_spawn is listed");
    assert_eq!(spawn["inputSchema"]["additionalProperties"], false);
    let read = tools.iter().find(|t| t["name"] == "read_file").unwrap();
    assert!(read["inputSchema"]["properties"]["worker_id"].is_object());

    let f = Fixture::shared(false);
    let ctx = f.session(
        "conversation-a",
        &["files.read", "files.write", "task.manage"],
    );
    let denied = call_tool(&ctx, "subagent_spawn", &json!({"request_id":"r1"}));
    assert_eq!(
        denied["error"]["message"], "INSUFFICIENT_CHAT_SCOPE",
        "{denied}"
    );

    f.request
        .service
        .grant_pending_scope_for_test(&f.request.profile, "agents.manage");
    let spawned = call_tool(
        &ctx,
        "subagent_spawn",
        &json!({"request_id":"r1","label":"w"}),
    );
    assert_eq!(spawned["ok"], true, "{spawned}");
    assert_eq!(spawned["worker"]["state"], "ready", "{spawned}");
    let id = spawned["worker"]["worker_id"].as_str().unwrap().to_owned();

    let record = super::workers::status(&ctx, Some(&id)).unwrap().remove(0);
    let tree = super::workers::worktree_path(&f.ctx.host, record.worktree_id.as_deref().unwrap());
    fs::write(tree.join("fixture.txt"), "worker\n").unwrap();
    let read = call_tool(
        &ctx,
        "read_file",
        &json!({"path":"fixture.txt","worker_id": id}),
    );
    assert_eq!(read["content"], "worker\n", "{read}");
    assert_eq!(
        fs::read_to_string(f.root.path().join("fixture.txt")).unwrap(),
        "original\n"
    );
    let status = call_tool(&ctx, "subagent_status", &json!({"worker_id": id}));
    assert_eq!(status["workers"][0]["worker_id"], id.as_str(), "{status}");
    // Another conversation cannot see or manage it.
    let other = f.session("conversation-b", &["files.read", "files.write"]);
    f.request
        .service
        .grant_pending_scope_for_test(&f.request.profile, "agents.manage");
    let foreign = call_tool(&other, "subagent_status", &json!({"worker_id": id}));
    assert_eq!(foreign["error"]["code"], "WORKER_NOT_OWNED", "{foreign}");
    let discarded = call_tool(&ctx, "subagent_discard", &json!({"worker_id": id}));
    // The worker tree is dirty, so discard reports DIRTY and keeps the worker.
    assert_eq!(discarded["error"]["code"], "DIRTY", "{discarded}");
    let cancelled = call_tool(&ctx, "subagent_cancel", &json!({"worker_id": id}));
    assert_eq!(cancelled["worker"]["state"], "cancelled", "{cancelled}");
}
