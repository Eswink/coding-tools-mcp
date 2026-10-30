//! A1 C5 (SPEC-A1 v5.2 §2.2, §5): collect, integrate, rollback and the journal.
use super::*;

fn write(root: &Path, path: &str, body: &[u8]) {
    let file = root.join(path);
    fs::create_dir_all(file.parent().unwrap()).unwrap();
    fs::write(file, body).unwrap();
}
fn collect(ctx: &ToolContext, id: &str, extra: Value) -> Value {
    let mut args = json!({"worker_id": id});
    for (k, v) in extra.as_object().unwrap() {
        args[k] = v.clone();
    }
    subagent(ctx, "subagent_collect", args)
}
/// Every chunk of the current diff, following next_cursor; returns the bytes.
fn collect_all(ctx: &ToolContext, id: &str, max_bytes: u64) -> (Vec<u8>, Value) {
    let first = collect(ctx, id, json!({"max_bytes": max_bytes}));
    assert_eq!(first["ok"], true, "{first}");
    let mut bytes = Vec::new();
    let mut page = first.clone();
    loop {
        let chunk = page["chunk"].as_str().unwrap();
        match page["encoding"].as_str().unwrap() {
            "utf-8" => bytes.extend_from_slice(chunk.as_bytes()),
            "base64" => {
                use base64::Engine;
                bytes.extend(
                    base64::engine::general_purpose::STANDARD
                        .decode(chunk)
                        .unwrap(),
                )
            }
            other => panic!("{other}"),
        }
        assert!(chunk.len() as u64 <= max_bytes, "{page}");
        assert_eq!(page["diff_sha256"], first["diff_sha256"]);
        let Some(cursor) = page["next_cursor"].as_str() else {
            break;
        };
        page = collect(ctx, id, json!({"max_bytes": max_bytes, "cursor": cursor}));
        assert_eq!(page["ok"], true, "{page}");
        assert!(page.get("files").is_none(), "{page}");
    }
    assert_eq!(bytes.len() as u64, first["total_bytes"].as_u64().unwrap());
    (bytes, first)
}
fn statuses(page: &Value) -> Vec<(String, String)> {
    page["files"]
        .as_array()
        .unwrap()
        .iter()
        .map(|f| {
            (
                f["path"].as_str().unwrap().to_owned(),
                f["reason"]
                    .as_str()
                    .unwrap_or(f["status"].as_str().unwrap())
                    .to_owned(),
            )
        })
        .collect()
}

#[test]
fn collect_pages_the_worker_diff_with_a_stateless_cursor() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    let clean = collect(&f.ctx, id, json!({}));
    assert_eq!(clean["ok"], true, "{clean}");
    assert_eq!(clean["total_bytes"], 0, "{clean}");
    assert_eq!(clean["files"], json!([]), "{clean}");
    assert!(clean.get("next_cursor").is_none(), "{clean}");

    fs::write(tree.join("fixture.txt"), "changed ünïcode\n".repeat(60)).unwrap();
    write(&tree, "src/new.rs", b"fn main() {}\n");
    let (patch, first) = collect_all(&f.ctx, id, 256);
    let text = String::from_utf8(patch).unwrap();
    assert!(
        text.contains("diff --git a/fixture.txt b/fixture.txt"),
        "{text}"
    );
    assert!(text.contains("+fn main() {}"), "{text}");
    assert!(first["total_bytes"].as_u64().unwrap() > 256, "{first}");
    assert_eq!(
        statuses(&first),
        [
            ("fixture.txt".to_owned(), "modified".to_owned()),
            ("src/new.rs".to_owned(), "added".to_owned())
        ]
    );
    // The cursor survives a reconnect: the same cursor reads the same chunk.
    let cursor = first["next_cursor"].as_str().unwrap();
    let a = collect(&f.ctx, id, json!({"max_bytes": 256, "cursor": cursor}));
    let b = collect(&f.ctx, id, json!({"max_bytes": 256, "cursor": cursor}));
    assert_eq!(a, b);
    // Any worker change invalidates outstanding cursors.
    write(&tree, "src/new.rs", b"fn main() { changed(); }\n");
    let stale = collect(&f.ctx, id, json!({"max_bytes": 256, "cursor": cursor}));
    assert_eq!(code(&stale), "CURSOR_STALE", "{stale}");
    let again = collect(&f.ctx, id, json!({}));
    assert_ne!(again["diff_sha256"], first["diff_sha256"], "{again}");
    // A cursor issued for another worker is stale, never a cross-worker read.
    let other = spawn_ok(&f.ctx, "c2", "w2");
    let foreign = collect(
        &f.ctx,
        other.worker_id.as_str(),
        json!({"cursor": again["next_cursor"].as_str().unwrap_or(cursor)}),
    );
    assert_eq!(code(&foreign), "CURSOR_STALE", "{foreign}");
    for bad in [json!({"cursor": 7}), json!({"cursor": "x", "extra": 1})] {
        let out = collect(&f.ctx, id, bad.clone());
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{bad}: {out}");
    }
}

#[test]
fn collect_withholds_exactly_the_spec_policy_list() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let withheld = [
        ".env",
        ".env.local",
        "config/.env.production",
        "id_rsa",
        "keys/id_ed25519",
        "server.pem",
        "tls/server.key",
        ".npmrc",
        ".netrc",
        ".git-credentials",
        "cert.p12",
        "cert.pfx",
        "kubeconfig",
        ".envrc",
        "id_rsa_old",
        "keys/id_ed25519-work",
        ".ssh/config",
        ".github/workflows/x.yml",
        "node_modules/x/index.js",
        "target/debug/x",
    ];
    let allowed = [
        ".gitignore",
        ".eslintrc.json",
        ".editorconfig",
        ".env.example",
        "id_rsa.pub",
        "id_ed25519_work.pub",
        "src/key_manager.rs",
        "docs/keys.md",
    ];
    for path in withheld.iter().chain(allowed.iter()) {
        write(&tree, path, format!("SECRET-{path}\n").as_bytes());
    }
    let (patch, first) = collect_all(&f.ctx, worker.worker_id.as_str(), 4096);
    let text = String::from_utf8(patch).unwrap();
    let mut seen = statuses(&first);
    seen.sort();
    for path in withheld {
        assert!(!text.contains(&format!("SECRET-{path}\n")), "{path} leaked");
        assert!(
            seen.iter().any(|(p, r)| p == path && r != "added"),
            "{path} not listed as withheld: {seen:?}"
        );
    }
    for path in allowed {
        assert!(text.contains(&format!("+SECRET-{path}")), "{path} missing");
        assert!(
            seen.contains(&(path.to_owned(), "added".to_owned())),
            "{path}"
        );
    }
    assert!(first["files_total"].as_u64().unwrap() >= 28, "{first}");
}

#[cfg(unix)]
#[test]
fn collect_lists_symlinks_as_withheld_and_never_follows_them() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let outside = tempfile::tempdir().unwrap();
    fs::write(outside.path().join("secret"), "OUTSIDE-SECRET\n").unwrap();
    std::os::unix::fs::symlink(outside.path().join("secret"), tree.join("link")).unwrap();
    let (patch, first) = collect_all(&f.ctx, worker.worker_id.as_str(), 4096);
    assert!(!String::from_utf8_lossy(&patch).contains("OUTSIDE-SECRET"));
    assert_eq!(
        statuses(&first),
        [("link".to_owned(), "symlink".to_owned())],
        "{first}"
    );
}

#[test]
fn collect_returns_binary_patches_as_base64_chunks() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let blob: Vec<u8> = (0..2048u32).map(|i| (i * 131 % 251) as u8).collect();
    write(&tree, "bin/data.bin", &blob);
    fs::write(tree.join("fixture.txt"), [0xff, 0xfe, 0x00, 0x80]).unwrap();
    let (patch, first) = collect_all(&f.ctx, worker.worker_id.as_str(), 300);
    assert!(String::from_utf8_lossy(&patch).contains("GIT binary patch"));
    assert_eq!(first["files"].as_array().unwrap().len(), 2, "{first}");
}

#[test]
fn collect_never_reads_repository_or_worktree_git_config() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let tree = worker_tree(&f.ctx, &worker);
    let marker = f.root.path().join("marker-ran");
    let hooks = f.root.path().join("hooks");
    fs::create_dir_all(&hooks).unwrap();
    let touch = format!("touch {}", marker.display());
    for hook in ["post-index-change", "reference-transaction", "pre-commit"] {
        let script = hooks.join(hook);
        fs::write(&script, format!("#!/bin/sh\n{touch}\n")).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&script, fs::Permissions::from_mode(0o755)).unwrap();
        }
    }
    let gitdir = f.root.path().join(".git");
    let private = gitdir
        .join("worktrees")
        .join(worker.worktree_id.as_deref().unwrap());
    let hostile = format!(
        "[core]\n\tfsmonitor = {touch}\n\thooksPath = {}\n\tautocrlf = true\n[filter \"x\"]\n\tclean = {touch}\n\tsmudge = {touch}\n\tprocess = {touch}\n[diff \"x\"]\n\ttextconv = {touch}\n\tcommand = {touch}\n",
        hooks.display()
    );
    let mut main_config = fs::read_to_string(gitdir.join("config")).unwrap();
    main_config.push_str(&hostile);
    fs::write(gitdir.join("config"), main_config).unwrap();
    fs::write(private.join("config.worktree"), &hostile).unwrap();
    fs::write(tree.join(".gitattributes"), "* filter=x diff=x\n").unwrap();
    fs::write(tree.join("fixture.txt"), "changed\r\n").unwrap();
    let (patch, first) = collect_all(&f.ctx, worker.worker_id.as_str(), 4096);
    assert!(!marker.exists(), "a Git config command ran");
    let text = String::from_utf8(patch).unwrap();
    assert!(text.contains("+changed\r\n"), "{text:?}");
    assert_eq!(first["files"].as_array().unwrap().len(), 2, "{first}");
    // The private gitdir is only read: no index or lock file appears.
    assert!(!private.join("index.lock").exists());
}

#[test]
fn collect_follows_ownership_and_state() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let foreign = remote(&f.ctx, "other-session");
    let direct = scoped(&foreign, |c| integrate::collect(c, id, 4096, None));
    assert_eq!(direct.unwrap_err().code(), "WORKER_NOT_OWNED");
    let unknown = collect(&f.ctx, &"0".repeat(32), json!({}));
    assert_eq!(code(&unknown), "WORKER_NOT_OWNED", "{unknown}");
    assert_eq!(collect(&f.ctx, id, json!({}))["ok"], true);
    let cancelled = subagent(&f.ctx, "subagent_cancel", json!({"worker_id": id}));
    assert_eq!(cancelled["ok"], true, "{cancelled}");
    assert_eq!(collect(&f.ctx, id, json!({}))["ok"], true);
    let discarded = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(discarded["ok"], true, "{discarded}");
    let out = collect(&f.ctx, id, json!({}));
    assert_eq!(code(&out), "WORKER_STATE", "{out}");
}

#[test]
fn spawn_records_an_advisory_main_fingerprint() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let print = worker.main_fingerprint.clone().expect("fingerprint");
    let manager = manager(&f.ctx).unwrap();
    assert_eq!(manager.main_fingerprint().unwrap(), print);
    fs::write(f.root.path().join("fixture.txt"), "main edit\n").unwrap();
    assert_ne!(manager.main_fingerprint().unwrap(), print);
}

// --- C5-3: the integration journal (§5.3) -----------------------------------
use crate::commands::native_owner::OwnerApproval;
use crate::harness::worktree::{ChangeKind, FileChange};
use journal::{check_size, Journal, JournalDoc, JournalEntry, JournalState, MAX_PREIMAGE_TOTAL};

fn modified(path: &str, size: usize) -> FileChange {
    let pre: Vec<u8> = (0..size).map(|i| (i * 7919 % 251) as u8).collect();
    FileChange {
        path: path.into(),
        kind: ChangeKind::Modified,
        pre: Some((pre, false)),
        post: Some((b"post\n".to_vec(), true)),
    }
}
fn prepared(journal: &Journal, changes: &[FileChange]) -> JournalDoc {
    JournalDoc {
        state: JournalState::Prepared,
        integration_id: Some("a".repeat(32)),
        entries: changes.iter().map(JournalEntry::from_change).collect(),
        ..journal.doc().clone()
    }
}

#[test]
fn journal_holds_exactly_512_kib_of_preimages_as_base64_and_round_trips() {
    let f = Fixture::new();
    let total = MAX_PREIMAGE_TOTAL as usize;
    let added = FileChange {
        path: "new.txt".into(),
        kind: ChangeKind::Added,
        pre: None,
        post: Some((vec![1; 4096], false)),
    };
    let single = vec![modified("one.bin", total), added.clone()];
    let multi: Vec<FileChange> = (0..8)
        .map(|i| modified(&format!("dir/f{i}.bin"), total / 8))
        .chain([added])
        .collect();
    for changes in [single, multi] {
        let mut journal = Journal::open(&f.ctx.host).unwrap();
        let epoch = journal.doc().journal_epoch.clone();
        let doc = prepared(&journal, &changes);
        check_size(&changes, &doc).unwrap();
        let raw = serde_json::to_string(&doc).unwrap();
        assert!(raw.len() < 1_048_576, "{}", raw.len());
        let value: Value = serde_json::from_str(&raw).unwrap();
        assert!(
            value["entries"][0]["pre"]["base64"].is_string(),
            "not a string"
        );
        journal.write(doc.clone()).unwrap();
        drop(journal);
        let reopened = Journal::open(&f.ctx.host).unwrap();
        assert_eq!(reopened.doc(), &doc);
        assert_eq!(reopened.doc().journal_epoch, epoch);
        for (entry, change) in reopened.doc().entries.iter().zip(&changes) {
            assert_eq!(
                entry.pre.as_ref().map(|p| p.bytes().unwrap()),
                change.pre.as_ref().map(|(b, _)| b.clone())
            );
        }
        let mut reopened = reopened;
        let idle = reopened.doc().idle();
        reopened.write(idle).unwrap();
        assert!(reopened.doc().entries.is_empty());
    }
}

#[test]
fn journal_rejects_524289_preimage_bytes_before_writing() {
    let f = Fixture::new();
    let mut journal = Journal::open(&f.ctx.host).unwrap();
    let before = journal.doc().clone();
    for changes in [
        vec![modified("one.bin", MAX_PREIMAGE_TOTAL as usize + 1)],
        vec![
            modified("a.bin", MAX_PREIMAGE_TOTAL as usize / 2),
            modified("b.bin", MAX_PREIMAGE_TOTAL as usize / 2 + 1),
        ],
    ] {
        let doc = prepared(&journal, &changes);
        let error = check_size(&changes, &doc).unwrap_err();
        assert_eq!(error.code(), "INTEGRATE_UNSUPPORTED");
        assert_eq!(
            error.details().unwrap(),
            &json!({"reason": "preimage_too_large", "total_bytes": 524_289})
        );
        let value = error_value(&error);
        assert_eq!(value["error"]["details"]["reason"], "preimage_too_large");
    }
    journal.refresh(&f.ctx.host).unwrap();
    assert_eq!(journal.doc(), &before);
}

#[test]
fn journal_epoch_is_stable_until_the_document_is_rebuilt_and_corruption_fails_closed() {
    let f = Fixture::new();
    assert!(Journal::open_existing(&f.ctx.host).unwrap().is_none());
    let mut journal = Journal::open(&f.ctx.host).unwrap();
    let epoch = journal.doc().journal_epoch.clone();
    assert_eq!(epoch.len(), 32);
    assert!(epoch.bytes().all(|c| c.is_ascii_hexdigit()));
    let file = namespace(&f.ctx.host).join("integration-journal/auth.json");
    assert!(file.is_file());
    // An external delete is a reset: a new epoch, never the old pre-images.
    let doc = prepared(&journal, &[modified("x", 4)]);
    journal.write(doc).unwrap();
    fs::remove_file(&file).unwrap();
    assert!(journal.missing());
    journal.refresh(&f.ctx.host).unwrap();
    assert_ne!(journal.doc().journal_epoch, epoch);
    assert_eq!(journal.doc().state, JournalState::None);
    // A write with a stale epoch is refused.
    let stale = JournalDoc {
        journal_epoch: epoch,
        ..journal.doc().clone()
    };
    assert_eq!(
        journal.write(stale).unwrap_err().code(),
        "STORE_UNAVAILABLE"
    );
    drop(journal);
    fs::write(&file, "corrupt").unwrap();
    assert_eq!(
        Journal::open(&f.ctx.host).err().unwrap().code(),
        "STORE_UNAVAILABLE"
    );
    assert_eq!(
        Journal::open_existing(&f.ctx.host).err().unwrap().code(),
        "STORE_UNAVAILABLE"
    );
    assert_eq!(fs::read_to_string(&file).unwrap(), "corrupt");
}

// ---- C5-4: integrate request, pending list, native apply (§5, NB-b) ----

fn integrate(ctx: &ToolContext, id: &str, sha: &str, request_id: &str) -> Value {
    subagent(
        ctx,
        "subagent_integrate",
        json!({"worker_id": id, "diff_sha256": sha, "request_id": request_id}),
    )
}
fn sha_of(ctx: &ToolContext, id: &str) -> String {
    let page = collect(ctx, id, json!({}));
    assert_eq!(page["ok"], true, "{page}");
    page["diff_sha256"].as_str().unwrap().to_owned()
}
fn record_of(ctx: &ToolContext, id: &str) -> WorkerRecord {
    let (_, store) = open(ctx).unwrap();
    let inner = store.lock().unwrap();
    inner
        .doc
        .workers
        .iter()
        .find(|w| w.worker_id.as_str() == id)
        .unwrap()
        .clone()
}
fn journal_of(ctx: &ToolContext) -> JournalDoc {
    let (_, store) = open(ctx).unwrap();
    let mut inner = store.lock().unwrap();
    integration::journal_rw(&mut inner, &ctx.host)
        .unwrap()
        .doc()
        .clone()
}
fn as_value(out: Result<Value, WorkerError>) -> Value {
    out.unwrap_or_else(|e| error_value(&e))
}
/// The native card: prepare, the owner approves exactly this digest, apply.
fn confirm(ctx: &ToolContext, integration_id: &str) -> Value {
    let card = scoped(ctx, |c| integration::prepare(c, integration_id))
        .unwrap_or_else(|e| panic!("prepare: {e:?}"));
    let approval = OwnerApproval::for_test(integration::INTEGRATE_SCOPE, &card.digest);
    as_value(scoped(ctx, |c| integration::apply(c, &card, &approval)))
}
fn ops(record: &WorkerRecord) -> Vec<String> {
    record.ops.iter().map(|o| o.tool.clone()).collect()
}
/// A main repository with a file to delete and one to make executable.
fn rich() -> Fixture {
    let f = Fixture::new();
    let root = f.root.path();
    fs::write(root.join("gone.txt"), "bye\n").unwrap();
    fs::write(root.join("tool.sh"), "echo hi\n").unwrap();
    git(root, &["add", "."]);
    git(root, &["commit", "-qm", "more"]);
    f
}

#[test]
fn integrate_writes_main_only_after_the_native_confirm_and_never_stages() {
    let f = rich();
    let root = f.root.path();
    let head = f.head();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    fs::write(tree.join("fixture.txt"), "worker\n").unwrap();
    write(&tree, "src/new/deep.rs", b"fn deep() {}\n");
    fs::remove_file(tree.join("gone.txt")).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let script = tree.join("tool.sh");
        let mut mode = fs::metadata(&script).unwrap().permissions();
        mode.set_mode(mode.mode() | 0o111);
        fs::set_permissions(&script, mode).unwrap();
    }
    let sha = sha_of(&f.ctx, id);

    let out = integrate(&f.ctx, id, &sha, "i1");
    assert_eq!(out["ok"], true, "{out}");
    assert_eq!(out["state"], "integrate_pending", "{out}");
    assert_eq!(out["conflicts"], json!([]), "{out}");
    let iid = out["integration_id"].as_str().unwrap().to_owned();
    // The request alone writes nothing to main.
    assert_eq!(
        fs::read_to_string(root.join("fixture.txt")).unwrap(),
        "original\n"
    );
    assert!(root.join("gone.txt").exists());
    assert!(!root.join("src").exists());
    assert_eq!(record_of(&f.ctx, id).state, WorkerState::IntegratePending);
    let status = subagent(&f.ctx, "subagent_status", json!({"worker_id": id}));
    assert_eq!(
        status["workers"][0]["integration"]["state"], "integrate_pending",
        "{status}"
    );
    // Idempotent replay, conflicting replay, and a second request.
    let again = integrate(&f.ctx, id, &sha, "i1");
    assert_eq!(again["deduplicated"], true, "{again}");
    assert_eq!(again["integration_id"], iid.as_str(), "{again}");
    let clash = integrate(&f.ctx, id, &"0".repeat(64), "i1");
    assert_eq!(code(&clash), "REQUEST_ID_CONFLICT", "{clash}");
    let second = integrate(&f.ctx, id, &sha, "i2");
    assert_eq!(code(&second), "WORKER_STATE", "{second}");
    // Discard while pending is refused.
    let discard = subagent(&f.ctx, "subagent_discard", json!({"worker_id": id}));
    assert_eq!(code(&discard), "WORKER_STATE", "{discard}");
    // The native list sees it, with the digest the card binds.
    let listed = integration::pending(&f.ctx).unwrap();
    assert_eq!(listed.len(), 1, "{listed:?}");
    assert_eq!(listed[0]["integration_id"], iid.as_str());
    assert_eq!(
        listed[0]["digest"],
        integration::digest(&iid, &sha).as_str()
    );

    // An approval for another digest never applies.
    let card = scoped(&f.ctx, |c| integration::prepare(c, &iid)).unwrap();
    assert!(card.title.contains('w'), "{}", card.title);
    assert!(
        card.summary.to_string().contains("src/new/deep.rs"),
        "{}",
        card.summary
    );
    let wrong = OwnerApproval::for_test(integration::INTEGRATE_SCOPE, &"f".repeat(64));
    let refused = as_value(scoped(&f.ctx, |c| integration::apply(c, &card, &wrong)));
    assert_eq!(code(&refused), "OWNER_CONFIRMATION_REQUIRED", "{refused}");
    let other_scope = OwnerApproval::for_test("worker_discard", &card.digest);
    let refused = as_value(scoped(&f.ctx, |c| {
        integration::apply(c, &card, &other_scope)
    }));
    assert_eq!(code(&refused), "OWNER_CONFIRMATION_REQUIRED", "{refused}");
    assert_eq!(
        fs::read_to_string(root.join("fixture.txt")).unwrap(),
        "original\n"
    );

    let done = confirm(&f.ctx, &iid);
    assert_eq!(done["state"], "integrated", "{done}");
    assert_eq!(done["staged"], false, "{done}");
    assert_eq!(done["files"], 4, "{done}");
    assert_eq!(
        fs::read_to_string(root.join("fixture.txt")).unwrap(),
        "worker\n"
    );
    assert_eq!(
        fs::read_to_string(root.join("src/new/deep.rs")).unwrap(),
        "fn deep() {}\n"
    );
    assert!(!root.join("gone.txt").exists());
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mode = fs::metadata(root.join("tool.sh"))
            .unwrap()
            .permissions()
            .mode();
        assert_eq!(mode & 0o111, 0o111, "{mode:o}");
    }
    // Nothing staged, nothing committed: the owner reviews in Git.
    assert_eq!(f.head(), head);
    assert_eq!(git(root, &["diff", "--cached", "--name-only"]), "");
    let unstaged = git(root, &["status", "--porcelain"]);
    for path in ["fixture.txt", "gone.txt", "src/"] {
        assert!(unstaged.contains(path), "{unstaged}");
    }
    let record = record_of(&f.ctx, id);
    assert_eq!(record.state, WorkerState::Integrated);
    let last = record.integrations.last().unwrap();
    assert_eq!(last.state.label(), "integrated");
    assert!(last.journal_epoch.is_some());
    assert!(ops(&record).ends_with(&[
        "integrate_requested".to_owned(),
        "integrate_committed".to_owned()
    ]));
    let journal = journal_of(&f.ctx);
    assert_eq!(journal.state, JournalState::Committed);
    assert_eq!(journal.integration_id.as_deref(), Some(iid.as_str()));
    assert_eq!(journal.head_at_commit.as_deref(), Some(head.as_str()));
    assert_eq!(journal.entries.len(), 4);
    let deep = journal
        .entries
        .iter()
        .find(|e| e.path == "src/new/deep.rs")
        .unwrap();
    assert_eq!(deep.created_dirs, ["src", "src/new"]);
    assert!(matches!(deep.kind(), Some(ChangeKind::Added)));
    assert_eq!(Some(journal.journal_epoch.clone()), last.journal_epoch);
    assert!(integration::pending(&f.ctx).unwrap().is_empty());
}

#[test]
fn integrate_refuses_stale_empty_conflicting_and_foreign_requests() {
    let f = rich();
    let root = f.root.path();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    let empty = integrate(&f.ctx, id, &sha_of(&f.ctx, id), "e");
    assert_eq!(code(&empty), "INTEGRATE_UNSUPPORTED", "{empty}");
    assert_eq!(empty["error"]["details"]["reason"], "empty", "{empty}");

    fs::write(tree.join("fixture.txt"), "worker\n").unwrap();
    write(&tree, "added.txt", b"new\n");
    let sha = sha_of(&f.ctx, id);
    write(&tree, "later.txt", b"after collect\n");
    let stale = integrate(&f.ctx, id, &sha, "s");
    assert_eq!(code(&stale), "INTEGRATE_STALE", "{stale}");
    fs::remove_file(tree.join("later.txt")).unwrap();
    assert_eq!(sha_of(&f.ctx, id), sha);

    // Main moved away from the worker's base: three-way conflicts, by path.
    fs::write(root.join("fixture.txt"), "owner edit\n").unwrap();
    fs::write(root.join("added.txt"), "owner too\n").unwrap();
    let clash = integrate(&f.ctx, id, &sha, "c");
    assert_eq!(code(&clash), "INTEGRATE_CONFLICT", "{clash}");
    assert_eq!(clash["error"]["details"]["conflicts_total"], 2, "{clash}");
    assert_eq!(
        clash["error"]["details"]["conflicts"],
        json!([
            {"path": "added.txt", "reason": "exists"},
            {"path": "fixture.txt", "reason": "changed"}
        ]),
        "{clash}"
    );
    assert_eq!(record_of(&f.ctx, id).state, WorkerState::Ready);
    fs::write(root.join("fixture.txt"), "original\n").unwrap();
    fs::remove_file(root.join("added.txt")).unwrap();

    // Another chat session cannot request this worker's integration.
    let foreign = integrate(&remote(&f.ctx, "other"), id, &sha, "x");
    assert_ne!(foreign["ok"], true, "{foreign}");
    assert_eq!(record_of(&f.ctx, id).state, WorkerState::Ready);
    for bad in [
        json!({"worker_id": id, "diff_sha256": "zz", "request_id": "r"}),
        json!({"worker_id": id, "diff_sha256": sha, "request_id": "r", "extra": 1}),
    ] {
        let out = subagent(&f.ctx, "subagent_integrate", bad.clone());
        assert_eq!(code(&out), "INVALID_ARGUMENT", "{bad}: {out}");
    }
    let ok = integrate(&f.ctx, id, &sha, "ok");
    assert_eq!(ok["ok"], true, "{ok}");
}

#[cfg(unix)]
#[test]
fn integrate_refuses_symlinks_as_unsupported() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    std::os::unix::fs::symlink("fixture.txt", tree.join("link")).unwrap();
    let out = integrate(&f.ctx, id, &sha_of(&f.ctx, id), "l");
    assert_eq!(code(&out), "INTEGRATE_UNSUPPORTED", "{out}");
    assert_eq!(out["error"]["details"]["path"], "link", "{out}");
}

#[test]
fn apply_rechecks_main_and_undoes_a_failed_write() {
    let f = rich();
    let root = f.root.path();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    fs::write(tree.join("fixture.txt"), "worker\n").unwrap();
    write(&tree, "a/b/new.txt", b"new\n");
    fs::remove_file(tree.join("gone.txt")).unwrap();
    let sha = sha_of(&f.ctx, id);
    let out = integrate(&f.ctx, id, &sha, "i1");
    let iid = out["integration_id"].as_str().unwrap().to_owned();

    // The owner's main moves while the dialog is open: nothing is written.
    let card = scoped(&f.ctx, |c| integration::prepare(c, &iid)).unwrap();
    fs::write(root.join("gone.txt"), "owner edit\n").unwrap();
    let approval = OwnerApproval::for_test(integration::INTEGRATE_SCOPE, &card.digest);
    let moved = as_value(scoped(&f.ctx, |c| integration::apply(c, &card, &approval)));
    assert_eq!(code(&moved), "INTEGRATE_CONFLICT", "{moved}");
    assert_eq!(
        fs::read_to_string(root.join("fixture.txt")).unwrap(),
        "original\n"
    );
    assert_eq!(record_of(&f.ctx, id).state, WorkerState::IntegratePending);
    fs::write(root.join("gone.txt"), "bye\n").unwrap();

    // The third write fails: the first two are undone, created dirs removed.
    mainfs::hooks::fail_at(2);
    let failed = confirm(&f.ctx, &iid);
    assert_eq!(code(&failed), "INTEGRATE_FAILED", "{failed}");
    assert_eq!(failed["error"]["details"]["restored"], true, "{failed}");
    assert_eq!(
        fs::read_to_string(root.join("fixture.txt")).unwrap(),
        "original\n"
    );
    assert_eq!(fs::read_to_string(root.join("gone.txt")).unwrap(), "bye\n");
    assert!(!root.join("a").exists());
    assert_eq!(git(root, &["status", "--porcelain"]), "");
    let record = record_of(&f.ctx, id);
    assert_eq!(record.state, WorkerState::Ready);
    assert_eq!(record.integrations.last().unwrap().state.label(), "failed");
    assert_eq!(
        ops(&record).last().map(String::as_str),
        Some("integrate_failed")
    );
    assert_eq!(journal_of(&f.ctx).state, JournalState::None);
    // The closed request cannot be confirmed again; a new one can.
    let closed = scoped(&f.ctx, |c| integration::prepare(c, &iid)).map(|_| ());
    assert_eq!(closed.unwrap_err().code(), "WORKER_STATE");
    let retry = integrate(&f.ctx, id, &sha, "i2");
    let done = confirm(&f.ctx, retry["integration_id"].as_str().unwrap());
    assert_eq!(done["state"], "integrated", "{done}");
    assert_eq!(
        fs::read_to_string(root.join("a/b/new.txt")).unwrap(),
        "new\n"
    );
}

#[test]
fn reject_and_expiry_restore_the_prior_state() {
    let f = Fixture::new();
    let worker = spawn_ok(&f.ctx, "c1", "w");
    let id = worker.worker_id.as_str();
    let tree = worker_tree(&f.ctx, &worker);
    fs::write(tree.join("fixture.txt"), "worker\n").unwrap();
    let cancelled = subagent(&f.ctx, "subagent_cancel", json!({"worker_id": id}));
    assert_eq!(cancelled["ok"], true, "{cancelled}");
    let sha = sha_of(&f.ctx, id);
    let out = integrate(&f.ctx, id, &sha, "i1");
    let iid = out["integration_id"].as_str().unwrap().to_owned();
    let rejected = scoped(&f.ctx, |c| integration::reject(c, &iid)).unwrap();
    assert_eq!(rejected["state"], "rejected");
    let record = record_of(&f.ctx, id);
    assert_eq!(record.state, WorkerState::Cancelled);
    assert_eq!(
        ops(&record).last().map(String::as_str),
        Some("integrate_rejected")
    );
    assert_eq!(
        fs::read_to_string(f.root.path().join("fixture.txt")).unwrap(),
        "original\n"
    );

    let out = integrate(&f.ctx, id, &sha, "i2");
    let iid = out["integration_id"].as_str().unwrap().to_owned();
    {
        let (_, store) = open(&f.ctx).unwrap();
        let mut inner = store.lock().unwrap();
        inner
            .apply(|doc| {
                let w = doc
                    .workers
                    .iter_mut()
                    .find(|w| w.worker_id.as_str() == id)
                    .unwrap();
                w.integrations.last_mut().unwrap().expires_at = 1;
                Ok(())
            })
            .unwrap();
    }
    // Status reports the expiry read-only; the store still says pending.
    let status = subagent(&f.ctx, "subagent_status", json!({"worker_id": id}));
    assert_eq!(
        status["workers"][0]["integration"]["state"], "expired",
        "{status}"
    );
    assert_eq!(record_of(&f.ctx, id).state, WorkerState::IntegratePending);
    // The native list closes it and the worker is cancelled again.
    assert!(integration::pending(&f.ctx).unwrap().is_empty());
    let record = record_of(&f.ctx, id);
    assert_eq!(record.state, WorkerState::Cancelled);
    assert_eq!(
        ops(&record).last().map(String::as_str),
        Some("integrate_expired")
    );
    let late = scoped(&f.ctx, |c| integration::prepare(c, &iid)).map(|_| ());
    assert_eq!(late.unwrap_err().code(), "WORKER_STATE");
}

#[test]
fn a_new_integrate_marks_the_committed_one_superseded() {
    // NB-b: the journal only ever holds the latest integration.
    let f = Fixture::new();
    let root = f.root.path();
    let a = spawn_ok(&f.ctx, "c1", "a");
    let b = spawn_ok(&f.ctx, "c2", "b");
    write(&worker_tree(&f.ctx, &a), "a.txt", b"a\n");
    write(&worker_tree(&f.ctx, &b), "b.txt", b"b\n");
    let first = integrate(
        &f.ctx,
        a.worker_id.as_str(),
        &sha_of(&f.ctx, a.worker_id.as_str()),
        "x",
    );
    let first_id = first["integration_id"].as_str().unwrap().to_owned();
    assert_eq!(confirm(&f.ctx, &first_id)["state"], "integrated");
    let second = integrate(
        &f.ctx,
        b.worker_id.as_str(),
        &sha_of(&f.ctx, b.worker_id.as_str()),
        "y",
    );
    let second_id = second["integration_id"].as_str().unwrap().to_owned();
    assert_eq!(confirm(&f.ctx, &second_id)["state"], "integrated");
    assert!(root.join("a.txt").exists() && root.join("b.txt").exists());
    let old = record_of(&f.ctx, a.worker_id.as_str());
    let old = old.integrations.last().unwrap();
    assert_eq!(old.closed_reason.as_deref(), Some("superseded"));
    let journal = journal_of(&f.ctx);
    assert_eq!(journal.integration_id.as_deref(), Some(second_id.as_str()));
    assert_eq!(journal.state, JournalState::Committed);
}
