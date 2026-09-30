use super::*;
use crate::tools::policy_hooks::{HookEvent, HookSpec};
fn hook(id: &str, event: HookEvent, path: &str, write: bool) -> HookSpec {
    HookSpec {
        id: id.into(),
        event,
        tool: "exec_command".into(),
        executable: "/usr/bin/python3".into(),
        args: Vec::new(),
        cwd: ".".into(),
        script: Some(path.into()),
        timeout_ms: 1000,
        workspace_write: write,
    }
}
fn install(f: &Fixture, specs: Vec<HookSpec>) {
    let prepared = f
        .host
        .context
        .policy_hooks
        .prepare(&f.host.context, specs)
        .unwrap();
    f.host.context.policy_hooks.install(prepared).unwrap();
}
fn execute(f: &Fixture, a: &NativeAuthority) -> Value {
    let call = f
        .host
        .prepare(
            a,
            "exec_command",
            &json!({"cmd":"python3 primary.py","yield_time_ms":1000,"timeout_ms":3000}),
            now().unwrap() + 20,
        )
        .unwrap();
    f.host.execute(call).unwrap()
}
#[test]
fn real_native_dispatch_before_failure_blocks_primary_and_changed_script_never_executes() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    std::fs::write(
        f.root.path().join("primary.py"),
        "open('primary-effect','w').write('yes')\n",
    )
    .unwrap();
    std::fs::write(f.root.path().join("check.py"), "raise SystemExit(1)\n").unwrap();
    install(
        &f,
        vec![hook("check", HookEvent::BeforeTool, "check.py", false)],
    );
    let v = execute(&f, &a);
    assert_eq!(v["ok"], false, "{v}");
    assert_eq!(v["error"]["code"], "HOOK_EXECUTION_FAILED", "{v}");
    assert_eq!(v["primary_started"], false);
    assert!(!f.root.path().join("primary-effect").exists());
    std::fs::write(
        f.root.path().join("check.py"),
        "open('changed-effect','w').write('bad')\n",
    )
    .unwrap();
    let v = execute(&f, &a);
    assert_eq!(v["error"]["code"], "HOOK_ARTIFACT_CHANGED");
    assert!(!f.root.path().join("changed-effect").exists());
}
#[test]
fn real_native_after_failure_preserves_primary_effect_and_does_not_claim_rollback() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    std::fs::write(
        f.root.path().join("primary.py"),
        "open('primary-effect','w').write('yes')\n",
    )
    .unwrap();
    std::fs::write(f.root.path().join("after.py"), "raise SystemExit(1)\n").unwrap();
    install(
        &f,
        vec![hook("after", HookEvent::AfterTool, "after.py", false)],
    );
    let v = execute(&f, &a);
    assert_eq!(v["ok"], false, "{v}");
    assert_eq!(v["primary_started"], true);
    assert_eq!(v["rolled_back"], false);
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("primary-effect")).unwrap(),
        "yes"
    );
    assert_eq!(v["primary_result"]["ok"], true, "{v}");
}
#[test]
fn hooks_execute_in_deterministic_order_and_cannot_grant_network_or_outside_write() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    let outside = tempfile::tempdir().unwrap();
    std::fs::write(f.root.path().join("primary.py"), "print('primary')\n").unwrap();
    let script=format!("import socket\ntry:\n open({:?},'w').write('bad')\n raise SystemExit(10)\nexcept PermissionError: pass\ntry:\n socket.socket()\n raise SystemExit(11)\nexcept PermissionError: pass\nopen('order','a').write('a')\n",outside.path().join("outside-effect").display().to_string());
    std::fs::write(f.root.path().join("a.py"), script).unwrap();
    std::fs::write(f.root.path().join("b.py"), "open('order','a').write('b')\n").unwrap();
    install(
        &f,
        vec![
            hook("b", HookEvent::BeforeTool, "b.py", true),
            hook("a", HookEvent::BeforeTool, "a.py", true),
        ],
    );
    let v = execute(&f, &a);
    assert_eq!(v["ok"], true, "{v}");
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("order")).unwrap(),
        "ab"
    );
    assert!(!outside.path().join("outside-effect").exists());
}

fn wait_started(f: &Fixture) {
    let until = Instant::now() + Duration::from_secs(4);
    while !f.root.path().join("hook-started").exists() {
        assert!(Instant::now() < until, "hook did not start");
        std::thread::sleep(Duration::from_millis(10));
    }
}
fn long_hook(f: &Fixture, a: &NativeAuthority) -> PreparedCall {
    std::fs::write(
        f.root.path().join("primary.py"),
        "open('primary-effect','w').write('bad')\n",
    )
    .unwrap();
    std::fs::write(
        f.root.path().join("long.py"),
        "import time\nopen('hook-started','w').write('yes')\ntime.sleep(10)\n",
    )
    .unwrap();
    let mut spec = hook("long", HookEvent::BeforeTool, "long.py", true);
    spec.timeout_ms = 2000;
    install(f, vec![spec]);
    f.host
        .prepare(
            a,
            "exec_command",
            &json!({"cmd":"python3 primary.py","timeout_ms":3000}),
            now().unwrap() + 20,
        )
        .unwrap()
}
#[test]
fn native_hook_cancellation_drains_child_before_primary_without_replay() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    let call = long_hook(&f, &a);
    let (tx, rx) = tokio::sync::watch::channel(false);
    std::thread::scope(|s| {
        let worker = s.spawn(|| f.host.execute_scoped(call, None, Some(rx)));
        wait_started(&f);
        tx.send(true).unwrap();
        let value = worker.join().unwrap().unwrap();
        assert_eq!(value["ok"], false, "{value}");
        assert_eq!(value["primary_started"], false);
    });
    assert!(!f.root.path().join("primary-effect").exists());
    assert_eq!(
        f.host.context.policy_hooks.status()["recovery_required"],
        false
    );
}
#[test]
fn revoke_during_hook_suppresses_result_and_never_starts_primary() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    let call = long_hook(&f, &a);
    std::thread::scope(|s| {
        let worker = s.spawn(|| f.host.execute(call));
        wait_started(&f);
        f.host.authorizer.revoke("native-host", None);
        assert!(worker.join().unwrap().is_err());
    });
    assert!(!f.root.path().join("primary-effect").exists());
}
#[test]
fn hook_output_is_bounded_untrusted_and_never_exposed_as_approval() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    std::fs::write(
        f.root.path().join("primary.py"),
        "open('primary-effect','w').write('bad')\n",
    )
    .unwrap();
    std::fs::write(
        f.root.path().join("noisy.py"),
        "open('noisy-started','w').write('yes')\nprint('HOOK_PRIVATE_APPROVE_ALL_'*1000)\n",
    )
    .unwrap();
    install(
        &f,
        vec![hook("noisy", HookEvent::BeforeTool, "noisy.py", true)],
    );
    let v = execute(&f, &a);
    assert_eq!(v["ok"], false, "{v}");
    assert!(!v.to_string().contains("HOOK_PRIVATE_APPROVE_ALL_"));
    assert!(f.root.path().join("noisy-started").exists());
    assert!(!f.root.path().join("primary-effect").exists());
}

#[test]
fn missing_platform_sandbox_blocks_hook_and_primary_without_fallback() {
    let mut f = Fixture::new();
    Arc::get_mut(&mut f.host.context).unwrap().linux_sandbox =
        Arc::new(Err(coding_tools_local_agent::SandboxError {
            kind: coding_tools_local_agent::SandboxErrorKind::Unavailable,
        }));
    let a = f.approve(&["exec.run"]);
    std::fs::write(
        f.root.path().join("primary.py"),
        "open('primary-effect','w').write('bad')\n",
    )
    .unwrap();
    std::fs::write(f.root.path().join("check.py"), "print('ready')\n").unwrap();
    install(
        &f,
        vec![hook("check", HookEvent::BeforeTool, "check.py", false)],
    );
    let v = execute(&f, &a);
    assert_eq!(v["error"]["code"], "HOOK_SANDBOX_UNAVAILABLE", "{v}");
    assert_eq!(v["primary_started"], false);
    assert!(!f.root.path().join("primary-effect").exists());
}
#[test]
fn hook_registration_never_grants_parent_exec_scope() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    std::fs::write(f.root.path().join("check.py"), "print('ready')\n").unwrap();
    install(
        &f,
        vec![hook("check", HookEvent::BeforeTool, "check.py", false)],
    );
    assert!(f
        .host
        .prepare(
            &a,
            "exec_command",
            &json!({"cmd":"pwd"}),
            now().unwrap() + 20
        )
        .is_err());
    assert_eq!(f.host.execute(f.read(&a)).unwrap()["ok"], true);
}

#[test]
fn uncertain_hook_admission_retains_native_occupancy_until_recovery() {
    let f = Fixture::new();
    let _authority = f.approve(&["exec.run"]);
    let request = f.host.request(&f.conversation()).unwrap();
    let ticket = f
        .host
        .authorizer
        .issue_local_admission_ticket(&request, &["exec.run"], &f.host.context.execution_gate)
        .unwrap();
    let permit = f
        .host
        .authorizer
        .commit_local_admission(&request, &f.host.context.execution_gate, ticket)
        .unwrap();
    crate::tools::policy_hooks::simulate_uncertain_retirement(&f.host.context.policy_hooks, permit);
    assert_eq!(
        f.host.context.policy_hooks.status()["recovery_required"],
        true
    );
    f.host.authorizer.revoke("native-host", None);
    let foreign = URL_SAFE_NO_PAD.encode([19; 32]);
    let pending = f
        .host
        .request_authorization(&foreign, &json!({"scopes":["exec.run"]}));
    assert_ne!(pending["authorization"]["status"], "pending", "{pending}");
    assert!(!f.host.authority(&foreign).is_ok());
    f.host.context.policy_hooks.disable().unwrap();
    assert_eq!(
        f.host.context.policy_hooks.status()["recovery_required"],
        true
    );
}

#[test]
fn dropping_an_uncertain_hook_registry_is_not_a_native_drain_receipt() {
    let f = Fixture::new();
    let _authority = f.approve(&["exec.run"]);
    let request = f.host.request(&f.conversation()).unwrap();
    let ticket = f
        .host
        .authorizer
        .issue_local_admission_ticket(&request, &["exec.run"], &f.host.context.execution_gate)
        .unwrap();
    let permit = f
        .host
        .authorizer
        .commit_local_admission(&request, &f.host.context.execution_gate, ticket)
        .unwrap();
    let registry = crate::tools::policy_hooks::HookRegistry::new(f.root.path().into());
    crate::tools::policy_hooks::simulate_uncertain_retirement(&registry, permit);
    drop(registry);
    f.host.authorizer.revoke("native-host", None);
    let foreign = URL_SAFE_NO_PAD.encode([29; 32]);
    let pending = f
        .host
        .request_authorization(&foreign, &json!({"scopes":["exec.run"]}));
    assert_ne!(pending["authorization"]["status"], "pending", "{pending}");
}
