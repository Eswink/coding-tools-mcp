#[test]
fn relative_names_remain_data_not_native_permission() {
    assert!(super::check_relative("src/input.txt").is_ok());
    for value in ["", "..", "C:\\input", "\\\\host\\input", "NUL.txt"] {
        assert!(super::check_relative(value).is_err());
    }
    // This test creates no NativeAuthority, Claim, permit, file handle or VM.
}
fn require_native_ci() -> std::path::PathBuf {
    assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"));
    assert_eq!(std::env::var("RUNNER_OS").as_deref(), Ok("Windows"));
    assert_eq!(std::env::var("CTM_NATIVE_WORKSPACE_IO_FIXTURE").as_deref(), Ok("owned-temporary-ci"));
    let source = std::env::var("GITHUB_SHA").expect("actual source-qualified CI required");
    assert_eq!(super::native_source(), Ok(source.as_str()));
    let path = std::path::PathBuf::from(std::env::var("RUNNER_TEMP").unwrap());
    assert!(path.is_absolute() && path.is_dir()); path.canonicalize().unwrap()
}
#[test]
fn native_input_lease_retains_original_and_detached_bytes_on_close_unknown() {
    use super::{root::WindowsInputAuthority, lease::InputLease};
    let runner = require_native_ci();
    let root = tempfile::tempdir_in(runner).unwrap();
    std::fs::write(root.path().join("input.txt"), b"actual-input-canary").unwrap();
    let host = uuid::Uuid::new_v4();
    let authority = WindowsInputAuthority::pin(host, "data-only", root.path()).unwrap();
    let mut lease = InputLease::new();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    lease.prepare(&authority, host, "data-only", "input.txt", deadline, &|| false).unwrap();
    let mut binding = super::transfer_tests::binding(); binding.host = host.to_string();
    let transfer = lease.transfer(binding.clone(), deadline, &|| false).unwrap();
    assert!(transfer.matches(&binding));
    lease.simulate_close_unknown(); assert!(!lease.retire());
    let (held, uncertain, original) = lease.recovery_evidence();
    assert!(held >= 1 && uncertain && original);
    assert!(transfer.matches(&binding));
    // Controlled unknown leaves the real handle and immutable owners held.
    // No grant, VM/output issuer or native execution is fabricated by this unit.
    let _ = Box::leak(Box::new((root, authority, lease, transfer)));
}
#[test]
fn native_input_root_and_relative_binding_reject_foreign_profiles() {
    use super::{root::WindowsInputAuthority, lease::InputLease};
    let root = tempfile::tempdir_in(require_native_ci()).unwrap();
    std::fs::write(root.path().join("input.txt"), b"actual-input-canary").unwrap();
    let host = uuid::Uuid::new_v4();
    let authority = WindowsInputAuthority::pin(host, "data-only", root.path()).unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    let mut rejected = InputLease::new();
    assert!(rejected.prepare(&authority, host, "foreign", "input.txt", deadline, &|| false).is_err());
    assert!(rejected.retire());
    let mut lease = InputLease::new();
    lease.prepare(&authority, host, "data-only", "input.txt", deadline, &|| false).unwrap();
    let mut binding = super::transfer_tests::binding(); binding.host = host.to_string();
    binding.input_relative = "other.txt".into();
    assert!(lease.transfer(binding, deadline, &|| false).is_err());
    assert!(lease.retire());
}
