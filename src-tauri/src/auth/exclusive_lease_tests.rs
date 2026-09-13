//! Real state-machine tests. Host metadata and credentials here are synthetic.
use super::*;
fn request(service: &Arc<ChatAuthorizer>, profile: &str, session: &str) -> RemoteRequest {
    let p = VerifiedPrincipal { issuer:"https://test.example".into(), subject:"desktop-owner".into(),
        client_id:"fixture-client".into(), expires_at:unix_now()+3600 , family_id: None };
    let mut r = RemoteRequest::verified(profile,"workspace",p,&json!({"openai/session":session}),"test-only-secret");
    r.service = service.clone(); r
}
fn approve(service: &Arc<ChatAuthorizer>, req: &RemoteRequest) -> String {
    let v = service.request(req,&json!({"scopes":["files.read"]}));
    let id = v["authorization"]["id"].as_str().unwrap().to_owned();
    service.decide(&req.profile,&id,true,&["files.read".into()]).unwrap(); id
}
#[test]
fn first_request_reserves_by_default_and_blocks_noise_before_approval() {
    let s = Arc::new(ChatAuthorizer::default()); let mut events = s.subscribe();
    let a = request(&s,"lease-pending","A"); let b = request(&s,"lease-pending","B");
    let pending = s.request(&a,&json!({"scopes":["files.read"]}));
    assert_eq!(pending["authorization"]["status"],"pending");
    assert_eq!(s.snapshot("lease-pending")["lease_state"],"reserved");
    assert_eq!(events.try_recv().unwrap().kind,"pending");
    for _ in 0..100 {
        let v = s.request(&b,&json!({}));
        assert_eq!(v["error"]["code"],"EXCLUSIVE_CHAT_LOCKED");
        assert_eq!(v["requires_local_action"],false);
        assert!(v.get("authorization").is_none());
        assert!(!v.to_string().contains(pending["authorization"]["fingerprint"].as_str().unwrap()));
    }
    assert!(events.try_recv().is_err());
    assert_eq!(s.snapshot("lease-pending")["records"].as_array().unwrap().len(),1);
    assert_eq!(s.request(&a,&json!({}))["authorization"],pending["authorization"]);
}
#[test]
fn active_owner_cannot_be_displaced_and_release_is_local() {
    let s = Arc::new(ChatAuthorizer::default()); let a = request(&s,"lease-active","A"); let b = request(&s,"lease-active","B");
    let id = approve(&s,&a);
    assert_eq!(s.status(&b)["error"]["code"],"EXCLUSIVE_CHAT_LOCKED");
    assert_eq!(s.permit(&b,&["files.read"]),Err("EXCLUSIVE_CHAT_LOCKED"));
    assert!(s.decide("lease-active","guessed",true,&["files.read".into()]).is_err());
    assert!(s.permit(&a,&["files.read"]).is_ok());
    s.revoke("lease-active",Some(&id));
    assert_eq!(s.snapshot("lease-active")["lease_state"],"free");
    approve(&s,&b); assert!(s.permit(&a,&["files.read"]).is_err());
}
#[test]
fn simultaneous_claims_emit_exactly_one_pending_event() {
    let s = Arc::new(ChatAuthorizer::default()); let mut events = s.subscribe();
    let barrier = Arc::new(std::sync::Barrier::new(16));
    let threads: Vec<_> = (0..16).map(|n| {
        let s=s.clone(); let b=barrier.clone();
        std::thread::spawn(move || { b.wait(); s.request(&request(&s,"lease-race",&format!("c{n}")),&json!({})) })
    }).collect();
    let results:Vec<_>=threads.into_iter().map(|t|t.join().unwrap()).collect();
    assert_eq!(results.iter().filter(|v|v["ok"]==true).count(),1);
    assert_eq!(results.iter().filter(|v|v["error"]["code"]=="EXCLUSIVE_CHAT_LOCKED").count(),15);
    assert_eq!(events.try_recv().unwrap().kind,"pending"); assert!(events.try_recv().is_err());
}
#[test]
fn admitted_call_holds_draining_fence_against_successor() {
    let s=Arc::new(ChatAuthorizer::default()); let a=request(&s,"lease-drain","A"); let b=request(&s,"lease-drain","B");
    let id=approve(&s,&a); let flight=s.admit(&a,&["files.read"]).unwrap();
    s.revoke("lease-drain",Some(&id));
    assert_eq!(s.snapshot("lease-drain")["lease_state"],"draining");
    assert_eq!(s.request(&b,&json!({}))["error"]["code"],"CHAT_WORK_DRAINING");
    drop(flight);
    assert_eq!(s.request(&b,&json!({}))["authorization"]["status"],"pending");
}
#[test]
fn pending_timeout_allows_new_candidate_but_stale_approval_does_not() {
    let s=Arc::new(ChatAuthorizer::default()); let a=request(&s,"lease-timeout","A"); let b=request(&s,"lease-timeout","B");
    let first=s.request(&a,&json!({})); let id=first["authorization"]["id"].as_str().unwrap();
    s.state.lock().unwrap().records.get_mut(a.binding.as_ref().unwrap()).unwrap().since-=Duration::from_secs(91);
    assert_eq!(s.request(&b,&json!({}))["ok"],true);
    assert!(s.decide("lease-timeout",id,true,&["files.read".into()]).is_err());
}
#[test]
fn access_renewal_keeps_binding_and_does_not_extend_lease() {
    let s=Arc::new(ChatAuthorizer::default()); let a=request(&s,"lease-renew","A"); approve(&s,&a);
    let before=s.status(&a)["authorization"].clone(); let mut renewed=a.clone();
    renewed.principal.as_mut().unwrap().expires_at+=3600;
    assert_eq!(renewed.binding,a.binding); assert!(s.permit(&renewed,&["files.read"]).is_ok());
    assert_eq!(s.status(&renewed)["authorization"]["expires_at"],before["expires_at"]);
    assert_eq!(s.status(&renewed)["authorization"]["idle_expires_at"],before["expires_at"]);
}
