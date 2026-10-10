#[test]
fn ordinary_three_scope_catalog_and_output_defaults_remain_closed() {
    let (host, root, _harness) = super::windows_input_tests::native_fixture();
    let arguments = serde_json::json!({"cmd":"Get-Content input.txt", "workspace_io": {
        "input":"input.txt", "output_parent":"results", "output_leaf":"new.txt"}});
    let spec = coding_tools_cloud_agent::catalog::tool("exec_command").unwrap();
    assert!(spec.validate(&arguments).is_ok());
    assert!(host.authority("not-approved").is_err());
    assert!(!root.path().join("results/new.txt").exists());
    // Valid catalog data has not created a grant, VM, Guest IO or output owner.
}
