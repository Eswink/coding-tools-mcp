use super::*;
use std::fs;
use std::path::PathBuf;
use std::sync::{Arc, Barrier};

use ring::rand::SystemRandom;
use serde_json::{json, Value};

struct Fixture {
    _directory: tempfile::TempDir,
    store: ConnectionStore,
    root: PathBuf,
    workspace: PathBuf,
    config: Value,
    private: String,
}

impl Fixture {
    fn new() -> Self {
        let directory = tempfile::tempdir().unwrap();
        let workspace = directory.path().join("approved-workspace");
        fs::create_dir(&workspace).unwrap();
        let root = directory.path().join("connections").join("selected");
        let (public, private) = key_pair();
        let config = json!({
            "version": 1,
            "origin": "https://gateway.example.test",
            "prefix": "/coding-tools",
            "connector": "a45d243b-9954-4a7e-894a-9b91ed6f622c",
            "device": "c8dac0b9-8dc1-481b-a10e-671f2ed4c002",
            "device_epoch": 1,
            "authority_epoch": 1,
            "public_key": public,
            "run_seconds": 3600
        });
        let store = ConnectionStore::at(root.clone(), "selected-profile", &workspace).unwrap();
        Self {
            _directory: directory,
            store,
            root,
            workspace,
            config,
            private,
        }
    }

    fn input(&self) -> CheckedImport {
        CheckedImport::parse(&self.config.to_string(), &self.private).unwrap()
    }

    fn initialize(&self) {
        self.store.initialize(self.input()).unwrap();
    }

    fn encrypted(&self) -> Vec<u8> {
        fs::read(self.root.join("auth.json")).unwrap()
    }
}

fn create_private_fixture_directory(path: &std::path::Path) {
    let mut builder = fs::DirBuilder::new();
    builder.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder.create(path).unwrap();
}

fn key_pair() -> (String, String) {
    let document = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
    let key = Ed25519KeyPair::from_pkcs8(document.as_ref()).unwrap();
    let public = URL_SAFE_NO_PAD.encode(key.public_key().as_ref());
    let private = json!({"pkcs8": URL_SAFE_NO_PAD.encode(document.as_ref())}).to_string();
    (public, private)
}

fn reject_field(field: &str, value: Value) {
    let fixture = Fixture::new();
    let mut config = fixture.config.clone();
    config[field] = value;
    assert!(CheckedImport::parse(&config.to_string(), &fixture.private).is_err());
    assert!(!fixture.root.exists());
}

#[test]
fn matching_input_has_a_configuration_only_public_summary() {
    let fixture = Fixture::new();
    let summary = fixture.store.initialize(fixture.input()).unwrap();
    let value = serde_json::to_value(summary).unwrap();
    assert_eq!(value["configured"], true);
    assert_eq!(value["scope"], "configuration_only_not_execution_authority");
    assert_eq!(value["origin"], fixture.config["origin"]);
    for forbidden in [
        "pkcs8",
        "binding_key",
        "workspace",
        "grants",
        "scopes",
        "online",
        "execution_enabled",
    ] {
        assert!(value.get(forbidden).is_none(), "unexpected summary field");
    }
}

#[test]
fn stored_credentials_are_encrypted_and_reopen_without_changes() {
    let fixture = Fixture::new();
    fixture.initialize();
    let encrypted = fixture.encrypted();
    let text = std::str::from_utf8(&encrypted).unwrap();
    let private: Value = serde_json::from_str(&fixture.private).unwrap();
    assert!(!text.contains(private["pkcs8"].as_str().unwrap()));
    assert!(!text.contains("selected-profile"));
    assert!(!text.contains("approved-workspace"));
    let second =
        ConnectionStore::at(fixture.root.clone(), "selected-profile", &fixture.workspace).unwrap();
    assert!(second.summary().unwrap().unwrap().configured);
    assert_eq!(
        second.summary().unwrap().unwrap().origin,
        "https://gateway.example.test"
    );
    assert_eq!(encrypted, fixture.encrypted());
}

#[test]
fn unsupported_origin_forms_are_not_normalized_into_trusted_identity() {
    for origin in [
        "http://gateway.example.test",
        "https://gateway.example.test/",
        "https://gateway.example.test/path",
        "https://user@gateway.example.test",
        "https://user:password@gateway.example.test",
        "https://gateway.example.test?q=1",
        "https://gateway.example.test#fragment",
        "https://GATEWAY.example.test",
        "https://gateway.example.test:443",
        "https://gateway.example.test\\evil",
        "https://gateway.example.test\n",
    ] {
        reject_field("origin", json!(origin));
    }
}

#[test]
fn explicit_nondefault_tls_port_is_preserved() {
    let mut fixture = Fixture::new();
    fixture.config["origin"] = json!("https://gateway.example.test:8443");
    let summary = fixture.store.initialize(fixture.input()).unwrap();
    assert_eq!(summary.origin, "https://gateway.example.test:8443");
}

#[test]
fn unknown_identity_versions_are_rejected() {
    for value in [json!(0), json!(2), json!("1"), Value::Null] {
        reject_field("version", value);
    }
}

#[test]
fn model_authority_paths_and_sandbox_switches_are_not_import_fields() {
    for key in [
        "grant",
        "scopes",
        "workspace",
        "path",
        "revision_file",
        "ca_der_file",
        "environment",
        "disable_sandbox",
        "force",
        "approved",
    ] {
        reject_field(key, json!(true));
    }
}

#[test]
fn route_prefix_cannot_traverse_or_become_a_second_url() {
    for prefix in [
        "",
        "/",
        "coding-tools",
        "/../x",
        "/a/b",
        "/a%2fb",
        "/A",
        "/-a",
        "/a-",
        "/a?b",
        "/a#b",
        "//host",
    ] {
        reject_field("prefix", json!(prefix));
    }
    reject_field("prefix", json!(format!("/{}", "a".repeat(65))));
}

#[test]
fn connector_and_device_require_canonical_nonnil_uuids() {
    for key in ["connector", "device"] {
        for id in [
            "",
            "../../other",
            "00000000-0000-0000-0000-000000000000",
            "A45D243B-9954-4A7E-894A-9B91ED6F622C",
            "a45d243b99544a7e894a9b91ed6f622c",
        ] {
            reject_field(key, json!(id));
        }
    }
}

#[test]
fn epochs_are_positive_signed_integers_without_coercion() {
    for key in ["device_epoch", "authority_epoch"] {
        for epoch in [json!(0), json!(-1), json!(1.5), json!("1"), json!(u64::MAX)] {
            reject_field(key, epoch);
        }
    }
}

#[test]
fn duration_is_bounded_and_not_implicitly_infinite() {
    for duration in [
        json!(0),
        json!(3601),
        json!(u64::MAX),
        json!("3600"),
        Value::Null,
    ] {
        reject_field("run_seconds", duration);
    }
}

#[test]
fn public_key_requires_canonical_base64url_and_exact_length() {
    for key in [
        "".to_owned(),
        "a".repeat(43),
        URL_SAFE_NO_PAD.encode([0u8; 31]),
        format!("{}=", URL_SAFE_NO_PAD.encode([0u8; 32])),
    ] {
        reject_field("public_key", json!(key));
    }
}

#[test]
fn private_key_mismatch_is_rejected_before_namespace_creation() {
    let fixture = Fixture::new();
    let (_, other) = key_pair();
    assert!(matches!(
        CheckedImport::parse(&fixture.config.to_string(), &other),
        Err(ConfigurationError::InvalidBinding)
    ));
    assert!(!fixture.root.exists());
}

#[test]
fn invalid_or_extra_private_fields_are_rejected_without_echoing_input() {
    let fixture = Fixture::new();
    for private in [
        "{}",
        "{\"pkcs8\":\"synthetic-secret-canary\"}",
        "{\"pkcs8\":false}",
        "[]",
    ] {
        let error = CheckedImport::parse(&fixture.config.to_string(), private)
            .err()
            .unwrap();
        assert!(!error.to_string().contains("synthetic-secret-canary"));
    }
    let mut private: Value = serde_json::from_str(&fixture.private).unwrap();
    private["grant"] = json!("active");
    assert!(CheckedImport::parse(&fixture.config.to_string(), &private.to_string()).is_err());
    assert!(!fixture.root.exists());
}

#[test]
fn bounded_inputs_reject_oversize_and_duplicate_fields() {
    let fixture = Fixture::new();
    assert!(CheckedImport::parse(&" ".repeat(MAX_CONFIG_BYTES + 1), &fixture.private).is_err());
    assert!(
        CheckedImport::parse(&fixture.config.to_string(), &" ".repeat(MAX_KEY_BYTES + 1)).is_err()
    );
    let public = fixture.config.to_string();
    let duplicate = format!("{{\"version\":1,{}", &public[1..]);
    assert!(CheckedImport::parse(&duplicate, &fixture.private).is_err());
    assert!(!fixture.root.exists());
}

#[test]
fn checked_input_and_store_debug_are_redacted() {
    let fixture = Fixture::new();
    assert_eq!(
        format!("{:?}", fixture.input()),
        "CheckedImport([REDACTED])"
    );
    assert_eq!(
        format!("{:?}", fixture.store),
        "ConnectionStore([LOCAL_BINDING_REDACTED])"
    );
}

#[test]
fn absent_status_does_not_initialize_any_namespace() {
    let fixture = Fixture::new();
    assert!(fixture.store.summary().unwrap().is_none());
    assert!(!fixture.root.exists());
    assert!(!fixture.root.parent().unwrap().exists());
}

#[test]
fn repeated_import_never_replaces_existing_ciphertext() {
    let fixture = Fixture::new();
    fixture.initialize();
    let original = fixture.encrypted();
    assert!(matches!(
        fixture.store.initialize(fixture.input()),
        Err(ConfigurationError::AlreadyInitialized)
    ));
    assert_eq!(original, fixture.encrypted());
}

#[test]
fn concurrent_initializers_have_exactly_one_winner() {
    let fixture = Fixture::new();
    let barrier = Arc::new(Barrier::new(8));
    let mut threads = Vec::new();
    for _ in 0..8 {
        let barrier = barrier.clone();
        let store =
            ConnectionStore::at(fixture.root.clone(), "selected-profile", &fixture.workspace)
                .unwrap();
        let input = fixture.input();
        threads.push(std::thread::spawn(move || {
            barrier.wait();
            store.initialize(input).map(|_| ())
        }));
    }
    let results: Vec<_> = threads
        .into_iter()
        .map(|thread| thread.join().unwrap())
        .collect();
    assert_eq!(results.iter().filter(|result| result.is_ok()).count(), 1);
    assert_eq!(
        results
            .iter()
            .filter(|result| matches!(result, Err(ConfigurationError::AlreadyInitialized)))
            .count(),
        7
    );
    assert!(fixture.store.summary().unwrap().is_some());
}

#[test]
fn empty_existing_namespace_is_not_a_fresh_import() {
    let fixture = Fixture::new();
    create_private_fixture_directory(&fixture.root);
    assert!(matches!(
        fixture.store.initialize(fixture.input()),
        Err(ConfigurationError::AlreadyInitialized)
    ));
    assert!(fixture.store.summary().is_err());
    assert_eq!(fs::read_dir(&fixture.root).unwrap().count(), 0);
}

#[test]
fn partial_namespace_is_preserved_without_lock_or_document_recreation() {
    let fixture = Fixture::new();
    create_private_fixture_directory(&fixture.root);
    fs::write(fixture.root.join("partial-canary"), "do-not-delete").unwrap();
    assert!(matches!(
        fixture.store.initialize(fixture.input()),
        Err(ConfigurationError::AlreadyInitialized)
    ));
    assert!(fixture.store.summary().is_err());
    assert_eq!(
        fs::read_to_string(fixture.root.join("partial-canary")).unwrap(),
        "do-not-delete"
    );
    assert_eq!(fs::read_dir(&fixture.root).unwrap().count(), 1);
}

#[test]
fn corrupted_ciphertext_is_not_overwritten_or_migrated() {
    let fixture = Fixture::new();
    fixture.initialize();
    fs::write(fixture.root.join("auth.json"), "invalid-ciphertext-canary").unwrap();
    assert!(fixture.store.summary().is_err());
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert_eq!(fixture.encrypted(), b"invalid-ciphertext-canary");
}

#[test]
fn deleted_existing_document_does_not_regenerate_key_or_document() {
    let fixture = Fixture::new();
    fixture.initialize();
    fs::remove_file(fixture.root.join("auth.json")).unwrap();
    assert!(fixture.store.summary().is_err());
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert!(!fixture.root.join("auth.json").exists());
}

#[test]
fn deleted_existing_lock_does_not_create_a_parallel_namespace() {
    let fixture = Fixture::new();
    fixture.initialize();
    fs::remove_file(fixture.root.join("auth.lock")).unwrap();
    assert!(fixture.store.summary().is_err());
    assert!(!fixture.root.join("auth.lock").exists());
}

#[test]
fn existing_document_lock_is_respected() {
    let fixture = Fixture::new();
    fixture.initialize();
    let _owner = crate::data::AuthDocument::open(&fixture.root).unwrap();
    assert!(fixture.store.summary().is_err());
}

#[test]
fn copied_ciphertext_cannot_switch_profile_or_workspace() {
    let fixture = Fixture::new();
    fixture.initialize();
    let other_profile =
        ConnectionStore::at(fixture.root.clone(), "other-profile", &fixture.workspace).unwrap();
    assert!(matches!(
        other_profile.summary(),
        Err(ConfigurationError::InvalidBinding)
    ));
    let other_workspace = fixture.workspace.parent().unwrap().join("other-workspace");
    fs::create_dir(&other_workspace).unwrap();
    let other =
        ConnectionStore::at(fixture.root.clone(), "selected-profile", &other_workspace).unwrap();
    assert!(matches!(
        other.summary(),
        Err(ConfigurationError::InvalidBinding)
    ));
}

#[test]
fn ciphertext_copied_to_another_namespace_is_rejected() {
    let first = Fixture::new();
    let second = Fixture::new();
    first.initialize();
    second.initialize();
    fs::copy(first.root.join("auth.json"), second.root.join("auth.json")).unwrap();
    assert!(second.store.summary().is_err());
}

#[test]
fn authenticated_unknown_document_state_still_fails_closed() {
    let fixture = Fixture::new();
    fixture.initialize();
    {
        let mut disk = crate::data::AuthDocument::open(&fixture.root).unwrap();
        let mut value: Value = disk.load().unwrap().unwrap();
        value["state"] = json!("approved_and_online");
        disk.save(&value).unwrap();
    }
    let before = fixture.encrypted();
    assert!(fixture.store.summary().is_err());
    assert_eq!(before, fixture.encrypted());
}

#[test]
fn no_authorization_or_runtime_journals_are_created_by_import() {
    let fixture = Fixture::new();
    fixture.initialize();
    let mut names: Vec<_> = fs::read_dir(&fixture.root)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect();
    names.sort();
    assert_eq!(names, ["auth.json", "auth.lock"]);
}

#[cfg(unix)]
#[test]
fn symlink_namespace_and_ancestor_are_rejected() {
    use std::os::unix::fs::symlink;
    let fixture = Fixture::new();
    create_private_fixture_directory(fixture.root.parent().unwrap());
    symlink(&fixture.workspace, &fixture.root).unwrap();
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert!(fixture.store.summary().is_err());
    assert_eq!(fs::read_dir(&fixture.workspace).unwrap().count(), 0);
    fs::remove_file(&fixture.root).unwrap();
    fs::remove_dir(fixture.root.parent().unwrap()).unwrap();
    symlink(&fixture.workspace, fixture.root.parent().unwrap()).unwrap();
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert_eq!(fs::read_dir(&fixture.workspace).unwrap().count(), 0);
}

#[cfg(unix)]
#[test]
fn writable_by_other_users_parent_is_rejected() {
    use std::os::unix::fs::PermissionsExt;
    let fixture = Fixture::new();
    fs::create_dir_all(fixture.root.parent().unwrap()).unwrap();
    fs::set_permissions(
        fixture.root.parent().unwrap(),
        fs::Permissions::from_mode(0o777),
    )
    .unwrap();
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert!(!fixture.root.exists());
}

#[cfg(windows)]
#[test]
fn junction_namespace_is_rejected_without_following_its_target() {
    let fixture = Fixture::new();
    fs::create_dir_all(fixture.root.parent().unwrap()).unwrap();
    let output = std::process::Command::new("cmd.exe")
        .args(["/d", "/c", "mklink", "/J"])
        .arg(&fixture.root)
        .arg(&fixture.workspace)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "owned junction fixture setup failed"
    );
    assert!(fixture.store.initialize(fixture.input()).is_err());
    assert!(fixture.store.summary().is_err());
    assert_eq!(fs::read_dir(&fixture.workspace).unwrap().count(), 0);
    fs::remove_dir(&fixture.root).unwrap();
}

#[test]
fn runtime_material_loads_only_immutable_local_configuration_without_initializing_journals() {
    let fixture=Fixture::new(); fixture.initialize();
    let before=fixture.encrypted();
    let material=fixture.store.runtime_material().unwrap();
    assert!(!material.root.exists());
    let cfg=coding_tools_cloud_agent::AgentConfig::from_bytes(&material.config).unwrap();
    assert_eq!(cfg.origin,"https://gateway.example.test");
    assert!(cfg.ca_der_file.is_none());
    assert!(material.link.for_workspace("selected-profile",&fixture.workspace));
    assert_eq!(before,fixture.encrypted());
    assert!(material.prepare_journals(false).is_err());
    assert!(!material.root.exists());
    material.prepare_journals(true).unwrap();
    assert!(material.prepare_journals(true).is_err());
    assert!(material.prepare_journals(false).is_err());
}
