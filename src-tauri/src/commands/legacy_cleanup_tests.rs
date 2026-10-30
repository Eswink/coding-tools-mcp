//! A1 C2-ad (NB-i, SPEC-A1 v5.1 §1.7): only a native-owner approval for scope
//! `legacy_cleanup` and this exact list digest applies a cleanup; the remote
//! (MCP) surface has no route to it.
use super::*;
use crate::tools::{call_tool, ToolContext};
use std::{fs, process::Command};

fn git(dir: &Path, args: &[&str]) {
    let output = Command::new("git")
        .current_dir(dir)
        .args(args)
        .output()
        .unwrap();
    assert!(output.status.success(), "git {args:?}: {output:?}");
}

#[test]
fn remote_callers_and_foreign_approvals_cannot_trigger_legacy_cleanup() {
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
    let ws = ctx.host.workspace_id.clone();
    let legacy_root = ctx.host.store_root.join("chat-v1").join("ab".repeat(32));
    fs::create_dir_all(&legacy_root).unwrap();
    let legacy = WorktreeManager::new(root.path(), &legacy_root, &ws).unwrap();
    let id = legacy.create_detached().unwrap().id;
    let tree = legacy_root.join("worktrees-v1").join(&ws).join(&id);

    // 1. No MCP tool exposes legacy cleanup; an unknown name is refused.
    for tool in crate::tools::registry::list_tools() {
        let name = tool["name"].as_str().unwrap_or_default();
        assert!(
            !name.contains("legacy") && !name.contains("cleanup"),
            "{name}"
        );
    }
    for name in [
        "legacy_cleanup",
        "apply_legacy_cleanup",
        "preview_legacy_cleanup",
    ] {
        let out = call_tool(&ctx, name, &json!({"ids":[id],"digest":"0".repeat(64)}));
        assert_ne!(out["ok"], true, "{name}: {out}");
    }
    // 2. The remote worktree tool still refuses legacy trees.
    let out = call_tool(&ctx, "worktree_remove", &json!({"id": id}));
    assert_eq!(out["error"]["code"], "LEGACY_WORKTREE", "{out}");
    assert!(tree.join("fixture.txt").is_file());

    // 3. Approvals for another scope or another digest are refused.
    let main = WorktreeManager::new(root.path(), &ctx.host.store_root, &ws).unwrap();
    let preview = preview_for(&main).unwrap();
    let digest = preview["digest"].as_str().unwrap().to_owned();
    assert_eq!(preview["native_dialog_required"], true);
    assert_eq!(preview["candidates"][0]["id"], id.as_str());
    assert!(preview
        .to_string()
        .find(legacy_root.to_str().unwrap())
        .is_none());
    let ids = vec![id.clone()];
    for approval in [
        OwnerApproval::for_test("hooks", &digest),
        OwnerApproval::for_test(SCOPE, &"0".repeat(64)),
    ] {
        assert_eq!(
            apply_approved(&main, &approval, &ids, &digest).map(|_| ()),
            Err("OWNER_CONFIRMATION_REQUIRED")
        );
        assert!(tree.join("fixture.txt").is_file());
    }
    // 4. The native owner approval for this digest applies it.
    let out = apply_approved(
        &main,
        &OwnerApproval::for_test(SCOPE, &digest),
        &ids,
        &digest,
    )
    .unwrap();
    assert_eq!(out[0].state, crate::harness::worktree::LegacyState::Removed);
    assert!(!tree.exists());
}
