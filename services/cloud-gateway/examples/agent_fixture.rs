//! Test-only enrolled key fixture. Refuses non-loopback or non-test databases.
//! Private output is consumed in-memory by the isolated process test, never logged.
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_gateway::{
    device::enrollment_message, IdentityStore, Lifetimes, PublicIdentity, SecretKey,
};
use ring::{
    rand::SystemRandom,
    signature::{Ed25519KeyPair, KeyPair},
};
use serde_json::{json, Value};
use std::io::Read;
#[tokio::main]
async fn main() {
    let mut b = Vec::new();
    std::io::stdin().take(16385).read_to_end(&mut b).unwrap();
    assert!(b.len() <= 16384);
    let doc: Value = serde_json::from_slice(&b).unwrap();
    let dsn = doc["secrets"]["database_url"].as_str().unwrap();
    let u = url::Url::parse(dsn).unwrap();
    assert!(matches!(u.host_str(), Some("127.0.0.1" | "localhost")));
    assert_eq!(u.path(), "/coding_tools_identity_test");
    let c = &doc["config"];
    let identity = PublicIdentity::new(
        c["origin"].as_str().unwrap(),
        c["prefix"].as_str().unwrap(),
        c["connector"].as_str().unwrap().parse().unwrap(),
    )
    .unwrap();
    let key = SecretKey::new(
        URL_SAFE_NO_PAD
            .decode(doc["secrets"]["identity_key"].as_str().unwrap())
            .unwrap()
            .as_slice()
            .try_into()
            .unwrap(),
    )
    .unwrap();
    let pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(2)
        .connect(dsn)
        .await
        .unwrap();
    let store = IdentityStore::open(pool.clone(), identity.clone(), key, Lifetimes::default())
        .await
        .unwrap();
    let pkcs = Ed25519KeyPair::generate_pkcs8(&SystemRandom::new()).unwrap();
    let pair = Ed25519KeyPair::from_pkcs8(pkcs.as_ref()).unwrap();
    let invite = store.create_device_invitation().await.unwrap();
    let proof =
        enrollment_message(&identity, invite.token.expose(), pair.public_key().as_ref()).unwrap();
    let device = store
        .redeem_device_invitation(
            invite.token.expose(),
            pair.public_key().as_ref(),
            pair.sign(&proof).as_ref(),
        )
        .await
        .unwrap();
    pool.close().await;
    println!(
        "{}",
        json!({"device":device.id,"device_epoch":device.epoch,"public_key":URL_SAFE_NO_PAD.encode(pair.public_key().as_ref()),"pkcs8":URL_SAFE_NO_PAD.encode(pkcs.as_ref())})
    );
}
