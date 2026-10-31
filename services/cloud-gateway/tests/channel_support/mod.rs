use crate::{
    common::identity,
    projection_support::{clock, Harness},
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_gateway::{channel::*, projection::*, IdentityError};
use ring::signature::Ed25519KeyPair;
use uuid::Uuid;
pub fn claims(c: &ConnectChallenge, device: Uuid, epoch: i64) -> ConnectClaims {
    ConnectClaims {
        version: c.version,
        issuer: c.issuer.clone(),
        resource: c.resource.clone(),
        connector: c.connector,
        device,
        device_epoch: epoch,
        gateway_boot: c.gateway_boot,
        attempt: c.attempt,
        nonce: c.nonce.clone(),
        issued_at: c.issued_at,
        expires_at: c.expires_at,
    }
}
pub fn sign(c: &ConnectClaims, key: &Ed25519KeyPair) -> SignedPayload {
    let bytes = serde_json::to_vec(c).unwrap();
    SignedPayload {
        signature: URL_SAFE_NO_PAD.encode(key.sign(&connect_message(&bytes).unwrap()).as_ref()),
        payload: URL_SAFE_NO_PAD.encode(bytes),
    }
}
pub async fn setup() -> (Harness, ChannelController) {
    let h = Harness::new().await;
    let c = ChannelController::activate(h.f.store.clone())
        .await
        .unwrap();
    (h, c)
}
pub async fn attach(h: &Harness, c: &ChannelController) -> ChannelSession {
    let pending = c.pending().unwrap();
    let signed = sign(
        &claims(pending.challenge(), h.device.id, h.device.epoch),
        &h.key,
    );
    c.authenticate(pending, &signed).await.unwrap()
}
pub async fn project(
    h: &Harness,
    c: &ChannelController,
    s: &ChannelSession,
    seq: i64,
    revision: i64,
) -> ProjectionClaims {
    project_workers(h, c, s, seq, revision, h.lease.clone(), vec![]).await
}
/// A1 C8-1: like `project`, with an explicit grant; a non-empty worker list is sent as
/// a version 2 projection signed under the v2 domain (an empty list stays version 1).
pub async fn project_workers(
    h: &Harness,
    c: &ChannelController,
    s: &ChannelSession,
    seq: i64,
    revision: i64,
    grant: LocalLease,
    workers: Vec<WorkerClaim>,
) -> ProjectionClaims {
    let response = c
        .control(s, ControlMessage::ProjectionChallenge { seq })
        .await
        .unwrap();
    let at = clock(&h.f).await;
    let version = if workers.is_empty() { 1 } else { 2 };
    let value = ProjectionClaims {
        version,
        issuer: identity().issuer(),
        resource: identity().resource(),
        connector: identity().connector(),
        device: h.device.id,
        device_epoch: h.device.epoch,
        gateway_boot: serde_json::from_value(response["gateway_boot"].clone()).unwrap(),
        challenge: response["nonce"].as_str().unwrap().into(),
        revision,
        authority_epoch: 1,
        issued_at: at,
        valid_until: response["snapshot_valid_until"].as_i64().unwrap(),
        phase: ProjectionPhase::Active,
        execution: ExecutionState::Online,
        grant: Some(grant),
        drained_grant: None,
        workers,
    };
    let (p, sig) = if version == 1 {
        h.signed(&value)
    } else {
        let bytes = serde_json::to_vec(&value).unwrap();
        let sig = h.key.sign(&projection_message_v2(&bytes).unwrap());
        (bytes, sig.as_ref().to_vec())
    };
    c.control(
        s,
        ControlMessage::Projection {
            seq: seq + 1,
            proof: SignedPayload {
                payload: URL_SAFE_NO_PAD.encode(p),
                signature: URL_SAFE_NO_PAD.encode(sig),
            },
        },
    )
    .await
    .unwrap();
    value
}
pub fn invalid<T>(r: Result<T, IdentityError>) {
    assert!(r.is_err());
}
