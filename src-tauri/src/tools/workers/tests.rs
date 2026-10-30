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
    let cancelled = cancel(&f.ctx, id).unwrap();
    assert_eq!(cancelled.state, WorkerState::Cancelled);
    assert_eq!(
        cancel(&f.ctx, id).unwrap(),
        cancelled,
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
fn public_schemas_expose_no_worker_surface_but_worker_id_routes_to_the_worker() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "req", "w");
    for tool in crate::tools::list_tools() {
        let text = tool.to_string();
        assert!(!text.contains("worker_id"), "{text}");
        assert!(!tool["name"].as_str().unwrap().starts_with("subagent_"));
        assert!(!tool["name"].as_str().unwrap().starts_with("worker_"));
    }
    // C2 (v4 §7.4): schemas and the catalog stay unchanged until C6, but dispatch
    // already re-roots a supported call carrying worker_id into the worker worktree.
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
    let err = scoped(&f.ctx, |c| spawn(c, "req", "w")).unwrap_err();
    assert_eq!(err.code(), "STORE_UNAVAILABLE");
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
    // Known C2 gap (SPEC-A1 v4 §4.2, closed by C4 `LinuxSandbox::for_worktree`):
    // the Linux git runner's Landlock root is the worktree, so the linked
    // worktree's gitdir under the main `.git/worktrees/` is unreadable. The
    // call is still routed into the worker worktree, never the main root.
    #[cfg(target_os = "linux")]
    {
        assert_eq!(status["is_repo"], false, "{status}");
        assert!(status.to_string().contains(".git/worktrees/"), "{status}");
    }
    #[cfg(not(target_os = "linux"))]
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
    for tool in [
        "worktree_list",
        "history_session_read",
        "server_info",
        "change_summary",
        "list_exec_tasks",
    ] {
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
    assert!(!WORKER_TOOLS.contains(&"change_summary"));
    assert_eq!(WORKER_TOOLS.len(), 20);
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
