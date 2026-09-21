use coding_tools_cloud_gateway::service::{read_protected, GatewayConfig};
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
use uuid::Uuid;

fn config() -> Value {
    json!({"origin":"https://gateway.example.invalid","prefix":"/coding-tools",
        "connector":Uuid::from_u128(1),"owner_subject":Uuid::from_u128(2),
        "client_id":"public-client","redirect_uri":"https://client.example.invalid/callback",
        "client_authentication":"public"})
}
struct PrivateDir(PathBuf);
impl PrivateDir {
    fn new() -> Self {
        let dir = std::env::temp_dir().join(format!("ctm-cli-contract-{}", Uuid::new_v4()));
        fs::create_dir(&dir).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        }
        Self(dir.canonicalize().unwrap())
    }
    fn file(&self, name: &str, bytes: &[u8]) -> PathBuf {
        let p = self.0.join(name);
        fs::write(&p, bytes).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&p, fs::Permissions::from_mode(0o600)).unwrap();
        }
        p
    }
}
impl Drop for PrivateDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn exe() -> &'static str {
    env!("CARGO_BIN_EXE_coding-tools-gateway")
}
fn cfg(bytes: &Value) -> bool {
    GatewayConfig::from_bytes(&serde_json::to_vec(bytes).unwrap()).is_ok()
}
#[test]
fn defaults_are_loopback_and_not_privileged() {
    let c = GatewayConfig::from_bytes(&serde_json::to_vec(&config()).unwrap()).unwrap();
    assert_eq!(c.bind.to_string(), "127.0.0.1:28880");
}
#[test]
fn public_bind_rejected() {
    for bind in ["0.0.0.0:28880", "[::]:28880", "192.0.2.1:3000"] {
        let mut c = config();
        c["bind"] = json!(bind);
        assert!(!cfg(&c));
    }
}
#[test]
fn privileged_ports_rejected() {
    for p in [80, 443, 1023] {
        let mut c = config();
        c["bind"] = json!(format!("127.0.0.1:{p}"));
        assert!(!cfg(&c));
    }
}
#[test]
fn ephemeral_loopback_accepted_for_isolated_tests() {
    let mut c = config();
    c["bind"] = json!("127.0.0.1:0");
    assert!(cfg(&c));
}
#[test]
fn unknown_or_missing_configuration_rejected() {
    let mut c = config();
    c["password"] = json!("canary");
    assert!(!cfg(&c));
    let mut c = config();
    c.as_object_mut().unwrap().remove("client_authentication");
    assert!(!cfg(&c));
}
#[test]
fn duplicate_config_keys_rejected() {
    let s = serde_json::to_string(&config()).unwrap();
    let duplicated = format!("{{\"origin\":\"https://other.invalid\",{}", &s[1..]);
    assert!(GatewayConfig::from_bytes(duplicated.as_bytes()).is_err());
}
#[test]
fn nil_subject_rejected() {
    let mut c = config();
    c["owner_subject"] = json!(Uuid::nil());
    assert!(!cfg(&c));
}
#[test]
fn http_and_noncanonical_origin_rejected() {
    for origin in [
        "http://example.invalid",
        "https://example.invalid/",
        "https://example.invalid/x",
        "https:example.invalid",
    ] {
        let mut c = config();
        c["origin"] = json!(origin);
        assert!(!cfg(&c));
    }
}
#[test]
fn invalid_redirect_rejected() {
    for r in [
        "http://bad.invalid",
        "https://client.invalid/cb#x",
        "https://client.invalid/cb?code=x",
    ] {
        let mut c = config();
        c["redirect_uri"] = json!(r);
        assert!(!cfg(&c));
    }
}
#[test]
fn oversized_config_rejected() {
    assert!(GatewayConfig::from_bytes(&vec![b' '; 16 * 1024 + 1]).is_err());
}
#[test]
fn binary_help_and_version_do_not_need_credentials() {
    for arg in ["--help", "--version"] {
        let r = Command::new(exe()).arg(arg).output().unwrap();
        assert!(r.status.success());
        assert!(r.stderr.is_empty());
    }
}
#[test]
fn unknown_argument_never_echoed() {
    let r = Command::new(exe())
        .arg("canary-secret-in-arg")
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(!String::from_utf8_lossy(&r.stderr).contains("canary"));
}
#[test]
fn check_config_does_not_contact_database() {
    let d = PrivateDir::new();
    let p = d.file("config.json", &serde_json::to_vec(&config()).unwrap());
    let r = Command::new(exe())
        .args(["check-config", "--config"])
        .arg(p)
        .env("DATABASE_URL", "not-a-real-DSN")
        .output()
        .unwrap();
    assert!(r.status.success());
    assert!(String::from_utf8_lossy(&r.stdout).contains("configuration_only"));
}
#[test]
fn no_ambient_secret_fallback() {
    let d = PrivateDir::new();
    let p = d.file("config.json", &serde_json::to_vec(&config()).unwrap());
    let r = Command::new(exe())
        .args(["serve", "--config"])
        .arg(p)
        .env("DATABASE_URL", "canary-url")
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("invalid_arguments"));
}
#[test]
fn malformed_stdin_is_not_logged() {
    let d = PrivateDir::new();
    let p = d.file("config.json", &serde_json::to_vec(&config()).unwrap());
    let mut child = Command::new(exe())
        .args(["serve", "--config"])
        .arg(p)
        .arg("--secrets-stdin")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(b"canary-secret-input")
        .unwrap();
    let r = child.wait_with_output().unwrap();
    assert!(!r.status.success());
    assert!(!String::from_utf8_lossy(&r.stderr).contains("canary"));
}
#[test]
fn secret_sources_are_mutually_exclusive() {
    let d = PrivateDir::new();
    let p = d.file("config.json", &serde_json::to_vec(&config()).unwrap());
    let r = Command::new(exe())
        .args(["serve", "--config"])
        .arg(&p)
        .arg("--secrets-stdin")
        .arg("--secrets-file")
        .arg(&p)
        .output()
        .unwrap();
    assert!(!r.status.success());
    assert!(String::from_utf8_lossy(&r.stderr).contains("invalid_arguments"));
}
#[test]
fn rotation_requires_positive_epoch() {
    let d = PrivateDir::new();
    let p = d.file("config.json", &serde_json::to_vec(&config()).unwrap());
    for epoch in [None, Some("0"), Some("-1"), Some("garbage")] {
        let mut c = Command::new(exe());
        c.args(["rotate-owner", "--config"])
            .arg(&p)
            .arg("--secrets-stdin");
        if let Some(e) = epoch {
            c.args(["--expected-epoch", e]);
        }
        let r = c.output().unwrap();
        assert!(!r.status.success());
        assert!(String::from_utf8_lossy(&r.stderr).contains("invalid_arguments"));
    }
}
#[cfg(unix)]
#[test]
fn owner_only_secret_read_succeeds() {
    let d = PrivateDir::new();
    let p = d.file("secret", b"canary");
    assert_eq!(read_protected(&p).unwrap().as_slice(), b"canary");
}
#[cfg(unix)]
#[test]
fn insecure_modes_rejected_even_when_root_can_read() {
    use std::os::unix::fs::PermissionsExt;
    let d = PrivateDir::new();
    let p = d.file("secret", b"canary");
    for mode in [0o644, 0o640, 0o606] {
        fs::set_permissions(&p, fs::Permissions::from_mode(mode)).unwrap();
        assert!(read_protected(&p).is_err());
    }
}
#[cfg(unix)]
#[test]
fn symlink_and_hardlink_secret_rejected() {
    use std::os::unix::fs::symlink;
    let d = PrivateDir::new();
    let p = d.file("secret", b"canary");
    let s = d.0.join("link");
    symlink(&p, &s).unwrap();
    assert!(read_protected(&s).is_err());
    fs::remove_file(s).unwrap();
    fs::hard_link(&p, d.0.join("hardlink")).unwrap();
    assert!(read_protected(&p).is_err());
}
#[cfg(unix)]
#[test]
fn fifo_secret_rejected_without_blocking() {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;
    let d = PrivateDir::new();
    let p = d.0.join("fifo");
    let name = CString::new(p.as_os_str().as_bytes()).unwrap();
    assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o600) }, 0);
    assert!(read_protected(&p).is_err());
}
#[cfg(unix)]
#[test]
fn writable_parent_and_directory_secret_rejected() {
    use std::os::unix::fs::PermissionsExt;
    let d = PrivateDir::new();
    assert!(read_protected(&d.0).is_err());
    let p = d.file("secret", b"canary");
    fs::set_permissions(&d.0, fs::Permissions::from_mode(0o777)).unwrap();
    assert!(read_protected(&p).is_err());
}
#[cfg(unix)]
#[test]
fn oversized_secret_file_rejected() {
    let d = PrivateDir::new();
    let p = d.file("secret", &vec![b'a'; 16 * 1024 + 1]);
    assert!(read_protected(&p).is_err());
}
#[cfg(not(unix))]
#[test]
fn secret_files_fail_closed_without_native_acl_validation() {
    let d = PrivateDir::new();
    let p = d.file("secret", b"canary");
    assert_eq!(
        read_protected(&p).unwrap_err(),
        coding_tools_cloud_gateway::service::ServiceError::FileAclUnsupported
    );
}
