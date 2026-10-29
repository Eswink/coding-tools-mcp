use coding_tools_cloud_gateway::{
    AuthorizationRequest, ClientCredential, IdentityStore, Lifetimes, PublicIdentity, Secret,
    SecretKey, TokenPair,
};
use sqlx::{postgres::PgPoolOptions, PgPool};
use uuid::Uuid;
pub fn identity() -> PublicIdentity {
    PublicIdentity::new(
        "https://gateway.example.invalid",
        "/coding-tools",
        Uuid::from_u128(1),
    )
    .unwrap()
}
pub struct Fixture {
    pub store: IdentityStore,
    pub pool: PgPool,
}
impl Fixture {
    pub async fn new() -> Self {
        let dsn = std::env::var("TEST_DATABASE_URL")
            .expect("TEST_DATABASE_URL required; no implicit skip or production fallback");
        let parsed = url::Url::parse(&dsn).expect("test DSN");
        assert_eq!(
            parsed.path(),
            "/coding_tools_identity_test",
            "refusing non-test database"
        );
        assert!(
            matches!(parsed.host_str(), Some("127.0.0.1" | "localhost")),
            "refusing non-loopback test database"
        );
        let admin = PgPoolOptions::new()
            .max_connections(2)
            .connect(&dsn)
            .await
            .unwrap();
        let schema = format!("ctm_test_{}", Uuid::new_v4().simple());
        sqlx::query(&format!("CREATE SCHEMA {schema}"))
            .execute(&admin)
            .await
            .unwrap();
        let pool = PgPoolOptions::new()
            .max_connections(4)
            .after_connect(move |conn, _| {
                let query = format!("SET search_path TO {schema}");
                Box::pin(async move {
                    sqlx::query(&query).execute(conn).await?;
                    Ok(())
                })
            })
            .connect(&dsn)
            .await
            .unwrap();
        admin.close().await;
        IdentityStore::migrate(&pool).await.unwrap();
        let store = IdentityStore::open(
            pool.clone(),
            identity(),
            SecretKey::new([7; 32]).unwrap(),
            Lifetimes::default(),
        )
        .await
        .unwrap();
        store
            .register_client(
                "public-client",
                "https://client.example.invalid/callback",
                None,
            )
            .await
            .unwrap();
        Self { store, pool }
    }
    pub async fn code(&self, owner: Uuid) -> Secret {
        let verifier = "a".repeat(43);
        let challenge = coding_tools_cloud_gateway::crypto::pkce_challenge(&verifier).unwrap();
        self.store
            .issue_after_owner_consent(
                owner,
                AuthorizationRequest {
                    client_id: "public-client",
                    redirect_uri: "https://client.example.invalid/callback",
                    resource: &identity().resource(),
                    code_challenge: &challenge,
                    code_challenge_method: "S256",
                },
            )
            .await
            .unwrap()
    }
    pub async fn tokens(&self, owner: Uuid) -> TokenPair {
        let code = self.code(owner).await;
        self.store
            .exchange_code(
                public(),
                code.expose(),
                &"a".repeat(43),
                "https://client.example.invalid/callback",
                &identity().resource(),
            )
            .await
            .unwrap()
    }
}
pub fn public() -> ClientCredential<'static> {
    ClientCredential {
        client_id: "public-client",
        secret: None,
    }
}
