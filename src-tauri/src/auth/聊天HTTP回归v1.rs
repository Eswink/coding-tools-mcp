use serde_json::{json, Value};
use super::{PublicOrigin, chat_fixture as fixture};
use crate::workspace::{AuthConfig, RuntimeConfig};
#[tokio::test]
async fn http_conversations_require_separate_grants_and_cannot_observe_each_others_jobs() {
    let root = tempfile::tempdir().unwrap(); let profile = uuid::Uuid::new_v4().to_string();
    let reserve = std::net::TcpListener::bind("127.0.0.1:0").unwrap(); let port = reserve.local_addr().unwrap().port(); drop(reserve);
    let (stop,task) = crate::mcp::spawn_listener_with_origin(port,root.path().into(),profile.clone(),
        AuthConfig { oauth_client_id:"test-client".into(), ..Default::default() },PublicOrigin::managed(fixture::ORIGIN).unwrap(),
        None,Some("password".into()),Some(fixture::KEY.into()),RuntimeConfig::default()).unwrap();
    let client = fixture::client(); let url = format!("http://127.0.0.1:{port}/mcp");
    async fn invoke(client:&reqwest::Client,url:&str,name:&str,args:Value,session:&str)->Value {
        let value: Value = client.post(url).json(&fixture::request(name,args,session)).send().await.unwrap().json().await.unwrap();
        value["result"]["structuredContent"].clone()
    }
    assert_eq!(invoke(&client,&url,"server_info",json!({}),"A").await["ok"],false);
    fixture::approve(&profile,root.path(),"A");
    assert_eq!(invoke(&client,&url,"server_info",json!({}),"A").await["ok"],true);
    assert_eq!(invoke(&client,&url,"server_info",json!({"_meta":{"openai/session":"A"}}),"B").await["ok"],false);
    let started = invoke(&client,&url,"start_exec_task",json!({"cmd":"echo chat-A-only","request_id":"same-key"}),"A").await;
    assert_eq!(started["ok"],true,"{started}"); let id = started["job_id"].clone();
    fixture::approve(&profile,root.path(),"B");
    assert_eq!(invoke(&client,&url,"list_exec_tasks",json!({}),"B").await["jobs"],json!([]));
    assert_eq!(invoke(&client,&url,"get_exec_task",json!({"job_id":id}),"B").await["ok"],false);
    assert_eq!(invoke(&client,&url,"cancel_exec_task",json!({"job_id":id}),"B").await["ok"],false);
    let until = std::time::Instant::now() + std::time::Duration::from_secs(10);
    loop {
        let v = invoke(&client,&url,"get_exec_task",json!({"job_id":id}),"A").await;
        if v["terminal"] == true { assert_eq!(v["status"],"succeeded","{v}"); break; }
        assert!(std::time::Instant::now() < until,"{v}"); tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }
    super::chat::service().revoke(&profile,None);
    assert_eq!(invoke(&client,&url,"get_exec_task",json!({"job_id":id}),"A").await["ok"],false);
    drop(client);stop.send(()).unwrap();task.await.unwrap();
}
#[tokio::test]
async fn noauth_listener_discovery_does_not_authorize_business_or_self_approval() {
    let root = tempfile::tempdir().unwrap();
    let reserve = std::net::TcpListener::bind("127.0.0.1:0").unwrap(); let port = reserve.local_addr().unwrap().port(); drop(reserve);
    let (stop,task) = crate::mcp::spawn_listener_with_origin(port,root.path().into(),uuid::Uuid::new_v4().to_string(),
        AuthConfig { auth_type:"noauth".into(),..Default::default() },PublicOrigin::managed("").unwrap(),None,None,None,RuntimeConfig::default()).unwrap();
    let client = fixture::client();let url = format!("http://127.0.0.1:{port}/mcp");
    for name in ["server_info","request_chat_authorization","exec_command"] {
        let v: Value = client.post(&url).json(&fixture::request(name,json!({}),"A")).send().await.unwrap().json().await.unwrap();
        assert_eq!(v["result"]["structuredContent"]["ok"],false,"{v}");
    }
    drop(client);stop.send(()).unwrap();task.await.unwrap();
}
