//! Compile from a sibling of `migrate`, matching the production DataStore call.
//! Moving these tests into `migrate::tests` would hide an E0603 regression.
use super::{migrate::migrate_data, AppData};

#[test]
fn sibling_module_can_normalize_an_unversioned_snapshot() {
    let normalized = migrate_data(AppData::default()).expect("sibling-module migration");
    assert_eq!(normalized.schema_version, 1);
}

#[test]
fn sibling_module_rejects_a_future_snapshot_without_echoing_credentials() {
    let mut data = AppData { schema_version: u32::MAX, ..AppData::default() };
    data.shared_secrets.insert("bearer_token".into(), "visibility-canary-v4".into());
    let error = migrate_data(data).expect_err("future version must fail closed").to_string();
    assert!(error.contains("配置版本"));
    assert!(!error.contains("visibility-canary-v4"));
}
