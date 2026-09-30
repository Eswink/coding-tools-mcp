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
