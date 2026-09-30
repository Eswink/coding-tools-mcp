use super::*;
use tempfile::tempdir;
fn spec() -> HookSpec {
    HookSpec {
        id: "check".into(),
        event: HookEvent::BeforeTool,
        tool: "exec_command".into(),
        executable: "/usr/bin/python3".into(),
        args: Vec::new(),
        cwd: ".".into(),
        script: Some("check.py".into()),
        timeout_ms: 1000,
        workspace_write: false,
    }
}
#[test]
fn manifest_has_no_permission_or_network_override_fields() {
    for key in [
        "env",
        "grant",
        "network",
        "workspace_root",
        "sandbox",
        "approved",
        "argv0",
    ] {
        let mut v = serde_json::to_value(spec()).unwrap();
        v[key] = json!(true);
        assert!(serde_json::from_value::<HookSpec>(v).is_err(), "{key}");
    }
}
#[cfg(target_os = "linux")]
#[test]
fn previews_are_immutable_workspace_bound_and_disabled_on_new_context() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::write(root.path().join("check.py"), "print('check')\n").unwrap();
    let pending = ctx.policy_hooks.prepare(&ctx, vec![spec()]).unwrap();
    assert_eq!(ctx.policy_hooks.status()["enabled"], false);
    assert_eq!(pending.digest().len(), 64);
    assert_eq!(pending.preview()["network_allowed"], false);
    std::fs::write(root.path().join("check.py"), "print('changed')\n").unwrap();
    assert!(ctx.policy_hooks.install(pending).is_err());
    let p = ctx.policy_hooks.prepare(&ctx, vec![spec()]).unwrap();
    assert_eq!(ctx.policy_hooks.install(p).unwrap()["enabled"], true);
    let fresh = HookRegistry::new(root.path().into());
    assert_eq!(fresh.status()["enabled"], false);
    let p = ctx.policy_hooks.prepare(&ctx, vec![spec()]).unwrap();
    assert!(fresh.install(p).is_err());
    ctx.policy_hooks.disable().unwrap();
    assert_eq!(ctx.policy_hooks.status()["enabled"], false);
}
#[cfg(target_os = "linux")]
#[test]
fn duplicates_limits_script_escape_and_mutable_executable_fail_closed() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::write(root.path().join("check.py"), "print('check')\n").unwrap();
    assert!(ctx
        .policy_hooks
        .prepare(&ctx, vec![spec(), spec()])
        .is_err());
    for change in [0, 1, 2, 3, 4] {
        let mut s = spec();
        match change {
            0 => s.timeout_ms = 2001,
            1 => s.tool = "read_file".into(),
            2 => s.script = Some("../outside.py".into()),
            3 => s.executable = root.path().join("check.py").display().to_string(),
            _ => s.args = vec!["x".into(); 17],
        }
        assert!(ctx.policy_hooks.prepare(&ctx, vec![s]).is_err());
    }
    let link = root.path().join("python3");
    std::os::unix::fs::symlink("/usr/bin/python3", &link).unwrap();
    let mut s = spec();
    s.executable = link.display().to_string();
    assert!(ctx.policy_hooks.prepare(&ctx, vec![s]).is_err());
}
#[cfg(not(target_os = "linux"))]
#[test]
fn unsupported_platform_never_approves_or_runs_hooks() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    assert!(ctx.policy_hooks.prepare(&ctx, vec![spec()]).is_err());
}

#[cfg(target_os = "linux")]
#[test]
fn script_parent_symlink_swap_and_stale_native_lease_commit_are_rejected() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let outside = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::create_dir(root.path().join("scripts")).unwrap();
    std::fs::write(root.path().join("scripts/check.py"), "print('check')\n").unwrap();
    std::fs::write(outside.path().join("check.py"), "print('check')\n").unwrap();
    let mut s = spec();
    s.script = Some("scripts/check.py".into());
    let mut p = ctx.policy_hooks.prepare(&ctx, vec![s.clone()]).unwrap();
    p.revalidate().unwrap();
    ctx.policy_hooks.disable().unwrap();
    assert!(ctx.policy_hooks.install_prevalidated(p).is_err());
    let mut p = ctx.policy_hooks.prepare(&ctx, vec![s]).unwrap();
    std::fs::rename(
        root.path().join("scripts"),
        root.path().join("original-scripts"),
    )
    .unwrap();
    std::os::unix::fs::symlink(outside.path(), root.path().join("scripts")).unwrap();
    assert!(p.revalidate().is_err());
    assert!(ctx.policy_hooks.install_prevalidated(p).is_err());
}

#[test]
fn cloud_tool_arguments_cannot_select_the_host_only_argv0() {
    assert!(coding_tools_cloud_agent::catalog::tool("exec_command")
        .unwrap()
        .arguments(&json!({"cmd":"pwd","argv0":"model-selected"}))
        .is_err());
}

#[cfg(target_os = "linux")]
#[test]
fn native_manifest_registration_cannot_add_to_command_policy() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::write(root.path().join("check.py"), "print('ready')\n").unwrap();
    ctx.policy.allowed_commands.clear();
    ctx.policy.allowed_commands.insert("cat".into());
    assert!(ctx.policy_hooks.prepare(&ctx, vec![spec()]).is_err());
}

#[test]
fn background_context_preserves_hook_recursion_scope_and_cancel_deadline() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let mut ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    let (tx, rx) = tokio::sync::watch::channel(false);
    ctx.hook_nested = true;
    ctx.hook_deadline = Some(Instant::now() + std::time::Duration::from_secs(2));
    ctx.hook_cancel = Some(rx);
    let nested = ctx.background_snapshot();
    assert!(nested.hook_nested);
    assert_eq!(nested.hook_deadline, ctx.hook_deadline);
    assert!(Arc::ptr_eq(&nested.policy_hooks, &ctx.policy_hooks));
    tx.send(true).unwrap();
    assert!(*nested.hook_cancel.as_ref().unwrap().borrow());
}
#[cfg(target_os = "linux")]
#[test]
fn native_registry_approval_never_substitutes_for_conversation_authority() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::write(root.path().join("check.py"), "print('ready')\n").unwrap();
    let p = ctx.policy_hooks.prepare(&ctx, vec![spec()]).unwrap();
    ctx.policy_hooks.install(p).unwrap();
    let result = crate::tools::call_tool(&ctx, "exec_command", &json!({"cmd":"pwd"}));
    assert_eq!(result["error"]["code"], "HOOK_LOCAL_AUTHORITY_REQUIRED");
    assert_eq!(result["primary_started"], false);
}

#[cfg(target_os = "linux")]
#[test]
fn async_primary_does_not_retrigger_exec_command_hooks() {
    let root = tempdir().unwrap();
    let storage = tempdir().unwrap();
    let ctx = ToolContext::for_test(root.path().into(), storage.path().into()).unwrap();
    std::fs::write(root.path().join("check.py"), "raise SystemExit(1)\n").unwrap();
    let prepared = ctx.policy_hooks.prepare(&ctx, vec![spec()]).unwrap();
    ctx.policy_hooks.install(prepared).unwrap();
    let accepted = crate::tools::call_tool(&ctx, "start_exec_task", &json!({
        "request_id":"nested-hook-regression", "cmd":"python3 -c \"print('primary')\"", "timeout_ms":1000
    }));
    assert_eq!(accepted["ok"], true, "{accepted}");
    let until = Instant::now() + std::time::Duration::from_secs(10);
    loop {
        let result = crate::tools::call_tool(&ctx, "get_exec_task", &json!({"job_id":accepted["job_id"]}));
        if result["terminal"] == true {
            // This host may fail mandatory sandbox startup. Either outcome must
            // come from the primary command, never a second unapproved hook.
            assert!(!result.to_string().contains("HOOK_LOCAL_AUTHORITY_REQUIRED"), "{result}");
            break;
        }
        assert!(Instant::now() < until, "{result}");
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
}

#[cfg(target_os = "linux")]
#[test]
fn script_preview_is_exact_utf8_and_unknown_encoding_is_rejected() {
    let root=tempdir().unwrap();let storage=tempdir().unwrap();
    let ctx=ToolContext::for_test(root.path().into(),storage.path().into()).unwrap();
    for bytes in [&b"print('\xff')\n"[..], &b"print('ok')\0\n"[..]] {
        std::fs::write(root.path().join("check.py"),bytes).unwrap();
        assert!(matches!(ctx.policy_hooks.prepare(&ctx,vec![spec()]),Err("HOOK_SCRIPT_REJECTED")));
    }
    let source="# exact native preview: 中文 café 🐈\nprint('hello')\n";
    std::fs::write(root.path().join("check.py"),source).unwrap();
    let prepared=ctx.policy_hooks.prepare(&ctx,vec![spec()]).unwrap();
    assert_eq!(prepared.preview()["hooks"][0]["script_source"],source);
}
