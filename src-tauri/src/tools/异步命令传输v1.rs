use std::time::{Duration, Instant};
use serde_json::{json, Value};
use crate::auth::{PublicOrigin, chat_fixture as fixture};
use crate::tools::policy::PolicySettings;
use crate::workspace::{AuthConfig, RuntimeConfig};

#[cfg(windows)]
const PYTHON: &str = "python";
#[cfg(not(windows))]
const PYTHON: &str = "python3";

fn port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port()
}

fn client() -> reqwest::Client {
    fixture::client()
}

fn request(tool: &str, args: Value) -> Value {
    fixture::request(tool,args,"lost-response-chat")
}

#[tokio::test]
async fn mcp_lost_submit_body_is_recovered_from_a_new_http_connection() {
    let root = tempfile::tempdir().unwrap();
    let port = port();
    let profile = uuid::Uuid::new_v4().to_string();
    fixture::approve(&profile,root.path(),"lost-response-chat");
    let (stop, handle) = crate::mcp::spawn_listener_with_origin(
        port, root.path().to_path_buf(), profile,
        AuthConfig { auth_type:"oauth".into(), oauth_client_id:"test-client".into(), ..Default::default() },
        PublicOrigin::managed(fixture::ORIGIN).unwrap(), None, Some("test-password".into()), Some(fixture::KEY.into()), RuntimeConfig::default(),
    ).unwrap();
    let url = format!("http://127.0.0.1:{port}/mcp");
    let args = json!({"request_id":"lost-http-response", "timeout_ms":5000,
        "cmd":format!("{PYTHON} -c \"import time; time.sleep(1); print('survived-disconnect')\"")});
    let original = client();
    // The server has accepted the request; lose the response body, not the underlying job.
    let response = original.post(&url).json(&request("start_exec_task", args.clone())).send().await.unwrap();
    assert!(response.status().is_success());
    drop(response); drop(original);
    let fresh = client();
    let listed: Value = fresh.post(&url).json(&request("list_exec_tasks", json!({"request_id":"lost-http-response"})))
        .send().await.unwrap().json().await.unwrap();
    let jobs = listed["result"]["structuredContent"]["jobs"].as_array().unwrap();
    assert_eq!(jobs.len(), 1, "{listed}");
    let id = jobs[0]["job_id"].as_str().unwrap();
    let retry: Value = fresh.post(&url).json(&request("start_exec_task", args))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(retry["result"]["structuredContent"]["job_id"], id);
    assert_eq!(retry["result"]["structuredContent"]["deduplicated"], true);
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        let r: Value = fresh.post(&url).json(&request("get_exec_task", json!({"job_id":id})))
            .send().await.unwrap().json().await.unwrap();
        let task = &r["result"]["structuredContent"];
        if task["terminal"] == true {
            assert_eq!(task["status"], "succeeded", "{r}");
            assert!(task["stdout"]["text"].as_str().unwrap().contains("survived-disconnect"));
            break;
        }
        assert!(Instant::now() < deadline, "{r}");
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    stop.send(()).unwrap(); handle.await.unwrap();
}

#[tokio::test]
async fn read_only_mcp_does_not_expose_submission_or_native_tasks_capability() {
    let root = tempfile::tempdir().unwrap();
    let port = port();
    let (stop, handle) = crate::mcp::spawn_listener_with_origin(
        port, root.path().to_path_buf(), uuid::Uuid::new_v4().to_string(),
        AuthConfig { auth_type:"noauth".into(), ..Default::default() },
        PublicOrigin::managed("").unwrap(), None, None, None,
        RuntimeConfig { tool_profile:"read-only".into(), ..Default::default() },
    ).unwrap();
    let url = format!("http://127.0.0.1:{port}/mcp");
    let client = client();
    let init: Value = client.post(&url).json(&json!({"jsonrpc":"2.0","id":1,"method":"initialize"}))
        .send().await.unwrap().json().await.unwrap();
    assert!(init["result"]["capabilities"].get("tasks").is_none());
    let listed: Value = client.post(&url).json(&json!({"jsonrpc":"2.0","id":2,"method":"tools/list"}))
        .send().await.unwrap().json().await.unwrap();
    let tools = listed["result"]["tools"].as_array().unwrap();
    assert!(tools.iter().any(|t|t["name"]=="get_exec_task"));
    assert!(!tools.iter().any(|t|t["name"]=="start_exec_task" || t["name"]=="cancel_exec_task"));
    let denied: Value = client.post(&url).json(&request("start_exec_task",json!({"cmd":"echo denied","request_id":"r"})))
        .send().await.unwrap().json().await.unwrap();
    assert_eq!(denied["error"]["code"], -32602);
    stop.send(()).unwrap(); handle.await.unwrap();
}

#[tokio::test]
async fn actions_cannot_bypass_conversation_approval_and_marks_submission_consequential() {
    let root = tempfile::tempdir().unwrap();
    let port = port();
    let (stop, handle) = crate::actions::spawn_listener_with_origin(
        &uuid::Uuid::new_v4().to_string(), port, root.path().to_path_buf(),
        PublicOrigin::managed("").unwrap(), "none".into(), None, String::new(), None, None, None,
        PolicySettings::default(),
    ).unwrap();
    let url = format!("http://127.0.0.1:{port}");
    let client = client();
    let schema: Value = client.get(format!("{url}/openapi.json")).send().await.unwrap().json().await.unwrap();
    assert_eq!(schema["paths"]["/actions/start_exec_task"]["post"]["x-openai-isConsequential"], true);
    assert_eq!(schema["paths"]["/actions/get_exec_task"]["post"]["x-openai-isConsequential"], false);
    let response = client.post(format!("{url}/actions/start_exec_task"))
        .json(&json!({"cmd":"echo actions-async", "request_id":"actions-job"}))
        .send().await.unwrap();
    let status = response.status();
    let body = response.text().await.unwrap();
    assert_eq!(status, reqwest::StatusCode::UNPROCESSABLE_ENTITY, "{body}");
    let denied: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(denied["structured_content"]["error"]["code"],"CHAT_AUTHORIZATION_REQUIRED");
    assert_eq!(std::fs::read_dir(root.path()).unwrap().count(),0);
    stop.send(()).unwrap(); handle.await.unwrap();
}
