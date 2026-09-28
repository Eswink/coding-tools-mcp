use crate::{canonical::digest_json,journal::Offered,projection::Tracker,wire::*,*};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD,Engine};
use ring::{rand::SystemRandom,signature::{Ed25519KeyPair,UnparsedPublicKey,ED25519}};
use serde_json::{json,Value};
use std::{fs::OpenOptions,io::Write,path::{Path,PathBuf},sync::Arc};
use uuid::Uuid;
use zeroize::Zeroizing;

fn key()->Arc<DeviceKey>{
    let pkcs8=Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
    Arc::new(DeviceKey::from_pkcs8(Zeroizing::new(pkcs8.as_ref().to_vec())).unwrap())
}
fn cfg()->DeviceConfig{DeviceConfig::new("https://gateway.example/coding-tools".into(),Uuid::new_v4(),Uuid::new_v4(),1).unwrap()}
fn private_root(path:&Path)->PathBuf{
    let root=path.canonicalize().unwrap();
    #[cfg(unix)] {use std::os::unix::fs::PermissionsExt;std::fs::set_permissions(&root,std::fs::Permissions::from_mode(0o700)).unwrap();}
    root
}
fn request()->ExecutionRequest {
    ExecutionRequest{binding:ExecutionBinding{
        request_id:Uuid::new_v4(),peer:PeerBinding{connector:Uuid::new_v4(),device:Uuid::new_v4(),device_epoch:1,
            gateway_boot:Uuid::new_v4(),channel_session:Uuid::new_v4(),channel_generation:1},
        grant_id:Uuid::new_v4(),grant_revision:2,authority_epoch:2,conversation:URL_SAFE_NO_PAD.encode([3;32]),
        scope:"exec.run".into(),tool:"exec_command".into(),arguments_hash:digest_json(&json!({"cmd":"synthetic-secret-command"}),4096).unwrap(),deadline:1300},
        arguments:json!({"cmd":"synthetic-secret-command"})}
}
fn grant()->NativeGrant{NativeGrant{id:Uuid::new_v4(),conversation:URL_SAFE_NO_PAD.encode([3;32]),issued_at:1000,expires_at:2000,scopes:vec!["exec.run".into()]}}
fn free()->Observation<u64>{Observation{phase:LocalPhase::Free,native_epoch:1,native_revision:1,execution_generation:1,
    execution_enabled:true,recovery_ready:true,drain_safe:true,grant:None,proof:None}}
fn active(g:NativeGrant)->Observation<u64>{Observation{phase:LocalPhase::Active,native_epoch:1,native_revision:3,execution_generation:1,
    execution_enabled:true,recovery_ready:true,drain_safe:true,grant:Some(g),proof:Some(42)}}

#[test]fn configuration_rejects_untrusted_origins(){
    for issuer in ["http://gateway.example", "wss://gateway.example", "https://a@b", "https://a/?x=1", "https://a/#secret", "https://a/", "https://a/%2f"]{
        assert!(DeviceConfig::new(issuer.into(),Uuid::new_v4(),Uuid::new_v4(),1).is_err(),"{issuer}");
    }
}
#[test]fn configuration_pins_endpoint_and_redacts_debug(){
    let c=cfg();assert_eq!(c.endpoint().unwrap(),"wss://gateway.example/coding-tools/agent");
    assert_eq!(format!("{c:?}"),"DeviceConfig([REDACTED])");assert!(!format!("{:?}",key()).contains("BEGIN"));
}
#[test]fn configuration_deserialization_is_not_validation(){
    let v=json!({"issuer":"http://evil.example","connector":Uuid::new_v4(),"device":Uuid::new_v4(),"device_epoch":1});
    let c:DeviceConfig=serde_json::from_value(v).unwrap();assert!(c.validate().is_err());assert!(c.endpoint().is_err());
}
#[test]fn configuration_rejects_unknown_authority_parameters(){
    let c=cfg();let mut value=serde_json::to_value(c).unwrap();value["workspace"]=json!("/");
    assert!(serde_json::from_value::<DeviceConfig>(value).is_err());
}
#[test]fn invalid_pkcs8_is_rejected(){assert!(DeviceKey::from_pkcs8(Zeroizing::new(vec![0;32])).is_err());}
#[test]fn canonical_hash_is_stable_for_object_order(){assert_eq!(digest_json(&json!({"b":2,"a":[1,3]}),1024).unwrap(),digest_json(&json!({"a":[1,3],"b":2}),1024).unwrap());}
#[test]fn canonical_hash_preserves_array_order(){assert_ne!(digest_json(&json!([1,2]),100).unwrap(),digest_json(&json!([2,1]),100).unwrap());}
#[test]fn canonical_limits_and_depth_are_enforced(){
    assert!(digest_json(&json!({"a":"x".repeat(4096)}),4096).is_err());
    let mut deep=Value::Null;for _ in 0..70{deep=json!([deep]);}assert!(digest_json(&deep,8192).is_err());
}
#[test]fn request_requires_exact_peer_arguments_and_deadline(){
    let mut r=request();let peer=r.binding.peer.clone();assert!(r.validate_at(&peer,1000).is_ok());
    r.arguments["cmd"]=json!("different");assert!(r.validate_at(&peer,1000).is_err());
    r=request();r.binding.deadline=1000;assert!(r.validate_at(&r.binding.peer,1000).is_err());
    r.binding.deadline=1301;assert!(r.validate_at(&r.binding.peer,1000).is_err());
}
#[test]fn request_rejects_foreign_generation_and_identity_fields(){
    let r=request();let mut peer=r.binding.peer.clone();peer.channel_generation+=1;assert!(r.validate_at(&peer,1000).is_err());
    let mut value=serde_json::to_value(&r).unwrap();value["binding"]["authorized"]=json!(true);
    assert!(serde_json::from_value::<ExecutionRequest>(value).is_err());
}
#[test]fn native_grant_is_bounded_and_debug_redacted(){
    let mut g=grant();assert!(g.valid());g.scopes.push("exec.run".into());assert!(!g.valid());
    assert_eq!(format!("{:?}",request()),"ExecutionRequest([REDACTED])");
}
#[test]fn approval_arguments_have_a_separate_digest_and_deadline(){
    let r=request();let mut a=ApprovalRequest{binding:ApprovalBinding{request_id:Uuid::new_v4(),peer:r.binding.peer.clone(),
        conversation:r.binding.conversation.clone(),arguments_hash:digest_json(&json!({"scopes":["exec.run"],"status_only":false}),1024).unwrap(),deadline:1015},
        scopes:vec!["exec.run".into()],status_only:false};
    assert!(a.validate_at(&r.binding.peer,1000).is_ok());a.status_only=true;assert!(a.validate_at(&r.binding.peer,1000).is_err());
}
#[test]fn incoming_frame_size_and_unknown_type_are_rejected(){
    assert!(ServerFrame::parse(&"x".repeat(MAX_MESSAGE+1)).is_err());
    assert!(ServerFrame::parse(r#"{"type":"approve","authorized":true}"#).is_err());
}
#[test]fn signed_connect_binds_exact_challenge_and_domain(){
    let c=cfg();let k=key();let challenge=ConnectChallenge{version:1,issuer:c.issuer().into(),resource:c.resource(),connector:c.connector(),
        gateway_boot:Uuid::new_v4(),attempt:Uuid::new_v4(),nonce:URL_SAFE_NO_PAD.encode([8;32]),issued_at:1000,expires_at:1010};
    let proof=k.connect(&c,&challenge,1001).unwrap();let raw=URL_SAFE_NO_PAD.decode(proof.payload).unwrap();let sig=URL_SAFE_NO_PAD.decode(proof.signature).unwrap();
    let mut valid=b"coding-tools-agent-connect-v1\0".to_vec();valid.extend_from_slice(&raw);
    let public=URL_SAFE_NO_PAD.decode(k.public_key()).unwrap();assert!(UnparsedPublicKey::new(&ED25519,&public).verify(&valid,&sig).is_ok());
    assert!(UnparsedPublicKey::new(&ED25519,&public).verify(&raw,&sig).is_err());
    assert!(k.connect(&c,&challenge,1010).is_err());
}
#[test]fn journal_claim_is_once_across_reopen_and_reconnection(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let mut r=request();
    let j=Journal::create(&root,&c,k.clone()).unwrap();assert_eq!(j.claim(&r).unwrap(),ClaimOutcome::Fresh);drop(j);
    let j=Journal::open_existing(&root,&c,k).unwrap();r.binding.peer.gateway_boot=Uuid::new_v4();r.binding.peer.channel_session=Uuid::new_v4();r.binding.peer.channel_generation+=1;
    assert_eq!(j.claim(&r).unwrap(),ClaimOutcome::AlreadyClaimed{completed:false});
}
#[test]fn journal_conflict_is_not_a_new_claim(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let j=Journal::create(&root,&cfg(),key()).unwrap();let mut r=request();
    j.claim(&r).unwrap();r.binding.arguments_hash=[9;32];assert_eq!(j.claim(&r),Err(LinkError::ReplayConflict));
}
#[test]fn journal_completion_is_idempotent_without_payload_persistence(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let j=Journal::create(&root,&c,k.clone()).unwrap();let r=request();
    j.claim(&r).unwrap();let result=json!({"ok":true,"stdout":"synthetic-private-result"});j.complete(&r,&result).unwrap();j.complete(&r,&result).unwrap();
    assert_eq!(j.complete(&r,&json!({"ok":false})),Err(LinkError::ReplayConflict));drop(j);
    let j=Journal::open_existing(&root,&c,k).unwrap();assert_eq!(j.claim(&r).unwrap(),ClaimOutcome::AlreadyClaimed{completed:true});
    let bytes=std::fs::read(root.join("requests.log")).unwrap();
    assert!(!bytes.windows(b"synthetic-secret-command".len()).any(|w|w==b"synthetic-secret-command"));
    assert!(!bytes.windows(b"synthetic-private-result".len()).any(|w|w==b"synthetic-private-result"));
}
#[test]fn journal_rejects_a_second_owner_and_changed_binding(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let j=Journal::create(&root,&c,k.clone()).unwrap();
    assert!(Journal::open_existing(&root,&c,k.clone()).is_err());drop(j);
    assert!(Journal::open_existing(&root,&cfg(),k.clone()).is_err());assert!(Journal::open_existing(&root,&c,key()).is_err());
    assert!(Journal::create(&root,&c,k).is_err());
}
#[test]fn journal_rejects_missing_files_and_tampered_signatures(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let j=Journal::create(&root,&c,k.clone()).unwrap();drop(j);
    let path=root.join("projection.state");let mut bytes=std::fs::read(&path).unwrap();bytes[3]^=1;std::fs::write(&path,bytes).unwrap();
    assert!(Journal::open_existing(&root,&c,k.clone()).is_err());std::fs::remove_file(&path).unwrap();assert!(Journal::open_existing(&root,&c,k).is_err());
}
#[test]fn journal_rejects_partial_tail(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let j=Journal::create(&root,&c,k.clone()).unwrap();j.claim(&request()).unwrap();drop(j);
    let mut f=OpenOptions::new().append(true).open(root.join("requests.log")).unwrap();f.write_all(&[0,0]).unwrap();f.sync_all().unwrap();drop(f);
    assert!(Journal::open_existing(&root,&c,k).is_err());
}
#[test]fn journal_rejects_complete_record_truncation(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let j=Journal::create(&root,&c,k.clone()).unwrap();
    let header=std::fs::metadata(root.join("requests.log")).unwrap().len();j.claim(&request()).unwrap();drop(j);
    let f=OpenOptions::new().write(true).open(root.join("requests.log")).unwrap();f.set_len(header).unwrap();f.sync_all().unwrap();drop(f);
    assert!(Journal::open_existing(&root,&c,k).is_err(),"NATIVE_JOURNAL_COMPLETE_RECORD_TRUNCATION");
}
#[cfg(unix)]#[test]fn journal_rejects_world_readable_root_and_symlink_files(){
    use std::os::unix::fs::{symlink,PermissionsExt};
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();
    std::fs::set_permissions(&root,std::fs::Permissions::from_mode(0o755)).unwrap();assert!(Journal::create(&root,&c,k.clone()).is_err());
    std::fs::set_permissions(&root,std::fs::Permissions::from_mode(0o700)).unwrap();let j=Journal::create(&root,&c,k.clone()).unwrap();drop(j);
    let original=root.join("requests.log");let moved=root.join("moved");std::fs::rename(&original,&moved).unwrap();symlink(&moved,&original).unwrap();
    assert!(Journal::open_existing(&root,&c,k).is_err());
}
#[test]fn projection_initializes_free_before_publishing_a_local_grant(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let journal=Arc::new(Journal::create(&root,&cfg(),key()).unwrap());
    let mut tracker=Tracker::new(journal).unwrap();let g=grant();
    let first=tracker.prepare(active(g.clone()),1000,1025).unwrap();assert_eq!(first.offered.state.phase,Phase::Free);tracker.acknowledged(first).unwrap();
    let second=tracker.prepare(active(g),1000,1025).unwrap();assert_eq!(second.offered.state.phase,Phase::Active);assert_eq!(second.proof,Some(42));
}
#[test]fn projection_does_not_sign_online_without_native_proof(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let journal=Arc::new(Journal::create(&root,&cfg(),key()).unwrap());
    let mut tracker=Tracker::new(journal).unwrap();let mut o=active(grant());o.proof=None;assert!(tracker.prepare(o,1000,1025).is_err());
}
#[test]fn projection_drain_precedes_free_on_restart_and_revoke(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let j=Arc::new(Journal::create(&root,&cfg(),key()).unwrap());let mut t=Tracker::new(j).unwrap();
    let initial=t.prepare(free(),1000,1025).unwrap();t.acknowledged(initial).unwrap();let g=grant();let approved=t.prepare(active(g.clone()),1000,1025).unwrap();t.acknowledged(approved).unwrap();
    let mut after=free();after.native_epoch=2;after.native_revision=4;let draining=t.prepare(after.clone(),1001,1025).unwrap();
    assert_eq!(draining.offered.state.phase,Phase::Draining);assert_eq!(draining.offered.state.grant.as_ref().unwrap().id,g.id);t.acknowledged(draining).unwrap();
    let freed=t.prepare(after,1002,1025).unwrap();assert_eq!(freed.offered.state.phase,Phase::Free);assert_eq!(freed.offered.state.drained_grant,Some(g.id));
}
#[test]fn pending_projection_is_not_execution_authority(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let journal=Arc::new(Journal::create(&root,&cfg(),key()).unwrap());let mut t=Tracker::new(journal).unwrap();
    let initial=t.prepare(free(),1000,1025).unwrap();t.acknowledged(initial).unwrap();let mut pending=active(grant());pending.phase=LocalPhase::Pending;pending.proof=None;
    let offer=t.prepare(pending,1000,1025).unwrap();assert_eq!(offer.offered.state.phase,Phase::Pending);assert_eq!(offer.offered.state.execution,ExecutionState::Offline);assert!(offer.proof.is_none());
}
#[test]fn unacknowledged_projection_is_preserved_and_cannot_skip_drain(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let c=cfg();let k=key();let journal=Arc::new(Journal::create(&root,&c,k.clone()).unwrap());
    let mut t=Tracker::new(journal.clone()).unwrap();let first=t.prepare(free(),1000,1025).unwrap();t.acknowledged(first).unwrap();
    let g=grant();let offered=t.prepare(active(g.clone()),1000,1025).unwrap();assert_eq!(offered.offered.state.phase,Phase::Active);drop(t);drop(journal);
    let journal=Arc::new(Journal::open_existing(&root,&c,k).unwrap());let mut t=Tracker::new(journal).unwrap();let mut o=free();o.native_epoch=2;
    let next=t.prepare(o,1001,1025).unwrap();assert_eq!(next.offered.state.phase,Phase::Draining);assert_eq!(next.offered.state.grant.unwrap().id,g.id);
}
#[test]fn session_is_opaque_and_revocation_fences_clones(){
    let r=request();let at=crate::now().unwrap();let s=Session::established("https://gateway.example".into(),r.binding.peer,at).unwrap();let other=s.clone();
    assert!(s.is_current());s.close();assert!(!other.is_current());assert!(other.renew(at).is_err());assert_eq!(format!("{other:?}"),"Session([REDACTED])");
}
#[test]fn expired_session_cannot_be_renewed(){let r=request();let s=Session::established("https://gateway.example".into(),r.binding.peer,crate::now().unwrap()-31).unwrap();assert!(!s.is_current());assert!(s.renew(crate::now().unwrap()).is_err());}
#[test]fn projection_ack_must_match_the_exact_offered_revision(){
    let temp=tempfile::tempdir().unwrap();let root=private_root(temp.path());let j=Journal::create(&root,&cfg(),key()).unwrap();
    let offer=j.offer(Offered{revision:0,state:Projected{phase:Phase::Free,execution:ExecutionState::Offline,authority_epoch:1,grant:None,drained_grant:None},native_epoch:1,native_revision:1,execution_generation:1}).unwrap();
    assert!(j.acknowledge(offer.revision+1).is_err());j.acknowledge(offer.revision).unwrap();
}
