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
        Duration::from_secs(1)
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
    )
    .unwrap();
    assert!(output.status.success());
    assert_eq!(String::from_utf8(output.stdout).unwrap().trim().len(), 40);
}
