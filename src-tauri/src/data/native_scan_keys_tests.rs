use super::*;

#[test]
fn native_scan_keys_use_fresh_unique_lookups_and_legacy_fallback() {
    let service = SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, 0).unwrap();
    let collection = service.get_default_collection().unwrap();
    let id = format!("scan-fixture-{}", uuid::Uuid::new_v4());
    let exact = HashMap::from([
        ("service", SERVICE),
        ("username", id.as_str()),
        ("target", "default"),
    ]);
    let legacy = HashMap::from([("service", SERVICE), ("username", id.as_str())]);
    let keys = ScanKeys::default();
    assert!(keys.get(&id).unwrap().is_none());
    let item = collection
        .create_item(
            "scan synthetic fixture",
            exact.clone(),
            &[42; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[42; 32]);
    item.set_secret(&[43; 32], "application/octet-stream")
        .unwrap();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[43; 32]);
    let duplicate = collection
        .create_item(
            "scan synthetic duplicate",
            exact,
            &[44; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    assert!(keys.get(&id).is_err());
    duplicate.delete().unwrap();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[43; 32]);
    item.delete().unwrap();
    assert!(keys.get(&id).unwrap().is_none());
    let old = collection
        .create_item(
            "scan synthetic legacy",
            legacy.clone(),
            &[45; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[45; 32]);
    let second = collection
        .create_item(
            "scan synthetic legacy duplicate",
            legacy,
            &[46; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    assert!(keys.get(&id).is_err());
    second.delete().unwrap();
    assert!(keys.set(&id, &[47; 32]).is_err());
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[45; 32]);
    old.delete().unwrap();
    assert!(keys.get(&id).unwrap().is_none());
}

#[test]
fn native_scan_exact_match_precedes_legacy_and_fallback_stays_in_default() {
    let service = SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, 0).unwrap();
    let default = service.get_default_collection().unwrap();
    let session = service.get_collection_by_alias("session").unwrap();
    let id = format!("scan-compatibility-{}", uuid::Uuid::new_v4());
    let legacy = HashMap::from([("service", SERVICE), ("username", id.as_str())]);
    let old = default
        .create_item(
            "scan old default",
            legacy.clone(),
            &[42; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    let outside = session
        .create_item(
            "scan old outside",
            legacy,
            &[43; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    let current = session
        .create_item(
            "scan current exact",
            HashMap::from([
                ("service", SERVICE),
                ("username", id.as_str()),
                ("target", "default"),
            ]),
            &[44; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    let keys = ScanKeys::default();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[44; 32]);
    current.delete().unwrap();
    assert_eq!(&**keys.get(&id).unwrap().as_ref().unwrap(), &[42; 32]);
    old.delete().unwrap();
    assert!(
        keys.get(&id).unwrap().is_none(),
        "fallback cannot search outside default"
    );
    outside.delete().unwrap();
}

/// Run only through scripts/native_scan_keyring_fixture.py, which owns a new
/// D-Bus, keyring daemon, home and disposable credentials. Never lock a user's
/// normal default collection or stop their Secret Service.
#[test]
fn native_scan_service_lifecycle() {
    use std::{
        path::PathBuf,
        time::{Duration, Instant},
    };
    let fixture = PathBuf::from(
        std::env::var_os("CTM_NATIVE_SCAN_FIXTURE").expect("private fixture required"),
    );
    assert_eq!(
        std::env::var_os("HOME").unwrap(),
        fixture.join("home").as_os_str()
    );
    let wait = |stage: &str| {
        std::fs::write(fixture.join(format!("ready-{stage}")), b"ready").unwrap();
        let deadline = Instant::now() + Duration::from_secs(20);
        while !fixture.join(format!("go-{stage}")).exists() {
            assert!(
                Instant::now() < deadline,
                "fixture stage timed out: {stage}"
            );
            std::thread::sleep(Duration::from_millis(10));
        }
    };
    let id = format!("scan-lifecycle-{}", uuid::Uuid::new_v4());
    let entry = keyring::Entry::new(SERVICE, &id).unwrap();
    entry.set_secret(&[42; 32]).unwrap();
    let reader = ScanKeys::default();
    assert_eq!(&**reader.get(&id).unwrap().as_ref().unwrap(), &[42; 32]);
    let service = SecretService::connect_with_max_prompt_timeout(EncryptionType::Dh, 0).unwrap();
    let session_collection = service.get_collection_by_alias("session").unwrap();
    let duplicate = session_collection
        .create_item(
            "scan lifecycle duplicate",
            HashMap::from([
                ("service", SERVICE),
                ("username", id.as_str()),
                ("target", "default"),
            ]),
            &[43; 32],
            false,
            "application/octet-stream",
        )
        .unwrap();
    assert!(reader.get(&id).is_err());
    wait("lock");
    let found = service
        .search_items(HashMap::from([
            ("service", SERVICE),
            ("username", id.as_str()),
            ("target", "default"),
        ]))
        .unwrap();
    assert_eq!(
        found.locked.len(),
        1,
        "fixture must prove a locked duplicate"
    );
    assert_eq!(
        found.unlocked.len(),
        1,
        "fixture must retain the unlocked duplicate"
    );
    assert!(reader.get(&id).is_err());
    duplicate.delete().unwrap();
    assert!(ScanKeys::default().get(&id).is_err());
    wait("disconnect");
    assert!(reader.get(&id).is_err());
    assert!(ScanKeys::default().get(&id).is_err());
    wait("restart");
    assert!(
        reader.get(&id).is_err(),
        "an expired encryption session cannot be reused"
    );
    let fresh = ScanKeys::default();
    assert_eq!(&**fresh.get(&id).unwrap().as_ref().unwrap(), &[42; 32]);
    entry.delete_credential().unwrap();
    assert!(fresh.get(&id).unwrap().is_none());
    wait("bus-disconnect");
    assert!(fresh.get(&id).is_err());
    assert!(ScanKeys::default().get(&id).is_err());
}
