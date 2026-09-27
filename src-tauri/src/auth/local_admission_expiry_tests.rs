//! A ticket cannot stay valid merely because its final commit waited on a lock.
use super::*;
use crate::auth::principal;
use serde_json::json;
use std::{sync::mpsc, time::Duration};

#[test]
fn local_ticket_expiring_while_authorization_lock_is_held_cannot_commit() {
    let root = tempfile::tempdir().unwrap();
    let harness = tempfile::tempdir().unwrap();
    let service = Arc::new(ChatAuthorizer::default());
    let profile = "expiry-lock-test";
    service
        .attach_storage(profile, root.path(), harness.path())
        .unwrap();
    let token = principal::issue(
        "https://mcp.example",
        "https://mcp.example",
        "fixture-key",
        "client",
        3600,
    )
    .unwrap();
    let principal = principal::verify(
        &token,
        "fixture-key",
        "https://mcp.example",
        "https://mcp.example",
    )
    .unwrap();
    let mut request = RemoteRequest::verified(
        profile,
        "workspace",
        principal,
        &json!({"openai/session": "expiry-lock"}),
        "fixture-key",
    );
    request.service = service.clone();
    let pending = service.request(&request, &json!({"scopes": ["exec.run"]}));
    service
        .decide(
            profile,
            pending["authorization"]["id"].as_str().unwrap(),
            true,
            &["exec.run".to_owned()],
        )
        .unwrap();
    let gate = crate::runtime::WorkspaceExecutionGate::shared();
    let mut ticket = service
        .issue_local_admission_ticket(&request, &["exec.run"], &gate)
        .unwrap();
    ticket.expires = Instant::now() + Duration::from_millis(100);
    let state = service.state.lock().unwrap();
    let clone = service.clone();
    let clone_gate = gate.clone();
    let (ready_tx, ready_rx) = mpsc::channel();
    let worker = std::thread::spawn(move || {
        ready_tx.send(()).unwrap();
        clone.commit_local_admission(&request, &clone_gate, ticket)
    });
    ready_rx.recv_timeout(Duration::from_secs(1)).unwrap();
    std::thread::sleep(Duration::from_millis(250));
    drop(state);
    assert_eq!(
        worker.join().unwrap().err(),
        Some("LOCAL_ADMISSION_EXPIRED")
    );
    assert_eq!(gate.snapshot().in_flight, 0);
    assert_eq!(
        service
            .state
            .lock()
            .unwrap()
            .flights
            .get(profile)
            .copied()
            .unwrap_or(0),
        0
    );
}
