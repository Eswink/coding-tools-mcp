use super::*;
use crate::data::key_store::MemoryKeys;

const ID: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const CANARY: &str = "credential-canary-v6-not-a-real-secret";

#[test]
fn all_snapshot_fields_are_encrypted_and_roundtrip_exactly() {
    let keys = MemoryKeys::default();
    let plaintext = format!(r#"{{"schema_version":1,"shared_secrets":{{"token":"{CANARY}"}},"proxy":{{"url":"https://user:{CANARY}@example.com"}},"unknown":"{CANARY}"}}"#);
    let sealed = seal(&plaintext, ID, true, &keys).unwrap();
    assert!(!sealed.contains(CANARY));
    assert!(!sealed.contains("shared_secrets"));
    assert_eq!(sealed.matches("key_id").count(), 1);
    let envelope = parse_envelope(&sealed).unwrap().unwrap();
    assert_eq!(&*open(&envelope, &keys).unwrap(), &plaintext);
}

#[test]
fn repeated_writes_use_distinct_nonces_and_ciphertext() {
    let keys = MemoryKeys::default();
    let a = parse_envelope(&seal(CANARY, ID, true, &keys).unwrap()).unwrap().unwrap();
    let b = parse_envelope(&seal(CANARY, ID, false, &keys).unwrap()).unwrap().unwrap();
    assert_ne!(a.nonce, b.nonce);
    assert_ne!(a.ciphertext, b.ciphertext);
}

#[test]
fn modified_ciphertext_and_nonce_fail_authentication() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    for field in ["ciphertext", "nonce"] {
        let mut value: serde_json::Value = serde_json::from_str(&sealed).unwrap();
        let mut bytes = STANDARD.decode(value[field].as_str().unwrap()).unwrap();
        bytes[0] ^= 1;
        value[field] = STANDARD.encode(bytes).into();
        let envelope = parse_envelope(&value.to_string()).unwrap().unwrap();
        let error = open(&envelope, &keys).unwrap_err().to_string();
        assert!(!error.contains(CANARY));
        assert!(error.contains("原文件已保留"));
    }
}

#[test]
fn modified_key_id_with_identical_key_still_fails_aad() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    let other = "b".repeat(64);
    keys.set(&other, &keys.get(ID).unwrap().unwrap()).unwrap();
    let mut envelope = parse_envelope(&sealed).unwrap().unwrap();
    envelope.key_id = other;
    assert!(open(&envelope, &keys).is_err());
}

#[test]
fn missing_key_does_not_create_a_replacement() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    let missing = MemoryKeys::default();
    assert!(open(&parse_envelope(&sealed).unwrap().unwrap(), &missing).is_err());
    assert!(seal(CANARY, ID, false, &missing).is_err());
    assert!(missing.get(ID).unwrap().is_none());
}

#[test]
fn unknown_envelope_fields_versions_and_algorithms_fail_closed() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    for (field, v) in [("schema_version", serde_json::json!(3)), ("storage_version", serde_json::json!(99)),
        ("algorithm", serde_json::json!("none")), ("extra", serde_json::json!(CANARY))] {
        let mut value: serde_json::Value = serde_json::from_str(&sealed).unwrap();
        value[field] = v;
        assert!(parse_envelope(&value.to_string()).is_err());
    }
}

#[test]
fn duplicate_envelope_keys_are_rejected() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    let duplicate = sealed.replacen('{', "{\"schema_version\":2,", 1);
    assert!(parse_envelope(&duplicate).is_err());
}

#[test]
fn invalid_key_length_never_saves_a_document() {
    let keys = MemoryKeys::default();
    keys.set(ID, b"short").unwrap();
    assert!(seal(CANARY, ID, true, &keys).is_err());
}

struct FailingKeys;
impl KeyStore for FailingKeys {
    fn get(&self, _: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> { Ok(None) }
    fn set(&self, _: &str, _: &[u8]) -> AppResult<()> { Err(invalid()) }
}

#[test]
fn backend_write_failure_is_not_a_plaintext_fallback() {
    assert!(seal(CANARY, ID, true, &FailingKeys).is_err());
}

struct NonPersistentKeys;
impl KeyStore for NonPersistentKeys {
    fn get(&self, _: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> { Ok(None) }
    fn set(&self, _: &str, _: &[u8]) -> AppResult<()> { Ok(()) }
}

#[test]
fn backend_must_confirm_created_key_is_readable() {
    assert!(seal(CANARY, ID, true, &NonPersistentKeys).is_err());
}

#[test]
fn legacy_json_is_identified_without_requesting_a_key() {
    assert!(parse_envelope(r#"{"profiles":[]}"#).unwrap().is_none());
    assert!(parse_envelope("not json").is_err());
}

#[test]
fn ordinary_legacy_extension_names_are_not_mistaken_for_an_envelope() {
    let raw = r#"{"profiles":[],"format":"editor-export","storage_version":9}"#;
    assert!(parse_envelope(raw).unwrap().is_none());
}

#[test]
fn changed_or_missing_format_does_not_bypass_envelope_validation() {
    let keys = MemoryKeys::default();
    let sealed = seal(CANARY, ID, true, &keys).unwrap();
    for format in [Some("unknown"), None] {
        let mut value: serde_json::Value = serde_json::from_str(&sealed).unwrap();
        match format {
            Some(format) => { value["format"] = format.into(); }
            None => { value.as_object_mut().unwrap().remove("format"); }
        }
        assert!(parse_envelope(&value.to_string()).is_err());
    }
}
