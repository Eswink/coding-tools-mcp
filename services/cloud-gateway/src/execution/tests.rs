use super::*;
use crate::admission::canonical_digest;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde_json::json;
use uuid::Uuid;
fn request() -> ExecutionRequest {
    ExecutionRequest {
        binding: ExecutionBinding {
            request_id: Uuid::new_v4(),
            peer: PeerBinding {
                connector: Uuid::new_v4(),
                device: Uuid::new_v4(),
                device_epoch: 1,
                gateway_boot: Uuid::new_v4(),
                channel_session: Uuid::new_v4(),
                channel_generation: 1,
            },
            grant_id: Uuid::new_v4(),
            grant_revision: 1,
            authority_epoch: 1,
            conversation: URL_SAFE_NO_PAD.encode([0x69_u8; 32]),
            scope: "files.read".into(),
            tool: "workspace_probe".into(),
            arguments_hash: canonical_digest(&json!({}), MAX_EXECUTION_ARGUMENTS).unwrap(),
            deadline: 120,
        },
        arguments: json!({}),
    }
}
#[test]
fn exact_request_binding_is_valid() {
    let r = request();
    r.validate_at(&r.binding.peer, 100).unwrap();
}
#[test]
fn changed_arguments_are_rejected() {
    let mut r = request();
    r.arguments = json!({"path":"secret"});
    assert!(r.validate_at(&r.binding.peer, 100).is_err());
}
#[test]
fn stale_channel_cannot_authorize_request() {
    let r = request();
    let mut p = r.binding.peer.clone();
    p.channel_generation += 1;
    assert!(r.validate_at(&p, 100).is_err());
}
#[test]
fn expired_request_is_rejected() {
    let r = request();
    assert!(r.validate_at(&r.binding.peer, 120).is_err());
}
#[test]
fn excessively_long_deadline_is_rejected() {
    let mut r = request();
    r.binding.deadline = 401;
    assert!(r.validate_at(&r.binding.peer, 100).is_err());
}
#[test]
fn nil_identity_and_invalid_scope_are_rejected() {
    let mut r = request();
    r.binding.peer.device = Uuid::nil();
    assert!(r.validate_at(&r.binding.peer, 100).is_err());
    let mut r = request();
    r.binding.scope = "admin".into();
    assert!(r.validate_at(&r.binding.peer, 100).is_err());
}
#[test]
fn bound_reply_requires_every_field() {
    let r = request();
    let mut p = ExecutionReply {
        binding: r.binding.clone(),
        result: json!({"ok":true}),
    };
    p.validate_for(&r.binding, 100).unwrap();
    p.binding.authority_epoch += 1;
    assert!(p.validate_for(&r.binding, 100).is_err());
}
#[test]
fn reply_requires_boolean_result_and_bounded_payload() {
    let r = request();
    for value in [
        json!({"ok":"true"}),
        json!({"ok":true,"secret":"x".repeat(8192)}),
    ] {
        assert!(ExecutionReply {
            binding: r.binding.clone(),
            result: value
        }
        .validate_for(&r.binding, 100)
        .is_err());
    }
}
#[test]
fn serde_rejects_extra_authority_fields() {
    let r = request();
    let mut v = serde_json::to_value(&r).unwrap();
    v["authorized"] = json!(true);
    assert!(serde_json::from_value::<ExecutionRequest>(v).is_err());
}
#[test]
fn debug_does_not_leak_payload_or_bindings() {
    let r = request();
    let d = format!("{r:?} {:?}", r.binding);
    assert!(d.contains("REDACTED"));
    assert!(!d.contains(&r.binding.conversation));
    assert!(!d.contains("files.read"));
}
#[tokio::test]
async fn old_registration_cannot_remove_new_peer() {
    let b = Broker::default();
    let r = request();
    let (old, _) = b.register(r.binding.peer.clone()).unwrap();
    let mut peer = r.binding.peer;
    peer.channel_generation += 1;
    peer.channel_session = Uuid::new_v4();
    let (new, mut rx) = b.register(peer.clone()).unwrap();
    drop(old);
    assert!(b.register(peer).is_err());
    drop(new);
    assert!(rx.recv().await.is_none());
}

#[test]
fn global_capacity_is_strictly_bounded() {
    let b = Broker::default();
    let mut permits = Vec::new();
    for _ in 0..CAPACITY {
        permits.push(b.capacity.clone().try_acquire_owned().unwrap());
    }
    assert!(b.capacity.clone().try_acquire_owned().is_err());
    drop(permits.pop());
    assert!(b.capacity.clone().try_acquire_owned().is_ok());
}

#[test]
fn conversation_digest_requires_canonical_base64url_encoding() {
    let r = request();
    r.validate_at(&r.binding.peer, 100).unwrap();
    // Equal length is not sufficient: the final non-zero pad bits are invalid.
    for invalid in ["a".repeat(43), "=".repeat(43), "x".repeat(42)] {
        let mut changed = r.clone();
        changed.binding.conversation = invalid;
        assert!(changed.validate_at(&changed.binding.peer, 100).is_err());
    }
}
