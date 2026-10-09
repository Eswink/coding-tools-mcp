use super::*;
use crate::auth::cloud_context::CloudPeer;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde_json::json;

#[cfg(windows)]
#[test]
fn independent_input_root_registration_does_not_replace_existing_native_authority() {
    let f = Fixture::new();
    assert!(f.host.windows_input.is_ok());
    assert!(f.host.authority(&f.conversation()).is_err());
    assert!(f.host.context.remote_request.is_none());
}

struct Fixture {
    root: tempfile::TempDir,
    _storage: tempfile::TempDir,
    _harness: tempfile::TempDir,
    host: NativeToolHost,
    peer: CloudPeer,
}
impl Fixture {
    fn new() -> Self {
        let root = tempfile::tempdir().unwrap();
        let storage = tempfile::tempdir().unwrap();
        let harness = tempfile::tempdir().unwrap();
        let context =
            Arc::new(ToolContext::for_test(root.path().into(), harness.path().into()).unwrap());
        let service = Arc::new(ChatAuthorizer::default());
        service
            .attach_storage("native-host", storage.path(), harness.path())
            .unwrap();
        let peer = CloudPeer {
            connector: Uuid::new_v4(),
            device: Uuid::new_v4(),
            device_epoch: 1,
            gateway_boot: Uuid::new_v4(),
            session: Uuid::new_v4(),
            generation: 1,
        };
        let link = CloudTransport::new(
            "native-host",
            root.path(),
            "https://gateway.example.invalid",
            "/coding-tools",
            peer.connector,
            peer.device,
            1,
            "native-host-fixture-private-binding-key",
        )
        .unwrap();
        link.activate(peer.clone(), Duration::from_secs(30))
            .unwrap();
        let host = NativeToolHost::new("native-host", context, link, service).unwrap();
        std::fs::write(root.path().join("fixture.txt"), "native-file-canary").unwrap();
        Self {
            root,
            _storage: storage,
            _harness: harness,
            host,
            peer,
        }
    }
    fn conversation(&self) -> String {
        URL_SAFE_NO_PAD.encode([7; 32])
    }
    fn approve(&self, scopes: &[&str]) -> NativeAuthority {
        let v = self
            .host
            .request_authorization(&self.conversation(), &json!({"scopes":scopes}));
        assert_eq!(v["ok"], true, "{v}");
        let selected: Vec<_> = scopes.iter().map(|s| (*s).into()).collect();
        self.host
            .authorizer
            .decide(
                "native-host",
                v["authorization"]["id"].as_str().unwrap(),
                true,
                &selected,
            )
            .unwrap();
        self.host.authority(&self.conversation()).unwrap()
    }
    fn read(&self, authority: &NativeAuthority) -> PreparedCall {
        self.host
            .prepare(
                authority,
                "read_file",
                &json!({"path":"fixture.txt"}),
                now().unwrap() + 30,
            )
            .unwrap()
    }
}
#[test]
fn remote_environment_reports_the_actual_platform_execution_gate() {
    let f = Fixture::new();
    let a = f.approve(&["workspace.read"]);
    let call = f
        .host
        .prepare(
            &a,
            "check_exec_environment",
            &json!({}),
            now().unwrap() + 30,
        )
        .unwrap();
    let value = f.host.execute(call).unwrap();
    assert_eq!(value["ok"], true, "{value}");
    assert_eq!(value["workspace_exec_sandbox_enforced"], false);
    assert_eq!(value["filesystem_sandbox"]["required"], true);
    assert_eq!(value["network_allowed"], false);
    if cfg!(target_os = "linux") {
        assert_eq!(value["workspace_exec_available"], true);
        assert_eq!(
            value["workspace_exec_boundary"],
            "landlock_seccomp_required"
        );
        assert_eq!(value["filesystem_sandbox"]["available"], Value::Null);
        assert_eq!(
            value["filesystem_sandbox"]["availability_check"],
            "per_child_before_exec"
        );
    } else {
        assert_eq!(value["workspace_exec_available"], false);
        assert_eq!(value["workspace_exec_boundary"], "sandbox_unavailable");
        assert_eq!(
            value["workspace_exec_unavailable_reason"],
            "SANDBOX_REQUIRED"
        );
        assert_eq!(value["filesystem_sandbox"]["available"], false);
        assert_eq!(value["global_tmp_write"], "denied");
    }
}

#[test]
fn actual_native_authorization_is_required_before_snapshot_or_prepare() {
    let f = Fixture::new();
    assert!(f.host.authority(&f.conversation()).is_err());
    let pending = f
        .host
        .request_authorization(&f.conversation(), &json!({"scopes":["files.read"]}));
    assert_eq!(pending["authorization"]["status"], "pending");
    assert!(f.host.authority(&f.conversation()).is_err());
}
#[test]
fn a_native_approved_opaque_ticket_reads_through_the_real_file_tool() {
    let f = Fixture::new();
    let authority = f.approve(&["files.read"]);
    let prepared = f.read(&authority);
    assert!(!format!("{prepared:?}").contains("fixture.txt"));
    assert!(!format!("{authority:?}").contains("native-host"));
    let v = f.host.execute(prepared).unwrap();
    assert_eq!(v["ok"], true, "{v}");
    assert!(v.to_string().contains("native-file-canary"));
}
#[test]
fn submitted_args_are_owned_and_cannot_be_replaced_before_commit() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    std::fs::write(f.root.path().join("other.txt"), "different-canary").unwrap();
    let mut args = json!({"path":"fixture.txt"});
    let prepared = f
        .host
        .prepare(&a, "read_file", &args, now().unwrap() + 30)
        .unwrap();
    args["path"] = json!("other.txt");
    let v = f.host.execute(prepared).unwrap();
    assert!(v.to_string().contains("native-file-canary"));
    assert!(!v.to_string().contains("different-canary"));
}
#[test]
fn revocation_between_prepare_and_commit_does_not_execute() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    let prepared = f.read(&a);
    f.host.authorizer.revoke("native-host", None);
    assert!(f.host.execute(prepared).is_err());
    assert!(f.host.authority(&f.conversation()).is_err());
}
#[test]
fn pause_resume_aba_invalidates_the_native_authority_view() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    let prepared = f.read(&a);
    f.host.context.execution_gate.pause().unwrap();
    f.host.context.execution_gate.resume().unwrap();
    assert!(f.host.execute(prepared).is_err());
    assert!(f
        .host
        .prepare(
            &a,
            "read_file",
            &json!({"path":"fixture.txt"}),
            now().unwrap() + 30
        )
        .is_err());
    let current = f.host.authority(&f.conversation()).unwrap();
    assert_eq!(f.host.execute(f.read(&current)).unwrap()["ok"], true);
}
#[test]
fn an_expired_monotonic_or_wall_deadline_rejects_before_commit() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    assert!(f
        .host
        .prepare(&a, "read_file", &json!({}), now().unwrap())
        .is_err());
    assert!(f
        .host
        .prepare(&a, "read_file", &json!({}), now().unwrap() + 301)
        .is_err());
    let mut prepared = f.read(&a);
    prepared.deadline = Instant::now();
    assert_eq!(f.host.execute(prepared), Err("CLOUD_DEADLINE_REJECTED"));
    let mut prepared = f.read(&a);
    prepared.deadline_epoch = now().unwrap();
    assert_eq!(f.host.execute(prepared), Err("CLOUD_DEADLINE_REJECTED"));
}
#[test]
fn reconnect_does_not_upgrade_the_old_prepared_credential() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    let prepared = f.read(&a);
    let mut peer = f.peer.clone();
    peer.session = Uuid::new_v4();
    peer.generation += 1;
    f.host.link.activate(peer, Duration::from_secs(30)).unwrap();
    assert_eq!(f.host.execute(prepared), Err("CLOUD_CONNECTION_REQUIRED"));
    assert_eq!(
        f.host
            .execute(f.read(&f.host.authority(&f.conversation()).unwrap()))
            .unwrap()["ok"],
        true
    );
}
#[test]
fn prepared_work_cannot_cross_host_instance_or_workspace() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    let prepared = f.read(&a);
    let other = Fixture::new();
    assert!(other.host.execute(prepared).is_err());
    assert!(other
        .host
        .prepare(&a, "read_file", &json!({}), now().unwrap() + 30)
        .is_err());
    assert!(NativeToolHost::new(
        "wrong-profile",
        f.host.context.clone(),
        f.host.link.clone(),
        f.host.authorizer.clone()
    )
    .is_err());
    let different = Arc::new(
        ToolContext::for_test(other.root.path().into(), other._harness.path().into()).unwrap(),
    );
    assert!(NativeToolHost::new(
        "native-host",
        different,
        f.host.link.clone(),
        f.host.authorizer.clone()
    )
    .is_err());
}
#[test]
fn cloud_scope_and_isolation_overrides_never_reach_native_tools() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    for args in [
        json!({"path":"fixture.txt","authorized":true}),
        json!({"path":"fixture.txt","sandbox":false}),
        json!({"path":"fixture.txt","env":{"PATH":"/host"}}),
        json!({"path":"fixture.txt","filesystem_scope":"host"}),
        json!({"path":"fixture.txt","_meta":{"openai/session":"forged"}}),
    ] {
        assert!(f
            .host
            .prepare(&a, "read_file", &args, now().unwrap() + 30)
            .is_err());
    }
    assert!(f
        .host
        .prepare(&a, "apply_patch", &json!({}), now().unwrap() + 30)
        .is_err());
    assert!(f
        .host
        .prepare(
            &a,
            "request_permissions",
            &json!({"mode":"dangerous"}),
            now().unwrap() + 30
        )
        .is_err());
}
#[test]
fn relative_and_existing_symlink_paths_cannot_escape_cloud_workspace() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    for path in ["/etc/passwd", "../outside", "C:\\outside", "\\host", ""] {
        assert!(
            f.host
                .prepare(&a, "read_file", &json!({"path":path}), now().unwrap() + 30)
                .is_err(),
            "{path}"
        );
    }
    #[cfg(unix)]
    {
        let outside = tempfile::tempdir().unwrap();
        std::fs::write(outside.path().join("canary"), "outside").unwrap();
        std::os::unix::fs::symlink(outside.path(), f.root.path().join("escape")).unwrap();
        assert!(f
            .host
            .prepare(
                &a,
                "read_file",
                &json!({"path":"escape/canary"}),
                now().unwrap() + 30
            )
            .is_err());
    }
}
#[test]
fn native_argument_and_output_bounds_are_enforced_without_truncating_truth() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    assert!(f
        .host
        .prepare(
            &a,
            "read_file",
            &json!({"path":"x".repeat(4096)}),
            now().unwrap() + 30
        )
        .is_err());
    std::fs::write(f.root.path().join("fixture.txt"), "x".repeat(16384)).unwrap();
    assert_eq!(f.host.execute(f.read(&a)), Err("CLOUD_EXECUTION_UNKNOWN"));
}
#[test]
fn native_pause_and_foreign_conversations_do_not_create_extra_pending_work() {
    let f = Fixture::new();
    f.host.context.execution_gate.pause().unwrap();
    assert_eq!(
        f.host
            .request_authorization(&f.conversation(), &json!({"scopes":["files.read"]}))["ok"],
        false
    );
    assert!(f.host.authorizer.snapshot("native-host")["records"]
        .as_array()
        .unwrap()
        .is_empty());
    f.host.context.execution_gate.resume().unwrap();
    f.approve(&["files.read"]);
    let other = URL_SAFE_NO_PAD.encode([8; 32]);
    for attempt in 0..100 {
        // This exercises exclusivity under a live peer, not lease expiry.
        // Windows durable authorization reads can outlast a single 30s lease;
        // model the real peer's heartbeat without changing its identity.
        f.host.link.renew(&f.peer, Duration::from_secs(30)).unwrap();
        let result = f
            .host
            .request_authorization(&other, &json!({"scopes":["exec.run"]}));
        assert_eq!(
            result["error"]["code"], "EXCLUSIVE_CHAT_LOCKED",
            "foreign request {attempt}: {result}"
        );
    }
    assert_eq!(
        f.host.authorizer.snapshot("native-host")["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn closing_cloud_link_rejects_prepared_work_without_native_authority_mutation() {
    let f = Fixture::new();
    let a = f.approve(&["files.read"]);
    let prepared = f.read(&a);
    f.host.link.close();
    assert!(f.host.execute(prepared).is_err());
    assert_eq!(
        f.host.authorizer.snapshot("native-host")["records"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}

#[cfg(target_os = "linux")]
#[path = "hook_tests.rs"]
mod hook_tests;

#[path = "async_deadline_tests.rs"]
mod async_deadline_tests;
