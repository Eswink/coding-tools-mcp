use super::*;
pub(super) fn native_fixture() -> (NativeToolHost, tempfile::TempDir, tempfile::TempDir) {
    assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"));
    assert_eq!(std::env::var("RUNNER_OS").as_deref(), Ok("Windows"));
    assert_eq!(std::env::var("CTM_NATIVE_WORKSPACE_IO_FIXTURE").as_deref(), Ok("owned-temporary-ci"));
    let source = std::env::var("GITHUB_SHA").unwrap();
    assert_eq!(crate::tools::windows_vm::input::native_source(), Ok(source.as_str()));
    let runner = std::path::PathBuf::from(std::env::var("RUNNER_TEMP").unwrap()).canonicalize().unwrap();
    let root = tempfile::tempdir_in(&runner).unwrap();
    let harness = tempfile::tempdir_in(&runner).unwrap();
    let context = Arc::new(ToolContext::for_test(root.path().into(), harness.path().into()).unwrap());
    let peer = crate::auth::cloud_context::CloudPeer {
        connector: Uuid::new_v4(), device: Uuid::new_v4(), device_epoch: 1,
        gateway_boot: Uuid::new_v4(), session: Uuid::new_v4(), generation: 1,
    };
    let link = CloudTransport::new("input-only", root.path(), "https://gateway.example.invalid",
        "/coding-tools", peer.connector, peer.device, 1, "input-test-private-data-only-key").unwrap();
    link.activate(peer, Duration::from_secs(30)).unwrap();
    let host = NativeToolHost::new("input-only", context, link, Arc::new(ChatAuthorizer::default())).unwrap();
    (host, root, harness)
}
#[test]
fn native_input_registration_does_not_authorize_cloud_execution() {
    let (host, _root, _harness) = native_fixture();
    assert!(host.windows_input.is_ok());
    assert!(host.authority("not-approved").is_err());
    assert!(host.context.remote_request.is_none());
}
