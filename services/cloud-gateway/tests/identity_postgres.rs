mod common;
use coding_tools_cloud_gateway::{
    crypto::pkce_challenge, AuthorizationRequest, ClientCredential, IdentityError, IdentityStore,
    Lifetimes, Secret, SecretKey,
};
use common::{identity, public, Fixture};
use uuid::Uuid;

#[tokio::test]
async fn pkce_code_exchange_and_access_identity() {
    let f = Fixture::new().await;
    let owner = Uuid::new_v4();
    let t = f.tokens(owner).await;
    let p = f
        .store
        .authenticate_access(t.access_token.expose())
        .await
        .unwrap();
    assert_eq!(p.subject, owner);
    assert_eq!(p.resource, identity().resource());
    assert_eq!(t.expires_in, 3600);
    assert!(f
        .store
        .authenticate_access(t.refresh_token.expose())
        .await
        .is_err());
}
#[tokio::test]
async fn incorrect_verifier_does_not_consume_code() {
    let f = Fixture::new().await;
    let c = f.code(Uuid::new_v4()).await;
    assert!(f
        .store
        .exchange_code(
            public(),
            c.expose(),
            &"b".repeat(43),
            "https://client.example.invalid/callback",
            &identity().resource()
        )
        .await
        .is_err());
    assert!(f
        .store
        .exchange_code(
            public(),
            c.expose(),
            &"a".repeat(43),
            "https://client.example.invalid/callback",
            &identity().resource()
        )
        .await
        .is_ok());
}
#[tokio::test]
async fn exact_resource_and_redirect_binding() {
    let f = Fixture::new().await;
    let c = f.code(Uuid::new_v4()).await;
    for (redirect, resource) in [
        (
            "https://client.example.invalid/callback/",
            identity().resource(),
        ),
        (
            "https://client.example.invalid/callback",
            "https://other.invalid/mcp".into(),
        ),
    ] {
        assert!(f
            .store
            .exchange_code(public(), c.expose(), &"a".repeat(43), redirect, &resource)
            .await
            .is_err());
    }
}
#[tokio::test]
async fn code_replay_revokes_issued_access_and_refresh() {
    let f = Fixture::new().await;
    let c = f.code(Uuid::new_v4()).await;
    let first = f
        .store
        .exchange_code(
            public(),
            c.expose(),
            &"a".repeat(43),
            "https://client.example.invalid/callback",
            &identity().resource(),
        )
        .await
        .unwrap();
    assert!(f
        .store
        .exchange_code(
            public(),
            c.expose(),
            &"a".repeat(43),
            "https://client.example.invalid/callback",
            &identity().resource()
        )
        .await
        .is_err());
    assert!(f
        .store
        .authenticate_access(first.access_token.expose())
        .await
        .is_err());
    assert!(f
        .store
        .refresh(
            public(),
            first.refresh_token.expose(),
            &identity().resource()
        )
        .await
        .is_err());
}
#[tokio::test]
async fn refresh_persists_across_core_reopen_without_any_agent() {
    let f = Fixture::new().await;
    let owner = Uuid::new_v4();
    let t = f.tokens(owner).await;
    let reopened = IdentityStore::open(
        f.pool.clone(),
        identity(),
        SecretKey::new([7; 32]).unwrap(),
        Lifetimes::default(),
    )
    .await
    .unwrap();
    let r = reopened
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .unwrap();
    assert_eq!(
        reopened
            .authenticate_access(r.access_token.expose())
            .await
            .unwrap()
            .subject,
        owner
    );
    assert_ne!(t.refresh_token.expose(), r.refresh_token.expose());
}
#[tokio::test]
async fn old_refresh_reuse_revokes_whole_family() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    let new = f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .unwrap();
    assert!(f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .is_err());
    assert!(f
        .store
        .authenticate_access(new.access_token.expose())
        .await
        .is_err());
    assert!(f
        .store
        .refresh(public(), new.refresh_token.expose(), &identity().resource())
        .await
        .is_err());
}
#[tokio::test]
async fn concurrent_refresh_has_one_rotation_and_reuse_revocation() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    let resource = identity().resource();
    let (a, b) = tokio::join!(
        f.store
            .refresh(public(), t.refresh_token.expose(), &resource),
        f.store
            .refresh(public(), t.refresh_token.expose(), &resource)
    );
    assert_ne!(a.is_ok(), b.is_ok());
    let winner = a.or(b).unwrap();
    assert!(
        f.store
            .authenticate_access(winner.access_token.expose())
            .await
            .is_err(),
        "reuse revokes the success response too"
    );
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_refresh_tokens")
        .fetch_one(&f.pool)
        .await
        .unwrap();
    assert_eq!(count, 2);
}
#[tokio::test]
async fn foreign_client_cannot_consume_or_revoke_refresh() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    f.store
        .register_client("other", "https://other.invalid/callback", None)
        .await
        .unwrap();
    assert!(f
        .store
        .refresh(
            ClientCredential {
                client_id: "other",
                secret: None
            },
            t.refresh_token.expose(),
            &identity().resource()
        )
        .await
        .is_err());
    assert!(f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .is_ok());
}
#[tokio::test]
async fn owner_revocation_survives_reopen() {
    let f = Fixture::new().await;
    let owner = Uuid::new_v4();
    let t = f.tokens(owner).await;
    f.store.revoke_owner_sessions(owner).await.unwrap();
    let new = IdentityStore::open(
        f.pool.clone(),
        identity(),
        SecretKey::new([7; 32]).unwrap(),
        Lifetimes::default(),
    )
    .await
    .unwrap();
    assert!(new
        .authenticate_access(t.access_token.expose())
        .await
        .is_err());
    assert!(new
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .is_err());
}
#[tokio::test]
async fn absolute_expiry_does_not_slide_on_refresh() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    sqlx::query("UPDATE ctm_families SET expires_at=floor(extract(epoch FROM clock_timestamp()))::bigint+20").execute(&f.pool).await.unwrap();
    let r = f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .unwrap();
    assert!(r.expires_in <= 20);
    sqlx::query("UPDATE ctm_families SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(f
        .store
        .refresh(public(), r.refresh_token.expose(), &identity().resource())
        .await
        .is_err());
}
#[tokio::test]
async fn expired_code_and_access_are_rejected() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    let c = f.code(Uuid::new_v4()).await;
    sqlx::query("UPDATE ctm_codes SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    sqlx::query("UPDATE ctm_access_tokens SET expires_at=0")
        .execute(&f.pool)
        .await
        .unwrap();
    assert!(f
        .store
        .authenticate_access(t.access_token.expose())
        .await
        .is_err());
    assert!(f
        .store
        .exchange_code(
            public(),
            c.expose(),
            &"a".repeat(43),
            "https://client.example.invalid/callback",
            &identity().resource()
        )
        .await
        .is_err());
    assert!(f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .is_ok());
}
#[tokio::test]
async fn store_refuses_changed_pepper_or_identity() {
    let f = Fixture::new().await;
    assert!(matches!(
        IdentityStore::open(
            f.pool.clone(),
            identity(),
            SecretKey::new([9; 32]).unwrap(),
            Lifetimes::default()
        )
        .await,
        Err(IdentityError::IdentityMismatch)
    ));
    let changed = coding_tools_cloud_gateway::PublicIdentity::new(
        "https://other.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap();
    assert!(matches!(
        IdentityStore::open(
            f.pool.clone(),
            changed,
            SecretKey::new([7; 32]).unwrap(),
            Lifetimes::default()
        )
        .await,
        Err(IdentityError::IdentityMismatch)
    ));
}
#[tokio::test]
async fn confidential_client_requires_secret_in_addition_to_pkce() {
    let f = Fixture::new().await;
    let secret = Secret::random().unwrap();
    let v = "a".repeat(43);
    let challenge = pkce_challenge(&v).unwrap();
    f.store
        .register_client("private", "https://private.invalid/cb", Some(&secret))
        .await
        .unwrap();
    let code = f
        .store
        .issue_after_owner_consent(
            Uuid::new_v4(),
            AuthorizationRequest {
                client_id: "private",
                redirect_uri: "https://private.invalid/cb",
                resource: &identity().resource(),
                code_challenge: &challenge,
                code_challenge_method: "S256",
            },
        )
        .await
        .unwrap();
    assert!(matches!(
        f.store
            .exchange_code(
                ClientCredential {
                    client_id: "private",
                    secret: None
                },
                code.expose(),
                &v,
                "https://private.invalid/cb",
                &identity().resource()
            )
            .await,
        Err(IdentityError::InvalidClient)
    ));
    assert!(f
        .store
        .exchange_code(
            ClientCredential {
                client_id: "private",
                secret: Some(secret.expose())
            },
            code.expose(),
            &v,
            "https://private.invalid/cb",
            &identity().resource()
        )
        .await
        .is_ok());
}
#[tokio::test]
async fn database_contains_keyed_digests_not_token_bytes() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    for table in [
        "ctm_access_tokens",
        "ctm_refresh_tokens",
        "ctm_codes",
        "ctm_families",
    ] {
        let dump: String = sqlx::query_scalar(&format!("SELECT json_agg(t)::text FROM {table} t"))
            .fetch_one(&f.pool)
            .await
            .unwrap();
        assert!(!dump.contains(t.access_token.expose()));
        assert!(!dump.contains(t.refresh_token.expose()));
    }
}
#[tokio::test]
async fn binding_stable_across_refresh_but_not_across_conversations() {
    let f = Fixture::new().await;
    let t = f.tokens(Uuid::new_v4()).await;
    let p = f
        .store
        .authenticate_access(t.access_token.expose())
        .await
        .unwrap();
    let a = f.store.conversation_binding(&p, "session-a").unwrap();
    let b = f.store.conversation_binding(&p, "session-b").unwrap();
    assert_ne!(a, b);
    let t2 = f
        .store
        .refresh(public(), t.refresh_token.expose(), &identity().resource())
        .await
        .unwrap();
    let p2 = f
        .store
        .authenticate_access(t2.access_token.expose())
        .await
        .unwrap();
    assert_eq!(a, f.store.conversation_binding(&p2, "session-a").unwrap());
    assert!(f.store.conversation_binding(&p, "").is_err());
    assert!(f.store.conversation_binding(&p, "bad\n").is_err());
}
