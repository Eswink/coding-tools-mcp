//! Mandatory-sandbox tests: unsupported kernels fail, never silently skip.
use super::*;
fn long_args(f: &Fixture, key: &str, seconds: u64) -> Value {
    std::fs::write(f.root.path().join("long.py"),format!(
        "import time\nfrom pathlib import Path\np=Path('count')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\ntime.sleep({seconds})\nPath('finished').write_text('done')\n")).unwrap();
    json!({"cmd":"python3 long.py","request_id":key,"timeout_ms":6000})
}
fn wait_started(f: &Fixture) {
    let until = Instant::now() + Duration::from_secs(3);
    while !f.root.path().join("count").exists() {
        assert!(
            Instant::now() < until,
            "mandatory sandbox did not start the real child"
        );
        std::thread::sleep(Duration::from_millis(10));
    }
}
#[test]
fn real_job_outlives_rpc_and_duplicate_does_not_create_a_second_side_effect() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    let args = long_args(&f, "long-single-effect", 4);
    let call = prepare(&f, &a, &args, 2);
    let rpc_deadline = call.deadline;
    let accepted = f.host.execute(call).unwrap();
    assert_eq!(accepted["ok"], true, "{accepted}");
    wait_started(&f);
    while Instant::now() <= rpc_deadline + Duration::from_millis(100) {
        std::thread::sleep(Duration::from_millis(20));
    }
    let running =
        crate::tools::exec_tasks::get(&context(&f), &json!({"job_id":accepted["job_id"]})).unwrap();
    assert_eq!(running["terminal"], false, "{running}");
    assert_eq!(running["execution_timeout_ms"], 6000);
    let duplicate = f.host.execute(prepare(&f, &a, &args, 15)).unwrap();
    assert_eq!(duplicate["deduplicated"], true, "{duplicate}");
    assert_eq!(duplicate["job_id"], accepted["job_id"]);
    let done = settle(&f, accepted["job_id"].as_str().unwrap());
    assert_eq!(done["status"], "succeeded", "{done}");
    assert!(f.root.path().join("finished").exists());
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("count")).unwrap(),
        "x"
    );
}
#[test]
fn approved_task_cancel_still_drains_a_long_job_after_submission_response() {
    let f = Fixture::new();
    let a = f.approve(&["exec.run", "task.manage"]);
    let args = long_args(&f, "long-cancel", 4);
    let accepted = f.host.execute(prepare(&f, &a, &args, 2)).unwrap();
    wait_started(&f);
    let cancel = f
        .host
        .prepare(
            &a,
            "cancel_exec_task",
            &json!({"job_id":accepted["job_id"]}),
            now().unwrap() + 10,
        )
        .unwrap();
    let cancelled = f.host.execute(cancel).unwrap();
    assert_eq!(cancelled["ok"], true, "{cancelled}");
    let done = settle(&f, accepted["job_id"].as_str().unwrap());
    assert_eq!(done["status"], "cancelled", "{done}");
    assert_ne!(done["result"]["process_may_be_running"], true);
    assert!(!f.root.path().join("finished").exists());
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("count")).unwrap(),
        "x"
    );
}
#[test]
fn revoke_and_pause_block_new_jobs_but_retain_the_admitted_job_drain_fence() {
    for pause in [false, true] {
        let f = Fixture::new();
        let a = f.approve(&["exec.run"]);
        let args = long_args(&f, "long-drain", 2);
        let accepted = f.host.execute(prepare(&f, &a, &args, 10)).unwrap();
        wait_started(&f);
        let blocked = prepare(&f, &a, &super::args("blocked-after-transition", 6000), 10);
        if pause {
            f.host.context.execution_gate.pause().unwrap();
        } else {
            f.host.authorizer.revoke("native-host", None);
        }
        assert!(f.host.execute(blocked).is_err());
        if !pause {
            let foreign = URL_SAFE_NO_PAD.encode([19; 32]);
            let pending = f
                .host
                .request_authorization(&foreign, &json!({"scopes":["exec.run"]}));
            assert_ne!(pending["authorization"]["status"], "pending", "{pending}");
        }
        let done = settle(&f, accepted["job_id"].as_str().unwrap());
        assert_eq!(done["status"], "succeeded", "{done}");
        assert_eq!(
            std::fs::read_to_string(f.root.path().join("count")).unwrap(),
            "x"
        );
        assert_eq!(
            crate::tools::exec_tasks::list(&context(&f), &json!({})).unwrap()["jobs"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
}
#[test]
fn before_hook_consumes_submission_time_without_rewriting_the_job_budget() {
    use crate::tools::policy_hooks::{HookEvent, HookSpec};
    let f = Fixture::new();
    let a = f.approve(&["exec.run"]);
    std::fs::write(
        f.root.path().join("before.py"),
        "print('native-approved')\n",
    )
    .unwrap();
    let hook = HookSpec {
        id: "before".into(),
        event: HookEvent::BeforeTool,
        tool: "start_exec_task".into(),
        executable: "/usr/bin/python3".into(),
        args: vec![],
        cwd: ".".into(),
        script: Some("before.py".into()),
        timeout_ms: 1000,
        workspace_write: false,
    };
    let prepared = f
        .host
        .context
        .policy_hooks
        .prepare(&f.host.context, vec![hook])
        .unwrap();
    f.host.context.policy_hooks.install(prepared).unwrap();
    let accepted = f
        .host
        .execute(prepare(&f, &a, &args("hook-budget", 600000), 10))
        .unwrap();
    assert_eq!(accepted["ok"], true, "{accepted}");
    assert_eq!(accepted["execution_timeout_ms"], 600000);
    let done = settle(&f, accepted["job_id"].as_str().unwrap());
    assert_eq!(done["status"], "succeeded", "{done}");
}

#[test]
fn concurrent_new_outer_requests_share_one_write_enabled_hook_and_one_primary() {
    use crate::tools::policy_hooks::{HookEvent, HookSpec};
    let f = Arc::new(Fixture::new());
    let authority = f.approve(&["exec.run"]);
    std::fs::write(f.root.path().join("hook.py"),"import time\nfrom pathlib import Path\np=Path('hook-count')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\ntime.sleep(0.2)\n").unwrap();
    std::fs::write(f.root.path().join("primary.py"),"from pathlib import Path\np=Path('primary-count')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\n").unwrap();
    let hook = HookSpec {
        id: "write-once".into(),
        event: HookEvent::BeforeTool,
        tool: "start_exec_task".into(),
        executable: "/usr/bin/python3".into(),
        args: vec![],
        cwd: ".".into(),
        script: Some("hook.py".into()),
        timeout_ms: 1000,
        workspace_write: true,
    };
    let p = f
        .host
        .context
        .policy_hooks
        .prepare(&f.host.context, vec![hook])
        .unwrap();
    f.host.context.policy_hooks.install(p).unwrap();
    let args =
        json!({"cmd":"python3 primary.py","request_id":"same-inner-two-outer","timeout_ms":600000});
    let barrier = Arc::new(std::sync::Barrier::new(2));
    let workers = (0..2)
        .map(|index| {
            let f = f.clone();
            let a = authority.clone();
            let args = args.clone();
            let barrier = barrier.clone();
            std::thread::spawn(move || {
                let call = prepare(&f, &a, &args, 10 + index * 5);
                barrier.wait();
                f.host.execute(call).unwrap()
            })
        })
        .collect::<Vec<_>>();
    let results = workers
        .into_iter()
        .map(|w| w.join().unwrap())
        .collect::<Vec<_>>();
    for result in &results {
        assert_eq!(result["ok"], true, "{results:?}");
    }
    assert_eq!(results[0]["job_id"], results[1]["job_id"]);
    assert_eq!(
        results.iter().filter(|v| v["deduplicated"] == true).count(),
        1
    );
    let done = settle(&f, results[0]["job_id"].as_str().unwrap());
    assert_eq!(done["status"], "succeeded", "{done}");
    let third = f.host.execute(prepare(&f, &authority, &args, 20)).unwrap();
    assert_eq!(third["deduplicated"], true, "{third}");
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("hook-count")).unwrap(),
        "x"
    );
    assert_eq!(
        std::fs::read_to_string(f.root.path().join("primary-count")).unwrap(),
        "x"
    );
}
