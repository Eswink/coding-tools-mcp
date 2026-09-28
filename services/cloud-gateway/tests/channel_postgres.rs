#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;
use channel_support::*;
use coding_tools_cloud_gateway::{channel::*, projection::ProjectionDecision as D};
use ring::signature::Ed25519KeyPair;

#[tokio::test]
async fn connection_does_not_create_a_local_grant() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    assert!(c.validate(&s).await.is_ok());
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::AuthorizationUnavailable
    );
}
#[tokio::test]
async fn authenticated_link_relays_signed_projection() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    assert_eq!(c.assess(&h.a, "files.read").await.unwrap(), D::Eligible);
    assert_eq!(
        c.assess(&h.b, "files.read").await.unwrap(),
        D::AuthorizationUnavailable
    );
}
#[tokio::test]
async fn invalid_proof_cannot_fence_active_connection() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    let p = c.pending().unwrap();
    let wrong = Ed25519KeyPair::from_seed_unchecked(&[6; 32]).unwrap();
    let proof = sign(&claims(p.challenge(), h.device.id, 1), &wrong);
    invalid(c.authenticate(p, &proof).await);
    assert_eq!(c.assess(&h.a, "files.read").await.unwrap(), D::Eligible);
    c.control(&s, ControlMessage::Heartbeat { seq: 3 })
        .await
        .unwrap();
}
#[tokio::test]
async fn proof_cannot_be_replayed_on_a_second_attempt() {
    let (h, c) = setup().await;
    let p = c.pending().unwrap();
    let proof = sign(&claims(p.challenge(), h.device.id, 1), &h.key);
    let q = c.pending().unwrap();
    invalid(c.authenticate(q, &proof).await);
    c.authenticate(p, &proof).await.unwrap();
}
#[tokio::test]
async fn registry_epoch_is_checked_on_heartbeat() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    sqlx::query("UPDATE ctm_devices SET epoch=epoch+1")
        .execute(&h.f.pool)
        .await
        .unwrap();
    invalid(c.control(&s, ControlMessage::Heartbeat { seq: 1 }).await);
}
#[tokio::test]
async fn registry_revocation_closes_authority() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    h.f.store.revoke_device(h.device.id).await.unwrap();
    invalid(c.validate(&s).await);
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::AuthorizationUnavailable
    );
    c.disconnect(&s).await.unwrap();
}
#[tokio::test]
async fn stale_connection_cleanup_preserves_replacement() {
    let (h, c) = setup().await;
    let old = attach(&h, &c).await;
    project(&h, &c, &old, 1, 1).await;
    let new = attach(&h, &c).await;
    invalid(c.control(&old, ControlMessage::Heartbeat { seq: 3 }).await);
    project(&h, &c, &new, 1, 2).await;
    c.disconnect(&old).await.unwrap();
    c.validate(&new).await.unwrap();
    assert_eq!(c.assess(&h.a, "files.read").await.unwrap(), D::Eligible);
}
#[tokio::test]
async fn disconnect_keeps_exclusive_owner_state() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    let before: String = sqlx::query_scalar("SELECT state_text FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    c.disconnect(&s).await.unwrap();
    let after: String = sqlx::query_scalar("SELECT state_text FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(before, after);
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::RecoveryRequired
    );
    assert_eq!(
        c.assess(&h.b, "files.read").await.unwrap(),
        D::AuthorizationUnavailable
    );
}
#[tokio::test]
async fn heartbeat_sequence_must_be_exact() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    invalid(c.control(&s, ControlMessage::Heartbeat { seq: 2 }).await);
    c.control(&s, ControlMessage::Heartbeat { seq: 1 })
        .await
        .unwrap();
    invalid(c.control(&s, ControlMessage::Heartbeat { seq: 1 }).await);
}
#[tokio::test]
async fn expired_presence_cannot_renew_itself() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    sqlx::query("UPDATE ctm_agent_channel SET lease_until=0")
        .execute(&h.f.pool)
        .await
        .unwrap();
    invalid(c.control(&s, ControlMessage::Heartbeat { seq: 3 }).await);
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::WorkspaceOffline
    );
}
#[tokio::test]
async fn absolute_expiry_cannot_renew_itself() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    sqlx::query("UPDATE ctm_agent_channel SET absolute_until=0")
        .execute(&h.f.pool)
        .await
        .unwrap();
    invalid(c.control(&s, ControlMessage::Heartbeat { seq: 1 }).await);
}
#[tokio::test]
async fn heartbeat_does_not_renew_projection() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    sqlx::query("UPDATE ctm_grant_projection SET snapshot_until=0")
        .execute(&h.f.pool)
        .await
        .unwrap();
    c.control(&s, ControlMessage::Heartbeat { seq: 3 })
        .await
        .unwrap();
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        D::WorkspaceOffline
    );
}
#[tokio::test]
async fn reboot_fences_handles_and_captured_proofs() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    let pending = c.pending().unwrap();
    let proof = sign(&claims(pending.challenge(), h.device.id, 1), &h.key);
    let next = ChannelController::activate(h.f.store.clone())
        .await
        .unwrap();
    invalid(c.validate(&s).await);
    invalid(next.authenticate(pending, &proof).await);
    let fresh = attach(&h, &next).await;
    next.validate(&fresh).await.unwrap();
    invalid(c.disconnect(&s).await);
    next.validate(&fresh).await.unwrap();
}
#[tokio::test]
async fn concurrent_authenticated_reconnect_has_one_current_session() {
    let (h, c) = setup().await;
    let p = c.pending().unwrap();
    let q = c.pending().unwrap();
    let a = sign(&claims(p.challenge(), h.device.id, 1), &h.key);
    let b = sign(&claims(q.challenge(), h.device.id, 1), &h.key);
    let (a, b) = tokio::join!(c.authenticate(p, &a), c.authenticate(q, &b));
    let a = a.unwrap();
    let b = b.unwrap();
    let n = usize::from(c.validate(&a).await.is_ok()) + usize::from(c.validate(&b).await.is_ok());
    assert_eq!(n, 1);
}
#[tokio::test]
async fn generation_overflow_fails_without_wrapping() {
    let (h, c) = setup().await;
    sqlx::query("UPDATE ctm_agent_channel SET generation=9223372036854775807")
        .execute(&h.f.pool)
        .await
        .unwrap();
    let p = c.pending().unwrap();
    let s = sign(&claims(p.challenge(), h.device.id, 1), &h.key);
    invalid(c.authenticate(p, &s).await);
}
#[tokio::test]
async fn oauth_refresh_survives_channel_disconnect() {
    let (h, c) = setup().await;
    let tokens = h.f.tokens(uuid::Uuid::from_u128(8)).await;
    let s = attach(&h, &c).await;
    c.disconnect(&s).await.unwrap();
    let r =
        h.f.store
            .refresh(
                common::public(),
                tokens.refresh_token.expose(),
                &common::identity().resource(),
            )
            .await;
    assert!(r.is_ok());
}
#[tokio::test]
async fn unselected_device_cannot_connect() {
    let (h, c) = setup().await;
    sqlx::query("UPDATE ctm_grant_projection SET device=NULL")
        .execute(&h.f.pool)
        .await
        .unwrap();
    let p = c.pending().unwrap();
    let proof = sign(&claims(p.challenge(), h.device.id, 1), &h.key);
    invalid(c.authenticate(p, &proof).await);
}
#[tokio::test]
async fn invalid_projection_signature_does_not_change_owner() {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    let bad = SignedPayload {
        payload: "YQ".into(),
        signature: "A".repeat(86),
    };
    invalid(
        c.control(&s, ControlMessage::Projection { seq: 1, proof: bad })
            .await,
    );
    let count: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM ctm_grant_projection WHERE state_text IS NOT NULL",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    assert_eq!(count, 0);
}

#[tokio::test]
async fn snapshot_freshness_cannot_outlive_authenticated_channel_lease() {
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
    use coding_tools_cloud_gateway::projection::{
        ExecutionState, ProjectionClaims, ProjectionPhase,
    };
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    let reply = c
        .control(&s, ControlMessage::ProjectionChallenge { seq: 1 })
        .await
        .unwrap();
    let at = projection_support::clock(&h.f).await;
    let value = ProjectionClaims {
        version: 1,
        issuer: common::identity().issuer(),
        resource: common::identity().resource(),
        connector: common::identity().connector(),
        device: h.device.id,
        device_epoch: 1,
        gateway_boot: serde_json::from_value(reply["gateway_boot"].clone()).unwrap(),
        challenge: reply["nonce"].as_str().unwrap().into(),
        revision: 1,
        authority_epoch: 1,
        issued_at: at,
        valid_until: at + 60,
        phase: ProjectionPhase::Active,
        execution: ExecutionState::Online,
        grant: Some(h.lease.clone()),
        drained_grant: None,
    };
    let (p, sig) = h.signed(&value);
    let result = c
        .control(
            &s,
            ControlMessage::Projection {
                seq: 2,
                proof: SignedPayload {
                    payload: URL_SAFE_NO_PAD.encode(p),
                    signature: URL_SAFE_NO_PAD.encode(sig),
                },
            },
        )
        .await;
    assert!(
        result.is_err(),
        "projection validity must be bounded by the authenticated connection lease"
    );
}

#[tokio::test]
async fn another_enrolled_device_cannot_replace_selected_local_device() {
    use coding_tools_cloud_gateway::device::enrollment_message;
    use ring::signature::KeyPair;
    let (h, c) = setup().await;
    let key = Ed25519KeyPair::from_seed_unchecked(&[101; 32]).unwrap();
    let invitation = h.f.store.create_device_invitation().await.unwrap();
    let msg = enrollment_message(
        &common::identity(),
        invitation.token.expose(),
        key.public_key().as_ref(),
    )
    .unwrap();
    let device =
        h.f.store
            .redeem_device_invitation(
                invitation.token.expose(),
                key.public_key().as_ref(),
                key.sign(&msg).as_ref(),
            )
            .await
            .unwrap();
    let p = c.pending().unwrap();
    let proof = sign(&claims(p.challenge(), device.id, device.epoch), &key);
    invalid(c.authenticate(p, &proof).await);
    let owner = attach(&h, &c).await;
    c.validate(&owner).await.unwrap();
}
#[tokio::test]
async fn concurrent_activation_does_not_adopt_another_controllers_boot() {
    for _ in 0..6 {
        let h = projection_support::Harness::new().await;
        let (a, b) = tokio::join!(
            ChannelController::activate(h.f.store.clone()),
            ChannelController::activate(h.f.store.clone())
        );
        let mut winners = 0;
        for c in [a, b].into_iter().flatten() {
            let p = c.pending().unwrap();
            let proof = sign(&claims(p.challenge(), h.device.id, 1), &h.key);
            winners += usize::from(c.authenticate(p, &proof).await.is_ok());
        }
        assert_eq!(winners, 1, "exactly one active boot may accept a link");
    }
}

#[tokio::test]
async fn restoring_authority_does_not_resurrect_persisted_channel_or_owner() {
    let (h, c) = setup().await;
    let old_session = attach(&h, &c).await;
    project(&h, &c, &old_session, 1, 1).await;
    sqlx::query("CREATE TABLE authority_backup AS TABLE ctm_grant_projection")
        .execute(&h.f.pool)
        .await
        .unwrap();
    c.disconnect(&old_session).await.unwrap();
    sqlx::query("TRUNCATE ctm_grant_projection")
        .execute(&h.f.pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO ctm_grant_projection SELECT * FROM authority_backup")
        .execute(&h.f.pool)
        .await
        .unwrap();
    // Restore is an offline operator action. Startup MUST create a fresh boot.
    let restarted = ChannelController::activate(h.f.store.clone())
        .await
        .unwrap();
    invalid(c.validate(&old_session).await);
    assert_ne!(
        restarted.assess(&h.a, "files.read").await.unwrap(),
        coding_tools_cloud_gateway::projection::ProjectionDecision::Eligible
    );
    let new_session = attach(&h, &restarted).await;
    // Reauthentication alone cannot resurrect a local grant projection.
    assert_ne!(
        restarted.assess(&h.a, "files.read").await.unwrap(),
        coding_tools_cloud_gateway::projection::ProjectionDecision::Eligible
    );
    restarted.validate(&new_session).await.unwrap();
}
