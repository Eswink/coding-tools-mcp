use coding_tools_cloud_gateway::{
    device::EnrolledDevice, projection::*, IdentityError, PublicIdentity, Secret,
};
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde_json::{json, Value};
use uuid::Uuid;
fn identity() -> PublicIdentity {
    PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap()
}
fn sample() -> (Ed25519KeyPair, EnrolledDevice, ProjectionClaims) {
    let key = Ed25519KeyPair::from_seed_unchecked(&[11; 32]).unwrap();
    let device = EnrolledDevice {
        id: Uuid::from_u128(2),
        connector: identity().connector(),
        public_key: key.public_key().as_ref().into(),
        epoch: 3,
    };
    let claims = ProjectionClaims {
        version: 1,
        issuer: identity().issuer(),
        resource: identity().resource(),
        connector: identity().connector(),
        device: device.id,
        device_epoch: 3,
        gateway_boot: Uuid::from_u128(4),
        challenge: Secret::random().unwrap().expose().into(),
        revision: 7,
        authority_epoch: 9,
        issued_at: 100,
        valid_until: 150,
        phase: ProjectionPhase::Active,
        execution: ExecutionState::Online,
        grant: Some(LocalLease {
            id: Uuid::from_u128(5),
            conversation: Secret::random().unwrap().expose().into(),
            issued_at: 80,
            expires_at: 200,
            scopes: vec!["files.read".into()],
        }),
        drained_grant: None,
    };
    (key, device, claims)
}
fn check(c: &ProjectionClaims, at: i64) -> bool {
    let (k, d, _) = sample();
    let p = serde_json::to_vec(c).unwrap();
    let s = k.sign(&projection_message(&p).unwrap());
    verify_snapshot(&identity(), &d, &p, s.as_ref(), at).is_ok()
}
fn check_value(v: &Value) -> bool {
    let (k, d, _) = sample();
    let p = serde_json::to_vec(v).unwrap();
    let s = k.sign(&projection_message(&p).unwrap());
    verify_snapshot(&identity(), &d, &p, s.as_ref(), 120).is_ok()
}
#[test]
fn valid_snapshot_verifies_without_granting_execution() {
    let (_, _, c) = sample();
    assert!(check(&c, 120));
}
#[test]
fn fabricated_signature_or_other_device_key_is_rejected() {
    let (_, d, c) = sample();
    let p = serde_json::to_vec(&c).unwrap();
    assert!(verify_snapshot(&identity(), &d, &p, &[0; 64], 120).is_err());
    let k = Ed25519KeyPair::from_seed_unchecked(&[12; 32]).unwrap();
    let s = k.sign(&projection_message(&p).unwrap());
    assert!(verify_snapshot(&identity(), &d, &p, s.as_ref(), 120).is_err());
}
#[test]
fn grant_v1_signature_cannot_be_reused_as_projection() {
    let (k, d, c) = sample();
    let p = serde_json::to_vec(&c).unwrap();
    let s = k.sign(&coding_tools_cloud_gateway::grant::grant_message(&p).unwrap());
    assert!(verify_snapshot(&identity(), &d, &p, s.as_ref(), 120).is_err());
}
#[test]
fn signed_resource_and_issuer_mismatch_fail_closed() {
    let (_, _, c) = sample();
    for field in ["issuer", "resource"] {
        let mut v = serde_json::to_value(&c).unwrap();
        v[field] = json!("https://foreign.invalid/path");
        assert!(!check_value(&v));
    }
}
#[test]
fn signed_connector_and_device_mismatch_fail_closed() {
    let (_, _, c) = sample();
    for field in ["connector", "device"] {
        let mut v = serde_json::to_value(&c).unwrap();
        v[field] = json!(Uuid::new_v4());
        assert!(!check_value(&v));
    }
}
#[test]
fn stale_registry_epoch_and_nil_boot_are_rejected() {
    let (_, _, mut c) = sample();
    c.device_epoch = 2;
    assert!(!check(&c, 120));
    c.device_epoch = 3;
    c.gateway_boot = Uuid::nil();
    assert!(!check(&c, 120));
}
#[test]
fn unknown_version_and_invalid_monotonic_values_are_rejected() {
    let (_, _, c) = sample();
    for field in ["version", "revision", "authority_epoch"] {
        let mut v = serde_json::to_value(&c).unwrap();
        v[field] = json!(0);
        assert!(!check_value(&v));
    }
}
#[test]
fn bounded_snapshot_lifetime_future_and_expired_rejected() {
    let (_, _, mut c) = sample();
    assert!(!check(&c, 99));
    assert!(!check(&c, 150));
    c.valid_until = 161;
    assert!(!check(&c, 120));
    c.valid_until = i64::MAX;
    assert!(!check(&c, 120));
    c.issued_at = i64::MIN;
    assert!(!check(&c, 120));
}
#[test]
fn active_grant_expiry_and_future_issuance_rejected() {
    let (_, _, mut c) = sample();
    c.grant.as_mut().unwrap().expires_at = 120;
    assert!(!check(&c, 120));
    c.grant.as_mut().unwrap().expires_at = 200;
    c.grant.as_mut().unwrap().issued_at = 121;
    assert!(!check(&c, 120));
}
#[test]
fn expired_original_grant_can_be_drained_but_not_reactivated() {
    let (_, _, mut c) = sample();
    c.grant.as_mut().unwrap().expires_at = 110;
    assert!(!check(&c, 120));
    c.phase = ProjectionPhase::Draining;
    c.execution = ExecutionState::Offline;
    assert!(check(&c, 120));
}
#[test]
fn scopes_are_nonempty_known_and_unique() {
    let (_, _, c) = sample();
    for scopes in [vec![], vec!["admin"], vec!["files.read", "files.read"]] {
        let mut v = serde_json::to_value(&c).unwrap();
        v["grant"]["scopes"] = json!(scopes);
        assert!(!check_value(&v));
    }
}
#[test]
fn every_nonactive_phase_requires_offline_execution() {
    let (_, _, mut c) = sample();
    for phase in [
        ProjectionPhase::Free,
        ProjectionPhase::Draining,
        ProjectionPhase::RecoveryRequired,
    ] {
        c.phase = phase;
        assert!(!check(&c, 120));
    }
}
#[test]
fn free_state_cannot_hide_an_active_grant() {
    let (_, _, mut c) = sample();
    c.phase = ProjectionPhase::Free;
    c.execution = ExecutionState::Offline;
    assert!(!check(&c, 120));
    c.grant = None;
    assert!(check(&c, 120));
}
#[test]
fn drain_ack_is_only_well_formed_for_a_free_snapshot() {
    let (_, _, mut c) = sample();
    c.drained_grant = Some(Uuid::new_v4());
    assert!(!check(&c, 120));
    c.phase = ProjectionPhase::Free;
    c.execution = ExecutionState::Offline;
    c.grant = None;
    c.drained_grant = Some(Uuid::nil());
    assert!(!check(&c, 120));
}
#[test]
fn duplicate_unknown_json_fields_and_invalid_challenge_are_rejected() {
    let (k, d, c) = sample();
    let mut v = serde_json::to_value(&c).unwrap();
    v["path"] = json!("/private");
    assert!(!check_value(&v));
    v = serde_json::to_value(&c).unwrap();
    v["challenge"] = json!("short");
    assert!(!check_value(&v));
    let original = serde_json::to_string(&c).unwrap();
    let p = format!("{{\"version\":1,{}", &original[1..]).into_bytes();
    let s = k.sign(&projection_message(&p).unwrap());
    assert!(verify_snapshot(&identity(), &d, &p, s.as_ref(), 120).is_err());
}
#[test]
fn payload_bounds_and_debug_do_not_expose_authority_material() {
    assert_eq!(projection_message(&[]), Err(IdentityError::InvalidProof));
    assert_eq!(
        projection_message(&vec![b'a'; 8193]),
        Err(IdentityError::InvalidProof)
    );
    let (k, d, c) = sample();
    let p = serde_json::to_vec(&c).unwrap();
    let s = k.sign(&projection_message(&p).unwrap());
    let verified = verify_snapshot(&identity(), &d, &p, s.as_ref(), 120).unwrap();
    let debug = format!("{verified:?}");
    assert!(!debug.contains(&c.challenge));
    assert!(!debug.contains(&c.grant.unwrap().conversation));
}
