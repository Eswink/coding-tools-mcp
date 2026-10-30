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
