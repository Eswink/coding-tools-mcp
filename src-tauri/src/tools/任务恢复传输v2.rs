use std::time::{Duration, Instant};
use serde_json::{json, Value};
use crate::auth::{PublicOrigin, chat_fixture as fixture};
use crate::workspace::{AuthConfig, RuntimeConfig};

#[cfg(target_os = "linux")]
fn loopback_listener_inode(port: u16) -> Option<String> {
    let local = format!("0100007F:{port:04X}");
    let table = std::fs::read_to_string("/proc/net/tcp").ok()?;
    table.lines().skip(1).find_map(|line| {
        let fields = line.split_whitespace().collect::<Vec<_>>();
        (fields.len() > 9
            && fields[1].eq_ignore_ascii_case(&local)
            && fields[3] == "0A")
            .then(|| fields[9].to_owned())
    })
}

#[cfg(not(target_os = "linux"))]
fn loopback_listener_inode(_port: u16) -> Option<String> { None }

#[tokio::test]
async fn listener_restart_keeps_the_running_job_and_its_idempotency_key() {
    let root = tempfile::tempdir().unwrap();
    let profile = uuid::Uuid::new_v4().to_string();
    fixture::approve(&profile,root.path(),"restart-chat");
    let start_listener = |port| crate::mcp::spawn_listener_with_origin(port, root.path().to_path_buf(), profile.clone(),
        AuthConfig {auth_type:"oauth".into(),oauth_client_id:"test-client".into(),..Default::default()}, PublicOrigin::managed(fixture::ORIGIN).unwrap(),
        None,Some("test-password".into()),Some(fixture::KEY.into()),RuntimeConfig::default());
    // Acquire the port by the production bind itself, never probe and release it.
    // This test-only range is below both hosted CI systems' dynamic client ranges.
    // Only initial fixture setup may try another port; the same-port restart below
    // is intentionally NOT retried, and no command is ever replayed by this loop.
    let offset = (std::process::id() % 8000) as u16;
    let (port, (stop, handle)) = (0..128u16).find_map(|attempt| {
        let candidate = 12000 + (offset + attempt) % 8000;
        match start_listener(candidate) {
            Ok(listener) => Some((candidate, listener)),
            Err(error) if error.starts_with("MCP 本地端口 ") && error.contains("绑定失败") => {
                eprintln!("initial fixture port {candidate} unavailable: {error}");
                None
            }
            Err(error) => panic!("listener fixture failed before binding: {error}"),
        }
    }).expect("no available test listener port in bounded fixture range");
    let initial_listener_inode = loopback_listener_inode(port);
    eprintln!("[issue62-inode] phase=initial port={port} inode={initial_listener_inode:?}");
    let conflict = start_listener(port).err().expect("an occupied listener port must be rejected");
    assert!(conflict.contains("绑定失败"), "{conflict}");
    let client = fixture::client();
    let url = format!("http://127.0.0.1:{port}/mcp");
    let python = if cfg!(windows) {"python"} else {"python3"};
    let args = json!({"request_id":"restart-id", "cmd":format!("{python} -c \"import time; time.sleep(3); print('recovered')\""),"timeout_ms":60000});
    let request = |name: &str, args: Value| fixture::request(name,args,"restart-chat");
    let accepted: Value = client.post(&url).json(&request("start_exec_task", args.clone())).send().await.unwrap().json().await.unwrap();
    let id = accepted["result"]["structuredContent"]["job_id"].as_str().unwrap().to_owned();
    // Explicitly release the old HTTP pool before shutdown; shadowing a Client
    // does not drop it and can leave idle transport state alive until scope exit.
    drop(client);
    stop.send(()).unwrap(); handle.await.unwrap();
    let after_await_inode = loopback_listener_inode(port);
    eprintln!(
        "[issue62-inode] phase=after-await port={port} initial={initial_listener_inode:?} after={after_await_inode:?} same={}",
        initial_listener_inode.is_some() && initial_listener_inode == after_await_inode
    );
    let restarted = start_listener(port);
    if restarted.is_err() {
        let after_failure_inode = loopback_listener_inode(port);
        eprintln!(
            "[issue62-inode] phase=rebind-failed port={port} initial={initial_listener_inode:?} current={after_failure_inode:?} same={}",
            initial_listener_inode.is_some() && initial_listener_inode == after_failure_inode
        );
    }
    let (stop, handle) = restarted.expect("same-port restart after completed shutdown");
    // A restarted HTTP listener invalidates the old keep-alive connection. Use a
    // new client exactly as a reconnecting MCP client would, without resubmitting
    // with a fresh idempotency key or changing the operation assertions.
    let client = fixture::client();
    let retry: Value = client.post(&url).json(&request("start_exec_task", args)).send().await.unwrap().json().await.unwrap();
    assert_eq!(retry["result"]["structuredContent"]["job_id"], id);
    assert_eq!(retry["result"]["structuredContent"]["deduplicated"], true);
    let until = Instant::now() + Duration::from_secs(65);
    loop {
        let polled: Value = client.post(&url).json(&request("get_exec_task",json!({"job_id":id}))).send().await.unwrap().json().await.unwrap();
        let job = &polled["result"]["structuredContent"];
        assert_eq!(job["ok"], true, "{polled}");
        if job["terminal"] == true {
            assert_eq!(job["status"], "succeeded", "{polled}");
            assert!(job["stdout"]["text"].as_str().unwrap().contains("recovered"));
            assert_eq!(job["restart_recoverable"], true);
            break;
        }
        assert!(Instant::now() < until, "{polled}");
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    drop(client);
    stop.send(()).unwrap(); handle.await.unwrap();
}
