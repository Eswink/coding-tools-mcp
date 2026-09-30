use super::*;
use crate::auth::chat::ChatAuthorizer;
use crate::auth::cloud_context::{CloudTransport};
use crate::tools::ToolContext;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD,Engine};
use sha2::{Digest,Sha256};
use uuid::Uuid;

struct Fixture {
    _root:tempfile::TempDir,
    storage:tempfile::TempDir,
    _auth:tempfile::TempDir,
    _harness:tempfile::TempDir,
    live:NativeLiveHost,
    peer:PeerBinding,
}
impl Fixture {
    fn new()->Self {
        let root=tempfile::tempdir().unwrap();
        let storage=tempfile::tempdir().unwrap();
        let auth=tempfile::tempdir().unwrap();
        let harness=tempfile::tempdir().unwrap();
        let context=Arc::new(ToolContext::for_test(root.path().into(),harness.path().into()).unwrap());
        let authorizer=Arc::new(ChatAuthorizer::default());
        authorizer.attach_storage("native-live",auth.path(),harness.path()).unwrap();
        let peer=PeerBinding {connector:Uuid::new_v4(),device:Uuid::new_v4(),device_epoch:1,
            gateway_boot:Uuid::new_v4(),channel_session:Uuid::new_v4(),channel_generation:1};
        let link=CloudTransport::new("native-live",root.path(),"https://gateway.example.invalid",
            "/coding-tools",peer.connector,peer.device,1,"native-live-synthetic-fixture-key").unwrap();
        link.activate(super::peer(&peer).unwrap(),Duration::from_secs(30)).unwrap();
        let tools=Arc::new(NativeToolHost::new("native-live",context,link,authorizer).unwrap());
        let live=NativeLiveHost::open(tools,storage.path(),true,1).unwrap();
        std::fs::write(root.path().join("data.txt"),"real-native-read-canary").unwrap();
        Self {_root:root,storage,_auth:auth,_harness:harness,live,peer}
    }
    fn conversation(&self)->String {URL_SAFE_NO_PAD.encode([7;32])}
    fn approved(&self)->HostAuthoritySnapshot {
        let free=self.live.current().unwrap();
        assert_eq!(free.phase(),ProjectionPhase::Free);
        self.live.receipt(&free).unwrap();
        let p=self.live.request_authorization(&self.conversation(),&json!({"scopes":["files.read"]}));
        assert_eq!(p["ok"],true,"{p}");
        assert_eq!(p["authorization"]["status"],"pending");
        self.live.tools.authorizer.decide("native-live",p["authorization"]["id"].as_str().unwrap(),
            true,&["files.read".into()]).unwrap();
        let active=self.live.current().unwrap();
        assert_eq!(active.phase(),ProjectionPhase::Active);
        self.live.receipt(&active).unwrap();active
    }
    fn request(&self,view:&HostAuthoritySnapshot)->ExecutionRequest {
        let args=json!({"path":"data.txt"});
        ExecutionRequest {binding:ExecutionBinding {
            request_id:Uuid::new_v4(),peer:self.peer.clone(),grant_id:view.grant().unwrap().id,
            grant_revision:7,authority_epoch:view.epoch(),conversation:self.conversation(),
            scope:"files.read".into(),tool:"read_file".into(),
            arguments_hash:Sha256::digest(serde_json::to_vec(&args).unwrap()).into(),
            deadline:now().unwrap() as i64+25,
        },arguments:args}
    }
}
#[test]
fn empty_live_native_authorizer_is_free_not_an_active_grant() {
    let f=Fixture::new();
    let v=f.live.current().unwrap();
    assert_eq!(v.phase(),ProjectionPhase::Free);
    assert_eq!(v.execution(),ExecutionState::Offline);
    assert!(v.grant().is_none());
}
#[test]
fn pending_request_cannot_become_a_signed_active_grant() {
    let f=Fixture::new();
    let free=f.live.current().unwrap();f.live.receipt(&free).unwrap();
    let p=f.live.request_authorization(&f.conversation(),&json!({"scopes":["files.read"]}));
    assert_eq!(p["authorization"]["status"],"pending");
    let v=f.live.current().unwrap();
    assert_ne!(v.phase(),ProjectionPhase::Active);
    assert!(v.grant().is_none());
}
#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn same_live_adapter_executes_the_actual_native_file_dispatcher() {
    let f=Fixture::new();let v=f.approved();let request=f.request(&v);
    let permit=f.live.admit(v,request.clone()).await.unwrap();
    let (_tx,rx)=watch::channel(false);
    let result=f.live.execute(permit,request,rx).await.unwrap();
    assert_eq!(result["ok"],true,"{result}");
    assert!(result.to_string().contains("real-native-read-canary"));
}
#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn peer_and_argument_replacement_cannot_reuse_native_admission() {
    let f=Fixture::new();let v=f.approved();let mut request=f.request(&v);
    request.arguments=json!({"path":"other.txt"});
    assert!(f.live.admit(v.clone(),request).await.is_err());
    let request=f.request(&v);let permit=f.live.admit(v.clone(),request.clone()).await.unwrap();
    let mut replaced=request;replaced.binding.request_id=Uuid::new_v4();
    let (_tx,rx)=watch::channel(false);
    assert!(f.live.execute(permit,replaced,rx).await.is_err());
    assert_eq!(f.live.tools.context.execution_gate.snapshot().in_flight,0);
}
#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn native_pause_resume_changes_live_generation_and_rejects_old_view() {
    let f=Fixture::new();let old=f.approved();let request=f.request(&old);
    f.live.tools.context.execution_gate.pause().unwrap();
    let paused=f.live.current().unwrap();
    assert_eq!(paused.execution(),ExecutionState::Offline);
    assert!(paused.grant()==old.grant());
    f.live.tools.context.execution_gate.resume().unwrap();
    let resumed=f.live.current().unwrap();
    assert_eq!(resumed.execution(),ExecutionState::Online);
    assert_ne!(resumed.execution_generation(),old.execution_generation());
    assert!(f.live.admit(old,request).await.is_err());
}
#[test]
fn native_revoke_requires_acknowledged_draining_before_free() {
    let f=Fixture::new();let active=f.approved();
    f.live.tools.authorizer.revoke("native-live",None);
    let draining=f.live.current().unwrap();
    assert_eq!(draining.phase(),ProjectionPhase::Draining);
    assert!(draining.grant()==active.grant());
    assert_eq!(f.live.current().unwrap().phase(),ProjectionPhase::Draining);
    f.live.receipt(&draining).unwrap();
    let free=f.live.current().unwrap();
    assert_eq!(free.phase(),ProjectionPhase::Free);
    assert_eq!(free.drained_grant(),active.grant().map(|g|g.id));
    assert_eq!(free.epoch(),active.epoch());
}
#[test]
fn lost_free_acknowledgement_is_persisted_and_replayed_as_receipt_only() {
    let f=Fixture::new();let active=f.approved();
    f.live.tools.authorizer.revoke("native-live",None);
    let draining=f.live.current().unwrap();f.live.receipt(&draining).unwrap();
    let free=f.live.current().unwrap();
    let tools=f.live.tools.clone();let path=f.storage.path().to_path_buf();
    drop(f.live);
    let reopened=NativeLiveHost::open(tools,&path,false,1).unwrap();
    let again=reopened.current().unwrap();
    assert_eq!(again.phase(),ProjectionPhase::Free);
    assert_eq!(again.epoch(),free.epoch());
    assert_eq!(again.drained_grant(),active.grant().map(|g|g.id));
}
#[test]
fn native_successor_waits_for_both_remote_drain_barriers() {
    let f=Fixture::new();let active=f.approved();
    f.live.tools.authorizer.revoke("native-live",None);
    let draining=f.live.current().unwrap();
    let other=URL_SAFE_NO_PAD.encode([8;32]);
    let p=f.live.request_authorization(&other,&json!({"scopes":["files.read"]}));
    assert_eq!(p["ok"],true,"{p}");
    f.live.tools.authorizer.decide("native-live",p["authorization"]["id"].as_str().unwrap(),
        true,&["files.read".into()]).unwrap();
    assert_eq!(f.live.current().unwrap().phase(),ProjectionPhase::Draining);
    f.live.receipt(&draining).unwrap();
    let free=f.live.current().unwrap();
    assert_eq!(free.phase(),ProjectionPhase::Free);
    assert_eq!(f.live.current().unwrap().phase(),ProjectionPhase::Free);
    f.live.receipt(&free).unwrap();
    let successor=f.live.current().unwrap();
    assert_eq!(successor.phase(),ProjectionPhase::Active);
    assert!(successor.epoch()>active.epoch());
    assert_eq!(successor.grant().unwrap().conversation,other);
}
#[test]
fn stopped_or_paused_native_host_allocates_no_pending_or_conversation_record() {
    let f=Fixture::new();
    f.live.tools.context.execution_gate.pause().unwrap();
    for i in 1..100 {
        let result=f.live.request_authorization(&URL_SAFE_NO_PAD.encode([i;32]),&json!({"scopes":["files.read"]}));
        assert_ne!(result["ok"],true);
    }
    assert_eq!(f.live.projection.lock().unwrap().conversations().count(),0);
    assert_eq!(f.live.tools.authorizer.snapshot("native-live")["records"].as_array().unwrap().len(),0);
    f.live.tools.link.close();
    assert!(f.live.current().is_err());
}
#[test]
fn foreign_native_owner_cannot_fill_the_cloud_conversation_registry() {
    let f=Fixture::new();let _=f.approved();
    for i in 20..120 {
        let value=f.live.request_authorization(&URL_SAFE_NO_PAD.encode([i;32]),&json!({"scopes":["files.read"]}));
        assert_ne!(value["ok"],true);
    }
    assert_eq!(f.live.projection.lock().unwrap().conversations().count(),1);
    assert_eq!(f.live.tools.authorizer.snapshot("native-live")["records"].as_array().unwrap().len(),1);
}
#[test]
fn native_projection_state_is_encrypted_and_missing_or_corrupt_state_is_not_initialized() {
    let f=Fixture::new();let active=f.approved();
    let data=std::fs::read_to_string(f.storage.path().join("auth.json")).unwrap();
    assert!(!data.contains(&f.conversation()));
    assert!(!data.contains(&active.grant().unwrap().id.to_string()));
    let tools=f.live.tools.clone();
    let path=f.storage.path().to_path_buf();
    drop(f.live);
    std::fs::write(path.join("auth.json"),"corrupt-canary").unwrap();
    assert!(NativeLiveHost::open(tools.clone(),&path,false,1).is_err());
    assert_eq!(std::fs::read_to_string(path.join("auth.json")).unwrap(),"corrupt-canary");
    let missing=tempfile::tempdir().unwrap();
    assert!(NativeLiveHost::open(tools,missing.path(),false,1).is_err());
}
#[tokio::test]
async fn stale_connection_cleanup_does_not_invalidate_its_successor() {
    let f=Fixture::new();let old=f.peer.clone();
    f.live.disconnected(&old);
    assert!(f.live.connected(old.clone(),30).await.is_err());
    let mut fresh=old.clone();
    fresh.channel_generation+=1;fresh.channel_session=Uuid::new_v4();
    f.live.connected(fresh.clone(),30).await.unwrap();
    f.live.disconnected(&old);
    assert!(f.live.tools.link.matches(&super::peer(&fresh).unwrap()));
    assert!(f.live.heartbeat(old,30).await.is_err());
    assert!(f.live.heartbeat(fresh,30).await.is_ok());
}
#[tokio::test]
async fn a_cancelled_native_call_never_reaches_the_tool_dispatcher() {
    let f=Fixture::new();let v=f.approved();let request=f.request(&v);
    let permit=f.live.admit(v,request.clone()).await.unwrap();
    let (_tx,rx)=watch::channel(true);
    assert!(f.live.execute(permit,request,rx).await.is_err());
    assert_eq!(f.live.tools.context.execution_gate.snapshot().in_flight,0);
}
#[test]
fn source_restart_does_not_treat_persisted_projection_as_native_approval() {
    let f=Fixture::new();let active=f.approved();
    // A new native authorizer, attached to the same durable authority namespace,
    // has no newly approved grant; persisted metadata cannot resurrect it.
    let link=f.live.tools.link.clone();
    let context=f.live.tools.context.clone();
    let path=f.storage.path().to_path_buf();
    let auth_root=f._auth.path().to_path_buf();
    let harness_root=f._harness.path().to_path_buf();
    drop(f.live);
    let service=Arc::new(ChatAuthorizer::default());
    service.attach_storage("native-live",&auth_root,&harness_root).unwrap();
    let tools=Arc::new(NativeToolHost::new("native-live",context,link,service).unwrap());
    let reopened=NativeLiveHost::open(tools,&path,false,1).unwrap();
    let view=reopened.current().unwrap();
    assert_ne!(view.phase(),ProjectionPhase::Active);
    assert_eq!(view.execution(),ExecutionState::Offline);
    assert!(view.grant()==active.grant());
}

fn approve_catalog_scopes(f: &Fixture, scopes: &[&str]) -> HostAuthoritySnapshot {
    let free=f.live.current().unwrap(); f.live.receipt(&free).unwrap();
    let pending=f.live.request_authorization(&f.conversation(),&json!({"scopes":scopes}));
    assert_eq!(pending["authorization"]["status"],"pending","{pending}");
    let owned:Vec<String>=scopes.iter().map(|s|s.to_string()).collect();
    f.live.tools.authorizer.decide("native-live",pending["authorization"]["id"].as_str().unwrap(),true,&owned).unwrap();
    let view=f.live.current().unwrap(); f.live.receipt(&view).unwrap(); view
}
fn catalog_request(f: &Fixture, view: &HostAuthoritySnapshot, name: &str, scope: &str, args: Value) -> ExecutionRequest {
    let mut request=f.request(view);
    request.binding.tool=name.into(); request.binding.scope=scope.into();
    request.binding.arguments_hash=Sha256::digest(serde_json::to_vec(&args).unwrap()).into();
    request.arguments=args; request
}
#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn direct_agent_frames_cannot_bypass_catalog_or_inject_host_policy() {
    let f=Fixture::new(); let view=f.approved();
    for (name,args) in [("request_permissions",json!({})),("read_file",json!({"path":"data.txt","env":{}})),
        ("read_file",json!({"path":"../secret"})),("read_file",json!({"path":"data.txt","max_bytes":9000}))] {
        let request=catalog_request(&f,&view,name,"files.read",args);
        assert!(f.live.admit(view.clone(),request).await.is_err(),"{name}");
    }
}
#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn primary_scope_does_not_replace_all_native_required_scopes() {
    let f=Fixture::new(); let view=approve_catalog_scopes(&f,&["task.manage"]);
    let request=catalog_request(&f,&view,"write_stdin","task.manage",json!({"session_id":"missing"}));
    assert!(f.live.admit(view,request).await.is_err());
    let f=Fixture::new(); let view=approve_catalog_scopes(&f,&["task.manage","exec.run"]);
    let request=catalog_request(&f,&view,"write_stdin","task.manage",json!({"session_id":"missing"}));
    // Admission checks authority; nonexistent session still cannot cause effects.
    #[cfg(target_os="linux")]
    assert!(f.live.admit(view,request).await.is_ok());
    #[cfg(not(target_os="linux"))]
    assert!(f.live.admit(view,request).await.is_err());
}

#[tokio::test(flavor="multi_thread",worker_threads=2)]
async fn history_validate_read_only_needs_no_write_authority_and_repair_cannot_forge_it() {
    let f=Fixture::new(); let view=approve_catalog_scopes(&f,&["history.read"]);
    for args in [json!({}),json!({"repair":false})] {
        let request=catalog_request(&f,&view,"history_session_validate","history.read",args);
        assert!(f.live.admit(view.clone(),request).await.is_ok());
    }
    for scope in ["history.read","history.write"] {
        let request=catalog_request(&f,&view,"history_session_validate",scope,json!({"repair":true}));
        assert!(f.live.admit(view.clone(),request).await.is_err());
    }
    let f=Fixture::new(); let view=approve_catalog_scopes(&f,&["history.write"]);
    let request=catalog_request(&f,&view,"history_session_validate","history.write",json!({"repair":true}));
    assert!(f.live.admit(view,request).await.is_ok());
}
