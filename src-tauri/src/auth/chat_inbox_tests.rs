//! The inbox is trusted local state, not a collection of independently versioned rows.
use super::*;

fn add(service: &Arc<ChatAuthorizer>, profile: &str) -> RemoteRequest {
    let principal = VerifiedPrincipal { issuer: "https://fixture.example".into(),
        subject: "desktop-owner".into(), client_id: "fixture-client".into(),
        expires_at: unix_now() + 3600, family_id: None };
    let mut req = RemoteRequest::verified(profile, "fixture-workspace", principal,
        &json!({"openai/session": "fixture-session"}), "fixture-secret");
    req.service = service.clone();
    assert_eq!(service.request(&req, &json!({}))["ok"], true);
    req
}

#[test]
fn empty_workspace_selection_keeps_the_global_revision() {
    let service = Arc::new(ChatAuthorizer::default());
    let req = add(&service, "removed-workspace");
    let before = service.pending_inbox(&BTreeSet::from([req.profile.clone()])).unwrap();
    assert!(before.revision > 0);
    assert_eq!(before.entries.len(), 1);
    // Mirrors deletion of the final workspace: revoke its grants then remove
    // the profile from the local list. The UI must accept the empty snapshot.
    service.revoke(&req.profile, None);
    let after = service.pending_inbox(&BTreeSet::new()).unwrap();
    assert!(after.entries.is_empty());
    assert!(after.revision > before.revision);
}

#[test]
fn inbox_filters_nonselected_and_expired_requests_without_mutating_permissions() {
    let service = Arc::new(ChatAuthorizer::default());
    let a = add(&service, "inbox-A");
    let b = add(&service, "inbox-B");
    let selected = BTreeSet::from([a.profile.clone()]);
    let first = service.pending_inbox(&selected).unwrap();
    assert_eq!(first.entries.len(), 1);
    assert_eq!(first.entries[0].profile, a.profile);
    assert!(first.entries[0].exclusive);
    service.state.lock().unwrap().records.get_mut(a.binding.as_ref().unwrap()).unwrap()
        .since -= Duration::from_secs(PENDING);
    let expired = service.pending_inbox(&selected).unwrap();
    assert!(expired.entries.is_empty());
    assert!(expired.revision > first.revision);
    assert_eq!(service.status(&b)["authorization"]["status"], "pending");
    assert!(service.permit(&b, &["files.read"]).is_err());
}

#[test]
fn inbox_is_bounded_and_all_rows_share_its_state_revision() {
    let service = Arc::new(ChatAuthorizer::default());
    let mut profiles = BTreeSet::new();
    for n in 0..256 {
        let profile = format!("inbox-capacity-{n}");
        add(&service, &profile);
        profiles.insert(profile);
    }
    let snapshot = service.pending_inbox(&profiles).unwrap();
    assert_eq!(snapshot.entries.len(), 256);
    assert_eq!(snapshot.revision, service.state.lock().unwrap().revision);
    add(&service, "inbox-overflow");
    profiles.insert("inbox-overflow".into());
    assert!(service.pending_inbox(&profiles).is_err());
}
