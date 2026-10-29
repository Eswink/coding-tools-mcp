use coding_tools_cloud_gateway::{
    crypto::pkce_challenge,
    device::EnrolledDevice,
    grant::{grant_message, verify_grant, GrantClaims},
    IdentityError, PublicIdentity, Secret, SecretKey,
};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use uuid::Uuid;
fn identity() -> PublicIdentity {
    PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap()
}
#[test]
fn pkce_rfc7636_vector() {
    assert_eq!(
        pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk").unwrap(),
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    );
}
#[test]
fn pkce_bounds_and_alphabet() {
    for v in [
        "a".repeat(42),
        "a".repeat(129),
        " ".repeat(43),
        "é".repeat(43),
    ] {
        assert!(pkce_challenge(&v).is_err());
    }
    assert!(pkce_challenge(&"a".repeat(128)).is_ok());
}
#[test]
fn identities_are_explicit_https_not_forwarded_origins() {
    for origin in [
        "http://gateway.example.invalid",
        "https://u:p@gateway.example.invalid",
        "https://gateway.example.invalid/path",
        "https://gateway.example.invalid?x=y",
        "https://gateway.example.invalid#x",
        " https://gateway.example.invalid",
        "https://gateway.example.invalid/",
        "https://GATEWAY.example.invalid",
        "https://gateway.example.invalid:443",
    ] {
        assert!(
            PublicIdentity::new(origin, "/coding-tools", Uuid::from_u128(1)).is_err(),
            "{origin}"
        );
    }
}
#[test]
fn path_prefixes_cannot_escape_or_take_over_root() {
    for prefix in [
        "/",
        "",
        "/coding-tools/",
        "/../a",
        "/a/b",
        "/%2e",
        "/a?b",
        "/UPPER",
    ] {
        assert!(PublicIdentity::new(
            "https://gateway.example.invalid",
            prefix,
            Uuid::from_u128(1)
        )
        .is_err());
    }
}
#[test]
fn metadata_inserts_issuer_and_resource_paths_after_well_known() {
    let i = identity();
    assert_eq!(
        i.server_metadata_path(),
        "/.well-known/oauth-authorization-server/coding-tools/oauth"
    );
    assert_eq!(i.resource_metadata()["resource"], i.resource());
    assert_eq!(
        i.server_metadata()["code_challenge_methods_supported"],
        serde_json::json!(["S256"])
    );
    assert_eq!(
        i.resource_metadata()["scopes_supported"],
        serde_json::json!(["mcp"])
    );
}
#[test]
fn token_types_and_debug_cannot_leak_credentials() {
    let key = SecretKey::new([42; 32]).unwrap();
    let secret = Secret::random().unwrap();
    assert_eq!(secret.expose().len(), 43);
    assert!(!format!("{secret:?}").contains(secret.expose()));
    assert_ne!(
        key.digest("access-v1", b"same"),
        key.digest("refresh-v1", b"same")
    );
    assert!(!key.matches("refresh-v1", b"same", &key.digest("access-v1", b"same")));
    assert!(SecretKey::new([0; 32]).is_err());
}
fn signed() -> (Ed25519KeyPair, EnrolledDevice, GrantClaims) {
    let rng = SystemRandom::new();
    let key =
        Ed25519KeyPair::from_pkcs8(Ed25519KeyPair::generate_pkcs8(&rng).unwrap().as_ref()).unwrap();
    let device = EnrolledDevice {
        id: Uuid::from_u128(2),
        connector: identity().connector(),
        public_key: key.public_key().as_ref().to_vec(),
        epoch: 3,
    };
    let claims = GrantClaims {
        issuer: identity().issuer(),
        connector: device.connector,
        device: device.id,
        conversation: Secret::random().unwrap().expose().into(),
        epoch: 3,
        issued_at: 100,
        expires_at: 200,
        scopes: vec!["files.read".into()],
    };
    (key, device, claims)
}
#[test]
fn verified_grant_still_needs_matching_local_epoch_and_scope() {
    let (key, d, c) = signed();
    let payload = serde_json::to_vec(&c).unwrap();
    let signature = key.sign(&grant_message(&payload).unwrap());
    let g = verify_grant(&identity(), &d, &payload, signature.as_ref(), 150).unwrap();
    assert!(g.allows("files.read", &c.conversation, 3, 150));
    assert!(!g.allows("exec.run", &c.conversation, 3, 150));
    assert!(!g.allows("files.read", &c.conversation, 4, 150));
    assert!(!g.allows("files.read", "foreign", 3, 150));
    assert!(!g.allows("files.read", &c.conversation, 3, 200));
}
#[test]
fn correctly_signed_wrong_identity_or_expired_claims_are_rejected() {
    let (key, d, c) = signed();
    for field in [
        "issuer",
        "connector",
        "device",
        "conversation",
        "epoch",
        "expires_at",
        "issued_at",
        "scopes",
    ] {
        let mut v = serde_json::to_value(&c).unwrap();
        v[field] = match field {
            "issuer" => "https://foreign.invalid/oauth".into(),
            "connector" | "device" => Uuid::new_v4().to_string().into(),
            "conversation" => "not-a-binding".into(),
            "epoch" => 4.into(),
            "expires_at" => 150.into(),
            "issued_at" => 151.into(),
            "scopes" => serde_json::json!(["root"]),
            _ => unreachable!(),
        };
        let p = serde_json::to_vec(&v).unwrap();
        let sig = key.sign(&grant_message(&p).unwrap());
        assert!(
            verify_grant(&identity(), &d, &p, sig.as_ref(), 150).is_err(),
            "{field}"
        );
    }
}
#[test]
fn unsigned_or_cross_domain_grants_are_rejected() {
    let (key, d, c) = signed();
    let p = serde_json::to_vec(&c).unwrap();
    assert!(verify_grant(&identity(), &d, &p, key.sign(&p).as_ref(), 150).is_err());
    assert!(verify_grant(&identity(), &d, &p, &[0; 64], 150).is_err());
}
#[test]
fn malformed_or_oversized_grants_fail_closed() {
    let (key, d, c) = signed();
    let mut v = serde_json::to_value(c).unwrap();
    v["execute_anything"] = true.into();
    let p = serde_json::to_vec(&v).unwrap();
    let sig = key.sign(&grant_message(&p).unwrap());
    assert!(verify_grant(&identity(), &d, &p, sig.as_ref(), 150).is_err());
    assert_eq!(
        grant_message(&vec![0; 4097]),
        Err(IdentityError::InvalidProof)
    );
}
