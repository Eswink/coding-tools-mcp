//! Independent client/server codecs must agree without sharing authority objects.
use coding_tools_cloud_agent as client;
use coding_tools_cloud_gateway as server;
use serde_json::{json, Value};
use uuid::Uuid;
fn request() -> Value {
    let args = json!({"path":"fixture","nested":{"b":2,"a":1}});
    json!({"binding":{
        "request_id":Uuid::new_v4(),"peer":{"connector":Uuid::new_v4(),"device":Uuid::new_v4(),
        "device_epoch":1,"gateway_boot":Uuid::new_v4(),"channel_session":Uuid::new_v4(),"channel_generation":1},
        "grant_id":Uuid::new_v4(),"grant_revision":1,"authority_epoch":1,
        "conversation":"BwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwc",
        "scope":"files.read","tool":"read_file",
        "arguments_hash":server::admission::canonical_digest(&args,4096).unwrap(),"deadline":120},
        "arguments":args})
}
#[test]
fn client_server_execution_binding_roundtrip_is_byte_equivalent() {
    let input = request();
    let a: client::execution::ExecutionRequest = serde_json::from_value(input.clone()).unwrap();
    let b: server::execution::ExecutionRequest = serde_json::from_value(input).unwrap();
    assert_eq!(
        serde_json::to_vec(&a).unwrap(),
        serde_json::to_vec(&b).unwrap()
    );
    a.validate_at(&a.binding.peer, 100).unwrap();
    b.validate_at(&b.binding.peer, 100).unwrap();
    let result = json!({"ok":true,"data":{"z":1,"a":[true,null]}});
    let ra = client::execution::ExecutionReply {
        binding: a.binding.clone(),
        result: result.clone(),
    };
    let rb = server::execution::ExecutionReply {
        binding: b.binding.clone(),
        result,
    };
    assert_eq!(
        ra.validate_for(&a.binding, 100).unwrap(),
        rb.validate_for(&b.binding, 100).unwrap()
    );
}
#[test]
fn client_server_reject_the_same_stale_forged_and_oversize_requests() {
    for mode in 0..9 {
        let mut value = request();
        match mode {
            0 => value["binding"]["deadline"] = json!(100),
            1 => value["binding"]["peer"]["channel_generation"] = json!(0),
            2 => value["binding"]["scope"] = json!("host.root"),
            3 => value["binding"]["conversation"] = json!("a".repeat(43)),
            4 => value["arguments"]["path"] = json!("changed"),
            5 => value["binding"]["grant_id"] = json!(Uuid::nil()),
            6 => value["arguments"] = json!({"huge":"x".repeat(4096)}),
            7 => value["binding"]["grant_revision"] = json!(0),
            _ => value["binding"]["tool"] = json!("bad\nname"),
        }
        let a: client::execution::ExecutionRequest = serde_json::from_value(value.clone()).unwrap();
        let b: server::execution::ExecutionRequest = serde_json::from_value(value).unwrap();
        assert!(a.validate_at(&a.binding.peer, 100).is_err(), "{mode}");
        assert!(b.validate_at(&b.binding.peer, 100).is_err(), "{mode}");
    }
}
#[test]
fn client_server_scopes_domains_and_frame_bounds_match() {
    assert_eq!(client::grant::LOCAL_SCOPES, server::grant::LOCAL_SCOPES);
    assert_eq!(client::channel::SUBPROTOCOL, server::channel::SUBPROTOCOL);
    assert_eq!(client::channel::MAX_MESSAGE, server::channel::MAX_MESSAGE);
    assert_eq!(client::channel::AUTH_SECONDS, server::channel::AUTH_SECONDS);
    assert_eq!(
        client::channel::connect_message(b"fixture").unwrap(),
        server::channel::connect_message(b"fixture").unwrap()
    );
    assert_eq!(
        client::projection::projection_message(b"fixture").unwrap(),
        server::projection::projection_message(b"fixture").unwrap()
    );
    assert_eq!(
        client::execution::MAX_EXECUTION_ARGUMENTS,
        server::execution::MAX_EXECUTION_ARGUMENTS
    );
    assert_eq!(
        client::execution::MAX_EXECUTION_RESULT,
        server::execution::MAX_EXECUTION_RESULT
    );
}
#[test]
fn client_server_strict_codecs_reject_added_authority_fields() {
    let mut value = request();
    value["authorized"] = json!(true);
    assert!(serde_json::from_value::<client::execution::ExecutionRequest>(value.clone()).is_err());
    assert!(serde_json::from_value::<server::execution::ExecutionRequest>(value).is_err());
    for value in [
        json!({"type":"heartbeat","seq":1}),
        json!({"type":"execution_ready","seq":2,"version":1}),
    ] {
        let a: client::channel::ControlMessage = serde_json::from_value(value.clone()).unwrap();
        let b: server::channel::ControlMessage = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(
            serde_json::to_value(a).unwrap(),
            serde_json::to_value(b).unwrap()
        );
        let mut bad = value;
        bad["grant"] = json!("forged");
        assert!(serde_json::from_value::<client::channel::ControlMessage>(bad.clone()).is_err());
        assert!(serde_json::from_value::<server::channel::ControlMessage>(bad).is_err());
    }
}
#[test]
fn client_server_both_accept_agents_manage_bindings() {
    // A1 C6 / NB-d (agent_wire_parity.rs:65): both ends carry the same 10 scopes
    // and accept an agents.manage execution binding identically.
    let mut value = request();
    value["binding"]["scope"] = json!("agents.manage");
    value["binding"]["tool"] = json!("subagent_status");
    let a: client::execution::ExecutionRequest = serde_json::from_value(value.clone()).unwrap();
    let b: server::execution::ExecutionRequest = serde_json::from_value(value).unwrap();
    assert!(a.validate_at(&a.binding.peer, 100).is_ok());
    assert!(b.validate_at(&b.binding.peer, 100).is_ok());
    assert!(client::grant::LOCAL_SCOPES.contains(&"agents.manage"));
    assert_eq!(server::grant::LOCAL_SCOPES.len(), 10);
}

// ---- A1 C7 (SPEC §3.3): projection v2 / worker_id cross vectors ----
// Independently: sha256 of `{"path":"fixture","worker_id":"abab…ab"}` (sorted keys, compact).
const C7_WORKER_ARGS_DIGEST: &str =
    "372f47cab2323b920a9fef5027c2605da2e27b72b1175040a2f170e0274c08d9";
#[test]
fn c7_projection_v2_domain_and_worker_bounds_match() {
    assert_eq!(
        client::projection::projection_message_v2(b"fixture").unwrap(),
        server::projection::projection_message_v2(b"fixture").unwrap()
    );
    assert_ne!(
        server::projection::projection_message(b"fixture").unwrap(),
        server::projection::projection_message_v2(b"fixture").unwrap()
    );
    assert_eq!(
        client::projection::MAX_PROJECTED_WORKERS,
        server::projection::MAX_PROJECTED_WORKERS
    );
    for id in [
        "ab".repeat(16),
        "AB".repeat(16),
        "0".repeat(31),
        "g".repeat(32),
        String::new(),
    ] {
        assert_eq!(
            client::projection::valid_worker_id(&id),
            server::projection::valid_worker_id(&id)
        );
    }
}
#[test]
fn c7_worker_id_arguments_hash_is_a_fixed_cross_vector() {
    let args = json!({"worker_id":"ab".repeat(16),"path":"fixture"});
    let digest = server::admission::canonical_digest(&args, 4096).unwrap();
    let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
    assert_eq!(hex, C7_WORKER_ARGS_DIGEST);
    let mut value = request();
    value["arguments"] = args;
    value["binding"]["arguments_hash"] = json!(digest);
    let a: client::execution::ExecutionRequest = serde_json::from_value(value.clone()).unwrap();
    let b: server::execution::ExecutionRequest = serde_json::from_value(value).unwrap();
    assert_eq!(
        serde_json::to_vec(&a).unwrap(),
        serde_json::to_vec(&b).unwrap()
    );
    a.validate_at(&a.binding.peer, 100).unwrap();
    b.validate_at(&b.binding.peer, 100).unwrap();
}
#[test]
fn c7_client_v2_claims_with_workers_verify_on_the_server() {
    use ring::signature::{Ed25519KeyPair, KeyPair};
    let identity = server::PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap();
    let key = Ed25519KeyPair::from_seed_unchecked(&[21; 32]).unwrap();
    let device = server::device::EnrolledDevice {
        id: Uuid::from_u128(2),
        connector: identity.connector(),
        public_key: key.public_key().as_ref().into(),
        epoch: 3,
    };
    let conversation = "BwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwc".to_owned();
    let claims = client::projection::ProjectionClaims {
        version: 2,
        issuer: identity.issuer(),
        resource: identity.resource(),
        connector: identity.connector(),
        device: device.id,
        device_epoch: 3,
        gateway_boot: Uuid::from_u128(4),
        challenge: "CQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQk".into(),
        revision: 7,
        authority_epoch: 9,
        issued_at: 100,
        valid_until: 150,
        phase: client::projection::ProjectionPhase::Active,
        execution: client::projection::ExecutionState::Online,
        grant: Some(client::projection::LocalLease {
            id: Uuid::from_u128(5),
            conversation: conversation.clone(),
            issued_at: 80,
            expires_at: 200,
            scopes: vec!["agents.manage".into()],
        }),
        drained_grant: None,
        workers: vec![client::projection::WorkerClaim {
            id: "ab".repeat(16),
            conversation,
        }],
    };
    let payload = serde_json::to_vec(&claims).unwrap();
    let sig = key.sign(&client::projection::projection_message_v2(&payload).unwrap());
    assert!(
        server::projection::verify_snapshot(&identity, &device, &payload, sig.as_ref(), 120)
            .is_ok()
    );
    // The server codec re-encodes the client's v2 claims byte-for-byte.
    let parsed: server::projection::ProjectionClaims = serde_json::from_slice(&payload).unwrap();
    assert_eq!(serde_json::to_vec(&parsed).unwrap(), payload);
    let v1 = key.sign(&client::projection::projection_message(&payload).unwrap());
    assert!(
        server::projection::verify_snapshot(&identity, &device, &payload, v1.as_ref(), 120)
            .is_err()
    );
}

/// A1 C8-1: the agent and the gateway each compile their own copy of the
/// canonical-JSON codec (two files, not one shared constant). This locks the
/// two copies byte-identical by SHA-256, so the worker_id cross vectors and
/// every arguments_hash keep meaning the same bytes on both sides.
#[test]
fn c8_canonical_codec_copies_are_byte_identical() {
    const AGENT: &str = include_str!("../../cloud-agent/src/canonical.rs");
    const GATEWAY: &str = include_str!("../src/admission/canonical.rs");
    let digest = |text: &str| {
        ring::digest::digest(&ring::digest::SHA256, text.as_bytes())
            .as_ref()
            .to_vec()
    };
    assert_eq!(
        digest(AGENT),
        digest(GATEWAY),
        "services/cloud-agent/src/canonical.rs and services/cloud-gateway/src/admission/canonical.rs diverged"
    );
}
