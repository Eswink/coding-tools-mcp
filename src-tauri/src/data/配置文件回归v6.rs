use super::*;
use crate::data::key_store::MemoryKeys;

#[test]
fn ciphertext_commit_roundtrips_without_plaintext_artifacts() {
    let keys = MemoryKeys::default();
    let vault = Vault::new(&keys);
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("profiles.json");
    let canary = r#"{"secret":"vault-canary-v6"}"#;
    vault.write(&path, canary).unwrap();
    assert_eq!(&*vault.read(&path).unwrap().0, canary);
    let content = fs::read_to_string(&path).unwrap();
    assert!(!content.contains("vault-canary-v6"));
    assert!(vault.read(&path).unwrap().1);
    assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
}

#[test]
fn legacy_protection_is_lossless_and_idempotent() {
    let keys = MemoryKeys::default();
    let vault = Vault::new(&keys);
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("profiles.json.bak");
    let legacy = "{\n  \"secret\": \"legacy-canary-v6\"\n}\n";
    fs::write(&path, legacy).unwrap();
    vault.protect_legacy(&path).unwrap();
    assert_eq!(&*vault.read(&path).unwrap().0, legacy);
    let before = fs::read(&path).unwrap();
    vault.protect_legacy(&path).unwrap();
    assert_eq!(fs::read(&path).unwrap(), before);
}

#[test]
fn lost_key_never_overwrites_ciphertext() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("profiles.json");
    Vault::new(&MemoryKeys::default()).write(&path, r#"{"token":"old"}"#).unwrap();
    let bytes = fs::read(&path).unwrap();
    let keys = MemoryKeys::default();
    assert!(Vault::new(&keys).write(&path, r#"{"token":"new"}"#).is_err());
    assert_eq!(fs::read(&path).unwrap(), bytes);
}

#[test]
fn tampered_ciphertext_is_not_replaced_with_new_data() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("profiles.json");
    let keys = MemoryKeys::default();
    let vault = Vault::new(&keys);
    vault.write(&path, r#"{"token":"old"}"#).unwrap();
    let mut value: serde_json::Value = serde_json::from_str(&fs::read_to_string(&path).unwrap()).unwrap();
    value["ciphertext"] = "AAAA".into();
    fs::write(&path, value.to_string()).unwrap();
    let bytes = fs::read(&path).unwrap();
    assert!(vault.write(&path, r#"{"token":"new"}"#).is_err());
    assert_eq!(fs::read(&path).unwrap(), bytes);
}

#[test]
fn encrypted_backup_can_be_read_after_rename_with_same_system_key() {
    let dir = tempfile::tempdir().unwrap();
    let from = dir.path().join("profiles.json");
    let to = dir.path().join("profiles.json.bak");
    let keys = MemoryKeys::default();
    let vault = Vault::new(&keys);
    vault.write(&from, r#"{"token":"stable"}"#).unwrap();
    fs::rename(from, &to).unwrap();
    assert_eq!(&*vault.read(&to).unwrap().0, r#"{"token":"stable"}"#);
    vault.write(&to, r#"{"token":"updated"}"#).unwrap();
    assert_eq!(&*vault.read(&to).unwrap().0, r#"{"token":"updated"}"#);
}

#[test]
fn failed_rename_cleans_only_the_new_temporary_file() {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("profiles.json");
    fs::create_dir(&path).unwrap();
    fs::write(path.join("original"), b"unchanged").unwrap();
    assert!(atomic_replace(&path, b"ciphertext").is_err());
    assert_eq!(fs::read(path.join("original")).unwrap(), b"unchanged");
    assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
}

#[cfg(unix)]
#[test]
fn symlink_configuration_is_rejected_without_modifying_target() {
    let dir = tempfile::tempdir().unwrap();
    let target = dir.path().join("target");
    let link = dir.path().join("profiles.json");
    fs::write(&target, b"{}").unwrap();
    std::os::unix::fs::symlink(&target, &link).unwrap();
    let keys = MemoryKeys::default();
    assert!(Vault::new(&keys).write(&link, "{}").is_err());
    assert_eq!(fs::read(target).unwrap(), b"{}");
}
