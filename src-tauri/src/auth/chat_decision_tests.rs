//! Deterministic pending-deadline tests at the actual mutex-protected decision.
//! Synthetic identities only; no production secret or wall-clock sleeps.
use super::*;

fn pending() -> (Arc<ChatAuthorizer>, RemoteRequest, String, Instant) {
    let service = Arc::new(ChatAuthorizer::default());
    let principal = VerifiedPrincipal {
        issuer: "https://fixture.example".into(), subject: "desktop-owner".into(),
        client_id: "fixture-client".into(), expires_at: unix_now() + 3600, family_id: None,
    };
    let mut request = RemoteRequest::verified("decision-boundary", "fixture-workspace",
        principal, &json!({"openai/session": "fixture-chat"}), "fixture-secret");
    request.service = service.clone();
    let response = service.request(&request, &json!({"scopes": ["files.read"]}));
    let id = response["authorization"]["id"].as_str().unwrap().to_owned();
    let since = service.state.lock().unwrap().records[request.binding.as_ref().unwrap()].since;
    (service, request, id, since)
}

#[test]
fn decision_rechecks_deadline_after_an_earlier_successful_reconciliation() {
    for elapsed in [PENDING, PENDING + 1] {
        let (service, request, id, since) = pending();
        service.reconcile(&request.profile);
        let mut events = service.subscribe();
        let mut state = service.state.lock().unwrap();
        let key = request.binding.as_ref().unwrap();
        assert_eq!(state.records[key].view.status, "pending");
        let original = state.records[key].view.clone();
        // The time between reconciliation and acquiring the decision mutex can
        // cross the deadline. Pass that instant to the production decision core.
        assert!(service.decide_locked(&mut state, &request.profile, &id, true,
            &["files.read".into()], since + Duration::from_secs(elapsed)).is_err());
        assert_eq!(state.records[key].view.status, "expired");
        assert_eq!(state.records[key].view.scopes, original.scopes);
        assert_eq!(state.records[key].view.expires_at, original.expires_at);
        assert_eq!(state.owners[&request.profile].phase, Phase::Draining);
        assert_eq!(events.try_recv().unwrap().kind, "changed");
        assert!(events.try_recv().is_err());
    }
}

#[test]
fn approval_before_deadline_still_requires_nonempty_requested_scope_subset() {
    let (service, request, id, since) = pending();
    let mut state = service.state.lock().unwrap();
    let now = since + Duration::from_secs(PENDING) - Duration::from_nanos(1);
    for scopes in [vec![], vec!["exec.run".into()]] {
        assert!(service.decide_locked(&mut state, &request.profile, &id, true, &scopes, now).is_err());
        assert_eq!(state.records[request.binding.as_ref().unwrap()].view.status, "pending");
    }
    service.decide_locked(&mut state, &request.profile, &id, true, &["files.read".into()], now).unwrap();
    assert_eq!(state.records[request.binding.as_ref().unwrap()].view.status, "active");
    assert_eq!(state.owners[&request.profile].phase, Phase::Active);
}

#[test]
fn stale_id_or_expired_denial_cannot_change_a_successor() {
    let (service, request, id, since) = pending();
    let mut state = service.state.lock().unwrap();
    let revision = state.revision;
    assert!(service.decide_locked(&mut state, &request.profile, "not-the-request", true,
        &["files.read".into()], since).is_err());
    assert_eq!(state.revision, revision);
    assert!(service.decide_locked(&mut state, &request.profile, &id, false, &[],
        since + Duration::from_secs(PENDING)).is_err());
    assert_eq!(state.records[request.binding.as_ref().unwrap()].view.status, "expired");
    drop(state);
    service.reconcile(&request.profile);
    let next = service.request(&request, &json!({"scopes": ["files.read"]}));
    let next_id = next["authorization"]["id"].as_str().unwrap();
    assert_ne!(next_id, id);
    assert!(service.decide(&request.profile, &id, true, &["files.read".into()]).is_err());
    assert_eq!(service.status(&request)["authorization"]["id"], next_id);
    assert_eq!(service.status(&request)["authorization"]["status"], "pending");
}
