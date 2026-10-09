#[test]
fn diagnostic_metadata_cannot_authorize_output() {
    for data in [
        r#"{"whole_exit_observed":true,"source_handles_closed":true}"#,
        r#"{"permission":true,"scopes":["files.write"],"retired":true}"#,
        r#"{"system_id":"existing","native_handle":123,"stage_approved":true}"#,
        r#"{"source":"0000000000000000000000000000000000000000","closed_vm":true}"#,
    ] { assert!(super::request_publication(data).is_err()); }
    let raw = serde_json::json!({"host":uuid::Uuid::new_v4().to_string(),"profile":"data-only",
        "caller":"caller","source":"1".repeat(40),"session":uuid::Uuid::new_v4().to_string(),
        "operation":uuid::Uuid::new_v4().to_string(),"input_relative":"input.txt",
        "output_parent":"results","output_leaf":"new.txt","bytes":0,
        "sha256":"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}).to_string();
    assert_eq!(super::request_publication(&raw), Err("WINDOWS_OUTPUT_ACTUAL_CLOSED_OWNER_REQUIRED"));
    let forged = raw.replacen("\"bytes\":0", "\"bytes\":0,\"bytes\":0", 1);
    assert!(super::request_publication(&forged).is_err());
}
