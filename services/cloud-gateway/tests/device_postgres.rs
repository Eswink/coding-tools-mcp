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
