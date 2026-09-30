use super::*;
use key_store::{KeyStore, MemoryKeys};
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Mutex,
};

struct ChangingKeys {
    value: Mutex<Result<Option<Zeroizing<Vec<u8>>>, ()>>,
    reads: AtomicUsize,
}
impl KeyStore for ChangingKeys {
    fn get(&self, _: &str) -> AppResult<Option<Zeroizing<Vec<u8>>>> {
        self.reads.fetch_add(1, Ordering::SeqCst);
        self.value
            .lock()
            .unwrap()
            .as_ref()
            .cloned()
            .map_err(|_| invalid())
    }
    fn set(&self, _: &str, _: &[u8]) -> AppResult<()> {
        panic!("a scan must never write credentials")
    }
}

#[test]
fn every_record_reloads_keys_and_authenticates_current_bytes() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("auth.json");
    let id = encrypted_config::key_id_for_path(&path).unwrap();
    let initial = MemoryKeys::default();
    initial.set(&id, &[42; 32]).unwrap();
    Vault::new(&initial)
        .write_scoped(&path, r#"{"epoch":1}"#, &id, false)
        .unwrap();
    let document = AuthDocument::open(root.path()).unwrap();
    let keys = ChangingKeys {
        value: Mutex::new(Ok(Some(Zeroizing::new(vec![42; 32])))),
        reads: AtomicUsize::new(0),
    };
    let read = || document.load_using::<serde_json::Value>(&keys);
    assert_eq!(read().unwrap().unwrap()["epoch"], 1);
    assert_eq!(read().unwrap().unwrap()["epoch"], 1);
    assert_eq!(keys.reads.load(Ordering::SeqCst), 2);
    let original = std::fs::read(&path).unwrap();

    *keys.value.lock().unwrap() = Ok(None); // deleted key
    assert!(read().is_err());
    *keys.value.lock().unwrap() = Ok(Some(Zeroizing::new(vec![43; 32]))); // rotated key
    assert!(read().is_err());
    *keys.value.lock().unwrap() = Err(()); // locked / ambiguous / disconnected provider
    assert!(read().is_err());
    assert_eq!(std::fs::read(&path).unwrap(), original);
    assert_eq!(keys.reads.load(Ordering::SeqCst), 5);

    *keys.value.lock().unwrap() = Ok(Some(Zeroizing::new(vec![42; 32])));
    Vault::new(&initial)
        .write_scoped(&path, r#"{"epoch":2}"#, &id, false)
        .unwrap();
    assert_eq!(read().unwrap().unwrap()["epoch"], 2); // no document cache
    let mut envelope: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let ciphertext = envelope["ciphertext"].as_str().unwrap();
    envelope["ciphertext"] = format!(
        "{}{}",
        if ciphertext.starts_with('A') {
            "B"
        } else {
            "A"
        },
        &ciphertext[1..]
    )
    .into();
    std::fs::write(&path, serde_json::to_vec(&envelope).unwrap()).unwrap();
    assert!(read().is_err()); // valid envelope, invalid authentication tag
    assert_eq!(keys.reads.load(Ordering::SeqCst), 7);
}

#[cfg(all(target_os = "linux", feature = "native-keyring-tests"))]
#[test]
fn native_scan_reader_rechecks_deleted_rotated_keys_and_ciphertext() {
    let root = tempfile::tempdir().unwrap();
    let mut document = AuthDocument::open(root.path()).unwrap();
    struct Cleanup(String);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            let _ = keyring::Entry::new(key_store::SERVICE, &self.0)
                .and_then(|entry| entry.delete_credential());
        }
    }
    let _cleanup = Cleanup(document.key_id.clone());
    document.save(&serde_json::json!({"epoch":1})).unwrap();
    let original = std::fs::read(&document.path).unwrap();
    let entry = keyring::Entry::new(key_store::SERVICE, &document.key_id).unwrap();
    let key = Zeroizing::new(entry.get_secret().unwrap());
    let reader = AuthDocumentReader::default();
    assert_eq!(
        reader
            .load::<serde_json::Value>(&document)
            .unwrap()
            .unwrap()["epoch"],
        1
    );
    document.save(&serde_json::json!({"epoch":2})).unwrap();
    assert_eq!(
        reader
            .load::<serde_json::Value>(&document)
            .unwrap()
            .unwrap()["epoch"],
        2
    );
    let mut changed_key = key.clone();
    changed_key[0] ^= 1;
    entry.set_secret(&changed_key).unwrap();
    assert!(reader.load::<serde_json::Value>(&document).is_err());
    entry.delete_credential().unwrap();
    assert!(reader.load::<serde_json::Value>(&document).is_err());
    assert!(matches!(entry.get_secret(), Err(keyring::Error::NoEntry)));
    entry.set_secret(&key).unwrap();
    std::fs::write(&document.path, original).unwrap();
    assert_eq!(
        reader
            .load::<serde_json::Value>(&document)
            .unwrap()
            .unwrap()["epoch"],
        1
    );
    std::fs::write(&document.path, "corrupt").unwrap();
    assert!(reader.load::<serde_json::Value>(&document).is_err());
    assert_eq!(std::fs::read_to_string(&document.path).unwrap(), "corrupt");
}
