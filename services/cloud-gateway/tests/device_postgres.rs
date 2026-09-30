#[allow(dead_code)]
mod common;
use coding_tools_cloud_gateway::device::enrollment_message;
use common::{identity, Fixture};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
fn key() -> Ed25519KeyPair {
    Ed25519KeyPair::from_pkcs8(
        Ed25519KeyPair::generate_pkcs8(&SystemRandom::new())
            .unwrap()
            .as_ref(),
    )
    .unwrap()
}
#[tokio::test]
async fn device_enrollment_requires_private_key_and_one_time_invite() {
    let f = Fixture::new().await;
    let i = f.store.create_device_invitation().await.unwrap();
    let k = key();
    let pk = k.public_key().as_ref();
    assert!(f
        .store
        .redeem_device_invitation(i.token.expose(), pk, &[0; 64])
        .await
        .is_err());
    let sig = k.sign(&enrollment_message(&identity(), i.token.expose(), pk).unwrap());
    let d = f
        .store
        .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
        .await
        .unwrap();
    assert_eq!(f.store.registered_device(d.id).await.unwrap(), d);
    assert!(f
        .store
        .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
        .await
        .is_err());
    let families: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_families")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(
        families, 0,
        "device enrollment must not grant OAuth or tool authority"
    );
}
#[tokio::test]
async fn concurrent_enrollment_creates_one_device() {
    let f = Fixture::new().await;
    let i = f.store.create_device_invitation().await.unwrap();
    let k = key();
    let pk = k.public_key().as_ref();
    let sig = k.sign(&enrollment_message(&identity(), i.token.expose(), pk).unwrap());
    let (a, b) = tokio::join!(
        f.store
            .redeem_device_invitation(i.token.expose(), pk, sig.as_ref()),
        f.store
            .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
    );
    assert_ne!(a.is_ok(), b.is_ok());
    let n: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_devices")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(n, 1);
}
#[tokio::test]
async fn expired_invite_and_revoked_device_are_rejected() {
    let f = Fixture::new().await;
    let i = f.store.create_device_invitation().await.unwrap();
    let k = key();
    let pk = k.public_key().as_ref();
    let sig = k.sign(&enrollment_message(&identity(), i.token.expose(), pk).unwrap());
    let d = f
        .store
        .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
        .await
        .unwrap();
    f.store.revoke_device(d.id).await.unwrap();
    assert!(f.store.registered_device(d.id).await.is_err());
    let i = f.store.create_device_invitation().await.unwrap();
    let sig = k.sign(&enrollment_message(&identity(), i.token.expose(), pk).unwrap());
    sqlx::query("UPDATE ctm_enrollments SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(f
        .store
        .redeem_device_invitation(i.token.expose(), pk, sig.as_ref())
        .await
        .is_err());
}

#[tokio::test]
async fn enrollment_lock_wait_does_not_extend_invitation_expiry() {
    let f = Fixture::new().await;
    let invite = f.store.create_device_invitation().await.unwrap();
    let k = key();
    let public = k.public_key().as_ref().to_vec();
    let signature = k
        .sign(&enrollment_message(&identity(), invite.token.expose(), &public).unwrap())
        .as_ref()
        .to_vec();
    sqlx::query("UPDATE ctm_enrollments SET expires_at=floor(extract(epoch FROM clock_timestamp()))::bigint+1 WHERE id=$1")
        .bind(invite.id).execute(&f.pool).await.unwrap();
    let mut lock = f.pool.begin().await.unwrap();
    sqlx::query("SELECT id FROM ctm_enrollments WHERE id=$1 FOR UPDATE")
        .bind(invite.id)
        .fetch_one(&mut *lock)
        .await
        .unwrap();
    let store = f.store.clone();
    let token = invite.token.expose().to_owned();
    let pending = tokio::spawn(async move {
        store
            .redeem_device_invitation(&token, &public, &signature)
            .await
    });
    tokio::time::sleep(std::time::Duration::from_millis(1200)).await;
    assert!(
        !pending.is_finished(),
        "redemption did not wait on the held row lock"
    );
    lock.commit().await.unwrap();
    assert!(pending.await.unwrap().is_err());
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_devices")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
}
