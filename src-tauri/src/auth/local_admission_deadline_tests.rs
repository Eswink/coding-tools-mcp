use super::*;
use std::sync::{mpsc, TryLockError};
use std::thread;

struct Fixture {
    _root: tempfile::TempDir,
    request: RemoteRequest,
    gate: Arc<crate::runtime::WorkspaceExecutionGate>,
}

impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let service = Arc::new(ChatAuthorizer::default());
        let profile = uuid::Uuid::new_v4().to_string();
        service
            .attach_storage(&profile, root.path(), &root.path().join("harness"))
            .unwrap();
        let token = crate::auth::principal::issue(
            "https://mcp.example",
            "https://mcp.example",
            "deadline-fixture-key",
            "deadline-client",
            3600,
        )
        .unwrap();
        let principal = crate::auth::principal::verify(
            &token,
            "https://mcp.example",
            "https://mcp.example",
            "deadline-fixture-key",
            "deadline-client",
        )
        .unwrap();
        let mut request = RemoteRequest::verified(
            &profile,
            "workspace",
            principal,
            &json!({"openai/session": "deadline-test"}),
            "deadline-fixture-key",
        );
        request.service = service.clone();
        let response = service.request(&request, &json!({"scopes": ["exec.run"]}));
        assert_eq!(response["ok"], true, "{response}");
        service
            .decide(
                &profile,
                response["authorization"]["id"].as_str().unwrap(),
                true,
                &["exec.run".to_owned()],
            )
            .unwrap();
        Self {
            _root: root,
            request,
            gate: crate::runtime::WorkspaceExecutionGate::shared(),
        }
    }

    fn ticket(&self) -> LocalAdmissionTicket {
        self.request
            .service
            .issue_local_admission_ticket(&self.request, &["exec.run"], &self.gate)
            .unwrap()
    }

    fn assert_quiet(&self) {
        assert_eq!(self.gate.snapshot().in_flight, 0);
        assert_eq!(
            self.request
                .service
                .state
                .lock()
                .unwrap()
                .flights
                .get(&self.request.profile)
                .copied()
                .unwrap_or(0),
            0
        );
    }
}

#[test]
fn ticket_expiring_while_authorization_lock_is_held_is_rejected() {
    let fixture = Fixture::new();
    let mut ticket = fixture.ticket();
    ticket.expires = Instant::now() + Duration::from_secs(2);
    let expires = ticket.expires;
    let state = fixture.request.service.state.lock().unwrap();
    let touched = state.records[fixture.request.identity().unwrap()].touched;
    let request = fixture.request.clone();
    let gate = fixture.gate.clone();
    let (started_tx, started_rx) = mpsc::channel();
    let worker = thread::spawn(move || {
        started_tx.send(()).unwrap();
        request.service.commit_local_admission(&request, &gate, ticket).err()
    });
    // Always release locks before asserting on the joined worker.
    let started = started_rx.recv_timeout(Duration::from_secs(1)).is_ok();
    thread::sleep(expires.saturating_duration_since(Instant::now()) + Duration::from_millis(50));
    drop(state);
    let error = worker.join().unwrap();
    assert!(started, "worker did not enter before ticket expiry");
    assert_eq!(error, Some("LOCAL_ADMISSION_EXPIRED"));
    assert_eq!(
        fixture.request.service.state.lock().unwrap().records[fixture.request.identity().unwrap()].touched,
        touched,
        "expired admission must not refresh the idle lease"
    );
    fixture.assert_quiet();
}

#[test]
fn ticket_expiring_while_execution_gate_is_held_is_rejected() {
    let fixture = Fixture::new();
    let mut ticket = fixture.ticket();
    ticket.expires = Instant::now() + Duration::from_secs(2);
    let expires = ticket.expires;
    let touched = fixture.request.service.state.lock().unwrap().records[fixture.request.identity().unwrap()].touched;
    let hold = fixture.gate.hold_online().unwrap();
    let request = fixture.request.clone();
    let gate = fixture.gate.clone();
    let worker = thread::spawn(move || {
        request.service.commit_local_admission(&request, &gate, ticket).err()
    });
    let mut observed_wait = false;
    while Instant::now() < expires {
        match fixture.request.service.state.try_lock() {
            Err(TryLockError::WouldBlock) => {
                observed_wait = true;
                break;
            }
            Ok(state) => drop(state),
            Err(TryLockError::Poisoned(_)) => break,
        }
        thread::sleep(Duration::from_millis(5));
    }
    thread::sleep(expires.saturating_duration_since(Instant::now()) + Duration::from_millis(50));
    drop(hold);
    let error = worker.join().unwrap();
    assert!(observed_wait, "did not observe the authorization-to-execution lock handoff");
    assert_eq!(error, Some("LOCAL_ADMISSION_EXPIRED"));
    assert_eq!(
        fixture.request.service.state.lock().unwrap().records[fixture.request.identity().unwrap()].touched,
        touched,
        "expired admission must not refresh the idle lease"
    );
    fixture.assert_quiet();
}

#[test]
fn fresh_ticket_retains_exactly_one_live_local_permit() {
    let fixture = Fixture::new();
    let permit = fixture.request.service.commit_local_admission(
        &fixture.request,
        &fixture.gate,
        fixture.ticket(),
    ).unwrap();
    assert_eq!(fixture.gate.snapshot().in_flight, 1);
    drop(permit);
    fixture.assert_quiet();
}
