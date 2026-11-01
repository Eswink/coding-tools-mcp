use super::*;
use crate::tools::{call_tool, ToolContext};
use serde_json::json;
use std::{fs, os::unix::fs::PermissionsExt, process::Command};

fn git(root: &Path, args: &[&str]) {
    let status = Command::new("/usr/bin/git")
        .arg("-C")
        .arg(root)
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .args(args)
        .output()
        .unwrap();
    assert!(
        status.status.success(),
        "fixture: {}",
        String::from_utf8_lossy(&status.stderr)
    );
}
fn repository(root: &Path) {
    fs::create_dir_all(root).unwrap();
    git(root, &["init", "-q"]);
    git(root, &["config", "user.name", "Synthetic Fixture"]);
    git(root, &["config", "user.email", "fixture@example.invalid"]);
    fs::write(root.join("input.txt"), "before\n").unwrap();
    git(root, &["add", "input.txt"]);
    git(root, &["commit", "-qm", "fixture"]);
}
fn hook(root: &Path, marker: &Path) -> String {
    let path = root.join("untrusted-helper.sh");
    fs::write(
        &path,
        format!(
            "#!/bin/sh\nprintf EXTERNAL_SIDE_EFFECT > '{}'\nprintf 'rewritten\\n'\n",
            marker.display()
        ),
    )
    .unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
    path.to_str().unwrap().into()
}
#[test]
fn git_diff_does_not_execute_repository_external_diff() {
    let fixture = tempfile::tempdir().unwrap();
    let root = fixture.path().join("workspace");
    repository(&root);
    let marker = fixture.path().join("outside-marker");
    let script = hook(&root, &marker);
    git(&root, &["config", "diff.external", &script]);
    fs::write(root.join("input.txt"), "after\n").unwrap();
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.clone(), harness.path().into()).unwrap();
    let result = call_tool(&ctx, "git_diff", &json!({}));
    assert_eq!(result["ok"], true, "{result}");
    assert!(
        result["diff"].as_str().unwrap().contains("+after"),
        "{result}"
    );
    assert!(
        !marker.exists(),
        "repository external diff executed outside its workspace"
    );
}
#[test]
fn git_status_does_not_execute_repository_fsmonitor() {
    let fixture = tempfile::tempdir().unwrap();
    let root = fixture.path().join("workspace");
    repository(&root);
    let marker = fixture.path().join("fsmonitor-marker");
    let script = hook(&root, &marker);
    git(&root, &["config", "core.fsmonitor", &script]);
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.clone(), harness.path().into()).unwrap();
    let result = call_tool(&ctx, "git_status", &json!({}));
    assert_eq!(result["is_repo"], true, "{result}");
    assert!(
        !marker.exists(),
        "repository fsmonitor escaped read-only inspection"
    );
}
#[test]
fn git_diff_and_show_do_not_execute_textconv() {
    let fixture = tempfile::tempdir().unwrap();
    let root = fixture.path().join("workspace");
    repository(&root);
    let marker = fixture.path().join("textconv-marker");
    let script = hook(&root, &marker);
    git(&root, &["config", "diff.synthetic.textconv", &script]);
    fs::write(root.join(".gitattributes"), "input.txt diff=synthetic\n").unwrap();
    fs::write(root.join("input.txt"), "after\n").unwrap();
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.clone(), harness.path().into()).unwrap();
    for tool in ["git_diff", "git_show"] {
        let result = call_tool(&ctx, tool, &json!({}));
        assert_eq!(result["ok"], true, "{result}");
        assert!(!marker.exists(), "repository textconv executed: {tool}");
    }
}
#[test]
fn git_directory_redirect_cannot_read_an_external_repository() {
    let fixture = tempfile::tempdir().unwrap();
    let external = fixture.path().join("external");
    repository(&external);
    fs::write(external.join("private.txt"), "SYNTHETIC_PRIVATE_CONTENT").unwrap();
    git(&external, &["add", "private.txt"]);
    git(&external, &["commit", "-qm", "private-fixture"]);
    let root = fixture.path().join("workspace");
    fs::create_dir(&root).unwrap();
    fs::write(
        root.join(".git"),
        format!("gitdir: {}\n", external.join(".git").display()),
    )
    .unwrap();
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(root.clone(), harness.path().into()).unwrap();
    let result = call_tool(&ctx, "git_show", &json!({}));
    assert_ne!(result["is_repo"], true, "{result}");
    assert!(!result.to_string().contains("SYNTHETIC_PRIVATE_CONTENT"));
}
#[test]
fn inspection_rejects_mutating_git_commands_before_spawn() {
    let fixture = tempfile::tempdir().unwrap();
    assert!(run(
        fixture.path(),
        fixture.path(),
        &["init"],
        Duration::from_secs(1),
        GitRoot::Main
    )
    .is_err());
    assert!(!fixture.path().join(".git").exists());
}
#[tokio::test]
async fn inspection_can_be_called_inside_an_async_host_without_nested_runtime() {
    let fixture = tempfile::tempdir().unwrap();
    repository(fixture.path());
    let output = run(
        fixture.path(),
        fixture.path(),
        &["rev-parse", "HEAD"],
        Duration::from_secs(2),
        GitRoot::Main,
    )
    .unwrap();
    assert!(output.status.success());
    assert_eq!(String::from_utf8(output.stdout).unwrap().trim().len(), 40);
}

/// `(main repository, linked worktree)` created by the real `git worktree add`.
fn linked_worktree(fixture: &Path) -> (std::path::PathBuf, std::path::PathBuf) {
    let main = fixture.join("main");
    repository(&main);
    let linked = fixture.join("linked");
    git(
        &main,
        &[
            "worktree",
            "add",
            "-q",
            "--detach",
            linked.to_str().unwrap(),
        ],
    );
    fs::write(linked.join("input.txt"), "linked change\n").unwrap();
    (main, linked)
}

#[test]
fn linked_worktree_git_status_reads_its_gitdirs_under_landlock() {
    // SPEC-A1 v4 §4.2 (C4): previously `is_repo:false` (known gap C2-3).
    let fixture = tempfile::tempdir().unwrap();
    let (main, linked) = linked_worktree(fixture.path());
    let common = fs::canonicalize(main.join(".git")).unwrap();
    assert_eq!(
        linked_worktree_gitdirs(&linked),
        Some((common.join("worktrees").join("linked"), common.clone()))
    );
    let harness = tempfile::tempdir().unwrap();
    let ctx = ToolContext::for_test(linked.clone(), harness.path().into()).unwrap();
    let status = call_tool(&ctx, "git_status", &json!({}));
    assert_eq!(status["is_repo"], true, "{status}");
    assert!(status.to_string().contains("input.txt"), "{status}");
    let diff = call_tool(&ctx, "git_diff", &json!({}));
    assert!(diff.to_string().contains("linked change"), "{diff}");
    // Inspection still never writes Git metadata.
    assert!(!common.join("worktrees/linked/index.lock").exists());
    assert!(!common.join("index.lock").exists());
}

#[test]
fn forged_worktree_links_never_widen_the_git_sandbox() {
    let fixture = tempfile::tempdir().unwrap();
    let (main, linked) = linked_worktree(fixture.path());
    fs::write(main.join("private.txt"), "SYNTHETIC_PRIVATE_CONTENT").unwrap();
    git(&main, &["add", "private.txt"]);
    git(&main, &["commit", "-qm", "private-fixture"]);
    let private = fs::canonicalize(main.join(".git/worktrees/linked")).unwrap();
    let harness = tempfile::tempdir().unwrap();
    // A different root pointing at another worktree's real metadata: the
    // back-pointer names `linked/.git`, not this root.
    let forged = fixture.path().join("forged");
    fs::create_dir(&forged).unwrap();
    fs::write(
        forged.join(".git"),
        format!("gitdir: {}\n", private.display()),
    )
    .unwrap();
    assert_eq!(linked_worktree_gitdirs(&forged), None);
    let ctx = ToolContext::for_test(forged.clone(), harness.path().into()).unwrap();
    let result = call_tool(&ctx, "git_show", &json!({}));
    assert_ne!(result["is_repo"], true, "{result}");
    assert!(!result.to_string().contains("SYNTHETIC_PRIVATE_CONTENT"));
    // A symlinked `.git` is never followed.
    let symlinked = fixture.path().join("symlinked");
    fs::create_dir(&symlinked).unwrap();
    std::os::unix::fs::symlink(linked.join(".git"), symlinked.join(".git")).unwrap();
    assert_eq!(linked_worktree_gitdirs(&symlinked), None);
    // A plain checkout and a `commondir` that does not own the private gitdir.
    assert_eq!(linked_worktree_gitdirs(&main), None);
    fs::write(private.join("commondir"), "../../..\n").unwrap();
    assert_eq!(linked_worktree_gitdirs(&linked), None);
}

/// A1 C2-ad (NB5, SPEC-A1 v5 §1.4.2): a main root that is itself a linked
/// worktree nested inside its own common gitdir cannot get the gitdir-pinned
/// sandbox (`for_worktree` rejects the containment); the root falls back to
/// the plain root sandbox instead of "Git workspace isolation unavailable".
#[test]
fn a_linked_main_root_contained_in_its_gitdir_falls_back_to_the_plain_sandbox() {
    let fixture = tempfile::tempdir().unwrap();
    let main = fixture.path().join("main");
    repository(&main);
    let nested = main.join(".git").join("nested-root");
    git(
        &main,
        &[
            "worktree",
            "add",
            "-q",
            "--detach",
            nested.to_str().unwrap(),
        ],
    );
    let gitdirs = linked_worktree_gitdirs(&nested);
    assert!(
        gitdirs.is_some(),
        "fixture must be a validated linked worktree"
    );
    let (private, common) = gitdirs.unwrap();
    assert!(
        LinuxSandbox::for_worktree(&nested, private, common).is_err(),
        "fixture must hit the containment rejection"
    );
    let sandbox = sandbox_for_root(&nested);
    assert!(sandbox.is_ok(), "no fallback: {:?}", sandbox.err());
    let out = run(
        &nested,
        &nested,
        &["rev-parse", "HEAD"],
        Duration::from_secs(5),
        GitRoot::Main,
    );
    assert_ne!(
        out.as_ref().err().copied(),
        Some("Git workspace isolation unavailable")
    );
}

/// A1 C2-ad2 (NB-p, SPEC-A1 v5.2 §1.4.2): the main-root fallback is taken
/// only for the containment refusal (`InvalidRoot`); every other refusal kind
/// propagates unchanged instead of silently widening to the root-only sandbox.
#[test]
fn the_main_root_fallback_is_taken_only_for_invalid_root() {
    let fixture = tempfile::tempdir().unwrap();
    let root = fixture.path().canonicalize().unwrap();
    let refused = |kind| Err(SandboxError { kind });
    assert!(
        main_root_fallback(&root, refused(SandboxErrorKind::InvalidRoot)).is_ok(),
        "InvalidRoot keeps the NB5 fallback"
    );
    for kind in [
        SandboxErrorKind::Unsupported,
        SandboxErrorKind::InvalidWorkingDirectory,
        SandboxErrorKind::InvalidExecutable,
        SandboxErrorKind::Unavailable,
        SandboxErrorKind::PrivilegedHost,
    ] {
        let out = main_root_fallback(&root, refused(kind));
        assert_eq!(
            out.err().map(|e| e.kind),
            Some(kind),
            "{kind:?} must not fall back"
        );
    }
}

/// A1 C2-ad2 (NB-p): a worker context never falls back. The containment case
/// that the main root tolerates (NB5) and a root that is not a validated
/// linked worktree are both refused; a proper linked worktree is pinned.
#[test]
fn the_worker_sandbox_is_fail_closed_without_fallback() {
    let fixture = tempfile::tempdir().unwrap();
    let main = fixture.path().join("main");
    repository(&main);
    let nested = main.join(".git").join("nested-root");
    git(
        &main,
        &[
            "worktree",
            "add",
            "-q",
            "--detach",
            nested.to_str().unwrap(),
        ],
    );
    assert!(linked_worktree_gitdirs(&nested).is_some());
    assert!(sandbox_for_root(&nested).is_ok(), "main root keeps NB5");
    assert_eq!(
        worker_sandbox_for_root(&nested).err().map(|e| e.kind),
        Some(SandboxErrorKind::InvalidRoot),
        "a worker must not fall back to the root-only sandbox"
    );
    assert_eq!(
        worker_sandbox_for_root(&main).err().map(|e| e.kind),
        Some(SandboxErrorKind::InvalidRoot),
        "a worker root that is not a linked worktree is refused"
    );
    let linked = fixture.path().join("linked");
    git(
        &main,
        &[
            "worktree",
            "add",
            "-q",
            "--detach",
            linked.to_str().unwrap(),
        ],
    );
    let pinned = worker_sandbox_for_root(&linked);
    assert!(pinned.is_ok(), "{:?}", pinned.err());
}

/// A1 C5 (NB-g, SPEC-A1 v5.3 §1.4.2): Git inspection of a worker root uses the
/// fail-closed worker sandbox. The NB5 containment root the main root tolerates
/// is refused for a worker, at `run` and through `git_status`, with no
/// root-only fallback; the same root as a main root still runs.
#[test]
fn git_inspection_of_a_worker_root_is_fail_closed() {
    let fixture = tempfile::tempdir().unwrap();
    let main = fixture.path().join("main");
    repository(&main);
    let nested = main.join(".git").join("nested-root");
    git(
        &main,
        &[
            "worktree",
            "add",
            "-q",
            "--detach",
            nested.to_str().unwrap(),
        ],
    );
    assert!(git_sandbox(&nested, GitRoot::Main).is_ok());
    assert_eq!(
        git_sandbox(&nested, GitRoot::Worker).err().map(|e| e.kind),
        Some(SandboxErrorKind::InvalidRoot)
    );
    let timeout = Duration::from_secs(10);
    assert_eq!(
        run(&nested, &nested, &["status"], timeout, GitRoot::Worker).err(),
        Some("Git workspace isolation unavailable"),
        "a worker root must not fall back to the root-only sandbox"
    );
    let mut worker = crate::tools::Workspace::new(nested.clone()).unwrap();
    worker.mark_worker_root();
    assert!(worker.is_worker_root());
    assert!(
        crate::tools::git::git_status(&worker, &json!({})).is_err(),
        "git_status on a refused worker root fails closed"
    );
    let main_view = crate::tools::Workspace::new(nested).unwrap();
    assert!(!main_view.is_worker_root());
    assert!(crate::tools::git::git_status(&main_view, &json!({})).is_ok());
}
