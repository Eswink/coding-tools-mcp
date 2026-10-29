use super::{
    config::AgentConfig,
    journal::RevisionJournal,
    signer::RecoverySigner,
    wire::{ServerMessage, SnapshotChallenge},
    AgentError,
};
use crate::{
    channel::{verify_connect, ConnectChallenge},
    device::EnrolledDevice,
    projection::{verify_snapshot, ExecutionState, ProjectionClaims, ProjectionPhase},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use serde_json::json;
use std::{fs, io::Write, path::PathBuf};
use uuid::Uuid;
struct Fixture {
    root: PathBuf,
    cfg: AgentConfig,
    input: Vec<u8>,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!("ctm-agent-unit-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        let pkcs = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        let key = Ed25519KeyPair::from_pkcs8(pkcs.as_ref()).unwrap();
        let doc = json!({"origin":"https://gateway.example.invalid","prefix":"/coding-tools","connector":Uuid::new_v4(),"device":Uuid::new_v4(),
            "device_epoch":1,"authority_epoch":1,"public_key":URL_SAFE_NO_PAD.encode(key.public_key().as_ref()),"revision_file":root.join("revision.bin"),"run_seconds":30});
        let cfg = AgentConfig::from_bytes(&serde_json::to_vec(&doc).unwrap()).unwrap();
        Self {
            root,
            cfg,
            input: serde_json::to_vec(&json!({"pkcs8":URL_SAFE_NO_PAD.encode(pkcs.as_ref())}))
                .unwrap(),
        }
    }
    fn signer(&self) -> RecoverySigner {
        RecoverySigner::from_input(self.cfg.clone(), &self.input).unwrap()
    }
    fn challenge(&self) -> ConnectChallenge {
        let id = self.cfg.identity().unwrap();
        ConnectChallenge {
            version: 1,
            issuer: id.issuer(),
            resource: id.resource(),
            connector: id.connector(),
            gateway_boot: Uuid::new_v4(),
            attempt: Uuid::new_v4(),
            nonce: URL_SAFE_NO_PAD.encode([2; 32]),
            issued_at: 100,
            expires_at: 110,
        }
    }
    fn device(&self) -> EnrolledDevice {
        EnrolledDevice {
            id: self.cfg.device,
            connector: self.cfg.connector,
            epoch: 1,
            public_key: self.cfg.key_bytes().unwrap(),
        }
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
#[test]
fn config_derives_exact_wss_endpoint() {
    let f = Fixture::new();
    assert_eq!(
        f.cfg.endpoint().unwrap(),
        "wss://gateway.example.invalid/coding-tools/agent"
    );
}
#[test]
fn config_rejects_origin_repairs() {
    for origin in [
        "http://example.com",
        "https://example.com/",
        "https:example.com",
        "https://example.com?x=1",
        "https://user@example.com",
    ] {
        let f = Fixture::new();
        let mut c = f.cfg.clone();
        c.origin = origin.into();
        assert!(c.identity().is_err());
    }
}
#[test]
fn config_rejects_arbitrary_peer_signing_fields() {
    let f = Fixture::new();
    let base = json!({"origin":f.cfg.origin,"prefix":f.cfg.prefix,"connector":f.cfg.connector,"device":f.cfg.device,"device_epoch":1,"authority_epoch":1,"public_key":f.cfg.public_key,"revision_file":f.cfg.revision_file});
    for field in [
        "grant",
        "scopes",
        "endpoint",
        "execution",
        "insecure",
        "revision",
    ] {
        let mut c = base.clone();
        c[field] = json!(true);
        assert!(AgentConfig::from_bytes(&serde_json::to_vec(&c).unwrap()).is_err());
    }
}
#[test]
fn config_bounds_runtime() {
    let f = Fixture::new();
    for seconds in [0, 3601, u64::MAX] {
        let c = json!({"origin":f.cfg.origin,"prefix":f.cfg.prefix,"connector":f.cfg.connector,"device":f.cfg.device,"device_epoch":1,"authority_epoch":1,"public_key":f.cfg.public_key,"revision_file":f.cfg.revision_file,"run_seconds":seconds});
        assert!(AgentConfig::from_bytes(&serde_json::to_vec(&c).unwrap()).is_err());
    }
}
#[test]
fn key_must_match_pinned_public_key() {
    let f = Fixture::new();
    let other = Fixture::new();
    assert!(matches!(
        RecoverySigner::from_input(f.cfg.clone(), &other.input),
        Err(AgentError::Credentials)
    ));
}
#[test]
fn key_unknown_duplicate_or_bad_fields_rejected() {
    let f = Fixture::new();
    for doc in [
        b"{}".as_slice(),
        b"{\"pkcs8\":\"x\",\"pkcs8\":\"x\"}",
        b"{\"pkcs8\":\"x\",\"command\":\"ls\"}",
    ] {
        assert!(RecoverySigner::from_input(f.cfg.clone(), doc).is_err());
    }
}
#[test]
fn validated_connect_proof_passes_server_verifier() {
    let f = Fixture::new();
    let c = f.challenge();
    let copy: ConnectChallenge = serde_json::from_value(serde_json::to_value(&c).unwrap()).unwrap();
    let (_, p) = f.signer().connect(c, 101).unwrap();
    let (b, s) = p.decode(4096).unwrap();
    verify_connect(&f.cfg.identity().unwrap(), &f.device(), &copy, &b, &s, 101).unwrap();
}
#[test]
fn wrong_server_identity_is_not_signed() {
    let f = Fixture::new();
    for field in [
        "issuer",
        "resource",
        "connector",
        "version",
        "attempt",
        "nonce",
    ] {
        let c = f.challenge();
        let mut v = serde_json::to_value(c).unwrap();
        v[field] = match field {
            "connector" | "attempt" => json!(Uuid::nil()),
            "version" => json!(2),
            _ => json!("bad"),
        };
        let c = serde_json::from_value(v).unwrap();
        assert!(f.signer().connect(c, 101).is_err());
    }
}
#[test]
fn expired_future_and_extended_challenges_not_signed() {
    let f = Fixture::new();
    for (issued, expires, now) in [
        (100, 110, 110),
        (101, 111, 100),
        (100, 120, 101),
        (-1, 9, 0),
    ] {
        let mut c = f.challenge();
        c.issued_at = issued;
        c.expires_at = expires;
        assert!(f.signer().connect(c, now).is_err());
    }
}
fn snap(boot: Uuid) -> SnapshotChallenge {
    SnapshotChallenge {
        boot,
        nonce: URL_SAFE_NO_PAD.encode([4; 32]),
        expires_at: 160,
        ceiling: 130,
    }
}
#[test]
fn recovery_proof_can_never_create_grant() {
    let f = Fixture::new();
    let boot = Uuid::new_v4();
    let p = f.signer().snapshot(snap(boot), boot, 1, 100).unwrap();
    let (b, s) = p.decode(8192).unwrap();
    verify_snapshot(&f.cfg.identity().unwrap(), &f.device(), &b, &s, 100).unwrap();
    let claims: ProjectionClaims = serde_json::from_slice(&b).unwrap();
    assert_eq!(claims.phase, ProjectionPhase::RecoveryRequired);
    assert_eq!(claims.execution, ExecutionState::Offline);
    assert!(claims.grant.is_none() && claims.drained_grant.is_none());
}
#[test]
fn snapshot_wrong_boot_rejected() {
    let f = Fixture::new();
    assert!(f
        .signer()
        .snapshot(snap(Uuid::new_v4()), Uuid::new_v4(), 1, 100)
        .is_err());
}
#[test]
fn snapshot_lease_ceiling_enforced() {
    let f = Fixture::new();
    let boot = Uuid::new_v4();
    for ceiling in [100, 131, i64::MAX] {
        let mut c = snap(boot);
        c.ceiling = ceiling;
        assert!(f.signer().snapshot(c, boot, 1, 100).is_err());
    }
}
#[test]
fn strict_server_message_types() {
    for t in [
        "{}",
        "{\"type\":\"exec\",\"command\":\"echo no\"}",
        "{\"type\":\"heartbeat_ack\",\"seq\":1,\"seq\":2}",
        "{\"type\":\"heartbeat_ack\",\"seq\":1,\"grant\":{}}",
    ] {
        assert!(ServerMessage::parse(t).is_err());
    }
    assert!(ServerMessage::parse(&"x".repeat(16385)).is_err());
}
#[test]
fn journal_requires_explicit_initialization() {
    let f = Fixture::new();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &f.signer(), false).is_err());
}
#[test]
fn journal_init_never_overwrites() {
    let f = Fixture::new();
    let s = f.signer();
    drop(RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap());
    let before = fs::read(&f.cfg.revision_file).unwrap();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, true).is_err());
    assert_eq!(before, fs::read(&f.cfg.revision_file).unwrap());
}
#[test]
fn journal_preserves_revision_across_reopen() {
    let f = Fixture::new();
    let s = f.signer();
    let mut j = RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap();
    assert_eq!(j.next(&s).unwrap(), 1);
    drop(j);
    let mut j = RevisionJournal::open(&f.cfg.revision_file, &s, false).unwrap();
    assert_eq!(j.next(&s).unwrap(), 2);
}
#[test]
fn journal_os_lock_excludes_parallel_process_handle() {
    let f = Fixture::new();
    let s = f.signer();
    let j = RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, false).is_err());
    drop(j);
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, false).is_ok());
}
#[test]
fn journal_truncation_fails_closed() {
    let f = Fixture::new();
    let s = f.signer();
    drop(RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap());
    fs::OpenOptions::new()
        .write(true)
        .open(&f.cfg.revision_file)
        .unwrap()
        .set_len(80)
        .unwrap();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, false).is_err());
}
#[test]
fn journal_identity_mismatch_rejected() {
    let f = Fixture::new();
    let s = f.signer();
    drop(RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap());
    let mut cfg = f.cfg.clone();
    cfg.authority_epoch += 1;
    let s2 = RecoverySigner::from_input(cfg, &f.input).unwrap();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s2, false).is_err());
}
#[test]
fn journal_corruption_and_duplicate_record_rejected() {
    let f = Fixture::new();
    let s = f.signer();
    drop(RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap());
    let bytes = fs::read(&f.cfg.revision_file).unwrap();
    let mut file = fs::OpenOptions::new()
        .append(true)
        .open(&f.cfg.revision_file)
        .unwrap();
    file.write_all(&bytes).unwrap();
    drop(file);
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, false).is_err());
}
#[cfg(unix)]
#[test]
fn journal_symlink_and_broad_permissions_rejected() {
    use std::os::unix::fs::{symlink, PermissionsExt};
    let f = Fixture::new();
    let s = f.signer();
    drop(RevisionJournal::open(&f.cfg.revision_file, &s, true).unwrap());
    let link = f.root.join("link");
    symlink(&f.cfg.revision_file, &link).unwrap();
    assert!(RevisionJournal::open(&link, &s, false).is_err());
    fs::set_permissions(&f.cfg.revision_file, fs::Permissions::from_mode(0o644)).unwrap();
    assert!(RevisionJournal::open(&f.cfg.revision_file, &s, false).is_err());
}
#[test]
fn protocol_error_messages_do_not_echo_remote_payload() {
    for e in [
        AgentError::Protocol,
        AgentError::Tls,
        AgentError::Authentication,
        AgentError::Journal,
    ] {
        assert!(e.to_string().starts_with("agent_"));
    }
}
