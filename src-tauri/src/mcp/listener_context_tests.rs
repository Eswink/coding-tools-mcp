//! Real native listener tests; no reserve/drop/rebind and no fake HTTP service.
use super::*;
use crate::tools::listener_context::{ListenerContextLease, ListenerLeaseError};
use std::{net::{Ipv4Addr, SocketAddr, TcpListener}, time::Duration};

type Running = (
    tempfile::TempDir,
    SocketAddr,
    ShutdownSender,
    tauri::async_runtime::JoinHandle<()>,
    Arc<crate::runtime::WorkspaceExecutionGate>,
    ListenerContextLease,
);

fn start() -> Running {
    let root = tempfile::tempdir().unwrap();
    let socket = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = socket.local_addr().unwrap();
    let (stop, task, gate, lease) = spawn_listener_with_lease_binding(
        address.port(),
        root.path().into(),
        uuid::Uuid::new_v4().to_string(),
        AuthConfig { auth_type: "noauth".into(), ..Default::default() },
        PublicOrigin::managed("").unwrap(),
        None, None, None, RuntimeConfig::default(),
        move || {
            socket.set_nonblocking(true).map_err(|e| e.to_string())?;
            tokio::net::TcpListener::from_std(socket).map_err(|e| e.to_string())
        },
    ).unwrap();
    (root, address, stop, task, gate, lease)
}

async fn stop(stop: ShutdownSender, task: tauri::async_runtime::JoinHandle<()>, lease: &ListenerContextLease) {
    let _ = stop.send(());
    tokio::time::timeout(Duration::from_secs(5), task).await.expect("listener did not stop").unwrap();
    tokio::time::timeout(Duration::from_secs(2), lease.wait_closed()).await.unwrap();
    assert!(!lease.is_live());
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}

#[tokio::test]
async fn actual_listener_context_shares_pause_and_never_replaces_the_bound_socket() {
    let (_root, address, shutdown, task, gate, lease) = start();
    assert!(TcpListener::bind(address).is_err());
    lease.with_live(|ctx| assert!(Arc::ptr_eq(&ctx.execution_gate(), &gate))).unwrap();
    let paused = gate.pause().unwrap();
    lease.with_live(|ctx| {
        let state = ctx.execution_gate().snapshot();
        assert_eq!(state.generation, paused.generation);
        assert_eq!(state.availability, crate::runtime::ExecutionAvailability::Offline);
    }).unwrap();
    let client = reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(5)).build().unwrap();
    let response = client.get(format!("http://{address}/mcp")).send().await.unwrap();
    assert_eq!(response.status(), 200);
    let data: serde_json::Value = response.json().await.unwrap();
    assert_eq!(data["name"], "coding-tools-mcp");
    drop(client);
    stop(shutdown, task, &lease).await;
    assert_eq!(gate.snapshot().generation, paused.generation);
}

#[tokio::test]
async fn actual_graceful_shutdown_closes_all_retained_context_observers() {
    let (_root, _address, shutdown, task, _gate, lease) = start();
    let first = lease.clone(); let second = lease.clone();
    let retained = lease.with_live(Arc::clone).unwrap();
    stop(shutdown, task, &lease).await;
    assert!(retained.workspace.root().is_dir());
    assert_eq!(first.with_live(|_| ()), Err(ListenerLeaseError::Closed));
    assert_eq!(second.with_live(|_| ()), Err(ListenerLeaseError::Closed));
}

#[tokio::test]
async fn actual_aborted_listener_task_closes_its_context_lease() {
    let (_root, _address, shutdown, task, _gate, lease) = start();
    task.abort();
    let outcome = tokio::time::timeout(Duration::from_secs(5), task).await.unwrap();
    assert!(outcome.is_err());
    tokio::time::timeout(Duration::from_secs(2), lease.wait_closed()).await.unwrap();
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
    drop(shutdown);
}

#[tokio::test]
async fn dropping_observers_does_not_stop_the_actual_listener() {
    let (_root, address, shutdown, task, _gate, lease) = start();
    drop(lease.clone());
    let copy = lease.clone();
    let waiter = tokio::spawn(async move { copy.wait_closed().await; });
    waiter.abort(); let _ = waiter.await;
    assert!(lease.is_live());
    let client = reqwest::Client::builder().no_proxy().timeout(Duration::from_secs(5)).build().unwrap();
    assert_eq!(client.get(format!("http://{address}/mcp")).send().await.unwrap().status(), 200);
    drop(client);
    stop(shutdown, task, &lease).await;
}
