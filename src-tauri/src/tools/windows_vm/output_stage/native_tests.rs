fn require_native_ci() -> std::path::PathBuf {
    assert_eq!(std::env::var("GITHUB_ACTIONS").as_deref(), Ok("true"));
    assert_eq!(std::env::var("RUNNER_OS").as_deref(), Ok("Windows"));
    assert_eq!(std::env::var("CTM_NATIVE_WORKSPACE_IO_FIXTURE").as_deref(), Ok("owned-temporary-ci"));
    let source = std::env::var("GITHUB_SHA").expect("actual CI source required");
    assert_eq!(crate::tools::windows_vm::input::native_source(), Ok(source.as_str()));
    std::path::PathBuf::from(std::env::var("RUNNER_TEMP").unwrap()).canonicalize().unwrap()
}
#[test]
fn native_forged_metadata_never_changes_existing_or_creates_new_output() {
    let root = tempfile::tempdir_in(require_native_ci()).unwrap();
    std::fs::create_dir(root.path().join("results")).unwrap();
    let canary = root.path().join("results/existing.txt");
    std::fs::write(&canary, b"existing-canary").unwrap();
    for request in [r#"{"permission":true,"whole_vm_retired":true}"#,
        r#"{"source_handles_closed":true,"output":"results/new.txt"}"#,
        r#"{"stage_approved":true,"output":"results/existing.txt"}"#] {
        assert!(super::request_publication(request).is_err());
        assert_eq!(std::fs::read(&canary).unwrap(), b"existing-canary");
        assert!(!root.path().join("results/new.txt").exists());
    }
    assert_eq!(std::fs::read_dir(root.path().join("results")).unwrap().count(), 1);
}
