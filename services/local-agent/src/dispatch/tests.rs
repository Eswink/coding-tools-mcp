use super::*;
use crate::{ExecDecision, PrefixRule, TokenPattern, ToolOutput};
use serde_json::{json, Value};
use std::{fs, sync::atomic::{AtomicU64, Ordering}};

struct Fixture {
    parent: PathBuf,
    root: PathBuf,
    admission: LocalAdmission,
}
impl Fixture {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let parent = std::env::temp_dir().join(format!("ctm-dispatch-{}-{}-{}",
            std::process::id(), now().unwrap(), NEXT.fetch_add(1, Ordering::Relaxed)));
        let root = parent.join("workspace");
        fs::create_dir_all(&root).unwrap();
        fs::write(parent.join("secret"), "outside-private").unwrap();
        std::os::unix::fs::symlink(&parent, root.join("escape")).unwrap();
        Self { parent, root, admission: admission(1, now().unwrap() + 60_000) }
    }
    fn host(&self) -> SandboxedDispatch {
        SandboxedDispatch::new(&self.admission, &self.root, policy(ExecDecision::Allow)).unwrap()
    }
    fn call(&self, pty: bool, script: &str) -> ToolCall {
        ToolCall::new("request", "chat", "workspace",
            ToolName::parse(if pty { "sandbox_pty" } else { "sandbox_exec" }).unwrap(),
            json!({"argv":["/bin/sh","-c",script]})).unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) { let _ = fs::remove_dir_all(&self.parent); }
}
fn admission(generation: u64, expires: u64) -> LocalAdmission {
    LocalAdmission::fixture("chat", "workspace", required_capabilities(), generation, expires)
}
fn policy(decision: ExecDecision) -> ExecPolicy {
    ExecPolicy::new(["/bin/sh", "/usr/bin/python3"].into_iter().map(|program| {
        PrefixRule::new(vec![TokenPattern::exact(program).unwrap()], decision).unwrap()
    }).collect(), vec![], false).unwrap()
}
fn value(output: ToolOutput) -> Value {
    match output { ToolOutput::Json(value) => value, _ => panic!("expected JSON") }
}
fn bytes(value: &Value) -> Vec<u8> {
    value.as_array().unwrap().iter().map(|v| v.as_u64().unwrap() as u8).collect()
}
async fn complete(host: &SandboxedDispatch, call: &ToolCall, local: &LocalAdmission) -> Value {
    value(tokio::time::timeout(Duration::from_secs(10), host.invoke(call, local))
        .await.expect("bounded invocation").expect("dispatch result"))
}
async fn until_file<F: std::future::Future>(file: &Path, work: &mut std::pin::Pin<Box<F>>) {
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            tokio::select! {
                biased;
                _ = work.as_mut() => panic!("execution exited before ready"),
                _ = tokio::time::sleep(Duration::from_millis(10)) => {
                    if file.exists() { break; }
                }
            }
        }
    }).await.expect("child ready before test deadline");
}

#[tokio::test]
async fn actual_registry_dispatch_enforces_filesystem_and_network() {
    let f = Fixture::new(); let host = f.host();
    let mut call = f.call(false, "unused");
    call.arguments = json!({"argv":["/usr/bin/python3","-S","-c",
        r#"from pathlib import Path; import socket; Path('inside').write_text('ok'); exec('blocked=0\nfor p in ["../secret","escape/secret"]:\n try: Path(p).read_text()\n except PermissionError: blocked+=1\ntry: socket.socket()\nexcept PermissionError: blocked+=1\nprint(blocked); assert blocked==3')"#]});
    let output = complete(&host,&call,&f.admission).await;
    assert_eq!(output["ok"], true, "{output}");
    assert_eq!(fs::read_to_string(f.root.join("inside")).unwrap(), "ok");
    assert_eq!(fs::read_to_string(f.parent.join("secret")).unwrap(), "outside-private");
    host.revoke().await.unwrap();
}

#[tokio::test]
async fn model_cannot_disable_isolation_or_inject_environment() {
    let f=Fixture::new();let host=f.host();
    for field in ["sandbox","disable_sandbox","network","env","approval","generation","root"] {
        let mut call=f.call(false,"touch marker");call.arguments[field]=json!(false);
        assert_eq!(host.invoke(&call,&f.admission).await.unwrap_err().kind,ToolErrorKind::InvalidInput);
    }
    assert!(!f.root.join("marker").exists());host.revoke().await.unwrap();
}

#[tokio::test]
async fn identity_generation_capability_and_expiry_are_checked() {
    let f=Fixture::new();let host=f.host();let call=f.call(false,"touch marker");
    for bad in [LocalAdmission::fixture("foreign","workspace",required_capabilities(),1,now().unwrap()+5000),
        LocalAdmission::fixture("chat","foreign",required_capabilities(),1,now().unwrap()+5000),
        admission(2,now().unwrap()+5000),admission(1,now().unwrap())] {
        assert_eq!(host.invoke(&call,&bad).await.unwrap_err().kind,ToolErrorKind::Unauthorized);
    }
    let weak=LocalAdmission::fixture("chat","workspace",[Capability::ProcessExec],1,now().unwrap()+5000);
    assert_eq!(host.invoke(&call,&weak).await.unwrap_err().kind,ToolErrorKind::CapabilityDenied);
    assert!(!f.root.join("marker").exists());host.revoke().await.unwrap();
}

#[tokio::test]
async fn foreign_call_cannot_borrow_a_bound_host() {
    let f=Fixture::new();let host=f.host();
    for (chat,workspace) in [("foreign","workspace"),("chat","foreign")] {
        let mut call=f.call(false,"touch marker");call.conversation_id=chat.into();call.workspace_id=workspace.into();
        assert_eq!(host.invoke(&call,&f.admission).await.unwrap_err().kind,ToolErrorKind::Unauthorized);
    }
    host.revoke().await.unwrap();
}

#[tokio::test]
async fn forbidden_prompt_and_unmatched_policies_never_spawn() {
    let f=Fixture::new();let call=f.call(false,"touch marker");
    for p in [policy(ExecDecision::Forbidden),policy(ExecDecision::Prompt),ExecPolicy::new(vec![],vec![],false).unwrap()] {
        let host=SandboxedDispatch::new(&f.admission,&f.root,p).unwrap();
        assert!(host.invoke(&call,&f.admission).await.is_err());host.revoke().await.unwrap();
    }
    assert!(!f.root.join("marker").exists());
}

#[tokio::test]
async fn absolute_parent_and_symlink_cwd_are_rejected() {
    let f=Fixture::new();let host=f.host();
    for path in [f.parent.to_str().unwrap(),"..","sub/../../","escape"] {
        let mut call=f.call(false,"touch marker");call.arguments["cwd"]=json!(path);
        assert!(host.invoke(&call,&f.admission).await.is_err(),"{path}");
    }
    assert!(!f.root.join("marker").exists());assert!(!f.parent.join("marker").exists());host.revoke().await.unwrap();
}

#[tokio::test]
async fn constructor_requires_live_complete_local_admission() {
    let f=Fixture::new();
    for bad in [admission(0,now().unwrap()+5000),admission(1,now().unwrap()),
        LocalAdmission::fixture("chat","workspace",[Capability::ProcessExec],1,now().unwrap()+5000)] {
        assert_eq!(SandboxedDispatch::new(&bad,&f.root,policy(ExecDecision::Allow)).unwrap_err().kind,ToolErrorKind::Unauthorized);
    }
}

#[tokio::test]
async fn output_bounds_and_pty_input_remain_effective() {
    let f=Fixture::new();let host=f.host();
    let call=f.call(false,"while :; do printf 0123456789; done");
    let output=complete(&host,&call,&f.admission).await;
    assert_eq!(output["ok"],false);assert!(bytes(&output["outcome"]["stdout"]).len()<=STREAM_LIMIT);
    let mut call=f.call(true,"test -t 0 && stty size && read value && printf %s \"$value\"");
    call.arguments["stdin"]=json!("hello\n");call.arguments["rows"]=json!(31);call.arguments["columns"]=json!(91);
    let output=complete(&host,&call,&f.admission).await;assert_eq!(output["ok"],true,"{output}");
    let text=String::from_utf8(bytes(&output["outcome"]["output"])).unwrap();
    assert!(text.contains("31 91") && text.contains("hello"),"{text}");host.revoke().await.unwrap();
}

#[tokio::test]
async fn debug_and_errors_never_disclose_bound_paths() {
    let f=Fixture::new();let host=f.host();
    assert!(!format!("{host:?}").contains(f.root.to_str().unwrap()));
    let mut call=f.call(false,"ignored");call.arguments["cwd"]=json!("missing");
    let error=host.invoke(&call,&f.admission).await.unwrap_err();
    assert!(!format!("{error:?}").contains(f.root.to_str().unwrap()));host.revoke().await.unwrap();
}

#[path = "lifecycle_tests.rs"]
mod lifecycle;
