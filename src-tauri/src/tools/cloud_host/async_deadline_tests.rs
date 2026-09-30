use super::*;

fn args(key: &str, timeout_ms: u64) -> Value {
    json!({"cmd":"python3 -c \"print('budget')\"","request_id":key,"timeout_ms":timeout_ms})
}
fn prepare(f: &Fixture, a: &NativeAuthority, args: &Value, seconds: u64) -> PreparedCall {
    f.host.prepare(a, "start_exec_task", args, now().unwrap()+seconds).unwrap()
}
fn context(f: &Fixture) -> ToolContext {
    let request=f.host.request(&f.conversation()).unwrap();
    f.host.context.chat_domains.scoped(&f.host.context,&request).unwrap()
}
fn settle(f: &Fixture, id: &str) -> Value {
    let until=Instant::now()+Duration::from_secs(10);
    loop {
        let value=crate::tools::exec_tasks::get(&context(f), &json!({"job_id":id})).unwrap();
        if value["terminal"]==true {return value;}
        assert!(Instant::now()<until,"{value}");
        std::thread::sleep(Duration::from_millis(10));
    }
}
#[test]
fn accepted_async_budget_is_independent_of_submission_rpc_deadline() {
    let f=Fixture::new();let a=f.approve(&["exec.run"]);
    let result=f.host.execute(prepare(&f,&a,&args("independent-budget",600000),10)).unwrap();
    assert_eq!(result["ok"],true,"{result}");
    settle(&f,result["job_id"].as_str().unwrap());
    assert_eq!(result["execution_timeout_ms"],600000,"{result}");
}
#[test]
fn identical_async_request_deduplicates_across_different_rpc_deadlines() {
    let f=Fixture::new();let a=f.approve(&["exec.run"]);let args=args("stable-key",600000);
    let first=f.host.execute(prepare(&f,&a,&args,10)).unwrap();
    assert_eq!(first["ok"],true,"{first}");
    settle(&f,first["job_id"].as_str().unwrap());
    let second=f.host.execute(prepare(&f,&a,&args,20)).unwrap();
    assert_eq!(second["ok"],true,"{second}");
    assert_eq!(second["job_id"],first["job_id"]);
    assert_eq!(second["deduplicated"],true);
    assert_eq!(crate::tools::exec_tasks::list(&context(&f), &json!({})).unwrap()["jobs"].as_array().unwrap().len(),1);
}
#[test]
fn cancelled_submission_does_not_reserve_an_async_job() {
    let f=Fixture::new();let a=f.approve(&["exec.run"]);
    let (_,rx)=tokio::sync::watch::channel(true);
    let result=f.host.execute_scoped(prepare(&f,&a,&args("cancel-before-reserve",600000),10),None,Some(rx));
    assert!(result.is_err(),"{result:?}");
    assert!(crate::tools::exec_tasks::list(&context(&f), &json!({})).unwrap()["jobs"].as_array().unwrap().is_empty());
}
#[test]
fn expired_submission_does_not_reserve_an_async_job() {
    let f=Fixture::new();let a=f.approve(&["exec.run"]);
    let mut call=prepare(&f,&a,&args("expired-before-reserve",600000),10);
    call.deadline=Instant::now();
    assert!(f.host.execute(call).is_err());
    assert!(crate::tools::exec_tasks::list(&context(&f), &json!({})).unwrap()["jobs"].as_array().unwrap().is_empty());
}
#[test]
fn native_task_policy_still_bounds_an_async_cloud_job() {
    let mut f=Fixture::new();
    Arc::get_mut(&mut f.host.context).unwrap().policy.max_task_timeout_ms=1000;
    let a=f.approve(&["exec.run"]);
    let result=f.host.execute(prepare(&f,&a,&args("above-native-policy",2000),10)).unwrap();
    assert_eq!(result["ok"],false,"{result}");
    assert!(crate::tools::exec_tasks::list(&context(&f), &json!({})).unwrap()["jobs"].as_array().unwrap().is_empty());
}

#[test]
fn submission_deadline_is_rechecked_at_the_actual_async_reservation_boundary() {
    let f=Fixture::new();
    let mut ctx=f.host.context.background_snapshot();
    ctx.hook_deadline=Some(Instant::now());
    let result=crate::tools::exec_tasks::start(&ctx,&args("late-boundary",600000));
    assert!(result.is_err());
    assert!(crate::tools::exec_tasks::list(&ctx,&json!({})).unwrap()["jobs"].as_array().unwrap().is_empty());
    ctx.hook_deadline=None;
    let (_,rx)=tokio::sync::watch::channel(true);ctx.hook_cancel=Some(rx);
    assert!(crate::tools::exec_tasks::start(&ctx,&args("cancelled-boundary",600000)).is_err());
    assert!(crate::tools::exec_tasks::list(&ctx,&json!({})).unwrap()["jobs"].as_array().unwrap().is_empty());
}
#[cfg(target_os="linux")]
#[path="async_deadline_runtime_tests.rs"]
mod runtime;

#[cfg(target_os="linux")]
#[test]
fn a_failed_before_hook_retains_the_logical_job_key_without_replay() {
    use crate::tools::policy_hooks::{HookEvent,HookSpec};
    let f=Fixture::new();let a=f.approve(&["exec.run"]);
    let script=f.root.path().join("before.py");std::fs::write(&script,"print('original')\n").unwrap();
    let hook=HookSpec{id:"before".into(),event:HookEvent::BeforeTool,tool:"start_exec_task".into(),
        executable:"/usr/bin/python3".into(),args:vec![],cwd:".".into(),script:Some("before.py".into()),timeout_ms:1000,workspace_write:false};
    let p=f.host.context.policy_hooks.prepare(&f.host.context,vec![hook]).unwrap();
    f.host.context.policy_hooks.install(p).unwrap();
    std::fs::write(&script,"print('changed')\n").unwrap();
    let args=args("failed-hook-key",600000);
    let first=f.host.execute(prepare(&f,&a,&args,10)).unwrap();
    assert_eq!(first["error"]["code"],"HOOK_ARTIFACT_CHANGED","{first}");
    let jobs=crate::tools::exec_tasks::list(&context(&f),&json!({})).unwrap();
    assert_eq!(jobs["jobs"].as_array().unwrap().len(),1,"failure must keep a durable logical key: {jobs}");
    assert_eq!(jobs["jobs"][0]["status"],"failed");
    // Restore the selected script. A new outer request must return the failed
    // logical job, not rerun the hook merely because its bytes now match again.
    std::fs::write(&script,"print('original')\n").unwrap();
    let duplicate=f.host.execute(prepare(&f,&a,&args,20)).unwrap();
    assert_eq!(duplicate["deduplicated"],true,"{duplicate}");
    assert_eq!(duplicate["status"],"failed");
    assert_eq!(duplicate["job_id"],jobs["jobs"][0]["job_id"]);
}

#[cfg(target_os="linux")]
#[test]
fn failed_hook_job_survives_source_context_restart_without_hook_or_primary_replay() {
    use crate::tools::policy_hooks::{HookEvent,HookSpec};
    let f=Fixture::new();let a=f.approve(&["exec.run"]);
    std::fs::write(f.root.path().join("before.py"),"print('approved')\n").unwrap();
    let hook=HookSpec{id:"before".into(),event:HookEvent::BeforeTool,tool:"start_exec_task".into(),
        executable:"/usr/bin/python3".into(),args:vec![],cwd:".".into(),script:Some("before.py".into()),timeout_ms:1000,workspace_write:false};
    let p=f.host.context.policy_hooks.prepare(&f.host.context,vec![hook]).unwrap();f.host.context.policy_hooks.install(p).unwrap();
    std::fs::write(f.root.path().join("before.py"),"print('changed')\n").unwrap();
    let args=args("restart-failed-hook",600000);
    let failed=f.host.execute(prepare(&f,&a,&args,10)).unwrap();assert_eq!(failed["error"]["code"],"HOOK_ARTIFACT_CHANGED");
    let task_root=context(&f).harness.store_root().join("exec-tasks-v1");
    let job_id=failed["job_id"].clone();
    let Fixture{root,_storage,_harness,host,peer:_}=f;
    drop(host);
    // Reopen the exact existing encrypted task namespace, with no new native
    // approval and no hook configuration. This is local recovery inspection.
    let mut recovered=ToolContext::for_test(root.path().into(),_harness.path().into()).unwrap();
    recovered.exec_tasks=crate::tools::exec_tasks::ExecTaskStore::shared(task_root);
    assert_eq!(recovered.policy_hooks.status()["enabled"],false);
    let duplicate=crate::tools::exec_tasks::start(&recovered,&args).unwrap();
    assert_eq!(duplicate["job_id"],job_id);assert_eq!(duplicate["deduplicated"],true);
    assert_eq!(duplicate["status"],"failed","{duplicate}");
    assert_eq!(duplicate["result"]["error"]["code"],"HOOK_ARTIFACT_CHANGED");
}
