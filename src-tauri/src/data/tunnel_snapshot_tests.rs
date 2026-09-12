use super::*;

fn fixture() -> (DataStore, WorkspaceProfile) {
    let profile = WorkspaceProfile::new("snapshot-fixture".into(), None);
    let data = AppData { profiles: vec![profile.clone()], ..Default::default() };
    (DataStore { data: data.clone(), baseline: data }, profile)
}

#[test]
fn route_and_credential_share_one_snapshot_and_rollback() {
    let (mut store, mut next) = fixture();
    let baseline = store.data.clone();
    next.tunnel.public_url = "https://updated.example".into();
    store.stage_profile_update(next.clone(), Some(("cloudflare_token", "snapshot-canary"))).unwrap();
    let writes = std::cell::Cell::new(0);
    assert!(store.commit_snapshot(baseline.clone(), |candidate| {
        writes.set(writes.get() + 1);
        assert_eq!(candidate.profiles[0].tunnel.public_url, "https://updated.example");
        assert_eq!(candidate.workspace_secrets[&next.id]["cloudflare_token"], "snapshot-canary");
        Err(AppError::Message("injected write failure".into()))
    }).is_err());
    assert_eq!(writes.get(), 1);
    assert_eq!(serde_json::to_value(&store.data).unwrap(), serde_json::to_value(&baseline).unwrap());
}

#[test]
fn missing_workspace_never_stages_a_credential() {
    let (mut store, mut next) = fixture();
    let before = serde_json::to_value(&store.data).unwrap();
    next.id = "not-present".into();
    assert!(store.stage_profile_update(next, Some(("frp_token", "not-stored"))).is_err());
    assert_eq!(serde_json::to_value(&store.data).unwrap(), before);
}
