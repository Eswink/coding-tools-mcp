//! Opt-in native test. Unlike unit doubles, this must fail when the actual
//! OS credential service is unavailable. It only creates its own random entry.
use super::*;
use crate::data::key_store::{NativeKeyStore, SERVICE};

#[test]
fn native_keychain_cross_process_file_roundtrip() {
    const CHILD_PATH: &str = "CODING_TOOLS_NATIVE_TEST_CHILD_PATH";
    const PAYLOAD: &str = r#"{"token":"native-canary-v6","schema_version":1}"#;
    if let Ok(path) = std::env::var(CHILD_PATH) {
        Vault::new(&NativeKeyStore).write(Path::new(&path), PAYLOAD).expect("native child write");
        return;
    }
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("native-config.json");
    let id = codec::key_id_for_path(&path).unwrap();
    struct Cleanup(String);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            if let Ok(entry) = keyring::Entry::new(SERVICE, &self.0) {
                let _ = entry.delete_credential();
            }
        }
    }
    let _cleanup = Cleanup(id);
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "data::secure_file::native_tests::native_keychain_cross_process_file_roundtrip", "--nocapture"])
        .env(CHILD_PATH, &path).output().unwrap();
    assert!(output.status.success(), "native child failed: {}", String::from_utf8_lossy(&output.stderr));
    // Fresh provider in a different process proves this is not process-local memory.
    let (plaintext, encrypted) = Vault::new(&NativeKeyStore).read(&path).expect("native parent read");
    assert!(encrypted);
    assert_eq!(&*plaintext, PAYLOAD);
    assert!(!fs::read_to_string(&path).unwrap().contains("native-canary-v6"));
}
