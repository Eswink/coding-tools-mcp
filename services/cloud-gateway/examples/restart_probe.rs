//! Disposable test-cluster probe only. No server and no production credential path.
#[allow(dead_code)]
#[path = "../tests/common/mod.rs"]
mod common;
use coding_tools_cloud_gateway::{IdentityStore, Lifetimes, SecretKey};
use serde::{Deserialize, Serialize};
use sqlx::postgres::PgPoolOptions;
use std::io::{Read, Write};
use uuid::Uuid;

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeState {
    schema: String,
    access: String,
    refresh: String,
    subject: Uuid,
}

#[tokio::main]
async fn main() {
    assert_eq!(
        std::env::var("CTM_DISPOSABLE_TEST_PROBE").as_deref(),
        Ok("1")
    );
    match std::env::args().nth(1).as_deref() {
        Some("seed") => {
            let fixture = common::Fixture::new().await;
            let subject = Uuid::new_v4();
            let pair = fixture.tokens(subject).await;
            let schema = sqlx::query_scalar("SELECT current_schema()")
                .fetch_one(&fixture.pool)
                .await
                .expect("test schema");
            // Parent captures stdout in memory; never log or persist these test credentials.
            let state = ProbeState {
                schema,
                access: pair.access_token.expose().to_owned(),
                refresh: pair.refresh_token.expose().to_owned(),
                subject,
            };
            std::io::stdout()
                .write_all(&serde_json::to_vec(&state).expect("encode test state"))
                .expect("test pipe");
            fixture.pool.close().await;
        }
        Some("verify") => {
            let mut input = Vec::new();
            std::io::stdin()
                .take(4097)
                .read_to_end(&mut input)
                .expect("test pipe");
            assert!(input.len() <= 4096, "oversized test state");
            let state: ProbeState = serde_json::from_slice(&input).expect("test state");
            assert!(state.schema.starts_with("ctm_test_") && state.schema.len() == 41);
            assert!(state.schema[9..].bytes().all(|b| b.is_ascii_hexdigit()));
            let dsn = std::env::var("TEST_DATABASE_URL").expect("test DSN required");
            let parsed = url::Url::parse(&dsn).expect("test DSN");
            assert_eq!(parsed.path(), "/coding_tools_identity_test");
            assert!(matches!(parsed.host_str(), Some("127.0.0.1" | "localhost")));
            let schema = state.schema;
            let pool = PgPoolOptions::new()
                .after_connect(move |conn, _| {
                    let query = format!("SET search_path TO {schema}");
                    Box::pin(async move {
                        sqlx::query(&query).execute(conn).await?;
                        Ok(())
                    })
                })
                .connect(&dsn)
                .await
                .expect("test DB after restart");
            let store = IdentityStore::open(
                pool.clone(),
                common::identity(),
                SecretKey::new([7; 32]).expect("fixed TEST key"),
                Lifetimes::default(),
            )
            .await
            .expect("identity retained across restart");
            assert_eq!(
                store
                    .authenticate_access(&state.access)
                    .await
                    .expect("saved access")
                    .subject,
                state.subject
            );
            let pair = store
                .refresh(
                    common::public(),
                    &state.refresh,
                    &common::identity().resource(),
                )
                .await
                .expect("saved refresh");
            assert_eq!(
                store
                    .authenticate_access(pair.access_token.expose())
                    .await
                    .expect("rotated access")
                    .subject,
                state.subject
            );
            pool.close().await;
            println!("{{\"restart_refresh\":\"PASS\",\"agent_connected\":false}}");
        }
        _ => panic!("only seed/verify disposable probe modes supported"),
    }
}
