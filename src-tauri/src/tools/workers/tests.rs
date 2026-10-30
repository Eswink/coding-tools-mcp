//! A1 C1 + C2 (SPEC-A1 v4 §7.4): worker identity, ownership, durable store,
//! state machine, concurrency cap, slot reservation and stored cwd. All worker
//! state hangs off the main root (v4 §1.5), never a chat session root.
use super::*;
use crate::auth::{chat::RemoteRequest, principal::VerifiedPrincipal};
use crate::tools::{call_tool, root_work};
use serde_json::{json, Value};
use std::{
    fs,
    path::Path,
    process::Command,
    time::{SystemTime, UNIX_EPOCH},
};

struct Fixture {
    root: tempfile::TempDir,
    _state: tempfile::TempDir,
    ctx: ToolContext,
}

fn git(dir: &Path, args: &[&str]) -> String {
    let output = Command::new("git")
        .current_dir(dir)
        .args(args)
        .output()
        .unwrap();
    assert!(output.status.success(), "git {args:?}: {output:?}");
    String::from_utf8(output.stdout).unwrap().trim().to_owned()
}

impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let state = tempfile::tempdir().unwrap();
        git(root.path(), &["init", "-q"]);
        git(root.path(), &["config", "user.name", "Fixture"]);
        git(
            root.path(),
            &["config", "user.email", "fixture@example.invalid"],
        );
        fs::write(root.path().join("fixture.txt"), "original\n").unwrap();
        git(root.path(), &["add", "."]);
        git(root.path(), &["commit", "-qm", "fixture"]);
        let ctx = ToolContext::for_test(root.path().into(), state.path().into()).unwrap();
        Self {
            root,
            _state: state,
            ctx,
        }
    }
    fn head(&self) -> String {
        git(self.root.path(), &["rev-parse", "HEAD"])
    }
}

/// Mirrors the production chain: every native operation runs inside a root scope.
fn scoped<T>(ctx: &ToolContext, run: impl FnOnce(&ToolContext) -> T) -> T {
    let mut out = None;
    root_work::dispatch(ctx, |scoped| {
        out = Some(run(scoped));
        Value::Null
    })
    .unwrap();
    out.unwrap()
}

/// Phase 1 only: the slot is reserved and a `creating` record persisted.
fn reserve_ok(ctx: &ToolContext, request_id: &str, label: &str) -> WorkerRecord {
    scoped(ctx, |c| spawn(c, request_id, label))
        .unwrap_or_else(|e| panic!("spawn {request_id}: {e:?}"))
        .0
}
fn spawn_ok(ctx: &ToolContext, request_id: &str, label: &str) -> WorkerRecord {
    let reserved = reserve_ok(ctx, request_id, label);
    assert_eq!(reserved.state, WorkerState::Creating);
    scoped(ctx, |c| complete_spawn(c, reserved.worker_id.as_str()))
        .unwrap_or_else(|e| panic!("complete {request_id}: {e:?}"))
}
fn worktree_ids(ctx: &ToolContext) -> Vec<String> {
    let listed = call_tool(ctx, "worktree_list", &json!({}));
    assert_eq!(listed["ok"], true, "{listed}");
    listed["worktrees"]
        .as_array()
        .unwrap()
        .iter()
        .map(|w| w["id"].as_str().unwrap().to_owned())
        .collect()
}

fn remote(ctx: &ToolContext, session: &str) -> ToolContext {
    let mut copy = ctx.background_snapshot();
    copy.remote_request = Some(RemoteRequest::verified(
        "fixture-profile",
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
        &json!({ "openai/session": session }),
        "synthetic-fixture-secret",
    ));
    copy
}

#[test]
fn worker_ids_are_independent_lowercase_opaque_identifiers() {
    let a = WorkerId::generate();
    let b = WorkerId::generate();
    assert_ne!(a, b);
    for id in [&a, &b] {
        assert_eq!(id.as_str().len(), 32);
        assert!(id
            .as_str()
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c)));
        assert_eq!(WorkerId::parse(id.as_str()).unwrap(), *id);
    }
    for bad in [
        "",
        "ABCDEFABCDEFABCDEFABCDEFABCDEFAB",
        "0123456789abcdef0123456789abcde",
        "0123456789abcdef0123456789abcdef0",
        "0123456789abcdef0123456789abcdeg",
        "../0123456789abcdef0123456789abc",
    ] {
        assert_eq!(WorkerId::parse(bad).unwrap_err().code(), "INVALID_ARGUMENT");
    }
}

#[test]
fn spawn_creates_a_ready_worker_on_its_own_detached_worktree() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req-1", "refactor parser");
    assert_eq!(worker.state, WorkerState::Ready);
    assert_eq!(worker.owner, WorkerOwner::local());
    assert_eq!(worker.label, "refactor parser");
    assert_eq!(worker.base_head.as_deref(), Some(f.head().as_str()));
    assert_eq!(worker.workspace_id, f.ctx.harness.workspace_id());
    let tree = worker.worktree_id.clone().unwrap();
    assert_ne!(
        tree,
        worker.worker_id.as_str(),
        "worker_id must not be the worktree id"
    );
    let records = status(&f.ctx, None).unwrap();
    assert_eq!(records, vec![worker.clone()]);
    assert_eq!(
        status(&f.ctx, Some(worker.worker_id.as_str())).unwrap(),
        vec![worker]
    );
}

#[test]
fn spawn_is_idempotent_per_request_id_and_rejects_conflicting_reuse() {
    let f = Fixture::new();
    let (first, created) = scoped(&f.ctx, |c| spawn(c, "req-same", "a")).unwrap();
    assert!(created);
    let (again, created) = scoped(&f.ctx, |c| spawn(c, "req-same", "a")).unwrap();
    assert!(!created);
    assert_eq!(first, again);
    let conflict = scoped(&f.ctx, |c| spawn(c, "req-same", "b")).unwrap_err();
    assert_eq!(conflict.code(), "REQUEST_ID_CONFLICT");
    assert_eq!(status(&f.ctx, None).unwrap().len(), 1);
    for bad in ["", &"x".repeat(129), "bad\nid"] {
        let err = scoped(&f.ctx, |c| spawn(c, bad, "a")).unwrap_err();
        assert_eq!(err.code(), "INVALID_ARGUMENT", "{bad:?}");
    }
    let err = scoped(&f.ctx, |c| spawn(c, "req-label", &"l".repeat(81))).unwrap_err();
    assert_eq!(err.code(), "INVALID_ARGUMENT");
    let err = scoped(&f.ctx, |c| spawn(c, "req-label", "tab\tlabel")).unwrap_err();
    assert_eq!(err.code(), "INVALID_ARGUMENT");
}
#[test]
fn concurrency_defaults_to_four_active_workers_and_frees_on_discard() {
    let f = Fixture::new();
    assert_eq!(DEFAULT_WORKER_LIMIT, 4);
    let workers: Vec<_> = (0..4)
        .map(|n| spawn_ok(&f.ctx, &format!("req-{n}"), "w"))
        .collect();
    let err = scoped(&f.ctx, |c| spawn(c, "req-4", "w")).unwrap_err();
    assert_eq!(err.code(), "WORKER_LIMIT");
    // Cancelled workers still hold a worktree and therefore still count.
    cancel(&f.ctx, workers[0].worker_id.as_str()).unwrap();
    let err = scoped(&f.ctx, |c| spawn(c, "req-4", "w")).unwrap_err();
    assert_eq!(err.code(), "WORKER_LIMIT");
    let gone = scoped(&f.ctx, |c| discard(c, workers[0].worker_id.as_str())).unwrap();
    assert_eq!(gone.state, WorkerState::Discarded);
    spawn_ok(&f.ctx, "req-4", "w");
}

#[test]
fn creating_workers_count_toward_the_limit_before_their_worktree_exists() {
    let f = Fixture::new();
    for n in 0..4 {
        reserve_ok(&f.ctx, &format!("r{n}"), "w");
    }
    assert!(worktree_ids(&f.ctx).is_empty());
    let err = scoped(&f.ctx, |c| spawn(c, "r4", "w")).unwrap_err();
    assert_eq!(err.code(), "WORKER_LIMIT");
}

#[test]
fn worker_limit_is_configurable_only_within_one_to_eight() {
    let f = Fixture::new();
    for bad in [0, 9, usize::MAX] {
        assert_eq!(
            configure_limit(&f.ctx, bad).unwrap_err().code(),
            "INVALID_ARGUMENT"
        );
    }
    configure_limit(&f.ctx, 1).unwrap();
    spawn_ok(&f.ctx, "one", "w");
    let err = scoped(&f.ctx, |c| spawn(c, "two", "w")).unwrap_err();
    assert_eq!(err.code(), "WORKER_LIMIT");
    configure_limit(&f.ctx, 8).unwrap();
    spawn_ok(&f.ctx, "two", "w");
    // A remote caller can never change the native cap.
    let chat = remote(&f.ctx, "conversation-a");
    assert_eq!(
        configure_limit(&chat, 8).unwrap_err().code(),
        "WORKER_NOT_OWNED"
    );
}

#[test]
fn workers_share_the_eight_managed_worktree_slots_and_pass_capacity_through() {
    let f = Fixture::new();
    for _ in 0..6 {
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(created["ok"], true, "{created}");
    }
    spawn_ok(&f.ctx, "a", "w");
    spawn_ok(&f.ctx, "b", "w");
    let err = scoped(&f.ctx, |c| spawn(c, "c", "w")).unwrap_err();
    assert_eq!(err.code(), "CAPACITY");
    // The failed attempt is durable but does not hold a slot.
    let records = status(&f.ctx, None).unwrap();
    assert_eq!(records.len(), 3);
    let failed: Vec<_> = records
        .iter()
        .filter(|r| r.state == WorkerState::Failed)
        .collect();
    assert_eq!(failed.len(), 1);
    assert!(failed[0].worktree_id.is_none());
}

#[test]
fn reserved_slots_are_held_before_the_worktree_is_built_so_create_cannot_race() {
    let f = Fixture::new();
    // Two spawns return with a reserved slot but no worktree yet (async build pending).
    let a = reserve_ok(&f.ctx, "a", "w");
    let b = reserve_ok(&f.ctx, "b", "w");
    assert!(a.worktree_id.is_some() && b.worktree_id.is_some());
    for n in 0..6 {
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(created["ok"], true, "create {n}: {created}");
    }
    let seventh = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(seventh["ok"], false, "{seventh}");
    assert_eq!(seventh["error"]["code"], "CAPACITY", "{seventh}");
    // The delayed builds still succeed into the slots they reserved.
    let a = scoped(&f.ctx, |c| complete_spawn(c, a.worker_id.as_str())).unwrap();
    let b = scoped(&f.ctx, |c| complete_spawn(c, b.worker_id.as_str())).unwrap();
    assert_eq!((a.state, b.state), (WorkerState::Ready, WorkerState::Ready));
    assert_eq!(a.base_head.as_deref(), Some(f.head().as_str()));
    // Completing twice is idempotent.
    let again = scoped(&f.ctx, |c| complete_spawn(c, a.worker_id.as_str())).unwrap();
    assert_eq!(again, a);
}

#[test]
fn state_machine_rejects_invalid_transitions() {
    let f = Fixture::new();
    let creating = reserve_ok(&f.ctx, "c", "w");
    let id = creating.worker_id.as_str();
    assert_eq!(cancel(&f.ctx, id).unwrap_err().code(), "WORKER_STATE");
    assert_eq!(
        scoped(&f.ctx, |c| discard(c, id)).unwrap_err().code(),
        "WORKER_STATE"
    );
    assert_eq!(set_cwd(&f.ctx, id, ".").unwrap_err().code(), "WORKER_STATE");
    let ready = scoped(&f.ctx, |c| complete_spawn(c, id)).unwrap();
    assert_eq!(ready.state, WorkerState::Ready);
    let (cancelled, killed) = cancel(&f.ctx, id).unwrap();
    assert_eq!(cancelled.state, WorkerState::Cancelled);
    assert_eq!(killed, 0);
    assert_eq!(
        cancel(&f.ctx, id).unwrap(),
        (cancelled, 0),
        "cancel is idempotent"
    );
    assert_eq!(set_cwd(&f.ctx, id, ".").unwrap_err().code(), "WORKER_STATE");
    let gone = scoped(&f.ctx, |c| discard(c, id)).unwrap();
    assert_eq!(gone.state, WorkerState::Discarded);
    assert_eq!(
        scoped(&f.ctx, |c| discard(c, id)).unwrap(),
        gone,
        "discard is idempotent"
    );
    assert_eq!(cancel(&f.ctx, id).unwrap_err().code(), "WORKER_STATE");
    assert_eq!(
        scoped(&f.ctx, |c| complete_spawn(c, id))
            .unwrap_err()
            .code(),
        "WORKER_STATE"
    );
}

#[test]
fn discard_passes_dirty_through_and_keeps_the_worker() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker.worktree_id.clone().unwrap();
    let root = f
        .ctx
        .harness
        .store_root()
        .join("worktrees-v1")
        .join(f.ctx.harness.workspace_id())
        .join(&tree);
    fs::write(root.join("fixture.txt"), "edited\n").unwrap();
    let err = scoped(&f.ctx, |c| discard(c, worker.worker_id.as_str())).unwrap_err();
    assert_eq!(err.code(), "DIRTY");
    assert_eq!(
        status(&f.ctx, Some(worker.worker_id.as_str())).unwrap()[0].state,
        WorkerState::Ready
    );
    assert!(root.exists());
}

#[test]
fn worker_cwd_is_stored_relative_and_confined_to_the_worktree() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    assert_eq!(worker.cwd, ".");
    let id = worker.worker_id.as_str();
    let tree = worker.worktree_id.clone().unwrap();
    let root = f
        .ctx
        .harness
        .store_root()
        .join("worktrees-v1")
        .join(f.ctx.harness.workspace_id())
        .join(&tree);
    fs::create_dir_all(root.join("src/inner")).unwrap();
    let moved = set_cwd(&f.ctx, id, "./src//inner").unwrap();
    assert_eq!(moved.cwd, "src/inner");
    assert_eq!(status(&f.ctx, Some(id)).unwrap()[0].cwd, "src/inner");
    for bad in [
        "",
        "/etc",
        "../x",
        "src/../../x",
        "src\\inner",
        "missing",
        "fixture.txt",
        "a\nb",
    ] {
        assert_eq!(
            set_cwd(&f.ctx, id, bad).unwrap_err().code(),
            "INVALID_ARGUMENT",
            "{bad:?}"
        );
    }
    #[cfg(unix)]
    {
        std::os::unix::fs::symlink(f.root.path(), root.join("escape")).unwrap();
        assert_eq!(
            set_cwd(&f.ctx, id, "escape").unwrap_err().code(),
            "INVALID_ARGUMENT"
        );
    }
    assert_eq!(status(&f.ctx, Some(id)).unwrap()[0].cwd, "src/inner");
    let chat = remote(&f.ctx, "conversation-a");
    assert_eq!(
        set_cwd(&chat, id, ".").unwrap_err().code(),
        "WORKER_NOT_OWNED"
    );
}

#[test]
fn worker_worktrees_are_hidden_from_and_protected_against_worktree_tools() {
    let f = Fixture::new();
    let plain = call_tool(&f.ctx, "worktree_create", &json!({}));
    let plain_id = plain["worktree"]["id"].as_str().unwrap().to_owned();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker.worktree_id.clone().unwrap();
    assert_eq!(worktree_ids(&f.ctx), vec![plain_id]);
    let removed = call_tool(&f.ctx, "worktree_remove", &json!({ "id": tree }));
    assert_eq!(removed["ok"], false, "{removed}");
    assert_eq!(removed["error"]["code"], "WORKER_OWNED", "{removed}");
    assert_eq!(
        status(&f.ctx, Some(worker.worker_id.as_str())).unwrap()[0].state,
        WorkerState::Ready
    );
    // A reserved-but-unbuilt worktree id is protected too.
    let pending = reserve_ok(&f.ctx, "pending", "w");
    let removed = call_tool(
        &f.ctx,
        "worktree_remove",
        &json!({ "id": pending.worktree_id.clone().unwrap() }),
    );
    assert_eq!(removed["error"]["code"], "WORKER_OWNED", "{removed}");
    // Passing the worker id to worktree_remove is not an alias either.
    let removed = call_tool(
        &f.ctx,
        "worktree_remove",
        &json!({ "id": worker.worker_id.as_str() }),
    );
    assert_ne!(removed["error"]["code"], "WORKER_OWNED", "{removed}");
    assert_eq!(
        status(&f.ctx, Some(worker.worker_id.as_str())).unwrap()[0].state,
        WorkerState::Ready
    );
}

#[test]
fn ownership_is_bound_to_origin_and_conversation_without_disclosing_existence() {
    let f = Fixture::new();
    let local = spawn_ok(&f.ctx, "req", "local");
    let chat_a = remote(&f.ctx, "conversation-a");
    let chat_b = remote(&f.ctx, "conversation-b");
    let owner_a = WorkerOwner::from_context(&chat_a).unwrap();
    let owner_b = WorkerOwner::from_context(&chat_b).unwrap();
    assert_ne!(owner_a, owner_b);
    assert_ne!(owner_a, WorkerOwner::local());
    assert_eq!(
        owner_a,
        WorkerOwner::from_context(&remote(&f.ctx, "conversation-a")).unwrap()
    );
    let remote_worker = spawn_ok(&chat_a, "req", "remote");
    assert_ne!(remote_worker.worker_id, local.worker_id);

    assert_eq!(status(&chat_a, None).unwrap(), vec![remote_worker.clone()]);
    assert!(status(&chat_b, None).unwrap().is_empty());
    assert_eq!(status(&f.ctx, None).unwrap(), vec![local.clone()]);
    let unknown = WorkerId::generate();
    for (ctx, id) in [
        (&chat_b, remote_worker.worker_id.as_str()),
        (&f.ctx, remote_worker.worker_id.as_str()),
        (&chat_a, local.worker_id.as_str()),
        (&chat_a, unknown.as_str()),
    ] {
        assert_eq!(
            status(ctx, Some(id)).unwrap_err().code(),
            "WORKER_NOT_OWNED"
        );
        assert_eq!(cancel(ctx, id).unwrap_err().code(), "WORKER_NOT_OWNED");
        assert_eq!(
            scoped(ctx, |c| discard(c, id)).unwrap_err().code(),
            "WORKER_NOT_OWNED"
        );
        assert_eq!(
            scoped(ctx, |c| complete_spawn(c, id)).unwrap_err().code(),
            "WORKER_NOT_OWNED"
        );
    }
    // Unresolved remote identity never falls back to the local owner.
    let mut unresolved = f.ctx.background_snapshot();
    unresolved.remote_request = Some(RemoteRequest::unresolved("fixture-profile"));
    assert_eq!(
        WorkerOwner::from_context(&unresolved).unwrap_err().code(),
        "WORKER_NOT_OWNED"
    );
}

#[test]
fn records_persist_encrypted_across_reopen_and_interrupted_spawns_recover() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "persist-label");
    let mgr = manager(&f.ctx).unwrap();
    let store = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    // Crash before the worktree was built: recovers to failed and frees the id.
    let lost = store
        .inject_interrupted_for_test(&WorkerOwner::local(), Some(WorkerId::generate().as_str()))
        .unwrap();
    // Crash after `git worktree add` but before the record moved to ready.
    let built = call_tool(&f.ctx, "worktree_create", &json!({}));
    let built_id = built["worktree"]["id"].as_str().unwrap().to_owned();
    let survived = store
        .inject_interrupted_for_test(&WorkerOwner::local(), Some(&built_id))
        .unwrap();
    drop(store);
    // The store is a process singleton (v4 N3); evicting it simulates a restart.
    WorkerStore::evict_for_test(&f.ctx.host);
    let namespace = f
        .ctx
        .harness
        .store_root()
        .join("agents-v1")
        .join(f.ctx.harness.workspace_id());
    let raw = fs::read(namespace.join("auth.json")).unwrap();
    let raw = String::from_utf8_lossy(&raw);
    assert!(!raw.contains("persist-label") && !raw.contains(worker.worker_id.as_str()));

    let records = status(&f.ctx, None).unwrap();
    assert_eq!(records.len(), 3, "{records:?}");
    assert_eq!(
        records
            .iter()
            .find(|r| r.worker_id == worker.worker_id)
            .unwrap(),
        &worker
    );
    let lost = records.iter().find(|r| r.worker_id == lost).unwrap();
    assert_eq!(lost.state, WorkerState::Failed);
    assert!(lost.worktree_id.is_none());
    let survived = records.iter().find(|r| r.worker_id == survived).unwrap();
    assert_eq!(survived.state, WorkerState::Ready);
    assert_eq!(survived.base_head.as_deref(), Some(f.head().as_str()));
    assert!(!worktree_ids(&f.ctx).contains(&built_id));
}

#[test]
fn public_schemas_expose_worker_id_on_exactly_the_worker_tools_and_route_it() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    // A1 C2b (v4 §2.1): the 22 worker tools carry an optional 32-hex worker_id;
    // the 7 subagent_* tools are registered; nothing else mentions worker_id.
    let tools = crate::tools::list_tools();
    let mut subagents = Vec::new();
    for tool in &tools {
        let name = tool["name"].as_str().unwrap();
        let props = &tool["inputSchema"]["properties"];
        if name.starts_with("subagent_") {
            subagents.push(name.to_owned());
            continue;
        }
        assert!(!name.starts_with("worker_"), "{name}");
        if WORKER_TOOLS.contains(&name) {
            assert_eq!(props["worker_id"]["type"], "string", "{name}");
            assert_eq!(props["worker_id"]["pattern"], "^[0-9a-f]{32}$", "{name}");
            let required = tool["inputSchema"]["required"].to_string();
            assert!(!required.contains("worker_id"), "{name}");
        } else {
            assert!(!tool.to_string().contains("worker_id"), "{name}");
        }
    }
    subagents.sort();
    let mut expected: Vec<_> = crate::tools::registry::SUBAGENT_TOOLS
        .iter()
        .map(|s| s.to_string())
        .collect();
    expected.sort();
    assert_eq!(subagents, expected);
    assert_eq!(expected.len(), 7);
    // Every listed worker tool carries the parameter (aliases such as `grep`
    // are dispatch-only and not listed).
    let listed = tools
        .iter()
        .filter(|t| t["inputSchema"]["properties"]["worker_id"].is_object())
        .count();
    assert!(listed >= WORKER_TOOLS.len() - 1, "{listed}");
    // Dispatch re-roots a supported call carrying worker_id into the worker worktree.
    let tree = f
        .ctx
        .harness
        .store_root()
        .join("worktrees-v1")
        .join(f.ctx.harness.workspace_id())
        .join(worker.worktree_id.as_deref().unwrap());
    fs::write(tree.join("fixture.txt"), "worker copy\n").unwrap();
    let result = call_tool(
        &f.ctx,
        "read_file",
        &json!({"path":"fixture.txt","worker_id":worker.worker_id.as_str()}),
    );
    assert_eq!(result["content"], "worker copy\n", "{result}");
    let main = call_tool(&f.ctx, "read_file", &json!({"path":"fixture.txt"}));
    assert_eq!(main["content"], "original\n", "{main}");
}

/// A real `ChatDomains::scoped()` session context (per-session harness root).
fn session(ctx: &ToolContext, name: &str) -> ToolContext {
    let outer = remote(ctx, name);
    let req = outer.remote_request.clone().unwrap();
    let domain = ctx.chat_domains.scoped(&outer, &req).unwrap();
    assert!(domain.chat_scoped);
    assert_ne!(domain.harness.store_root(), ctx.harness.store_root());
    domain
}

#[test]
fn slots_and_store_hang_off_the_main_root_across_real_chat_sessions() {
    let f = Fixture::new();
    let a = session(&f.ctx, "conversation-a");
    let b = session(&f.ctx, "conversation-b");
    for n in 0..4 {
        spawn_ok(&a, &format!("a{n}"), "w");
    }
    for n in 0..4 {
        reserve_ok(&b, &format!("b{n}"), "w");
    }
    // Per-session WORKER_LIMIT is still 4 ...
    let err = scoped(&a, |c| spawn(c, "a4", "w")).unwrap_err();
    assert_eq!(err.code(), "WORKER_LIMIT");
    // ... and the two sessions together already fill the device's 8 slots.
    let err = scoped(&f.ctx, |c| spawn(c, "local", "w")).unwrap_err();
    assert_eq!(err.code(), "CAPACITY");
    let created = call_tool(&f.ctx, "worktree_create", &json!({}));
    assert_eq!(created["error"]["code"], "CAPACITY", "{created}");
    let main = f
        .ctx
        .harness
        .store_root()
        .join("agents-v1")
        .join(f.ctx.harness.workspace_id());
    assert!(main.join("auth.json").is_file());
    for domain in [&a, &b] {
        assert!(!domain.harness.store_root().join("agents-v1").exists());
        assert!(!domain.harness.store_root().join("worktrees-v1").exists());
        assert_eq!(status(domain, None).unwrap().len(), 4);
    }
    // Ownership is still per session: neither sees the other's workers.
    let a_ids: Vec<_> = status(&a, None)
        .unwrap()
        .into_iter()
        .map(|r| r.worker_id)
        .collect();
    assert!(status(&b, None)
        .unwrap()
        .iter()
        .all(|r| !a_ids.contains(&r.worker_id)));
}

#[test]
fn the_store_is_one_process_singleton_per_main_root() {
    let f = Fixture::new();
    spawn_ok(&f.ctx, "req", "w");
    let mgr = manager(&f.ctx).unwrap();
    let first = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    let generation = first.generation();
    drop(first);
    status(&f.ctx, None).unwrap();
    let chat = session(&f.ctx, "conversation-a");
    status(&chat, None).unwrap();
    let again = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    assert_eq!(
        again.generation(),
        generation,
        "no reload / re-decrypt per call"
    );
    drop(again);
    WorkerStore::evict_for_test(&f.ctx.host);
    let reloaded = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    assert_ne!(reloaded.generation(), generation);
}

#[test]
fn pending_cleanup_is_only_retried_by_exclusive_callers() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "keep", "w");
    let built = call_tool(&f.ctx, "worktree_create", &json!({}));
    let tree = built["worktree"]["id"].as_str().unwrap().to_owned();
    let mgr = manager(&f.ctx).unwrap();
    let store = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    let stuck = store
        .inject_for_test(
            &WorkerOwner::local(),
            Some(&tree),
            WorkerState::PendingCleanup,
            now(),
        )
        .unwrap();
    drop(store);
    WorkerStore::evict_for_test(&f.ctx.host);
    let path = f
        .ctx
        .host
        .store_root
        .join("worktrees-v1")
        .join(&f.ctx.host.workspace_id)
        .join(&tree);
    // Non-exclusive callers never remove worktrees during recovery.
    status(&f.ctx, None).unwrap();
    cancel(&f.ctx, worker.worker_id.as_str()).unwrap();
    set_cwd(&f.ctx, worker.worker_id.as_str(), ".").unwrap_err();
    configure_limit(&f.ctx, 4).unwrap();
    assert!(path.exists());
    assert_eq!(
        status(&f.ctx, Some(stuck.as_str())).unwrap()[0].state,
        WorkerState::PendingCleanup
    );
    // An exclusive caller retries the clean removal.
    spawn_ok(&f.ctx, "next", "w");
    assert!(!path.exists());
    assert_eq!(
        status(&f.ctx, Some(stuck.as_str())).unwrap()[0].state,
        WorkerState::Discarded
    );
}

#[test]
fn an_early_create_reserved_failure_releases_the_slot_under_the_native_lock() {
    let f = Fixture::new();
    let mgr = manager(&f.ctx).unwrap();
    let slot = mgr.reserve_slot().unwrap();
    let _ = SlotReservation::take_last_release_locked_for_test();
    let target = f
        .ctx
        .host
        .store_root
        .join("worktrees-v1")
        .join(&f.ctx.host.workspace_id)
        .join(slot.id());
    fs::create_dir_all(&target).unwrap();
    assert!(mgr.create_reserved(slot).is_err());
    assert_eq!(
        SlotReservation::take_last_release_locked_for_test(),
        Some(true)
    );
    fs::remove_dir(&target).unwrap();
    for n in 0..8 {
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(
            created["ok"], true,
            "slot {n} must be free again: {created}"
        );
    }
}

#[test]
fn a_failed_commit_rolls_back_make_room_and_releases_the_reservation() {
    let f = Fixture::new();
    let mgr = manager(&f.ctx).unwrap();
    let store = WorkerStore::open(&f.ctx.host, &mgr).unwrap();
    let oldest = store
        .inject_for_test(&WorkerOwner::local(), None, WorkerState::Failed, 1)
        .unwrap();
    for n in 0..63 {
        store
            .inject_for_test(&WorkerOwner::local(), None, WorkerState::Failed, 10 + n)
            .unwrap();
    }
    drop(store);
    let namespace = f
        .ctx
        .host
        .store_root
        .join("agents-v1")
        .join(&f.ctx.host.workspace_id);
    fs::remove_file(namespace.join("auth.json")).unwrap();
    let _ = SlotReservation::take_last_release_locked_for_test();
    let err = scoped(&f.ctx, |c| spawn(c, "req", "w")).unwrap_err();
    assert_eq!(err.code(), "STORE_UNAVAILABLE");
    // C1-a: the reservation is dropped while the native lifecycle lock is held,
    // before that lock is released (never after, where create could race it).
    assert_eq!(
        SlotReservation::take_last_release_locked_for_test(),
        Some(true)
    );
    let records = status(&f.ctx, None).unwrap();
    assert_eq!(records.len(), 64, "make_room must not leak into memory");
    assert!(records.iter().any(|r| r.worker_id == oldest));
    assert!(records.iter().all(|r| r.spawn_request_id != "req"));
    // The reservation was released: all eight slots are still available.
    for n in 0..8 {
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(created["ok"], true, "slot {n}: {created}");
    }
}

// ---------------------------------------------------------------------------
// C2 (SPEC-A1 v4 §1.4, §3, §5.2): ToolContext::for_worker, dispatch stripping,
// remote scope computation and the main-root drain primitive.
// ---------------------------------------------------------------------------

fn worker_tree(ctx: &ToolContext, worker: &WorkerRecord) -> std::path::PathBuf {
    worktree_path(&ctx.host, worker.worktree_id.as_deref().unwrap())
}
fn with_worker(id: &str, args: Value) -> Value {
    let mut args = args;
    args["worker_id"] = json!(id);
    args
}
fn code(value: &Value) -> &str {
    value["error"]["code"].as_str().unwrap_or_default()
}
/// The inner routing layer as the chat-scoped domain sees it (after scoped()).
/// These sessions are deliberately unapproved, so the re-entered tool runs on
/// the worker context directly instead of through a second chat permit.
fn routed(ctx: &ToolContext, name: &str, args: &Value) -> Value {
    assert_eq!(name, "read_file");
    route(ctx, name, args, |worker_ctx, stripped| {
        assert!(worker_ctx.worker.is_some());
        assert!(stripped.get("worker_id").is_none());
        crate::tools::file::read_file(&worker_ctx.workspace, stripped)
            .unwrap_or_else(crate::tools::workspace::tool_err)
    })
    .expect("worker_id present")
}

#[test]
fn worker_id_reroutes_file_git_and_patch_tools_into_the_worker_worktree() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker_tree(&f.ctx, &worker);
    fs::write(tree.join("fixture.txt"), "worker copy\n").unwrap();
    fs::create_dir(tree.join("only-in-worker")).unwrap();
    let id = worker.worker_id.as_str();

    let listed = call_tool(&f.ctx, "list_dir", &with_worker(id, json!({"path":"."})));
    assert_eq!(listed["ok"], true, "{listed}");
    assert!(listed.to_string().contains("only-in-worker"), "{listed}");
    let main = call_tool(&f.ctx, "list_dir", &json!({"path":"."}));
    assert!(!main.to_string().contains("only-in-worker"), "{main}");

    let status = call_tool(&f.ctx, "git_status", &with_worker(id, json!({})));
    assert_eq!(status["ok"], true, "{status}");
    // SPEC-A1 v4 §4.2 (C4, closes known gap C2-3): on Linux the worker's git
    // runner uses `LinuxSandbox::for_worktree`, so the linked worktree's gitdir
    // under the main `.git/worktrees/` is readable and status is the worker's.
    // Other platforms keep their pre-C4 assertion unchanged.
    #[cfg(target_os = "linux")]
    assert_eq!(status["is_repo"], true, "{status}");
    assert!(status.to_string().contains("fixture.txt"), "{status}");
    let main_status = call_tool(&f.ctx, "git_status", &json!({}));
    assert!(
        !main_status.to_string().contains("fixture.txt"),
        "{main_status}"
    );

    let patch = "*** Begin Patch\n*** Add File: worker-made.txt\n+from worker\n*** End Patch\n";
    let written = call_tool(
        &f.ctx,
        "apply_patch",
        &with_worker(id, json!({"patch":patch})),
    );
    assert_eq!(written["ok"], true, "{written}");
    assert_eq!(
        fs::read_to_string(tree.join("worker-made.txt")).unwrap(),
        "from worker\n"
    );
    assert!(!f.root.path().join("worker-made.txt").exists());
    // Worker writes never touch the main task baseline or operation log (v4 §1.4.3).
    assert!(written.get("operation_id").is_none(), "{written}");
    assert!(written.get("harness").is_none(), "{written}");
    // The worker's paths are confined to its worktree: the main root is outside it.
    let escape = call_tool(
        &f.ctx,
        "read_file",
        &with_worker(id, json!({"path": f.root.path().join("fixture.txt")})),
    );
    assert_eq!(escape["ok"], false, "{escape}");
}

#[cfg(target_os = "linux")]
#[test]
fn worker_exec_runs_with_the_worker_worktree_as_its_root_and_cwd() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let out = call_tool(
        &f.ctx,
        "exec_command",
        &with_worker(worker.worker_id.as_str(), json!({"cmd":"pwd"})),
    );
    assert_eq!(out["ok"], true, "{out}");
    assert!(
        out.to_string().contains(tree.to_str().unwrap()),
        "{out} / {}",
        tree.display()
    );
}

/// SPEC-A1 v4 §4.2 (C4): the worker context's Linux sandbox (used for remote,
/// kernel-isolated worker exec) is `LinuxSandbox::for_worktree`. Its private and
/// common gitdirs are readable, neither gains any write right, and the worktree
/// itself stays writable. Exercised directly on the bound context's policy.
#[cfg(target_os = "linux")]
#[test]
fn worker_context_sandbox_reads_but_cannot_write_its_gitdirs() {
    use coding_tools_local_agent::{ExecSpec, ProcessManager};
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let (worker_ctx, _, _guard, _) = bind(
        &f.ctx,
        "exec_command",
        &json!(worker.worker_id.as_str()),
        &json!({}),
    )
    .unwrap();
    // A1 C5 (NB-g): the bound workspace is a worker root, so Git inspection
    // through `git_runner::run` takes the fail-closed worker sandbox.
    assert!(worker_ctx.workspace.is_worker_root());
    assert!(!f.ctx.workspace.is_worker_root());
    let policy = worker_ctx.linux_sandbox.as_ref().clone().unwrap();
    let script = concat!(
        "p=$(sed 's/^gitdir: //' .git); ",
        "head -c 1 \"$p/HEAD\" >/dev/null 2>&1 && printf Y || printf N; ",
        "head -c 1 \"$p/../../HEAD\" >/dev/null 2>&1 && printf Y || printf N; ",
        "(set -C; echo x > \"$p/c4-probe\") 2>/dev/null && printf Y || printf N; ",
        "(set -C; echo x > \"$p/../../c4-probe\") 2>/dev/null && printf Y || printf N; ",
        "(set -C; echo x > c4-inside) 2>/dev/null && printf Y || printf N"
    );
    let spec = ExecSpec::new(
        vec!["/bin/sh".into(), "-c".into(), script.into()],
        tree.canonicalize().unwrap(),
    )
    .unwrap()
    .with_env("PATH", "/usr/bin:/bin")
    .unwrap()
    .with_sandbox(policy);
    let output = tauri::async_runtime::block_on(ProcessManager::default().run(spec)).unwrap();
    // private read, common read, private create, common create, root create.
    assert_eq!(
        String::from_utf8_lossy(&output.stdout),
        "YYNNY",
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let link = fs::read_to_string(tree.join(".git")).unwrap();
    let private = std::path::Path::new(link.trim_end().strip_prefix("gitdir: ").unwrap());
    assert!(!private.join("c4-probe").exists());
    assert!(!f.root.path().join(".git").join("c4-probe").exists());
    assert!(tree.join("c4-inside").exists());
}

#[test]
fn worker_default_cwd_is_per_worker_and_persisted_in_the_store() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker_tree(&f.ctx, &worker);
    fs::create_dir_all(tree.join("sub/dir")).unwrap();
    let id = worker.worker_id.as_str();
    let set = call_tool(
        &f.ctx,
        "set_default_cwd",
        &with_worker(id, json!({"path":"sub/dir"})),
    );
    assert_eq!(set["ok"], true, "{set}");
    let stored = status(&f.ctx, Some(id)).unwrap();
    assert_eq!(stored[0].cwd, "sub/dir");
    // Survives a process restart: a fresh store reads the persisted cwd.
    WorkerStore::evict_for_test(&f.ctx.host);
    let got = call_tool(&f.ctx, "get_default_cwd", &with_worker(id, json!({})));
    assert_eq!(got["ok"], true, "{got}");
    assert!(got.to_string().contains("sub/dir"), "{got}");
    // The main task's cwd is untouched.
    let main = call_tool(&f.ctx, "get_default_cwd", &json!({}));
    assert!(!main.to_string().contains("sub/dir"), "{main}");
    // A worker cwd outside the worktree is rejected.
    let bad = call_tool(
        &f.ctx,
        "set_default_cwd",
        &with_worker(id, json!({"path": f.root.path()})),
    );
    assert_eq!(bad["ok"], false, "{bad}");
    assert_eq!(status(&f.ctx, Some(id)).unwrap()[0].cwd, "sub/dir");
}

#[test]
fn worker_id_is_rejected_on_unsupported_tools_and_malformed_ids() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str();
    for tool in ["worktree_list", "history_session_read", "server_info"] {
        let out = call_tool(&f.ctx, tool, &with_worker(id, json!({})));
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{tool}: {out}");
    }
    for bad in [json!("NOT-HEX"), json!(7), json!(null)] {
        let out = call_tool(
            &f.ctx,
            "read_file",
            &json!({"path":"fixture.txt","worker_id":bad}),
        );
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{bad}: {out}");
    }
    assert!(WORKER_TOOLS.contains(&"read_file"));
    assert!(WORKER_TOOLS.contains(&"change_summary"));
    assert!(WORKER_TOOLS.contains(&"list_exec_tasks"));
    assert_eq!(WORKER_TOOLS.len(), 22);
}

#[test]
fn unknown_and_foreign_worker_ids_are_indistinguishable_through_dispatch() {
    let f = Fixture::new();
    let a = session(&f.ctx, "conversation-a");
    let b = session(&f.ctx, "conversation-b");
    let mine = spawn_ok(&a, "req", "a");
    let local = spawn_ok(&f.ctx, "req", "local");
    let unknown = WorkerId::generate();
    let args = |id: &str| with_worker(id, json!({"path":"fixture.txt"}));
    let ok = routed(&a, "read_file", &args(mine.worker_id.as_str()));
    assert_eq!(ok["ok"], true, "{ok}");
    let mut seen = Vec::new();
    for (ctx, id) in [
        (&b, mine.worker_id.as_str()),
        (&b, unknown.as_str()),
        (&a, local.worker_id.as_str()),
    ] {
        let out = routed(ctx, "read_file", &args(id));
        assert_eq!(code(&out), "WORKER_NOT_OWNED", "{out}");
        assert!(!out.to_string().contains(id), "{out}");
        seen.push(out["error"].to_string());
    }
    assert!(seen.windows(2).all(|w| w[0] == w[1]), "{seen:?}");
    let out = call_tool(&f.ctx, "read_file", &args(mine.worker_id.as_str()));
    assert_eq!(code(&out), "WORKER_NOT_OWNED", "{out}");
}

#[test]
fn only_ready_workers_route_and_nested_worker_ids_are_rejected() {
    let f = Fixture::new();
    let creating = reserve_ok(&f.ctx, "req-c", "c");
    let out = call_tool(
        &f.ctx,
        "read_file",
        &with_worker(creating.worker_id.as_str(), json!({"path":"fixture.txt"})),
    );
    assert_eq!(code(&out), "WORKER_STATE", "{out}");
    let ready = spawn_ok(&f.ctx, "req-r", "r");
    let id = ready.worker_id.as_str().to_owned();
    let nested = route(
        &f.ctx,
        "read_file",
        &with_worker(&id, json!({"path":"fixture.txt"})),
        |worker_ctx, _| {
            assert!(worker_ctx.worker.is_some());
            assert_eq!(worker_ctx.worker.as_ref().unwrap().worker_id.as_str(), id);
            call_tool(
                worker_ctx,
                "read_file",
                &with_worker(&id, json!({"path":"fixture.txt"})),
            )
        },
    )
    .unwrap();
    assert_eq!(code(&nested), "WORKER_STATE", "{nested}");
    cancel(&f.ctx, &id).unwrap();
    let out = call_tool(
        &f.ctx,
        "read_file",
        &with_worker(&id, json!({"path":"fixture.txt"})),
    );
    assert_eq!(code(&out), "WORKER_STATE", "{out}");
    // Calls without worker_id are not routed at all.
    assert!(route(
        &f.ctx,
        "read_file",
        &json!({"path":"fixture.txt"}),
        |_, _| { unreachable!() }
    )
    .is_none());
}

#[test]
fn worker_context_is_a_field_carried_through_background_snapshots() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let id = worker.worker_id.as_str().to_owned();
    assert!(f.ctx.worker.is_none());
    assert!(f.ctx.background_snapshot().worker.is_none());
    route(
        &f.ctx,
        "read_file",
        &with_worker(&id, json!({"path":"fixture.txt"})),
        |w, stripped| {
            assert!(stripped.get("worker_id").is_none(), "{stripped}");
            assert_eq!(stripped["path"], "fixture.txt");
            let copy = w.background_snapshot();
            let binding = copy.worker.as_ref().unwrap();
            assert_eq!(binding.worker_id.as_str(), id);
            assert_eq!(binding.worktree_root, tree);
            assert_eq!(copy.workspace.root(), tree.as_path());
            // The store root stays the main root's harness, not the worktree.
            assert_eq!(copy.host.store_root, f.ctx.host.store_root);
            Value::Null
        },
    )
    .unwrap();
}

#[test]
fn remote_worker_calls_add_agents_manage_to_the_required_scopes() {
    use crate::tools::chat_domain::{required, scopes};
    let base = required("read_file", &json!({})).unwrap();
    assert_eq!(scopes("read_file", &json!({})).unwrap(), base.to_vec());
    let with = scopes("read_file", &json!({"worker_id":"x"})).unwrap();
    assert!(with.contains(&"agents.manage"), "{with:?}");
    for s in base {
        assert!(with.contains(s));
    }
    // Unknown tools stay unknown.
    assert!(scopes("no_such_tool", &json!({"worker_id":"x"})).is_none());
    // C2 grants never include agents.manage, so a remote worker call fails closed.
    assert!(!crate::auth::chat::SCOPES.contains(&"agents.manage"));
}

/// Simulates a running worker call (the guard route() holds for the call).
fn in_flight(ctx: &ToolContext, id: &str) -> FlightGuard {
    let owner = WorkerOwner::from_context(ctx).unwrap();
    let store = WorkerStore::open_existing(&ctx.host).unwrap().unwrap();
    store.enter(&owner, &WorkerId::parse(id).unwrap()).unwrap()
}

#[test]
fn integrate_busy_lists_only_the_callers_own_blocking_workers() {
    let f = Fixture::new();
    let a = session(&f.ctx, "conversation-a");
    let b = session(&f.ctx, "conversation-b");
    let wa = spawn_ok(&a, "req", "a");
    let wb = spawn_ok(&b, "req", "b");
    let wb2 = spawn_ok(&b, "req2", "b2");
    let _ga = in_flight(&a, wa.worker_id.as_str());
    let _gb = in_flight(&b, wb.worker_id.as_str());
    let _gb2 = in_flight(&b, wb2.worker_id.as_str());
    let busy = scoped(&a, |c| {
        drain_for_integrate(c, std::time::Duration::from_millis(300)).err()
    })
    .expect("drain must time out while workers are in flight");
    assert_eq!(busy["error"]["code"], "INTEGRATE_BUSY", "{busy}");
    assert_eq!(busy["error"]["retryable"], true, "{busy}");
    let details = &busy["error"]["details"];
    assert_eq!(details["retry_after_ms"], 1000, "{busy}");
    assert_eq!(
        details["blocking_worker_ids"],
        json!([wa.worker_id.as_str()]),
        "{busy}"
    );
    assert_eq!(details["other_sessions_blocking"], 2, "{busy}");
    let text = busy.to_string();
    assert!(!text.contains(wb.worker_id.as_str()), "{text}");
    assert!(!text.contains(wb2.worker_id.as_str()), "{text}");
    // Session B sees its own two, and only a count for A's.
    let busy_b = scoped(&b, |c| {
        drain_for_integrate(c, std::time::Duration::from_millis(100)).err()
    })
    .unwrap();
    let ids = busy_b["error"]["details"]["blocking_worker_ids"]
        .as_array()
        .unwrap()
        .clone();
    assert_eq!(ids.len(), 2, "{busy_b}");
    assert!(
        !busy_b.to_string().contains(wa.worker_id.as_str()),
        "{busy_b}"
    );
    assert_eq!(busy_b["error"]["details"]["other_sessions_blocking"], 1);
    // A timed-out drain clears the flag: running work was not cancelled and new
    // worker calls proceed.
    let ok = routed(
        &a,
        "read_file",
        &with_worker(wa.worker_id.as_str(), json!({"path":"fixture.txt"})),
    );
    assert_eq!(ok["ok"], true, "{ok}");
}

#[test]
fn draining_covers_every_session_on_the_main_root_and_waits_for_running_calls() {
    let f = Fixture::new();
    let a = session(&f.ctx, "conversation-a");
    let b = session(&f.ctx, "conversation-b");
    let wa = spawn_ok(&a, "req", "a");
    let wb = spawn_ok(&b, "req", "b");
    let store = WorkerStore::open_existing(&f.ctx.host).unwrap().unwrap();
    let guard = in_flight(&b, wb.worker_id.as_str());
    let watcher = {
        let store = store.clone();
        std::thread::spawn(move || {
            let until = std::time::Instant::now() + std::time::Duration::from_secs(5);
            while !store.draining() {
                assert!(std::time::Instant::now() < until, "drain never started");
                std::thread::sleep(std::time::Duration::from_millis(5));
            }
            std::thread::sleep(std::time::Duration::from_millis(150));
            drop(guard);
        })
    };
    scoped(&a, |c| {
        let drained = drain_for_integrate(c, std::time::Duration::from_secs(5));
        assert!(drained.is_ok(), "{:?}", drained.as_ref().err());
        assert!(store.draining());
        // While draining, every session's new worker calls and spawns are refused.
        for (ctx, id) in [(&a, wa.worker_id.as_str()), (&b, wb.worker_id.as_str())] {
            let out = route(
                ctx,
                "read_file",
                &with_worker(id, json!({"path":"fixture.txt"})),
                |_, _| unreachable!("must not run while draining"),
            )
            .unwrap();
            assert_eq!(code(&out), "INTEGRATE_BUSY", "{out}");
        }
        assert_eq!(
            spawn(c, "req-new", "n").unwrap_err().code(),
            "INTEGRATE_BUSY"
        );
        drop(drained);
        assert!(!store.draining());
    });
    watcher.join().unwrap();
    let ok = routed(
        &a,
        "read_file",
        &with_worker(wa.worker_id.as_str(), json!({"path":"fixture.txt"})),
    );
    assert_eq!(ok["ok"], true, "{ok}");
}

// ---------------------------------------------------------------------------
// A1 C2b: subagent_* handlers, worker change_summary / list_exec_tasks routing,
// and the C1-c spawn completion guard.
// ---------------------------------------------------------------------------
fn subagent(ctx: &ToolContext, name: &str, args: Value) -> Value {
    call_tool(ctx, name, &args)
}

#[test]
fn spawn_and_complete_never_leaks_a_pending_slot_on_early_return() {
    // C1-c: whether the failure is before complete_spawn or inside it before the
    // slot is taken, the guard releases the slot under the native lock and the
    // record ends failed; all 8 device slots stay usable.
    for point in [spawn_hooks::BEFORE_COMPLETE, spawn_hooks::INSIDE_COMPLETE] {
        let f = Fixture::new();
        let _ = SlotReservation::take_last_release_locked_for_test();
        spawn_hooks::arm(point);
        let out = subagent(
            &f.ctx,
            "subagent_spawn",
            json!({"request_id":"r1","label":"w"}),
        );
        assert_eq!(code(&out), "STORE_UNAVAILABLE", "{point}: {out}");
        let records = status(&f.ctx, None).unwrap();
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].state, WorkerState::Failed, "{point}");
        assert!(records[0].worktree_id.is_none());
        assert!(!pending_for_test(records[0].worker_id.as_str()));
        assert_eq!(
            SlotReservation::take_last_release_locked_for_test(),
            Some(true),
            "{point}"
        );
        for n in 0..8 {
            let created = call_tool(&f.ctx, "worktree_create", &json!({}));
            assert_eq!(created["ok"], true, "{point} slot {n}: {created}");
        }
    }
}

#[test]
fn successful_spawn_consumes_its_reservation_and_the_guard_is_a_no_op() {
    let f = Fixture::new();
    let out = subagent(&f.ctx, "subagent_spawn", json!({"request_id":"r1"}));
    assert_eq!(out["ok"], true, "{out}");
    let id = out["worker"]["worker_id"].as_str().unwrap().to_owned();
    assert!(!pending_for_test(&id));
    let record = &status(&f.ctx, Some(&id)).unwrap()[0];
    assert_eq!(record.state, WorkerState::Ready);
    assert!(worker_tree(&f.ctx, record).is_dir());
}

#[test]
fn subagent_tools_manage_the_callers_workers_through_dispatch() {
    let f = Fixture::new();
    let out = subagent(
        &f.ctx,
        "subagent_spawn",
        json!({"request_id":"r1","label":"alpha","base":"HEAD"}),
    );
    assert_eq!(out["ok"], true, "{out}");
    assert_eq!(out["deduplicated"], false);
    let worker = &out["worker"];
    assert_eq!(worker["state"], "ready");
    assert_eq!(worker["label"], "alpha");
    assert_eq!(worker["base_head"], f.head());
    assert_eq!(worker["changed_files"], Value::Null);
    assert!(worker.get("worktree_id").is_none(), "{worker}");
    assert!(!out.to_string().contains("worktrees-v1"), "{out}");
    let id = worker["worker_id"].as_str().unwrap().to_owned();
    let again = subagent(
        &f.ctx,
        "subagent_spawn",
        json!({"request_id":"r1","label":"alpha"}),
    );
    assert_eq!(again["deduplicated"], true, "{again}");
    assert_eq!(again["worker"]["worker_id"], id.as_str());

    let listed = subagent(&f.ctx, "subagent_status", json!({}));
    assert_eq!(listed["workers"].as_array().unwrap().len(), 1, "{listed}");
    let one = subagent(&f.ctx, "subagent_status", json!({"worker_id": id}));
    assert_eq!(one["workers"][0]["worker_id"], id.as_str(), "{one}");

    for (name, args) in [
        ("subagent_collect", json!({"worker_id": id})),
        (
            "subagent_integrate",
            json!({"worker_id": id, "diff_sha256": "0".repeat(64), "request_id": "i1"}),
        ),
        (
            "subagent_rollback",
            json!({"integration_id": "0".repeat(32), "request_id": "b1"}),
        ),
    ] {
        let out = subagent(&f.ctx, name, args);
        assert_eq!(code(&out), "INTEGRATE_UNSUPPORTED", "{name}: {out}");
    }
    for (name, args) in [
        ("subagent_spawn", json!({})),
        ("subagent_spawn", json!({"request_id":"r2","base":"main"})),
        ("subagent_spawn", json!({"request_id":"r2","extra":1})),
        ("subagent_status", json!({"worker_id": 7})),
        ("subagent_cancel", json!({})),
        ("subagent_collect", json!({"worker_id": id, "max_bytes": 1})),
        (
            "subagent_integrate",
            json!({"worker_id": id, "diff_sha256": "x", "request_id": "i"}),
        ),
    ] {
        let out = subagent(&f.ctx, name, args.clone());
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{name} {args}: {out}");
    }
    // worker_id on subagent_* names the target; it is never a routing key.
    let cancelled = subagent(&f.ctx, "subagent_cancel", json!({"worker_id": id}));
    assert_eq!(cancelled["worker"]["state"], "cancelled", "{cancelled}");
    let discarded = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(discarded["worker"]["state"], "discarded", "{discarded}");
    // Unknown ids stay indistinguishable from foreign ones.
    let unknown = subagent(
        &f.ctx,
        "subagent_status",
        json!({"worker_id": "0123456789abcdef0123456789abcdef"}),
    );
    assert_eq!(code(&unknown), "WORKER_NOT_OWNED", "{unknown}");
}

#[test]
fn worker_change_summary_reports_only_the_workers_own_state() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str();
    fs::write(
        worker_tree(&f.ctx, &worker).join("fixture.txt"),
        "changed\n",
    )
    .unwrap();
    let out = call_tool(&f.ctx, "change_summary", &with_worker(id, json!({})));
    assert_eq!(out["ok"], true, "{out}");
    assert_eq!(out["worker_id"], id);
    assert_eq!(out["state"], "ready");
    assert_eq!(out["base_head"], f.head());
    assert!(out.get("task_id").is_none(), "{out}");
    assert!(!out.to_string().contains("worktrees-v1"), "{out}");
    for args in [json!({"task_id":"t"}), json!({"change_id":"c"})] {
        let out = call_tool(&f.ctx, "change_summary", &with_worker(id, args.clone()));
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{args}: {out}");
    }
}

#[test]
fn worker_exec_tasks_are_tagged_and_listed_per_worker() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str();
    let started = call_tool(
        &f.ctx,
        "start_exec_task",
        &with_worker(id, json!({"cmd":"echo w","request_id":"job-w"})),
    );
    assert_eq!(started["ok"], true, "{started}");
    let main = call_tool(
        &f.ctx,
        "start_exec_task",
        &json!({"cmd":"echo m","request_id":"job-m"}),
    );
    assert_eq!(main["ok"], true, "{main}");
    let listed = call_tool(&f.ctx, "list_exec_tasks", &with_worker(id, json!({})));
    assert_eq!(listed["ok"], true, "{listed}");
    let jobs = listed["jobs"].as_array().unwrap();
    assert_eq!(jobs.len(), 1, "{listed}");
    assert_eq!(jobs[0]["job_id"], started["job_id"]);
    // Reusing the worker's request_id from main is a conflict, never a hit.
    let clash = call_tool(
        &f.ctx,
        "start_exec_task",
        &json!({"cmd":"echo w","request_id":"job-w"}),
    );
    assert_eq!(code(&clash), "IDEMPOTENCY_CONFLICT", "{clash}");
    // A1 C3 (C2b deviation 11): the main session lists only its own untagged
    // jobs; a worker's jobs are listed only through worker_id (v4 §2.3).
    let all = call_tool(&f.ctx, "list_exec_tasks", &json!({}));
    let jobs = all["jobs"].as_array().unwrap();
    assert_eq!(jobs.len(), 1, "{all}");
    assert_eq!(jobs[0]["job_id"], main["job_id"], "{all}");
    let by_request = call_tool(&f.ctx, "list_exec_tasks", &json!({"request_id":"job-w"}));
    assert_eq!(by_request["ok"], true, "{by_request}");
    assert_eq!(
        by_request["jobs"].as_array().unwrap().len(),
        0,
        "{by_request}"
    );
}

#[test]
fn workers_cannot_manage_workers() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let out = route(
        &f.ctx,
        "read_file",
        &with_worker(worker.worker_id.as_str(), json!({"path":"fixture.txt"})),
        |worker_ctx, _| subagent::call(worker_ctx, "subagent_status", &json!({})),
    )
    .expect("worker_id present");
    assert_eq!(code(&out), "WORKER_STATE", "{out}");
}

// ---------------------------------------------------------------------------
// A1 C3 (SPEC-A1 v4 §1.4.3): the worker operation log. Worker writes append a
// bounded, argument-free entry to the worker's own record in the encrypted
// main-root WorkerStore; the worker change_summary reads it back.
// ---------------------------------------------------------------------------
fn worker_ops(ctx: &ToolContext, id: &str) -> Value {
    let out = call_tool(ctx, "change_summary", &with_worker(id, json!({})));
    assert_eq!(out["ok"], true, "{out}");
    out["operations"].clone()
}

#[test]
fn worker_writes_append_a_bounded_ops_log_read_through_the_worker_change_summary() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let other = spawn_ok(&f.ctx, "req2", "x");
    let id = worker.worker_id.as_str();
    fs::create_dir_all(worker_tree(&f.ctx, &worker).join("nested")).unwrap();
    assert_eq!(worker_ops(&f.ctx, id), json!([]));

    // Reads and dry runs are not operations.
    for (name, args) in [
        ("read_file", json!({"path":"fixture.txt"})),
        ("list_dir", json!({"path":"."})),
        ("git_status", json!({})),
        ("get_default_cwd", json!({})),
        (
            "patch_check",
            json!({"patch":"*** Begin Patch\n*** Add File: probe.txt\n+p\n*** End Patch\n"}),
        ),
    ] {
        call_tool(&f.ctx, name, &with_worker(id, args));
    }
    assert_eq!(worker_ops(&f.ctx, id), json!([]));

    let patch = "*** Begin Patch\n*** Add File: secret-name.txt\n+secret body\n*** End Patch\n";
    let written = call_tool(
        &f.ctx,
        "apply_patch",
        &with_worker(id, json!({"patch":patch})),
    );
    assert_eq!(written["ok"], true, "{written}");
    let broken = "*** Begin Patch\n*** Delete File: secret-missing.txt\n*** End Patch\n";
    let failed = call_tool(
        &f.ctx,
        "apply_patch",
        &with_worker(id, json!({"patch":broken})),
    );
    assert_eq!(failed["ok"], false, "{failed}");
    let cwd = call_tool(
        &f.ctx,
        "set_default_cwd",
        &with_worker(id, json!({"path":"nested"})),
    );
    assert_eq!(cwd["ok"], true, "{cwd}");
    let job = call_tool(
        &f.ctx,
        "start_exec_task",
        &with_worker(
            id,
            json!({"cmd":"echo secret-cmd","request_id":"secret-req"}),
        ),
    );
    assert_eq!(job["ok"], true, "{job}");

    let log = worker_ops(&f.ctx, id);
    let entries = log.as_array().expect("operations array");
    let tools: Vec<_> = entries.iter().map(|e| e["tool"].clone()).collect();
    assert_eq!(
        tools,
        [
            json!("apply_patch"),
            json!("apply_patch"),
            json!("set_default_cwd"),
            json!("start_exec_task")
        ],
        "{log}"
    );
    let seqs: Vec<_> = entries.iter().map(|e| e["seq"].as_u64().unwrap()).collect();
    assert_eq!(seqs, [1, 2, 3, 4], "{log}");
    assert_eq!(entries[0]["ok"], true, "{log}");
    assert_eq!(entries[0]["affected_files"], 1, "{log}");
    assert_eq!(entries[1]["ok"], false, "{log}");
    assert_eq!(entries[1]["error_code"], failed["error"]["code"], "{log}");
    assert!(
        entries.iter().all(|e| e["at"].as_u64().unwrap() > 0),
        "{log}"
    );
    // No arguments, paths, contents, commands or request ids are recorded.
    for needle in ["secret", "nested", "echo", "Begin", "path"] {
        assert!(!log.to_string().contains(needle), "{needle}: {log}");
    }
    // The log is the worker's own; the main operation log is untouched.
    assert_eq!(worker_ops(&f.ctx, other.worker_id.as_str()), json!([]));
    assert!(written.get("operation_id").is_none(), "{written}");

    // Persisted encrypted in the main-root store: survives a restart, and the
    // ciphertext carries no plaintext tool names.
    WorkerStore::evict_for_test(&f.ctx.host);
    assert_eq!(worker_ops(&f.ctx, id), log);
    let raw = fs::read(namespace(&f.ctx.host).join("auth.json")).unwrap();
    assert!(
        !String::from_utf8_lossy(&raw).contains("set_default_cwd"),
        "plaintext ops on disk"
    );

    // Bounded: only the newest MAX_OPS entries are kept; seq keeps counting.
    for _ in 0..40 {
        let out = call_tool(
            &f.ctx,
            "set_default_cwd",
            &with_worker(id, json!({"path":"."})),
        );
        assert_eq!(out["ok"], true, "{out}");
    }
    let log = worker_ops(&f.ctx, id);
    let entries = log.as_array().unwrap();
    // MAX_OPS = 32 per worker.
    assert_eq!(entries.len(), 32, "{log}");
    assert_eq!(entries.last().unwrap()["seq"], 44, "{log}");
    assert_eq!(entries[0]["seq"], 13, "{log}");
}

#[test]
fn c2b_records_without_an_ops_log_still_load_and_gain_an_empty_one() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    // The exact C2b record shape: no ops fields.
    let c2b = json!({
        "worker_id": worker.worker_id.as_str(),
        "worktree_id": worker.worktree_id,
        "workspace_id": worker.workspace_id,
        "owner": worker.owner,
        "spawn_request_id": "req",
        "spawn_fingerprint": worker.spawn_fingerprint,
        "label": "w",
        "base_head": worker.base_head,
        "state": worker.state,
        "cwd": ".",
        "created_at": 1,
        "last_activity_at": 2
    });
    let record: WorkerRecord = serde_json::from_value(c2b).expect("C2b record loads");
    let back = serde_json::to_value(&record).unwrap();
    assert_eq!(back["ops"], json!([]), "{back}");
    assert_eq!(back["ops_seq"], 0, "{back}");
}

// ---------------------------------------------------------------------------
// A1 C3 (steering 1): discard refuses while the worker still runs commands.
// ---------------------------------------------------------------------------
/// A stopped command retires its root-work chain asynchronously; until then the
/// root guard answers NATIVE_ROOT_UNAVAILABLE (retryable by the caller).
#[cfg(unix)]
fn discard_when_root_settles(ctx: &ToolContext, id: &str) -> Value {
    for _ in 0..100 {
        let out = subagent(ctx, "subagent_discard", json!({"worker_id": id}));
        if code(&out) != "NATIVE_ROOT_UNAVAILABLE" {
            return out;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    subagent(ctx, "subagent_discard", json!({"worker_id": id}))
}
#[cfg(unix)]
#[test]
fn discard_returns_worker_busy_while_a_worker_exec_runs_and_keeps_the_worktree() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    let started = call_tool(
        &f.ctx,
        "start_exec_task",
        &with_worker(
            &id,
            json!({"cmd":"python3 -c \"import time; time.sleep(30)\"","request_id":"w-long"}),
        ),
    );
    assert_eq!(started["ok"], true, "{started}");
    let job = started["job_id"].as_str().unwrap().to_owned();
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(code(&out), "WORKER_BUSY", "{out}");
    assert!(tree.is_dir(), "discard removed a busy worker's worktree");
    assert_eq!(
        status(&f.ctx, Some(&id)).unwrap()[0].state,
        WorkerState::Ready
    );
    // A1 C2-a (SPEC-A1 v5 §5.2): cancel now also stops the worker's background
    // exec (C3 only marked the worker) and reports how many it stopped.
    let out = subagent(&f.ctx, "subagent_cancel", json!({"worker_id": id}));
    assert_eq!(out["ok"], true, "{out}");
    assert_eq!(out["killed_tasks"], 1, "{out}");
    let mut last = Value::Null;
    for _ in 0..200 {
        last = call_tool(&f.ctx, "get_exec_task", &json!({"job_id": job}));
        if !["queued", "running", "cancelling"].contains(&last["status"].as_str().unwrap()) {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    assert!(
        !["queued", "running", "cancelling"].contains(&last["status"].as_str().unwrap()),
        "cancel left the worker's task running: {last}"
    );
    let out = discard_when_root_settles(&f.ctx, &id);
    assert_eq!(out["ok"], true, "{out}");
    assert!(!tree.exists());
}

#[cfg(unix)]
#[test]
fn discard_returns_worker_busy_while_a_worker_interactive_session_runs() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    let run = call_tool(
        &f.ctx,
        "exec_command",
        &with_worker(
            &id,
            json!({"cmd":"python3 -c \"import time; time.sleep(30)\"","yield_time_ms":200}),
        ),
    );
    assert!(run["session_id"].is_string(), "still running: {run}");
    let session = run["session_id"].as_str().unwrap().to_owned();
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(code(&out), "WORKER_BUSY", "{out}");
    assert!(tree.is_dir());
    let killed = call_tool(
        &f.ctx,
        "kill_session",
        &json!({"session_id": session, "signal":"KILL", "wait_ms": 2000}),
    );
    assert_eq!(killed["ok"], true, "{killed}");
    let out = discard_when_root_settles(&f.ctx, &id);
    assert_eq!(out["ok"], true, "{out}");
    assert!(!tree.exists());
}

#[test]
fn concurrent_duplicate_spawns_with_one_request_id_end_failed_without_a_leak() {
    // A1 C3 (steering 3): the same request_id raced from several threads while the
    // build's lifecycle lock fails. One record, state failed, no pending slot, the
    // slot released inside the lock, and all 8 device slots usable afterwards.
    let f = Fixture::new();
    let barrier = std::sync::Barrier::new(4);
    let results: Vec<(Value, Option<bool>)> = std::thread::scope(|s| {
        let handles: Vec<_> = (0..4)
            .map(|_| {
                s.spawn(|| {
                    let _ = SlotReservation::take_last_release_locked_for_test();
                    spawn_hooks::arm(spawn_hooks::FAIL_BUILD_LOCK);
                    barrier.wait();
                    let out = subagent(
                        &f.ctx,
                        "subagent_spawn",
                        json!({"request_id":"dup","label":"w"}),
                    );
                    (out, SlotReservation::take_last_release_locked_for_test())
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    for (out, released) in &results {
        assert_ne!(*released, Some(false), "slot freed outside the lock: {out}");
        assert_ne!(out["worker"]["state"], "ready", "{out}");
    }
    // Whichever thread held the reservation released it inside the lifecycle
    // lock: the build path (LOCK_UNAVAILABLE) or, when a racing duplicate held
    // the root guard (NATIVE_ROOT_UNAVAILABLE), the spawn completion guard.
    assert!(
        results.iter().any(|(_, released)| *released == Some(true)),
        "no thread released the slot: {results:?}"
    );
    for (out, _) in &results {
        if out["ok"] == false {
            assert!(
                ["LOCK_UNAVAILABLE", "NATIVE_ROOT_UNAVAILABLE"].contains(&code(out)),
                "{out}"
            );
        }
    }
    let records = status(&f.ctx, None).unwrap();
    assert_eq!(records.len(), 1, "{records:?}");
    assert_eq!(records[0].state, WorkerState::Failed);
    assert!(records[0].worktree_id.is_none());
    assert!(!pending_for_test(records[0].worker_id.as_str()));
    // A retry with the same request_id returns the same failed worker.
    let again = subagent(
        &f.ctx,
        "subagent_spawn",
        json!({"request_id":"dup","label":"w"}),
    );
    assert_eq!(again["worker"]["state"], "failed", "{again}");
    assert_eq!(
        again["worker"]["worker_id"],
        records[0].worker_id.as_str(),
        "{again}"
    );
    for n in 0..8 {
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(created["ok"], true, "slot {n}: {created}");
    }
}

// ---------------------------------------------------------------------------
// A1 C2-a (SPEC-A1 v5 §5.2 C2-a, §2.1, T14): background exec counts toward the
// flight registry; discard backs off on a busy main root; NB-f re-check.
// ---------------------------------------------------------------------------
/// Holds one main-root dispatch chain on another thread for `hold`.
fn hold_main_root<'s>(
    scope: &'s std::thread::Scope<'s, '_>,
    ctx: &'s ToolContext,
    hold: std::time::Duration,
) -> std::thread::ScopedJoinHandle<'s, ()> {
    let (tx, rx) = std::sync::mpsc::channel();
    let handle = scope.spawn(move || {
        scoped(ctx, |_| {
            tx.send(()).unwrap();
            std::thread::sleep(hold);
        })
    });
    rx.recv().unwrap();
    handle
}

/// Holds one main-root dispatch chain on another thread until `release`
/// fires (load-independent: the hold cannot end inside the 2 s backoff).
fn hold_main_root_until<'s>(
    scope: &'s std::thread::Scope<'s, '_>,
    ctx: &'s ToolContext,
    release: std::sync::mpsc::Receiver<()>,
) -> std::thread::ScopedJoinHandle<'s, ()> {
    let (tx, rx) = std::sync::mpsc::channel();
    let handle = scope.spawn(move || {
        scoped(ctx, |_| {
            tx.send(()).unwrap();
            let _ = release.recv_timeout(std::time::Duration::from_secs(60));
        })
    });
    rx.recv().unwrap();
    handle
}

#[test]
fn discard_backs_off_then_answers_retryable_main_root_busy_and_changes_nothing() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    std::thread::scope(|scope| {
        let (release, held) = std::sync::mpsc::channel();
        let holder = hold_main_root_until(scope, &f.ctx, held);
        let started = std::time::Instant::now();
        let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
        let elapsed = started.elapsed();
        release.send(()).unwrap();
        assert_eq!(code(&out), "NATIVE_ROOT_UNAVAILABLE", "{out}");
        assert_eq!(out["error"]["retryable"], true, "{out}");
        assert_eq!(out["error"]["details"]["reason"], "main_root_busy", "{out}");
        assert!(
            elapsed >= std::time::Duration::from_millis(1900),
            "no 2 s backoff before main_root_busy: {elapsed:?}"
        );
        assert_eq!(
            status(&f.ctx, Some(&id)).unwrap()[0].state,
            WorkerState::Ready
        );
        assert!(tree.is_dir(), "a refused discard removed the worktree");
        holder.join().unwrap();
    });
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(out["ok"], true, "{out}");
    assert!(!tree.exists());
}

#[test]
fn discard_waits_out_a_short_main_root_hold_inside_its_backoff() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    std::thread::scope(|scope| {
        let holder = hold_main_root(scope, &f.ctx, std::time::Duration::from_millis(500));
        let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
        assert_eq!(out["ok"], true, "{out}");
        holder.join().unwrap();
    });
    assert!(!tree.exists());
}

#[cfg(unix)]
fn wait_terminal(ctx: &ToolContext, job: &str) -> Value {
    let mut last = Value::Null;
    for _ in 0..200 {
        last = call_tool(ctx, "get_exec_task", &json!({"job_id": job}));
        if !["queued", "running", "cancelling"].contains(&last["status"].as_str().unwrap_or("")) {
            return last;
        }
        std::thread::sleep(std::time::Duration::from_millis(50));
    }
    panic!("job never reached a terminal state: {last}");
}

#[cfg(unix)]
#[test]
fn integrate_drain_waits_for_worker_background_exec_and_lists_it() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let started = call_tool(
        &f.ctx,
        "start_exec_task",
        &with_worker(
            &id,
            json!({"cmd":"python3 -c \"import time; time.sleep(30)\"","request_id":"bg"}),
        ),
    );
    assert_eq!(started["ok"], true, "{started}");
    let job = started["job_id"].as_str().unwrap().to_owned();
    // No routed call is in flight any more; only the background task runs.
    let store = WorkerStore::open_existing(&f.ctx.host).unwrap().unwrap();
    assert!(store.flight().active.is_empty());
    let busy = scoped(&f.ctx, |c| {
        drain_for_integrate(c, std::time::Duration::from_millis(400)).err()
    })
    .expect("drain must wait for the worker's background exec");
    assert_eq!(code(&busy), "INTEGRATE_BUSY", "{busy}");
    assert_eq!(
        busy["error"]["details"]["blocking_tasks"],
        json!([{"worker_id": id, "running": 1}]),
        "{busy}"
    );
    assert_eq!(busy["error"]["details"]["other_sessions_blocking"], 0);
    // Another conversation sees only a count, never the worker id.
    let other = session(&f.ctx, "conversation-b");
    let busy_b = scoped(&other, |c| {
        drain_for_integrate(c, std::time::Duration::from_millis(100)).err()
    })
    .unwrap();
    assert_eq!(
        busy_b["error"]["details"]["other_sessions_blocking"], 1,
        "{busy_b}"
    );
    assert_eq!(
        busy_b["error"]["details"]["blocking_tasks"],
        json!([]),
        "{busy_b}"
    );
    assert!(!busy_b.to_string().contains(&id), "{busy_b}");
    // cancel stops it; then the drain goes through.
    let out = subagent(&f.ctx, "subagent_cancel", json!({"worker_id": id}));
    assert_eq!(out["killed_tasks"], 1, "{out}");
    wait_terminal(&f.ctx, &job);
    let drained = scoped(&f.ctx, |c| {
        drain_for_integrate(c, std::time::Duration::from_secs(5)).is_ok()
    });
    assert!(drained, "drain still blocked after the task ended");
}

/// NB-f: a call in flight before discard's root guard registers background exec
/// after the first idle check; the re-check under the guard refuses.
#[cfg(unix)]
#[test]
fn discard_rechecks_background_exec_registered_after_its_first_check() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    let runtime = tokio::runtime::Runtime::new().unwrap();
    let _enter = runtime.enter();
    let late = Arc::new(crate::tools::session::SessionStore::new());
    let child = runtime.block_on(async {
        tokio::process::Command::new("/bin/sleep")
            .arg("30")
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .unwrap()
    });
    let pid = child.id().unwrap();
    late.insert(crate::tools::session::ExecSession::new(child).for_worker(Some(id.clone())));
    assert_eq!(late.unfinished_worker_count(&id, &[]), 1);
    {
        let store = WorkerStore::open_existing(&f.ctx.host).unwrap().unwrap();
        let owner = WorkerOwner::from_context(&f.ctx).unwrap();
        let worker_id = WorkerId::parse(&id).unwrap();
        let source = BackgroundSource {
            tasks: std::sync::Weak::new(),
            sessions: Arc::downgrade(&late),
        };
        discard_hooks::arm(move || store.note_background(&owner, &worker_id, source));
    }
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(code(&out), "WORKER_BUSY", "{out}");
    assert!(
        tree.is_dir(),
        "discard removed a worktree with a running exec"
    );
    assert_eq!(
        status(&f.ctx, Some(&id)).unwrap()[0].state,
        WorkerState::Ready
    );
    // Stop exactly the child this test started (by its own session / PID).
    assert_eq!(late.kill_worker(&id, &[]), 1, "pid {pid}");
    assert_eq!(late.unfinished_worker_count(&id, &[]), 0);
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(out["ok"], true, "{out}");
    assert!(!tree.exists());
}

/// A1 C2-ad2 (NB-f2, SPEC-A1 v5.2 §5.2): a routed worker call whose
/// FlightGuard enters in the window between discard's first idle check and its
/// root guard is seen by the re-check under the guard; discard refuses
/// (`WORKER_BUSY`) and the tree stays. Once the guard drops, discard succeeds.
#[cfg(unix)]
#[test]
fn discard_rechecks_a_flight_guard_that_entered_after_its_first_check() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    let held: std::rc::Rc<std::cell::RefCell<Option<FlightGuard>>> = Default::default();
    {
        let store = WorkerStore::open_existing(&f.ctx.host).unwrap().unwrap();
        let owner = WorkerOwner::from_context(&f.ctx).unwrap();
        let worker_id = WorkerId::parse(&id).unwrap();
        let slot = held.clone();
        discard_hooks::arm(move || {
            assert!(
                !store.in_flight(&worker_id),
                "no call in flight before the window"
            );
            let guard = store.enter(&owner, &worker_id);
            assert!(guard.is_ok(), "the routed call enters while discard waits");
            *slot.borrow_mut() = guard.ok();
        });
    }
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert!(held.borrow().is_some(), "the hook ran inside the window");
    assert_eq!(code(&out), "WORKER_BUSY", "{out}");
    assert!(
        tree.is_dir(),
        "discard removed a worktree with a call in flight"
    );
    assert_eq!(
        status(&f.ctx, Some(&id)).unwrap()[0].state,
        WorkerState::Ready
    );
    held.borrow_mut().take(); // the routed call returns
    let out = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(out["ok"], true, "{out}");
    assert!(!tree.exists());
}

// ---------------------------------------------------------------------------
// A1 C2-d (SPEC-A1 v5 §1.4.4, T16): the stored worker cwd is re-canonicalized
// on every bind; a missing / non-directory / escaping cwd resets to the root.
// ---------------------------------------------------------------------------
fn cwd_after(f: &Fixture, id: &str) -> (Value, String) {
    let got = call_tool(&f.ctx, "get_default_cwd", &with_worker(id, json!({})));
    assert_eq!(got["ok"], true, "{got}");
    (got, status(&f.ctx, Some(id)).unwrap()[0].cwd.clone())
}

#[test]
fn a_stale_worker_cwd_falls_back_to_the_root_with_worker_cwd_reset() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    // Only the unix symlink case escapes to it.
    #[cfg_attr(not(unix), allow(unused_variables))]
    let outside = tempfile::tempdir().unwrap();
    #[allow(clippy::type_complexity)]
    let cases: Vec<(&str, Box<dyn Fn(&Path)>)> = vec![
        (
            "missing",
            Box::new(|sub: &Path| fs::remove_dir_all(sub).unwrap()),
        ),
        (
            "not_dir",
            Box::new(|sub: &Path| {
                fs::remove_dir_all(sub).unwrap();
                fs::write(sub, "file\n").unwrap();
            }),
        ),
        #[cfg(unix)]
        (
            "outside",
            Box::new(|sub: &Path| {
                fs::remove_dir_all(sub).unwrap();
                std::os::unix::fs::symlink(outside.path(), sub).unwrap();
            }),
        ),
    ];
    for (reason, break_it) in cases {
        let sub = tree.join("sub");
        let _ = fs::remove_file(&sub);
        let _ = fs::remove_dir_all(&sub);
        fs::create_dir_all(&sub).unwrap();
        set_cwd(&f.ctx, &id, "sub").unwrap();
        // A healthy cwd is used unchanged and nothing is reported.
        let (got, stored) = cwd_after(&f, &id);
        assert!(got.get("worker_cwd_reset").is_none(), "{got}");
        assert_eq!(stored, "sub");
        break_it(&sub);
        let (got, stored) = cwd_after(&f, &id);
        assert_eq!(
            got["worker_cwd_reset"],
            json!({"previous": "sub", "reason": reason}),
            "{got}"
        );
        assert_eq!(stored, ".", "{reason}: the stored cwd was not reset");
        let (got, _) = cwd_after(&f, &id);
        assert!(
            got.get("worker_cwd_reset").is_none(),
            "reported twice: {got}"
        );
    }
    // Exec through the worker runs at the root, never outside it.
    #[cfg(unix)]
    {
        let sub = tree.join("sub");
        let _ = fs::remove_file(&sub);
        let _ = fs::remove_dir_all(&sub);
        fs::create_dir_all(&sub).unwrap();
        set_cwd(&f.ctx, &id, "sub").unwrap();
        fs::remove_dir_all(&sub).unwrap();
        std::os::unix::fs::symlink(outside.path(), &sub).unwrap();
        let run = call_tool(
            &f.ctx,
            "exec_command",
            &with_worker(&id, json!({"cmd":"pwd -P","yield_time_ms":5000})),
        );
        assert_eq!(run["worker_cwd_reset"]["reason"], "outside", "{run}");
        let text = run.to_string();
        let canonical_tree = fs::canonicalize(&tree).unwrap();
        assert!(
            text.contains(canonical_tree.to_str().unwrap()),
            "exec did not run at the worktree root: {run}"
        );
        assert!(
            !text.contains(fs::canonicalize(outside.path()).unwrap().to_str().unwrap()),
            "{run}"
        );
    }
}

/// Windows: a directory junction out of the worktree resets like a symlink.
/// Compile-checked by the win-gnu cross build; it runs only on a Windows host.
#[cfg(windows)]
#[test]
fn a_worker_cwd_junction_out_of_the_worktree_resets_to_the_root() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    let id = worker.worker_id.as_str().to_owned();
    let tree = worker_tree(&f.ctx, &worker);
    let outside = tempfile::tempdir().unwrap();
    let sub = tree.join("sub");
    fs::create_dir_all(&sub).unwrap();
    set_cwd(&f.ctx, &id, "sub").unwrap();
    fs::remove_dir(&sub).unwrap();
    let made = Command::new("cmd")
        .args(["/C", "mklink", "/J"])
        .arg(&sub)
        .arg(outside.path())
        .output()
        .unwrap();
    assert!(made.status.success(), "{made:?}");
    let (got, stored) = cwd_after(&f, &id);
    assert_eq!(got["worker_cwd_reset"]["reason"], "outside", "{got}");
    assert_eq!(stored, ".");
}

/// A1 C2-ad (N2, SPEC-A1 v5 §1.7, T17): eight legacy chat-v1 trees alone fill
/// the slots: spawn and create return CAPACITY{legacy_slots:8, hint}; nothing is
/// deleted automatically; after a local owner cleanup of one, spawn succeeds.
#[test]
fn eight_legacy_trees_return_capacity_legacy_slots_until_one_is_cleaned_locally() {
    use crate::commands::{legacy_cleanup, native_owner::OwnerApproval};
    use crate::harness::worktree::WorktreeManager;
    let f = Fixture::new();
    let ws = f.ctx.host.workspace_id.clone();
    let legacy_root = f.ctx.host.store_root.join("chat-v1").join("ab".repeat(32));
    fs::create_dir_all(&legacy_root).unwrap();
    let legacy = WorktreeManager::new(f.root.path(), &legacy_root, &ws).unwrap();
    let ids: Vec<String> = (0..8)
        .map(|_| legacy.create_detached().unwrap().id)
        .collect();
    let details = json!({"legacy_slots": 8, "hint": "local_cleanup"});
    for n in 0..2 {
        let spawned = subagent(
            &f.ctx,
            "subagent_spawn",
            json!({"request_id": format!("cap{n}")}),
        );
        assert_eq!(spawned["error"]["code"], "CAPACITY", "{spawned}");
        assert_eq!(spawned["error"]["details"], details, "{spawned}");
        let created = call_tool(&f.ctx, "worktree_create", &json!({}));
        assert_eq!(created["error"]["code"], "CAPACITY", "{created}");
        assert_eq!(created["error"]["details"], details, "{created}");
    }
    assert_eq!(legacy.list().unwrap().len(), 8, "no automatic deletion");
    let main = WorktreeManager::new(f.root.path(), &f.ctx.host.store_root, &ws).unwrap();
    let digest = legacy_cleanup::preview_for(&main).unwrap()["digest"]
        .as_str()
        .unwrap()
        .to_owned();
    let approval = OwnerApproval::for_test(
        legacy_cleanup::SCOPE,
        &legacy_cleanup::approval_digest(&digest, &ids[..1]),
    );
    let out = legacy_cleanup::apply_approved(&main, &approval, &ids[..1], &digest);
    assert!(out.is_ok(), "{out:?}");
    let out = out.unwrap();
    assert_eq!(out.len(), 1);
    let spawned = subagent(&f.ctx, "subagent_spawn", json!({"request_id": "cap-after"}));
    assert_eq!(spawned["ok"], true, "{spawned}");
}
