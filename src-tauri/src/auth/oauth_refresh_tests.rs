use super::*;
fn context() -> RefreshContext {
    RefreshContext::new("synthetic-client","https://example.test","https://example.test/mcp",
        "synthetic-signing-secret","synthetic-password",Some("synthetic-client-secret"),&SessionPolicy::default())
}
#[test]
fn rotates_persists_and_revokes_replayed_family() {
    let root=tempfile::tempdir().unwrap(); let ctx=context();
    let store=RefreshStore::shared(root.path().into()); let one=store.issue(&ctx).unwrap();
    let two=store.rotate(&ctx,&one.token,"","").unwrap();
    assert_ne!(*one.token,*two.token); assert_eq!(one.family_id,two.family_id); assert_eq!(one.expires_at,two.expires_at);
    let raw=std::fs::read_to_string(root.path().join("auth.json")).unwrap();
    assert!(!raw.contains(&*one.token)); assert!(!raw.contains(&*two.token)); assert!(!raw.contains("synthetic"));
    drop(store);
    let store=RefreshStore::shared(root.path().into()); assert!(store.valid_family(&ctx,&two.family_id));
    assert_eq!(store.rotate(&ctx,&one.token,"","").err(),Some(RefreshError::InvalidGrant));
    assert!(!store.valid_family(&ctx,&two.family_id));
    assert_eq!(store.rotate(&ctx,&two.token,"","").err(),Some(RefreshError::InvalidGrant));
}
#[test]
fn rejects_foreign_client_credentials_issuer_resource_and_forgery_without_revoking_owner() {
    let root=tempfile::tempdir().unwrap(); let store=RefreshStore::shared(root.path().into()); let ctx=context();
    let pair=store.issue(&ctx).unwrap();
    let mut foreign=ctx.clone(); foreign.client_id="other".into();
    assert_eq!(store.rotate(&foreign,&pair.token,"","").err(),Some(RefreshError::InvalidGrant));
    foreign=ctx.clone(); foreign.issuer="https://other.test".into();
    assert_eq!(store.rotate(&foreign,&pair.token,"","").err(),Some(RefreshError::InvalidGrant));
    foreign=ctx.clone(); foreign.resource="https://example.test/other".into();
    assert_eq!(store.rotate(&foreign,&pair.token,"","").err(),Some(RefreshError::InvalidGrant));
    let changed=RefreshContext::new(&ctx.client_id,&ctx.issuer,&ctx.resource,"different","pw",None,&ctx.policy);
    assert_eq!(store.rotate(&changed,&pair.token,"","").err(),Some(RefreshError::InvalidGrant));
    assert_eq!(store.rotate(&ctx,&pair.token,"https://other.test","").err(),Some(RefreshError::InvalidTarget));
    assert_eq!(store.rotate(&ctx,&pair.token,"","admin").err(),Some(RefreshError::InvalidScope));
    let forged=format!("{}.bad",pair.token.rsplit_once('.').unwrap().0);
    assert_eq!(store.rotate(&ctx,&forged,"","").err(),Some(RefreshError::InvalidGrant));
    assert!(store.valid_family(&ctx,&pair.family_id));
}
#[test]
fn concurrent_rotation_yields_one_pair_then_reuse_closes_family() {
    let root=tempfile::tempdir().unwrap(); let store=RefreshStore::shared(root.path().into()); let ctx=context();
    let one=store.issue(&ctx).unwrap(); let token=Arc::new(one.token); let barrier=Arc::new(std::sync::Barrier::new(8));
    let threads:Vec<_>=(0..8).map(|_| { let (s,c,t,b)=(store.clone(),ctx.clone(),token.clone(),barrier.clone());
        std::thread::spawn(move|| {b.wait();s.rotate(&c,&t,"","").is_ok()}) }).collect();
    assert_eq!(threads.into_iter().map(|t|t.join().unwrap()).filter(|ok|*ok).count(),1);
    assert!(!store.valid_family(&ctx,&one.family_id));
}
#[test]
fn capacity_expiry_and_revocation_are_bounded() {
    let root=tempfile::tempdir().unwrap(); let store=RefreshStore::shared(root.path().into()); let ctx=context();
    for _ in 0..MAX_FAMILIES {store.issue(&ctx).unwrap();}
    assert_eq!(store.issue(&ctx).err(),Some(RefreshError::Capacity));
    assert_eq!(store.snapshot().unwrap()["active_families"],64);
    store.revoke_all().unwrap(); assert_eq!(store.snapshot().unwrap()["active_families"],0);
    // Tombstones are bounded until the original expiry; revocation does not reopen capacity for flooding.
    assert_eq!(store.issue(&ctx).err(),Some(RefreshError::Capacity));
    { let mut inner=store.inner.lock().unwrap();for f in inner.document.families.values_mut(){f.expires_at=unix_now()-1;} }
    assert!(store.issue(&ctx).is_ok());
}
#[test]
fn corrupt_unknown_schema_and_io_failure_never_return_new_credentials() {
    for raw in ["not-json",r#"{"version":99,"families":{}}"#] {
        let root=tempfile::tempdir().unwrap();
        if raw.starts_with('{') {let mut doc=AuthDocument::open(root.path()).unwrap();doc.save(&serde_json::from_str::<serde_json::Value>(raw).unwrap()).unwrap();}
        else {std::fs::write(root.path().join("auth.json"),raw).unwrap();}
        let before=std::fs::read(root.path().join("auth.json")).unwrap();
        let store=RefreshStore::shared(root.path().into());assert_eq!(store.issue(&context()).err(),Some(RefreshError::Unavailable));
        assert_eq!(std::fs::read(root.path().join("auth.json")).unwrap(),before);
    }
    let root=tempfile::tempdir().unwrap();let store=RefreshStore::shared(root.path().into());let ctx=context();let one=store.issue(&ctx).unwrap();
    std::fs::remove_file(root.path().join("auth.json")).unwrap();
    assert_eq!(store.rotate(&ctx,&one.token,"","").err(),Some(RefreshError::Unavailable));
    assert!(!store.valid_family(&ctx,&one.family_id));assert!(!root.path().join("auth.json").exists());
}
