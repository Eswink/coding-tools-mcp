//! Portable shipped-command contracts. All keys/tokens are disposable canaries.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde_json::{json, Value};
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, Output, Stdio},
};
use uuid::Uuid;
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let p = std::env::temp_dir().join(format!("ctm-enrollment-{}", Uuid::new_v4()));
        std::fs::create_dir(&p).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o700)).unwrap();
        }
        Self(p.canonicalize().unwrap())
    }
    fn identity(&self) -> PathBuf {
        let p = self.0.join("identity.json");
        std::fs::write(&p,serde_json::to_vec(&json!({"origin":"https://gateway.example.invalid","prefix":"/coding-tools","connector":Uuid::from_u128(1)})).unwrap()).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o600)).unwrap();
        }
        p
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
fn agent(args: &[&str], bytes: &[u8]) -> Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_coding-tools-agent"))
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child.stdin.take().unwrap().write_all(bytes).unwrap();
    child.wait_with_output().unwrap()
}
fn key() -> Value {
    let o = agent(&["generate-key", "--output-stdout"], b"");
    assert!(o.status.success());
    let k: Value = serde_json::from_slice(&o.stdout).unwrap();
    assert!(!String::from_utf8_lossy(&o.stderr).contains(k["pkcs8"].as_str().unwrap()));
    k
}
fn invite() -> Value {
    json!({"version":1,"origin":"https://gateway.example.invalid","prefix":"/coding-tools","connector":Uuid::from_u128(1),"token":URL_SAFE_NO_PAD.encode([7u8;32])})
}
fn prove(d: &Directory, invitation: Value, key: Value) -> Output {
    agent(
        &[
            "prove-enrollment",
            "--config",
            d.identity().to_str().unwrap(),
            "--bundle-stdin",
            "--output-stdout",
        ],
        &serde_json::to_vec(&json!({"invitation":invitation,"key":key})).unwrap(),
    )
}
fn rejected(o: Output) {
    assert!(!o.status.success());
    assert!(o.stdout.is_empty());
    assert!(o.stderr.len() < 100);
}
#[test]
fn generated_keys_are_distinct_valid_pkcs8_and_not_diagnostic_output() {
    let a = key();
    let b = key();
    assert_ne!(a, b);
    for k in [a, b] {
        let raw = URL_SAFE_NO_PAD
            .decode(k["pkcs8"].as_str().unwrap())
            .unwrap();
        ring::signature::Ed25519KeyPair::from_pkcs8(&raw).unwrap();
    }
}
#[test]
fn explicit_output_is_mandatory_and_duplicate_flags_are_rejected() {
    rejected(agent(&["generate-key"], b""));
    rejected(agent(
        &["generate-key", "--output-stdout", "--output-stdout"],
        b"",
    ));
    rejected(agent(&["generate-key", "--secret-canary-argument"], b""));
}
#[test]
fn device_proof_matches_existing_library_and_contains_no_private_key() {
    let d = Directory::new();
    let k = key();
    let i = invite();
    let o = prove(&d, i.clone(), k.clone());
    assert!(o.status.success());
    let p: Value = serde_json::from_slice(&o.stdout).unwrap();
    assert!(!String::from_utf8_lossy(&o.stdout).contains(k["pkcs8"].as_str().unwrap()));
    assert!(!String::from_utf8_lossy(&o.stderr).contains(i["token"].as_str().unwrap()));
    let id = coding_tools_cloud_gateway::PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap();
    let public = URL_SAFE_NO_PAD
        .decode(p["public_key"].as_str().unwrap())
        .unwrap();
    let signature = URL_SAFE_NO_PAD
        .decode(p["signature"].as_str().unwrap())
        .unwrap();
    let msg = coding_tools_cloud_gateway::device::enrollment_message(
        &id,
        i["token"].as_str().unwrap(),
        &public,
    )
    .unwrap();
    ring::signature::UnparsedPublicKey::new(&ring::signature::ED25519, public)
        .verify(&msg, &signature)
        .unwrap();
}
#[test]
fn foreign_invitation_identity_is_not_signed() {
    let d = Directory::new();
    let k = key();
    let mut i = invite();
    i["origin"] = json!("https://foreign.example.invalid");
    rejected(prove(&d, i, k));
}
#[test]
fn foreign_connector_and_unknown_invitation_version_are_not_signed() {
    let d = Directory::new();
    let k = key();
    let mut i = invite();
    i["connector"] = json!(Uuid::from_u128(2));
    rejected(prove(&d, i, k.clone()));
    let mut i = invite();
    i["version"] = json!(2);
    rejected(prove(&d, i, k));
}
#[test]
fn unknown_authority_or_key_fields_cannot_be_smuggled() {
    let d = Directory::new();
    let mut k = key();
    k["grant"] = json!("model-controlled");
    rejected(prove(&d, invite(), k));
    let mut i = invite();
    i["scopes"] = json!(["exec.run"]);
    rejected(prove(&d, i, key()));
}
#[test]
fn malformed_or_noncanonical_key_is_not_echoed() {
    let d = Directory::new();
    rejected(prove(
        &d,
        invite(),
        json!({"pkcs8":"secret-malformed-canary"}),
    ));
    let mut k = key();
    k["pkcs8"] = json!(format!("{}=", k["pkcs8"].as_str().unwrap()));
    rejected(prove(&d, invite(), k));
}
#[test]
fn duplicated_json_and_oversized_bundle_fail_closed() {
    let d = Directory::new();
    let path = d.identity();
    let args = [
        "prove-enrollment",
        "--config",
        path.to_str().unwrap(),
        "--bundle-stdin",
        "--output-stdout",
    ];
    rejected(agent(&args, b"{\"key\":{},\"key\":{},\"invitation\":{}}"));
    rejected(agent(&args, &vec![b'x'; 16_385]));
}
#[test]
fn multiple_stdin_documents_are_rejected_before_consumption() {
    let d = Directory::new();
    rejected(agent(
        &[
            "prove-enrollment",
            "--config",
            d.identity().to_str().unwrap(),
            "--input-stdin",
            "--key-stdin",
            "--output-stdout",
        ],
        b"",
    ));
}
#[cfg(unix)]
#[test]
fn private_key_file_is_owner_only_and_never_overwritten() {
    use std::os::unix::fs::MetadataExt;
    let d = Directory::new();
    let p = d.0.join("key.json");
    let args = ["generate-key", "--output-file", p.to_str().unwrap()];
    let o = agent(&args, b"");
    assert!(o.status.success());
    assert!(o.stdout.is_empty());
    let before = std::fs::read(&p).unwrap();
    assert_eq!(std::fs::metadata(&p).unwrap().mode() & 0o777, 0o600);
    rejected(agent(&args, b""));
    assert_eq!(before, std::fs::read(&p).unwrap());
}
#[cfg(unix)]
#[test]
fn symlink_and_unsafe_parent_output_are_rejected() {
    use std::os::unix::fs::{symlink, PermissionsExt};
    let d = Directory::new();
    let target = d.0.join("target");
    std::fs::write(&target, b"keep").unwrap();
    let link = d.0.join("link");
    symlink(&target, &link).unwrap();
    rejected(agent(
        &["generate-key", "--output-file", link.to_str().unwrap()],
        b"",
    ));
    assert_eq!(std::fs::read(target).unwrap(), b"keep");
    std::fs::set_permissions(&d.0, std::fs::Permissions::from_mode(0o777)).unwrap();
    rejected(agent(
        &[
            "generate-key",
            "--output-file",
            d.0.join("new").to_str().unwrap(),
        ],
        b"",
    ));
}
#[cfg(not(unix))]
#[test]
fn secret_file_output_requires_native_acl_support_and_stream_still_works() {
    let d = Directory::new();
    rejected(agent(
        &[
            "generate-key",
            "--output-file",
            d.0.join("key.json").to_str().unwrap(),
        ],
        b"",
    ));
    let _ = key();
}
