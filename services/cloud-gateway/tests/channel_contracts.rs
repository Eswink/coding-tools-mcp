use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_gateway::{channel::*, device::EnrolledDevice, PublicIdentity};
use ring::signature::{Ed25519KeyPair, KeyPair};
use uuid::Uuid;
fn identity() -> PublicIdentity {
    PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap()
}
fn fixture() -> (
    ConnectChallenge,
    ConnectClaims,
    Ed25519KeyPair,
    EnrolledDevice,
) {
    let key = Ed25519KeyPair::from_seed_unchecked(&[91; 32]).unwrap();
    let d = EnrolledDevice {
        id: Uuid::from_u128(5),
        connector: identity().connector(),
        epoch: 1,
        public_key: key.public_key().as_ref().into(),
    };
    let c = ConnectChallenge {
        version: 1,
        issuer: identity().issuer(),
        resource: identity().resource(),
        connector: identity().connector(),
        gateway_boot: Uuid::from_u128(7),
        attempt: Uuid::from_u128(8),
        nonce: URL_SAFE_NO_PAD.encode([1; 32]),
        issued_at: 1000,
        expires_at: 1010,
    };
    let v = ConnectClaims {
        version: 1,
        issuer: c.issuer.clone(),
        resource: c.resource.clone(),
        connector: c.connector,
        device: d.id,
        device_epoch: d.epoch,
        gateway_boot: c.gateway_boot,
        attempt: c.attempt,
        nonce: c.nonce.clone(),
        issued_at: c.issued_at,
        expires_at: c.expires_at,
    };
    (c, v, key, d)
}
fn verify(
    c: &ConnectChallenge,
    v: &ConnectClaims,
    k: &Ed25519KeyPair,
    d: &EnrolledDevice,
    at: i64,
) -> bool {
    let p = serde_json::to_vec(v).unwrap();
    verify_connect(
        &identity(),
        d,
        c,
        &p,
        k.sign(&connect_message(&p).unwrap()).as_ref(),
        at,
    )
    .is_ok()
}
#[test]
fn valid_exact_connection_proof() {
    let (c, v, k, d) = fixture();
    assert!(verify(&c, &v, &k, &d, 1001));
}
#[test]
fn signatures_are_domain_separated() {
    let (c, v, k, d) = fixture();
    let p = serde_json::to_vec(&v).unwrap();
    assert!(verify_connect(&identity(), &d, &c, &p, k.sign(&p).as_ref(), 1001).is_err());
}
#[test]
fn different_socket_challenge_is_rejected() {
    let (mut c, v, k, d) = fixture();
    c.attempt = Uuid::new_v4();
    assert!(!verify(&c, &v, &k, &d, 1001));
}
#[test]
fn stale_gateway_boot_is_rejected() {
    let (c, mut v, k, d) = fixture();
    v.gateway_boot = Uuid::new_v4();
    assert!(!verify(&c, &v, &k, &d, 1001));
}
#[test]
fn changed_device_epoch_is_rejected() {
    let (c, v, k, mut d) = fixture();
    d.epoch += 1;
    assert!(!verify(&c, &v, &k, &d, 1001));
}
#[test]
fn resource_is_not_taken_from_payload() {
    let (c, mut v, k, d) = fixture();
    v.resource = "https://foreign.invalid/mcp".into();
    assert!(!verify(&c, &v, &k, &d, 1001));
}
#[test]
fn proof_expires_at_exact_boundary() {
    let (c, v, k, d) = fixture();
    assert!(!verify(&c, &v, &k, &d, 1010));
    assert!(!verify(&c, &v, &k, &d, 999));
}
#[test]
fn unknown_and_duplicate_claim_fields_are_rejected() {
    let (c, v, k, d) = fixture();
    let p = serde_json::to_string(&v).unwrap();
    for suffix in [",\"unexpected\":true}", ",\"version\":1}"] {
        let q = format!("{}{}", &p[..p.len() - 1], suffix);
        assert!(verify_connect(
            &identity(),
            &d,
            &c,
            q.as_bytes(),
            k.sign(&connect_message(q.as_bytes()).unwrap()).as_ref(),
            1001
        )
        .is_err());
    }
}
#[test]
fn proof_and_frame_sizes_are_bounded() {
    assert!(connect_message(&[]).is_err());
    assert!(connect_message(&vec![0; 4097]).is_err());
    assert!(SignedPayload {
        payload: "a".repeat(20000),
        signature: "a".repeat(86)
    }
    .decode(4096)
    .is_err());
}
#[test]
fn control_messages_cannot_select_another_session() {
    assert!(serde_json::from_str::<ControlMessage>(
        r#"{"type":"heartbeat","seq":1,"session":"foreign"}"#
    )
    .is_err());
}
#[test]
fn unknown_actions_cannot_execute_commands() {
    for t in ["exec", "approve", "grant", "read_file"] {
        assert!(
            serde_json::from_str::<ControlMessage>(&format!(r#"{{"type":"{t}","seq":1}}"#))
                .is_err()
        );
    }
}
#[test]
fn duplicate_control_sequence_is_not_parsed() {
    assert!(
        serde_json::from_str::<ControlMessage>(r#"{"type":"heartbeat","seq":1,"seq":2}"#).is_err()
    );
}
