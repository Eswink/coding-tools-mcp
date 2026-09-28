//! Test-only listener ownership handoff. Never reserve/drop/rebind a port.
use std::net::{IpAddr, Ipv4Addr, TcpListener};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use crate::auth::PublicOrigin;
use crate::runtime::WorkspaceExecutionGate;
use crate::workspace::{AuthConfig, RuntimeConfig};

use super::{spawn_listener_with_binding, ShutdownSender};

#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_listener_from_bound(
    listener: TcpListener,
    workspace_path: PathBuf,
    workspace_id: String,
    auth: AuthConfig,
    public_base_url: PublicOrigin,
    oauth_client_secret: Option<String>,
    oauth_password: Option<String>,
    oauth_token_secret: Option<String>,
    runtime: RuntimeConfig,
) -> Result<
    (ShutdownSender, tauri::async_runtime::JoinHandle<()>, Arc<WorkspaceExecutionGate>),
    String,
> {
    let address = listener.local_addr().map_err(|err| err.to_string())?;
    if address.ip() != IpAddr::V4(Ipv4Addr::LOCALHOST) {
        return Err("test listener must use IPv4 loopback".into());
    }
    // local_addr, Origin/OAuth resolution, logging and the served socket all use
    // the same bound endpoint. Ownership moves into Tokio without closing it.
    spawn_listener_with_binding(
        address.port(),
        workspace_path,
        workspace_id,
        auth,
        public_base_url,
        oauth_client_secret,
        oauth_password,
        oauth_token_secret,
        runtime,
        move || {
            listener.set_nonblocking(true).map_err(|err| err.to_string())?;
            tokio::net::TcpListener::from_std(listener).map_err(|err| err.to_string())
        },
    )
}

#[tokio::test]
async fn requested_port_conflict_still_fails_synchronously() {
    let root = tempfile::tempdir().unwrap();
    // The competing owner itself asks the OS for its port and stays alive.
    // This regression must not introduce another reserve/drop/rebind race.
    let competing_owner = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = competing_owner.local_addr().unwrap();
    let result = super::spawn_listener_with_origin_and_execution_gate(
        address.port(),
        root.path().into(),
        uuid::Uuid::new_v4().to_string(),
        AuthConfig { auth_type: "noauth".into(), ..Default::default() },
        PublicOrigin::managed("").unwrap(),
        None,
        None,
        None,
        RuntimeConfig::default(),
    );
    let error = match result {
        Err(error) => error,
        Ok((stop, task, _gate)) => {
            let _ = stop.send(());
            tokio::time::timeout(Duration::from_secs(5), task)
                .await.expect("listener shutdown timed out").unwrap();
            panic!("an occupied requested port must not report startup success");
        }
    };
    assert!(error.contains(&format!("MCP 本地端口 {} 绑定失败", address.port())), "{error}");
    // No alternate port, retry or deferred background error is accepted.
    assert_eq!(competing_owner.local_addr().unwrap(), address);
}

#[tokio::test]
async fn retained_socket_stays_owned_and_serves_the_same_endpoint() {
    let root = tempfile::tempdir().unwrap();
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = listener.local_addr().unwrap();
    assert!(TcpListener::bind(address).is_err(), "reserved socket was not exclusive");
    let (stop, task, _gate) = spawn_listener_from_bound(
        listener,
        root.path().into(),
        uuid::Uuid::new_v4().to_string(),
        AuthConfig { auth_type: "noauth".into(), ..Default::default() },
        PublicOrigin::managed("").unwrap(),
        None,
        None,
        None,
        RuntimeConfig::default(),
    ).unwrap();
    assert!(TcpListener::bind(address).is_err(), "handoff released the reserved socket");
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(5))
        .build().unwrap();
    let response = client.get(format!("http://{address}/mcp")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    let body: serde_json::Value = response.json().await.unwrap();
    assert_eq!(body["name"], "coding-tools-mcp");
    drop(client);
    stop.send(()).unwrap();
    tokio::time::timeout(Duration::from_secs(5), task)
        .await.expect("listener shutdown timed out").unwrap();
}
