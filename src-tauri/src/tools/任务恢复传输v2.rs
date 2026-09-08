use std::time::{Duration, Instant};
use serde_json::{json, Value};
use crate::auth::PublicOrigin;
use crate::workspace::{AuthConfig, RuntimeConfig};

#[tokio::test]
async fn listener_restart_keeps_the_running_job_and_its_idempotency_key() {
    let root = tempfile::tempdir().unwrap();
    let profile = uuid::Uuid::new_v4().to_string();
    let port = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
    let start_listener = || crate::mcp::spawn_listener_with_origin(port, root.path().to_path_buf(), profile.clone(),
        AuthConfig {auth_type:"noauth".into(),..Default::default()}, PublicOrigin::managed("").unwrap(),
        None,None,None,RuntimeConfig::default()).unwrap();
    let (stop, handle) = start_listener();
    let client = reqwest::Client::builder().timeout(Duration::from_secs(10)).no_proxy().build().unwrap();
    let url = format!("http://127.0.0.1:{port}/mcp");
    let python = if cfg!(windows) {"python"} else {"python3"};
    let args = json!({"request_id":"restart-id", "cmd":format!("{python} -c \"import time; time.sleep(3); print('recovered')\""),"timeout_ms":60000});
    let request = |name: &str, args: Value| json!({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}});
    let accepted: Value = client.post(&url).json(&request("start_exec_task", args.clone())).send().await.unwrap().json().await.unwrap();
    let id = accepted["result"]["structuredContent"]["job_id"].as_str().unwrap().to_owned();
    stop.send(()).unwrap(); handle.await.unwrap();
    let (stop, handle) = start_listener();
    // A restarted HTTP listener invalidates the old keep-alive connection. Use a
    // new client exactly as a reconnecting MCP client would, without resubmitting
    // with a fresh idempotency key or changing the operation assertions.
    let client = reqwest::Client::builder().timeout(Duration::from_secs(10)).no_proxy().build().unwrap();
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
    stop.send(()).unwrap(); handle.await.unwrap();
}
