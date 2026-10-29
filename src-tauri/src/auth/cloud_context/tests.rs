use super::*;
use crate::tools::{call_tool, ToolContext};
use serde_json::json;
struct Fixture {
    root: tempfile::TempDir,
    harness: tempfile::TempDir,
    link: CloudTransport,
    peer: CloudPeer,
    service: Arc<ChatAuthorizer>,
}
impl Fixture {
    fn new(ttl: Duration) -> Self {
        let root = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let connector = Uuid::new_v4();
        let device = Uuid::new_v4();
        let link = CloudTransport::new(
            "native-cloud-profile",
            root.path(),
            "https://gateway.example.invalid",
            "/coding-tools",
            connector,
            device,
            1,
            "fixture-local-binding-key-with-enough-entropy",
        )
        .unwrap();
        let peer = CloudPeer {
            connector,
            device,
            device_epoch: 1,
            gateway_boot: Uuid::new_v4(),
            session: Uuid::new_v4(),
            generation: 1,
        };
        link.activate(peer.clone(), ttl).unwrap();
        let service = Arc::new(ChatAuthorizer::default());
        Self {
            root,
            harness,
            link,
            peer,
            service,
        }
    }
    fn request(&self, n: u8) -> RemoteRequest {
        self.link
            .request(&URL_SAFE_NO_PAD.encode([n; 32]), self.service.clone())
            .unwrap()
    }
    fn context(&self, n: u8) -> ToolContext {
        let mut ctx =
            ToolContext::for_test(self.root.path().into(), self.harness.path().into()).unwrap();
        ctx.remote_request = Some(self.request(n));
        ctx
    }
    fn approve(&self, n: u8, scopes: &[&str]) {
        let r = self.request(n);
        let pending = self.service.request(&r, &json!({"scopes":scopes}));
        assert_eq!(pending["ok"], true, "{pending}");
        self.service
            .decide(
                &r.profile,
                pending["authorization"]["id"].as_str().unwrap(),
                true,
                &scopes.iter().map(|x| (*x).into()).collect::<Vec<String>>(),
            )
            .unwrap();
    }
}
#[test]
fn cloud_connection_is_not_an_oauth_principal_or_local_grant() {
    let f = Fixture::new(Duration::from_secs(30));
    let req = f.request(1);
    assert!(req.principal.is_none());
    assert!(req.identity().is_ok());
    assert_eq!(
        f.service.status(&req)["authorization"]["status"],
        "unauthorized"
    );
    let ctx = f.context(1);
    let out = call_tool(
        &ctx,
        "read_file",
        &json!({"path":"secret","authorized":true}),
    );
    assert_eq!(out["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
}
#[test]
fn native_approval_controls_actual_file_tool_for_cloud_identity() {
    let f = Fixture::new(Duration::from_secs(30));
    std::fs::write(f.root.path().join("fixture.txt"), "real-native-file-canary").unwrap();
    let ctx = f.context(1);
    assert_eq!(
        call_tool(&ctx, "read_file", &json!({"path":"fixture.txt"}))["ok"],
        false
    );
    f.approve(1, &["files.read"]);
    let value = call_tool(&ctx, "read_file", &json!({"path":"fixture.txt"}));
    assert_eq!(value["ok"], true, "{value}");
    assert!(value.to_string().contains("real-native-file-canary"));
    f.service
        .revoke(&ctx.remote_request.as_ref().unwrap().profile, None);
    assert_eq!(
        call_tool(&ctx, "read_file", &json!({"path":"fixture.txt"}))["ok"],
        false
    );
}
#[test]
fn foreign_cloud_conversation_cannot_use_native_owner() {
    let f = Fixture::new(Duration::from_secs(30));
    f.approve(1, &["files.read"]);
    let b = f.context(2);
    assert_eq!(
        call_tool(
            &b,
            "request_chat_authorization",
            &json!({"scopes":["exec.run"]})
        )["error"]["code"],
        "EXCLUSIVE_CHAT_LOCKED"
    );
    assert_eq!(
        f.service.snapshot("native-cloud-profile")["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn native_pause_blocks_new_pending_cloud_authorization() {
    let f = Fixture::new(Duration::from_secs(30));
    let ctx = f.context(1);
    ctx.execution_gate.pause().unwrap();
    let out = call_tool(
        &ctx,
        "request_chat_authorization",
        &json!({"scopes":["files.read"]}),
    );
    assert_eq!(out["error"]["code"], "CHAT_AUTHORIZATION_UNAVAILABLE");
    assert!(f.service.snapshot("native-cloud-profile")["records"]
        .as_array()
        .unwrap()
        .is_empty());
}
#[test]
fn expired_cloud_lease_cannot_be_revived_by_a_late_heartbeat() {
    let f = Fixture::new(Duration::from_millis(10));
    let req = f.request(1);
    std::thread::sleep(Duration::from_millis(20));
    assert!(req.identity().is_err());
    let denied = f.service.request(&req, &json!({"scopes":["files.read"]}));
    assert_eq!(denied["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    assert_eq!(denied["error"]["message"], "CLOUD_CONNECTION_REQUIRED");
    assert!(f.service.snapshot("native-cloud-profile")["records"]
        .as_array()
        .unwrap()
        .is_empty());
    assert!(f.link.renew(&f.peer, Duration::from_secs(30)).is_err());
}
#[test]
fn reconnect_fences_old_native_request_but_does_not_transfer_approval() {
    let f = Fixture::new(Duration::from_secs(30));
    let old = f.request(1);
    f.approve(1, &["files.read"]);
    let mut newer = f.peer.clone();
    newer.session = Uuid::new_v4();
    newer.generation += 1;
    f.link.activate(newer, Duration::from_secs(30)).unwrap();
    assert!(old.identity().is_err());
    let fresh = f.request(1);
    assert!(f.service.permit(&fresh, &["files.read"]).is_ok());
    assert!(f.service.permit(&f.request(2), &["files.read"]).is_err());
}
#[test]
fn old_generation_or_boot_cannot_replace_the_current_channel() {
    let f = Fixture::new(Duration::from_secs(30));
    assert!(f
        .link
        .activate(f.peer.clone(), Duration::from_secs(30))
        .is_err());
    let mut second = f.peer.clone();
    second.gateway_boot = Uuid::new_v4();
    second.session = Uuid::new_v4();
    f.link
        .activate(second.clone(), Duration::from_secs(30))
        .unwrap();
    let mut replay = f.peer.clone();
    replay.generation += 9;
    replay.session = Uuid::new_v4();
    assert!(f.link.activate(replay, Duration::from_secs(30)).is_err());
    assert!(f.link.matches(&second));
}
#[test]
fn wrong_device_and_unbounded_lease_are_rejected() {
    let f = Fixture::new(Duration::from_secs(30));
    let mut wrong = f.peer.clone();
    wrong.device = Uuid::new_v4();
    assert!(f.link.activate(wrong, Duration::from_secs(1)).is_err());
    assert!(f.link.renew(&f.peer, Duration::from_secs(31)).is_err());
}
#[test]
fn ambiguous_oauth_and_cloud_credentials_fail_closed() {
    let f = Fixture::new(Duration::from_secs(30));
    let mut req = f.request(1);
    let token = crate::auth::principal::issue(
        "https://local.invalid",
        "https://local.invalid",
        "fixture-key",
        "client",
        3600,
    )
    .unwrap();
    req.principal = Some(
        crate::auth::principal::verify(
            &token,
            "fixture-key",
            "https://local.invalid",
            "https://local.invalid",
        )
        .unwrap(),
    );
    assert_eq!(req.identity(), Err("AUTHENTICATION_CONTEXT_AMBIGUOUS"));
}
#[test]
fn native_cloud_binding_cannot_be_modified_or_moved_between_workspaces() {
    let f = Fixture::new(Duration::from_secs(30));
    let mut req = f.request(1);
    let expected = req.binding.clone();
    req.binding = Some("0".repeat(64));
    assert!(req.identity().is_err());
    req.binding = expected;
    req.profile = "different-profile".into();
    assert!(req.identity().is_err());
    assert!(f.link.for_workspace("native-cloud-profile", f.root.path()));
    assert!(!f
        .link
        .for_workspace("native-cloud-profile", f.harness.path()));
}
#[test]
fn closing_transport_is_irreversible_without_a_new_native_instance() {
    let f = Fixture::new(Duration::from_secs(30));
    let req = f.request(1);
    f.link.close();
    assert!(req.identity().is_err());
    assert!(f
        .link
        .request(&URL_SAFE_NO_PAD.encode([1; 32]), f.service.clone())
        .is_err());
    let mut newer = f.peer.clone();
    newer.generation += 1;
    newer.session = Uuid::new_v4();
    assert!(f.link.activate(newer, Duration::from_secs(30)).is_err());
}
#[test]
fn metadata_cannot_manufacture_cloud_identity_or_escalate_native_scopes() {
    let f = Fixture::new(Duration::from_secs(30));
    let req = f.request(1);
    let pending = f.service.request(
        &req,
        &json!({"scopes":["files.read"],"cloud":true,"authorized":true}),
    );
    assert_eq!(pending["ok"], false);
    f.approve(1, &["files.read"]);
    assert!(f.service.permit(&req, &["exec.run"]).is_err());
    assert!(f
        .link
        .request("a".repeat(43).as_str(), f.service.clone())
        .is_err());
}

#[test]
fn rotating_device_epoch_never_reuses_a_previously_approved_native_binding() {
    let f = Fixture::new(Duration::from_secs(30));
    let old = f.request(1);
    f.approve(1, &["files.read"]);
    let next = CloudTransport::new(
        "native-cloud-profile",
        f.root.path(),
        "https://gateway.example.invalid",
        "/coding-tools",
        f.peer.connector,
        f.peer.device,
        2,
        "fixture-local-binding-key-with-enough-entropy",
    )
    .unwrap();
    let mut peer = f.peer.clone();
    peer.device_epoch = 2;
    next.activate(peer, Duration::from_secs(30)).unwrap();
    let fresh = next
        .request(&URL_SAFE_NO_PAD.encode([1; 32]), f.service.clone())
        .unwrap();
    assert_ne!(
        old.identity().unwrap(),
        fresh.identity().unwrap(),
        "DEVICE_EPOCH_NATIVE_BINDING_MUST_CHANGE"
    );
    assert!(f.service.permit(&fresh, &["files.read"]).is_err());
}
