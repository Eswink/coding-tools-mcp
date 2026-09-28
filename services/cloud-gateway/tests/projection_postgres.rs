#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;
use coding_tools_cloud_gateway::{
    projection::*, IdentityError, IdentityStore, Lifetimes, OAuthPrincipal, SecretKey,
};
use common::identity;
use projection_support::{clock, Harness};
use uuid::Uuid;
use ExecutionState::*;
use ProjectionDecision::*;
use ProjectionPhase::{Active, Draining, Free};

#[tokio::test]
async fn enrollment_and_oauth_identity_alone_never_make_local_authority() {
    let h = Harness::new().await;
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
    let n: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM ctm_grant_projection WHERE state_text IS NOT NULL",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    assert_eq!(n, 0);
}
#[tokio::test]
async fn valid_device_snapshot_is_only_projection_eligibility() {
    let h = Harness::new().await;
    h.active().await;
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        Eligible
    );
    assert_eq!(
        h.projection.assess(&h.b, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
    assert_eq!(
        h.projection.assess(&h.a, "exec.run").await.unwrap(),
        ScopeDenied
    );
}
#[tokio::test]
async fn signed_pause_resume_preserves_owner_and_scope() {
    let h = Harness::new().await;
    h.active().await;
    for (rev, exec, expected) in [(2, Offline, WorkspaceOffline), (3, Online, Eligible)] {
        let c = h.claims(rev, Active, exec).await;
        h.apply(&c).await.unwrap();
        assert_eq!(
            h.projection.assess(&h.a, "files.read").await.unwrap(),
            expected
        );
        assert_eq!(
            h.projection.assess(&h.b, "files.read").await.unwrap(),
            AuthorizationUnavailable
        );
    }
}
#[tokio::test]
async fn foreign_denial_is_identical_across_phase_freshness_and_restart() {
    let h = Harness::new().await;
    h.active().await;
    for phase in [Active, Draining, ProjectionPhase::RecoveryRequired] {
        let c = h
            .claims(
                match phase {
                    Active => 2,
                    Draining => 3,
                    _ => 4,
                },
                phase,
                Offline,
            )
            .await;
        h.apply(&c).await.unwrap();
        assert_eq!(
            h.projection.assess(&h.b, "files.read").await.unwrap(),
            AuthorizationUnavailable
        );
    }
    let p = ProjectionStore::activate(h.f.store.clone()).await.unwrap();
    assert_eq!(
        p.assess(&h.b, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
    let rows: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(rows, 1, "denials must allocate no per-chat state");
}
#[tokio::test]
async fn direct_owner_transfer_rejected_even_with_newer_epoch() {
    let h = Harness::new().await;
    h.active().await;
    let mut c = h.claims(2, Active, Online).await;
    c.authority_epoch = 2;
    let g = c.grant.as_mut().unwrap();
    g.id = Uuid::new_v4();
    g.conversation = h.b.as_str().into();
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn lease_renewal_or_scope_expansion_requires_a_new_drained_grant() {
    let h = Harness::new().await;
    h.active().await;
    let mut c = h.claims(2, Active, Online).await;
    c.grant.as_mut().unwrap().expires_at += 1;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    c.grant = Some(h.lease.clone());
    c.grant.as_mut().unwrap().scopes.push("exec.run".into());
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn free_requires_exact_signed_drain_acknowledgement() {
    let h = Harness::new().await;
    h.active().await;
    let mut c = h.claims(2, Free, Offline).await;
    c.drained_grant = Some(h.lease.id);
    assert_eq!(
        h.apply(&c).await,
        Err(IdentityError::InvalidProof),
        "no Active -> Free shortcut"
    );
    let d = h.claims(2, Draining, Offline).await;
    h.apply(&d).await.unwrap();
    let mut c = h.claims(3, Free, Offline).await;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    c.drained_grant = Some(Uuid::new_v4());
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    c.drained_grant = Some(h.lease.id);
    h.apply(&c).await.unwrap();
}
#[tokio::test]
async fn drained_owner_can_be_replaced_only_above_revocation_floor() {
    let h = Harness::new().await;
    h.active().await;
    h.drain_free().await;
    let mut c = h.claims(4, Active, Online).await;
    c.grant.as_mut().unwrap().id = Uuid::new_v4();
    c.grant.as_mut().unwrap().conversation = h.b.as_str().into();
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    c.authority_epoch = 2;
    h.apply(&c).await.unwrap();
    assert_eq!(
        h.projection.assess(&h.b, "files.read").await.unwrap(),
        Eligible
    );
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
}
#[tokio::test]
async fn exact_duplicate_is_idempotent_without_freshness_extension() {
    let h = Harness::new().await;
    let c = h.active().await;
    assert_eq!(h.apply(&c).await.unwrap(), ApplyOutcome::Duplicate);
    let until: i64 = sqlx::query_scalar("SELECT snapshot_until FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(until, c.valid_until);
}
#[tokio::test]
async fn duplicate_is_not_accepted_during_new_reconciliation() {
    let h = Harness::new().await;
    let c = h.active().await;
    h.projection.challenge(h.device.id).await.unwrap();
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn conflicting_duplicate_and_reordered_revision_rejected() {
    let h = Harness::new().await;
    h.active().await;
    let mut c = h.claims(1, Active, Offline).await;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    c.revision = 0;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn simultaneous_identical_submissions_apply_exactly_once() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    let (p, s) = h.signed(&c);
    let (a, b) = tokio::join!(
        h.projection.apply(h.device.id, &p, &s),
        h.projection.apply(h.device.id, &p, &s)
    );
    assert!(matches!(
        (a.unwrap(), b.unwrap()),
        (ApplyOutcome::Applied, ApplyOutcome::Duplicate)
            | (ApplyOutcome::Duplicate, ApplyOutcome::Applied)
    ));
}
#[tokio::test]
async fn concurrent_conflicting_signed_snapshots_have_one_winner() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    let mut other = c.clone();
    other.grant.as_mut().unwrap().conversation = h.b.as_str().into();
    let (p, s) = h.signed(&c);
    let (q, t) = h.signed(&other);
    let (a, b) = tokio::join!(
        h.projection.apply(h.device.id, &p, &s),
        h.projection.apply(h.device.id, &q, &t)
    );
    assert_ne!(a.is_ok(), b.is_ok());
}
#[tokio::test]
async fn invalid_signature_does_not_consume_the_valid_challenge() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    let (p, _) = h.signed(&c);
    assert_eq!(
        h.projection.apply(h.device.id, &p, &[0; 64]).await,
        Err(IdentityError::InvalidProof)
    );
    h.apply(&c).await.unwrap();
}
#[tokio::test]
async fn challenge_rotation_invalidates_inflight_snapshot() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    let fresh = h.claims(1, Active, Online).await;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    h.apply(&fresh).await.unwrap();
}
#[tokio::test]
async fn expired_challenge_fails_without_altering_authority() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    sqlx::query("UPDATE ctm_grant_projection SET challenge_until=0")
        .execute(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
}
#[tokio::test]
async fn revoked_device_loses_all_projection_access_immediately() {
    let h = Harness::new().await;
    let c = h.active().await;
    h.f.store.revoke_device(h.device.id).await.unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
    assert!(h.projection.challenge(h.device.id).await.is_err());
}
#[tokio::test]
async fn changed_registry_epoch_invalidates_cached_projection() {
    let h = Harness::new().await;
    h.active().await;
    sqlx::query("UPDATE ctm_devices SET epoch=epoch+1 WHERE id=$1")
        .bind(h.device.id)
        .execute(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
}
#[tokio::test]
async fn stale_controller_is_fenced_by_later_activation() {
    let h = Harness::new().await;
    let c = h.active().await;
    let p = ProjectionStore::activate(h.f.store.clone()).await.unwrap();
    assert_eq!(
        p.assess(&h.a, "files.read").await.unwrap(),
        RecoveryRequired
    );
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        RecoveryRequired
    );
    assert!(h.projection.challenge(h.device.id).await.is_err());
    assert!(h.apply(&c).await.is_err());
}
#[tokio::test]
async fn reopened_identity_requires_new_boot_challenge_and_revision() {
    let mut h = Harness::new().await;
    let old = h.active().await;
    let reopened = IdentityStore::open(
        h.f.pool.clone(),
        identity(),
        SecretKey::new([7; 32]).unwrap(),
        Lifetimes::default(),
    )
    .await
    .unwrap();
    h.projection = ProjectionStore::activate(reopened).await.unwrap();
    assert!(h.apply(&old).await.is_err());
    let c = h.claims(2, Active, Online).await;
    h.apply(&c).await.unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        Eligible
    );
}
#[tokio::test]
async fn restored_projection_rows_never_authorize_without_new_device_proof() {
    let mut h = Harness::new().await;
    let old = h.active().await;
    sqlx::query("CREATE TABLE projection_backup AS TABLE ctm_grant_projection")
        .execute(&h.f.pool)
        .await
        .unwrap();
    h.drain_free().await;
    sqlx::query("TRUNCATE ctm_grant_projection")
        .execute(&h.f.pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO ctm_grant_projection SELECT * FROM projection_backup")
        .execute(&h.f.pool)
        .await
        .unwrap();
    h.projection = ProjectionStore::activate(h.f.store.clone()).await.unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        RecoveryRequired
    );
    assert!(h.apply(&old).await.is_err());
    // Fresh proof of the LOCAL drained state, rather than treating the restored grant as active.
    let d = h.claims(4, Draining, Offline).await;
    h.apply(&d).await.unwrap();
    let mut c = h.claims(5, Free, Offline).await;
    c.drained_grant = Some(h.lease.id);
    h.apply(&c).await.unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
}
#[tokio::test]
async fn expired_snapshot_is_offline_not_released_owner() {
    let h = Harness::new().await;
    h.active().await;
    sqlx::query("UPDATE ctm_grant_projection SET snapshot_until=0")
        .execute(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        WorkspaceOffline
    );
    let mut c = h.claims(2, Active, Online).await;
    c.grant.as_mut().unwrap().conversation = h.b.as_str().into();
    assert!(h.apply(&c).await.is_err());
}
#[tokio::test]
async fn grant_expiry_does_not_silently_confirm_drain() {
    let mut h = Harness::new().await;
    h.lease.expires_at = clock(&h.f).await + 1;
    h.active().await;
    tokio::time::sleep(std::time::Duration::from_millis(1100)).await;
    assert_eq!(
        h.projection.assess(&h.a, "files.read").await.unwrap(),
        AuthorizationUnavailable
    );
    let mut c = h.claims(2, Active, Online).await;
    c.authority_epoch = 2;
    c.grant.as_mut().unwrap().expires_at += 600;
    assert!(h.apply(&c).await.is_err());
    // Expired old grants may still be explicitly drained.
    let c = h.claims(2, Draining, Offline).await;
    h.apply(&c).await.unwrap();
}
#[tokio::test]
async fn snapshot_expiry_is_rechecked_after_row_lock_wait() {
    let h = Harness::new().await;
    let mut c = h.claims(1, Active, Online).await;
    c.valid_until = clock(&h.f).await + 1;
    let (p, s) = h.signed(&c);
    let mut lock = h.f.pool.begin().await.unwrap();
    sqlx::query("SELECT connector FROM ctm_grant_projection FOR UPDATE")
        .fetch_one(&mut *lock)
        .await
        .unwrap();
    let projected = h.projection.clone();
    let device = h.device.id;
    let task = tokio::spawn(async move { projected.apply(device, &p, &s).await });
    tokio::time::sleep(std::time::Duration::from_millis(1100)).await;
    lock.commit().await.unwrap();
    assert_eq!(task.await.unwrap(), Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn device_revocation_wait_is_rechecked_before_snapshot_acceptance() {
    let h = Harness::new().await;
    let c = h.claims(1, Active, Online).await;
    let (p, s) = h.signed(&c);
    let mut lock = h.f.pool.begin().await.unwrap();
    sqlx::query("UPDATE ctm_devices SET revoked=true WHERE id=$1")
        .bind(h.device.id)
        .execute(&mut *lock)
        .await
        .unwrap();
    let projected = h.projection.clone();
    let device = h.device.id;
    let task = tokio::spawn(async move { projected.apply(device, &p, &s).await });
    tokio::time::sleep(std::time::Duration::from_millis(30)).await;
    lock.commit().await.unwrap();
    assert_eq!(task.await.unwrap(), Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn binding_is_per_conversation_principal_client_and_resource() {
    let h = Harness::new().await;
    assert_ne!(h.a.as_str(), h.b.as_str());
    let mut p = OAuthPrincipal {
        subject: Uuid::from_u128(8),
        client_id: "public-client".into(),
        resource: identity().resource(),
    };
    assert_eq!(
        h.projection
            .conversation_binding(&p, "host-session-A")
            .unwrap()
            .as_str(),
        h.a.as_str()
    );
    p.subject = Uuid::new_v4();
    assert_ne!(
        h.projection
            .conversation_binding(&p, "host-session-A")
            .unwrap()
            .as_str(),
        h.a.as_str()
    );
    p.resource = "https://foreign.invalid/mcp".into();
    assert!(h
        .projection
        .conversation_binding(&p, "host-session-A")
        .is_err());
}
#[tokio::test]
async fn persisted_minimal_state_contains_no_challenge_or_raw_session() {
    let h = Harness::new().await;
    let c = h.active().await;
    let value: String =
        sqlx::query_scalar("SELECT row_to_json(t)::text FROM ctm_grant_projection t")
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
    assert!(!value.contains(&c.challenge));
    assert!(!value.contains("host-session-A"));
    assert!(!value.contains("private_key"));
    assert!(!format!("{:?}", h.a).contains(h.a.as_str()));
}
#[tokio::test]
async fn same_device_binding_is_idempotent_and_unregistered_device_rejected() {
    let h = Harness::new().await;
    h.projection.bind_device(h.device.id).await.unwrap();
    assert!(h.projection.bind_device(Uuid::new_v4()).await.is_err());
}

#[tokio::test]
async fn another_valid_enrolled_device_cannot_hijack_connector_binding() {
    use coding_tools_cloud_gateway::device::enrollment_message;
    use ring::signature::KeyPair;
    let h = Harness::new().await;
    let i = h.f.store.create_device_invitation().await.unwrap();
    let pk = h.key.public_key().as_ref();
    let sig = h
        .key
        .sign(&enrollment_message(&identity(), i.token.expose(), pk).unwrap());
    let other =
        h.f.store
            .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
            .await
            .unwrap();
    assert_eq!(
        h.projection.bind_device(other.id).await,
        Err(IdentityError::Conflict)
    );
    assert!(h.projection.challenge(other.id).await.is_err());
    let mut c = h.claims(1, Active, Online).await;
    c.device = other.id;
    let (p, s) = h.signed(&c);
    assert!(h.projection.apply(other.id, &p, &s).await.is_err());
}
#[tokio::test]
async fn draining_cannot_become_active_without_free_and_new_epoch() {
    let h = Harness::new().await;
    h.active().await;
    let c = h.claims(2, Draining, Offline).await;
    h.apply(&c).await.unwrap();
    let c = h.claims(3, Active, Online).await;
    assert_eq!(h.apply(&c).await, Err(IdentityError::InvalidProof));
}
#[tokio::test]
async fn invalid_transition_leaves_revision_and_lease_unchanged() {
    let h = Harness::new().await;
    h.active().await;
    let before: (i64, String) =
        sqlx::query_as("SELECT revision,state_text FROM ctm_grant_projection")
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
    let mut c = h.claims(2, Active, Online).await;
    c.grant.as_mut().unwrap().conversation = h.b.as_str().into();
    assert!(h.apply(&c).await.is_err());
    let after: (i64, String) =
        sqlx::query_as("SELECT revision,state_text FROM ctm_grant_projection")
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
    assert_eq!(before, after);
}
#[tokio::test]
async fn invalid_session_contexts_are_rejected_not_merged_into_a_shared_chat() {
    let h = Harness::new().await;
    let p = OAuthPrincipal {
        subject: Uuid::from_u128(8),
        client_id: "public-client".into(),
        resource: identity().resource(),
    };
    for s in ["".into(), "a\nb".into(), "a".repeat(1025)] {
        assert!(h.projection.conversation_binding(&p, &s).is_err());
    }
    let mut other = p.clone();
    other.client_id = "another-client".into();
    assert_ne!(
        h.projection
            .conversation_binding(&other, "host-session-A")
            .unwrap()
            .as_str(),
        h.a.as_str()
    );
}
