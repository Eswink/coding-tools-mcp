use serde_json::{json, Value};

use super::{chat_fixture as fixture, PublicOrigin};
use crate::workspace::{AuthConfig, RuntimeConfig};

fn value_contains_secret(value: &Value, secret: &str) -> bool {
    if secret.is_empty() {
        return false;
    }
    match value {
        Value::String(text) => text.contains(secret),
        Value::Array(values) => values.iter().any(|value| value_contains_secret(value, secret)),
        Value::Object(values) => values.values().any(|value| value_contains_secret(value, secret)),
        _ => false,
    }
}

fn assert_no_workspace_secrets(value: &Value, secrets: &[String]) {
    for secret in secrets {
        assert!(
            !value_contains_secret(value, secret),
            "response leaked workspace-specific value {secret:?}: {value}"
        );
    }
}

async fn invoke(client: &reqwest::Client, url: &str, name: &str, session: &str) -> Value {
    let response = client
        .post(url)
        .json(&fixture::request(name, json!({}), session))
        .send()
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    let value: Value = response.json().await.unwrap();
    value["result"]["structuredContent"].clone()
}

#[tokio::test]
async fn foreign_owner_is_non_disclosing_online_and_offline() {
    let root = tempfile::tempdir().unwrap();
    let profile = uuid::Uuid::new_v4().to_string();
    let reserve = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = reserve.local_addr().unwrap().port();
    drop(reserve);

    let (stop, task, execution_gate) =
        crate::mcp::spawn_listener_with_origin_and_execution_gate(
            port,
            root.path().into(),
            profile.clone(),
            AuthConfig { oauth_client_id: "test-client".into(), ..Default::default() },
            PublicOrigin::managed(fixture::ORIGIN).unwrap(),
            None,
            Some("password".into()),
            Some(fixture::KEY.into()),
            RuntimeConfig::default(),
        )
        .unwrap();
    let client = fixture::client();
    let url = format!("http://127.0.0.1:{port}/mcp");

    fixture::approve(&profile, root.path(), "A");
    let owner = invoke(&client, &url, "auth_status", "A").await;
    let secrets = vec![
        root.path().display().to_string(),
        profile.clone(),
        owner["authorization"]["id"].as_str().unwrap().to_owned(),
        owner["authorization"]["fingerprint"].as_str().unwrap().to_owned(),
    ];

    let mut events = super::chat::service().subscribe();
    for name in ["auth_status", "server_info", "request_chat_authorization", "list_exec_tasks"] {
        let blocked = invoke(&client, &url, name, "B").await;
        assert_eq!(blocked["error"]["code"], "EXCLUSIVE_CHAT_LOCKED", "{name}: {blocked}");
        assert!(blocked.get("authorization").is_none(), "{name}: {blocked}");
        assert_no_workspace_secrets(&blocked, &secrets);
    }
    assert!(events.try_recv().is_err());

    execution_gate.pause().unwrap();
    for name in ["auth_status", "server_info", "request_chat_authorization", "list_exec_tasks"] {
        let blocked = invoke(&client, &url, name, "B").await;
        assert_eq!(blocked["error"]["code"], "EXCLUSIVE_CHAT_LOCKED", "{name}: {blocked}");
        assert_ne!(blocked["error"]["code"], "WORKSPACE_OFFLINE");
        assert!(blocked.get("authorization").is_none(), "{name}: {blocked}");
        assert_no_workspace_secrets(&blocked, &secrets);
    }

    for _ in 0..100 {
        let blocked = invoke(&client, &url, "request_chat_authorization", "B").await;
        assert_eq!(blocked["error"]["code"], "EXCLUSIVE_CHAT_LOCKED");
        assert!(blocked.get("authorization").is_none());
        assert_no_workspace_secrets(&blocked, &secrets);
    }
    assert!(events.try_recv().is_err());
    assert_eq!(
        super::chat::service().snapshot(&profile)["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );

    execution_gate.resume().unwrap();
    drop(client);
    stop.send(()).unwrap();
    task.await.unwrap();
}

#[tokio::test]
async fn unapproved_offline_chat_and_control_plane_do_not_disclose_workspace_state() {
    let root = tempfile::tempdir().unwrap();
    let profile = uuid::Uuid::new_v4().to_string();
    let reserve = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = reserve.local_addr().unwrap().port();
    drop(reserve);

    let (stop, task, execution_gate) =
        crate::mcp::spawn_listener_with_origin_and_execution_gate(
            port,
            root.path().into(),
            profile.clone(),
            AuthConfig { oauth_client_id: "test-client".into(), ..Default::default() },
            PublicOrigin::managed(fixture::ORIGIN).unwrap(),
            None,
            Some("password".into()),
            Some(fixture::KEY.into()),
            RuntimeConfig::default(),
        )
        .unwrap();
    let client = fixture::client();
    let url = format!("http://127.0.0.1:{port}/mcp");
    let secrets = vec![root.path().display().to_string(), profile.clone()];

    execution_gate.pause().unwrap();

    let status = invoke(&client, &url, "auth_status", "C").await;
    assert_eq!(status["authorization"]["status"], "unauthorized");
    assert_no_workspace_secrets(&status, &secrets);

    for name in ["server_info", "list_exec_tasks"] {
        let blocked = invoke(&client, &url, name, "C").await;
        assert_eq!(blocked["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED", "{name}: {blocked}");
        assert_ne!(blocked["error"]["code"], "WORKSPACE_OFFLINE");
        assert_no_workspace_secrets(&blocked, &secrets);
    }

    for method in ["initialize", "ping", "tools/list"] {
        let body = json!({"jsonrpc":"2.0","id":17,"method":method,"params":{}});
        let response = client.post(&url).json(&body).send().await.unwrap();
        assert_eq!(response.status(), 200, "{method}");
        let value: Value = response.json().await.unwrap();
        assert_no_workspace_secrets(&value, &secrets);
    }

    execution_gate.resume().unwrap();
    drop(client);
    stop.send(()).unwrap();
    task.await.unwrap();
}
