//! Signature serialization is unchanged by grouping its validity interval.
use crate::{wire::{ExecutionState, Phase, Projected}, DeviceConfig, DeviceKey};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use ring::{rand::SystemRandom, signature::{Ed25519KeyPair, UnparsedPublicKey, ED25519}};
use serde_json::Value;
use uuid::Uuid;
use zeroize::Zeroizing;

struct Fixture {
    config: DeviceConfig,
    key: DeviceKey,
    boot: Uuid,
    nonce: String,
    state: Projected,
}
impl Fixture {
    fn new() -> Self {
        let pkcs8 = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
        Self {
            config: DeviceConfig::new("https://gateway.example/coding-tools".into(), Uuid::new_v4(), Uuid::new_v4(), 1).unwrap(),
            key: DeviceKey::from_pkcs8(Zeroizing::new(pkcs8.as_ref().to_vec())).unwrap(),
            boot: Uuid::new_v4(),
            nonce: URL_SAFE_NO_PAD.encode([17; 32]),
            state: Projected { phase: Phase::Free, execution: ExecutionState::Offline,
                authority_epoch: 1, grant: None, drained_grant: None },
        }
    }
}

#[test]
fn projection_signature_preserves_exact_interval_and_domain() {
    let f = Fixture::new();
    let proof = f.key.projection(&f.config, f.boot, &f.nonce, 3, 1000..1030, &f.state).unwrap();
    let payload = URL_SAFE_NO_PAD.decode(proof.payload).unwrap();
    let signature = URL_SAFE_NO_PAD.decode(proof.signature).unwrap();
    let public = URL_SAFE_NO_PAD.decode(f.key.public_key()).unwrap();
    let verifier = UnparsedPublicKey::new(&ED25519, public);
    let mut message = b"coding-tools-authority-projection-v1\0".to_vec();
    message.extend_from_slice(&payload);
    assert!(verifier.verify(&message, &signature).is_ok());
    assert!(verifier.verify(&payload, &signature).is_err());
    let claims: Value = serde_json::from_slice(&payload).unwrap();
    assert_eq!(claims["issued_at"], 1000);
    assert_eq!(claims["valid_until"], 1030);
    assert_eq!(claims["revision"], 3);
    assert_eq!(claims["phase"], "free");
    assert_eq!(claims["execution"], "offline");
    assert_eq!(claims["gateway_boot"], f.boot.to_string());
    assert_eq!(claims["challenge"], f.nonce);
}

#[test]
fn projection_rejects_empty_reversed_negative_and_overlong_intervals() {
    let f = Fixture::new();
    for (start, end) in [(1000, 1000), (1001, 1000), (-1, 1), (1000, 1031), (i64::MIN, i64::MAX)] {
        assert!(f.key.projection(&f.config, f.boot, &f.nonce, 3, start..end, &f.state).is_err());
    }
    assert!(f.key.projection(&f.config, f.boot, &f.nonce, 3, 0..1, &f.state).is_ok());
}

#[test]
fn projection_deadline_cannot_be_changed_under_existing_signature() {
    let f = Fixture::new();
    let proof = f.key.projection(&f.config, f.boot, &f.nonce, 3, 1000..1010, &f.state).unwrap();
    let payload = URL_SAFE_NO_PAD.decode(proof.payload).unwrap();
    let signature = URL_SAFE_NO_PAD.decode(proof.signature).unwrap();
    let mut claims: Value = serde_json::from_slice(&payload).unwrap();
    claims["valid_until"] = serde_json::json!(1030);
    let mut changed = b"coding-tools-authority-projection-v1\0".to_vec();
    changed.extend_from_slice(&serde_json::to_vec(&claims).unwrap());
    let public = URL_SAFE_NO_PAD.decode(f.key.public_key()).unwrap();
    assert!(UnparsedPublicKey::new(&ED25519, public).verify(&changed, &signature).is_err());
}
