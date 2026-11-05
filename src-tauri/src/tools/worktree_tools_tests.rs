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

/// A1 C6-grant: widen this conversation's grant with agents.manage through the
/// normal path (local revoke -> remote request_chat_authorization -> local
/// approve); there is no test seam that injects the scope any more.
fn grant_agents_manage(ctx: &ToolContext) {
    let req = ctx.remote_request.as_ref().expect("remote session");
    let current = req.service.status(req);
    assert_eq!(current["authorization"]["status"], "active", "{current}");
    let old = current["authorization"]["id"].as_str().unwrap().to_owned();
    let mut scopes: Vec<String> = current["authorization"]["scopes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| s.as_str().unwrap().to_owned())
        .collect();
    scopes.push("agents.manage".into());
    req.service.revoke(&req.profile, Some(&old));
    let v = call_tool(
        ctx,
        "request_chat_authorization",
        &json!({ "scopes": scopes }),
    );
    assert_eq!(v["ok"], true, "{v}");
    assert_eq!(v["authorization"]["status"], "pending", "{v}");
    let id = v["authorization"]["id"].as_str().unwrap();
    assert_ne!(id, old);
    req.service.decide(&req.profile, id, true, &scopes).unwrap();
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
    // A1 C3 (C2b deviation 9): a malformed id is checked only after the scope
    // check, exactly like the cloud prepare path: without agents.manage it is
    // INSUFFICIENT_CHAT_SCOPE, never an argument error that skips the scope.
    for bad in [json!("NOT-HEX"), json!(7), json!(null)] {
        let out = call_tool(
            &ctx,
            "read_file",
            &json!({"path":"fixture.txt","worker_id":bad}),
        );
        assert_eq!(
            out["error"]["message"], "INSUFFICIENT_CHAT_SCOPE",
            "{bad}: {out}"
        );
    }
    assert!(!WorkerStore::registered_for_test(&f.ctx.host));
    assert!(!f.ctx.host.store_root.join("agents-v1").exists());
    // With the scope held, the same calls fail with the unified argument code
    // (error.code, as on the cloud path), still before any worker state.
    grant_agents_manage(&ctx);
    for (name, args) in [
        (
            "read_file",
            json!({"path":"fixture.txt","worker_id":"NOT-HEX"}),
        ),
        ("read_file", json!({"path":"fixture.txt","worker_id":7})),
        ("read_file", json!({"path":"fixture.txt","worker_id":null})),
        ("subagent_discard", json!({"worker_id":"NOT-HEX"})),
    ] {
        let out = call_tool(&ctx, name, &args);
        assert_eq!(
            out["error"]["code"], "INVALID_ARGUMENT",
            "{name} {args}: {out}"
        );
    }
    assert!(!WorkerStore::registered_for_test(&f.ctx.host));
    assert!(!f.ctx.host.store_root.join("agents-v1").exists());
}

#[test]
fn remote_subagent_lifecycle_runs_through_the_chat_permit_once_agents_manage_is_granted() {
    // C2-c / C6-grant: end to end through the permit. The schemas are exposed,
    // the call is denied without agents.manage and allowed once it is granted.
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

    grant_agents_manage(&ctx);
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
    grant_agents_manage(&other);
    let foreign = call_tool(&other, "subagent_status", &json!({"worker_id": id}));
    assert_eq!(foreign["error"]["code"], "WORKER_NOT_OWNED", "{foreign}");
    let discarded = call_tool(&ctx, "subagent_discard", &json!({"worker_id": id}));
    // The worker tree is dirty, so discard reports DIRTY and keeps the worker.
    assert_eq!(discarded["error"]["code"], "DIRTY", "{discarded}");
    let cancelled = call_tool(&ctx, "subagent_cancel", &json!({"worker_id": id}));
    assert_eq!(cancelled["worker"]["state"], "cancelled", "{cancelled}");
}

/// A1 C7 (nit4): end to end through the chat permit, a worker's exec result
/// carries the worker sandbox's group cleanup (a piped leader: legacy tty is
/// a pipe session), equal to its resource report; main-root exec has none.
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
#[test]
fn remote_worker_exec_reports_group_cleanup_end_to_end() {
    let f = Fixture::shared(false);
    let ctx = f.session(
        "conversation-a",
        &[
            "workspace.read",
            "files.read",
            "files.write",
            "exec.run",
            "task.manage",
        ],
    );
    grant_agents_manage(&ctx);
    let spawned = call_tool(
        &ctx,
        "subagent_spawn",
        &json!({"request_id":"c7-gc","label":"w"}),
    );
    assert_eq!(spawned["ok"], true, "{spawned}");
    let id = spawned["worker"]["worker_id"].as_str().unwrap().to_owned();
    let run = call_tool(
        &ctx,
        "exec_command",
        &json!({"cmd":"git status --short","worker_id": id}),
    );
    assert_eq!(run["ok"], true, "{run}");
    assert_eq!(run["sandbox_enforced"], true, "{run}");
    assert_eq!(run["sandbox_required"], true, "{run}");
    let expected = coding_tools_local_agent::LinuxSandbox::new(f.root.path())
        .unwrap()
        .with_worker_resources(&id)
        .resource_report()
        .unwrap()
        .group_cleanup;
    assert_eq!(run["group_cleanup"], expected, "{run}");
    assert!(run["resource_limit"].is_string(), "{run}");
    let main = call_tool(&ctx, "exec_command", &json!({"cmd":"git status --short"}));
    assert_eq!(main["sandbox_required"], true, "{main}");
    assert!(main.get("group_cleanup").is_none(), "{main}");
}

#[test]
fn worktree_list_shows_legacy_chat_root_trees_and_create_counts_them() {
    // A1 C3 (steering 2): pre-C1-b trees under `<store>/chat-v1/<key>` are listed
    // and occupy main-root slots; they are not moved and cannot be removed here.
    let f = Fixture::new(false);
    let key = "cd".repeat(32);
    let legacy_root = f.ctx.host.store_root.join("chat-v1").join(&key);
    fs::create_dir_all(&legacy_root).unwrap();
    let legacy = crate::harness::worktree::WorktreeManager::new(
        f.root.path(),
        &legacy_root,
        &f.ctx.host.workspace_id,
    )
    .unwrap();
    let mut old: Vec<String> = (0..2)
        .map(|_| legacy.create_detached().unwrap().id)
        .collect();
    old.sort();
    let listed = call_tool(&f.ctx, "worktree_list", &json!({}));
    let items = listed["worktrees"].as_array().unwrap();
    let ids: Vec<_> = items.iter().map(|i| i["id"].as_str().unwrap()).collect();
    assert_eq!(
        ids, old,
        "legacy trees missing from worktree_list: {listed}"
    );
    for item in items {
        assert_eq!(item["legacy"], true, "{item}");
        assert_eq!(
            item["display_path"],
            format!("legacy/{}", item["id"].as_str().unwrap())
        );
        let text = item.to_string();
        assert!(!text.contains(&key) && !text.contains("chat-v1"), "{text}");
    }
    for n in 0..6 {
        let out = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(out["ok"], true, "{n}: {out}");
        assert!(out["worktree"].get("legacy").is_none(), "{out}");
    }
    let out = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(out["error"]["code"], "CAPACITY", "{out}");
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": old[0]}));
    assert_eq!(out["error"]["code"], "LEGACY_WORKTREE", "{out}");
    for id in &old {
        assert!(legacy_root
            .join("worktrees-v1")
            .join(&f.ctx.host.workspace_id)
            .join(id)
            .join("fixture.txt")
            .is_file());
    }
    let listed = call_tool(&f.ctx, "worktree_list", &json!({}));
    assert_eq!(listed["worktrees"].as_array().unwrap().len(), 8, "{listed}");
}

#[test]
fn agents_manage_is_granted_only_through_request_and_explicit_local_approval() {
    // A1 C6-grant (SPEC v5.4 §3.1; O13 decided in C7pre: UI default only): the normal path end to end.
    let f = Fixture::shared(false);
    let ctx = f.session("conversation-a", &["files.read"]);
    let req = ctx.remote_request.as_ref().unwrap().clone();
    let service = req.service.clone();
    let old = service.status(&req)["authorization"]["id"]
        .as_str()
        .unwrap()
        .to_owned();
    service.revoke(&req.profile, Some(&old));
    // The default request never asks for the sensitive scope.
    let default = call_tool(&ctx, "request_chat_authorization", &json!({}));
    assert_eq!(default["ok"], true, "{default}");
    assert!(
        !default["authorization"]["scopes"]
            .as_array()
            .unwrap()
            .contains(&json!("agents.manage")),
        "{default}"
    );
    service.revoke(&req.profile, default["authorization"]["id"].as_str());
    // 1) Requested but the owner approves a subset without it: still denied.
    let asked = call_tool(
        &ctx,
        "request_chat_authorization",
        &json!({"scopes":["files.read","files.write","agents.manage"]}),
    );
    assert_eq!(asked["authorization"]["status"], "pending", "{asked}");
    let id = asked["authorization"]["id"].as_str().unwrap().to_owned();
    service
        .decide(
            &req.profile,
            &id,
            true,
            &["files.read".to_string(), "files.write".to_string()],
        )
        .unwrap();
    let denied = call_tool(&ctx, "subagent_spawn", &json!({"request_id":"r1"}));
    assert_eq!(
        denied["error"]["message"], "INSUFFICIENT_CHAT_SCOPE",
        "{denied}"
    );
    assert!(!f.ctx.host.store_root.join("agents-v1").exists());
    // 2) The active subset cannot be widened in place: re-request returns it.
    let again = call_tool(
        &ctx,
        "request_chat_authorization",
        &json!({"scopes":["files.read","files.write","agents.manage"]}),
    );
    assert_eq!(again["authorization"]["id"], id.as_str(), "{again}");
    assert_eq!(again["authorization"]["status"], "active", "{again}");
    assert!(!again["authorization"]["scopes"]
        .as_array()
        .unwrap()
        .contains(&json!("agents.manage")));
    // 3) Revoke, request again and approve including agents.manage: allowed.
    service.revoke(&req.profile, Some(&id));
    let asked = call_tool(
        &ctx,
        "request_chat_authorization",
        &json!({"scopes":["files.read","files.write","agents.manage"]}),
    );
    let id = asked["authorization"]["id"].as_str().unwrap().to_owned();
    let all: Vec<String> = ["files.read", "files.write", "agents.manage"]
        .iter()
        .map(|s| s.to_string())
        .collect();
    service.decide(&req.profile, &id, true, &all).unwrap();
    let spawned = call_tool(
        &ctx,
        "subagent_spawn",
        &json!({"request_id":"r1","label":"w"}),
    );
    assert_eq!(spawned["ok"], true, "{spawned}");
    // 4) A scope that was not requested can never be approved (no widening).
    let other = f.session("conversation-b", &["files.read"]);
    let oreq = other.remote_request.as_ref().unwrap();
    let oid = service.status(oreq)["authorization"]["id"]
        .as_str()
        .unwrap()
        .to_owned();
    service.revoke(&oreq.profile, Some(&oid));
    let asked = call_tool(
        &other,
        "request_chat_authorization",
        &json!({"scopes":["files.read"]}),
    );
    let pending = asked["authorization"]["id"].as_str().unwrap();
    assert!(service
        .decide(
            &oreq.profile,
            pending,
            true,
            &["files.read".to_string(), "agents.manage".to_string()],
        )
        .is_err());
}

/// A1 C12b D2 (Grok probe-tool-path.patch as tests): an interrupted fresh delete
/// through `worktree_remove` is finished by the next `worktree_remove` (no worker
/// owns the id = owner proof): metadata and marker gone, slot freed, 8 creates OK.
fn d2_interrupted_then_retried(step: usize, partial_target: bool) {
    use crate::harness::worktree::WorktreeManager;
    let f = Fixture::new(false);
    let out = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(out["ok"], true, "{out}");
    let id = out["worktree"]["id"].as_str().unwrap().to_owned();
    let target = workers::worktree_path(&f.ctx.host, &id);
    let metadata = f.root.path().join(".git/worktrees").join(&id);
    let marker = metadata.join("managed-removing");
    WorktreeManager::set_delete_fail_at_for_test(Some(step));
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": id}));
    WorktreeManager::set_delete_fail_at_for_test(None);
    assert_eq!(out["error"]["code"], "IO_FAILED", "step={step}: {out}");
    assert!(marker.is_file(), "step={step}: marker written");
    if partial_target {
        // e.g. Windows AV / handle lock mid-delete: a tracked file already gone.
        fs::remove_file(target.join("fixture.txt")).expect("partial target delete");
    }
    let manager = workers::manager(&f.ctx).unwrap();
    assert_eq!(manager.slots_in_use_for_test().0, 1, "step={step}");
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": id}));
    assert_eq!(out["ok"], true, "step={step}: {out}");
    assert_eq!(out["removed"], true, "step={step}: {out}");
    assert!(!marker.exists(), "step={step}: marker gone");
    assert!(!metadata.exists(), "step={step}: metadata gone");
    assert!(
        fs::symlink_metadata(&target).is_err(),
        "step={step}: target gone"
    );
    assert_eq!(
        manager.slots_in_use_for_test().0,
        0,
        "step={step}: slot freed"
    );
    // Idempotent: a further retry is a true absence.
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": id}));
    assert_eq!(out["ok"], true, "step={step}: {out}");
    for n in 0..8 {
        let out = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(out["ok"], true, "step={step} create {n}: {out}");
    }
    let out = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(out["error"]["code"], "CAPACITY", "step={step}: {out}");
    assert_eq!(
        fs::read_to_string(f.root.path().join("fixture.txt")).unwrap(),
        "original\n"
    );
}

#[test]
fn c12b_d2_worktree_remove_finishes_step0_leftover_with_partial_target() {
    d2_interrupted_then_retried(0, true);
}

#[test]
fn c12b_d2_worktree_remove_finishes_step0_leftover_intact_target() {
    d2_interrupted_then_retried(0, false);
}

#[test]
fn c12b_d2_worktree_remove_finishes_step1_leftover_and_frees_slot() {
    d2_interrupted_then_retried(1, false);
}

/// A1 C14 (SCOPE A′ 6): with no worker store, `worktree_remove` takes only the
/// native lock and never creates the store.
#[test]
fn c14_worktree_remove_without_a_worker_store_does_not_create_it() {
    let f = Fixture::new(false);
    let out = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(out["ok"], true, "{out}");
    let id = out["worktree"]["id"].as_str().unwrap().to_owned();
    assert!(!workers::store_exists_for_test(&f.ctx));
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": id}));
    assert_eq!(out["ok"], true, "{out}");
    assert!(!workers::store_exists_for_test(&f.ctx), "store not created");
    assert!(fs::symlink_metadata(workers::worktree_path(&f.ctx.host, &id)).is_err());
}

/// A1 C14 (SCOPE A′ 6): the owned check and the delete share one store lock;
/// a worker's tree is still refused (WORKER_OWNED) and left intact, and spawn
/// racing `worktree_remove` does not deadlock (store → native everywhere; the
/// cfg(test) assertion in `WorkerStore::lock` fails any reverse order).
#[test]
fn c14_worktree_remove_refuses_worker_owned_and_races_spawn_without_deadlock() {
    let f = Fixture::shared(false);
    let ctx = f.session(
        "conversation-a",
        &["files.read", "files.write", "task.manage"],
    );
    grant_agents_manage(&ctx);
    let spawned = call_tool(&ctx, "subagent_spawn", &json!({"request_id":"r0"}));
    assert_eq!(spawned["ok"], true, "{spawned}");
    let wid = spawned["worker"]["worker_id"].as_str().unwrap().to_owned();
    let record = workers::status(&ctx, Some(&wid)).unwrap().remove(0);
    let tree_id = record.worktree_id.clone().unwrap();
    let out = call_tool(&f.ctx, "worktree_remove", &json!({"id": tree_id}));
    assert_eq!(out["error"]["code"], "WORKER_OWNED", "{out}");
    assert!(workers::worktree_path(&f.ctx.host, &tree_id).is_dir());

    let (tx, rx) = std::sync::mpsc::channel();
    let (spawner, remover, tree_id) = (&ctx, &f.ctx, tree_id.as_str());
    let results = std::sync::Mutex::new(Vec::new());
    let results = &results;
    std::thread::scope(|scope| {
        let tx1 = tx.clone();
        scope.spawn(move || {
            for n in 0..4 {
                let s = call_tool(
                    spawner,
                    "subagent_spawn",
                    &json!({"request_id": format!("race{n}")}),
                );
                if s["ok"] == true {
                    let w = s["worker"]["worker_id"].as_str().unwrap().to_owned();
                    let _ = call_tool(spawner, "subagent_discard", &json!({"worker_id": w}));
                }
            }
            tx1.send("spawn").unwrap();
        });
        let tx2 = tx.clone();
        scope.spawn(move || {
            let mut seen = Vec::new();
            for _ in 0..4 {
                let c = call_tool(remover, "worktree_create", &json!({}));
                if let Some(id) = c["worktree"]["id"].as_str() {
                    seen.push(call_tool(remover, "worktree_remove", &json!({"id": id})));
                }
                seen.push(call_tool(
                    remover,
                    "worktree_remove",
                    &json!({"id": tree_id}),
                ));
            }
            *results.lock().unwrap() = seen;
            tx2.send("remove").unwrap();
        });
        drop(tx); // a panicked thread then disconnects instead of hanging
        let timeout = std::time::Duration::from_secs(120);
        let mut done = Vec::new();
        for _ in 0..2 {
            match rx.recv_timeout(timeout) {
                Ok(who) => done.push(who),
                // a worker thread panicked; the scope join re-raises it
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => return,
                Err(e) => {
                    eprintln!("deadlock: spawn vs worktree_remove did not finish: {e}");
                    std::process::abort();
                }
            }
        }
        done.sort();
        assert_eq!(done, vec!["remove", "spawn"]);
    });
    // Under the race a call may be refused as busy (root guard held by the
    // spawner); it must never remove the worker's tree or answer otherwise.
    for r in results.lock().unwrap().iter() {
        let code = r["error"]["code"].as_str();
        assert!(
            r["ok"] == true
                || matches!(
                    code,
                    Some("WORKER_OWNED" | "NATIVE_ROOT_UNAVAILABLE" | "BUSY")
                ),
            "{r}"
        );
        eprintln!("c14 race result: {r}");
    }
    assert!(workers::worktree_path(&f.ctx.host, tree_id).is_dir());
}
