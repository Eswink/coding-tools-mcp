//! Disposable process/database restart probe; cookie/CSRF travel only via parent pipes.
#[path = "../tests/browser_support/mod.rs"]
mod browser_support;
#[allow(dead_code)]
#[path = "../tests/common/mod.rs"]
mod common;
use browser_support::*;
use coding_tools_cloud_gateway::{browser::BrowserAuth, IdentityStore, Lifetimes, SecretKey};
use serde::{Deserialize, Serialize};
use sqlx::postgres::PgPoolOptions;
use std::io::{Read, Write};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ProbeState {
    schema: String,
    cookie: String,
    csrf: String,
}
#[tokio::main]
async fn main() {
    assert_eq!(
        std::env::var("CTM_DISPOSABLE_TEST_PROBE").as_deref(),
        Ok("1")
    );
    match std::env::args().nth(1).as_deref() {
        Some("seed") => {
            let (f, a) = setup().await;
            let p = logged_in(&a).await;
            let schema = sqlx::query_scalar("SELECT current_schema()")
                .fetch_one(&f.pool)
                .await
                .expect("test schema");
            let state = ProbeState {
                schema,
                cookie: p.cookie.expose().into(),
                csrf: p.csrf.expose().into(),
            };
            std::io::stdout()
                .write_all(&serde_json::to_vec(&state).expect("encode test state"))
                .expect("test pipe");
            f.pool.close().await;
        }
        Some("verify") => {
            let mut input = Vec::new();
            std::io::stdin()
                .take(4097)
                .read_to_end(&mut input)
                .expect("test pipe");
            assert!(input.len() <= 4096);
            let state: ProbeState = serde_json::from_slice(&input).expect("test state");
            assert!(state.schema.starts_with("ctm_test_") && state.schema.len() == 41);
            assert!(state.schema[9..].bytes().all(|b| b.is_ascii_hexdigit()));
            let dsn = std::env::var("TEST_DATABASE_URL").expect("test DSN");
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
                SecretKey::new([7; 32]).expect("test key"),
                Lifetimes::default(),
            )
            .await
            .expect("same identity after restart");
            let auth = BrowserAuth::new(store.clone());
            let redirect = auth
                .decide(&state.cookie, &state.csrf, true)
                .await
                .expect("persisted consent after process and database restart");
            assert!(auth.decide(&state.cookie, &state.csrf, true).await.is_err());
            let pair = store
                .exchange_code(
                    common::public(),
                    &code(&redirect),
                    &"a".repeat(43),
                    REDIRECT,
                    &common::identity().resource(),
                )
                .await
                .expect("code exchange");
            let pair = store
                .refresh(
                    common::public(),
                    pair.refresh_token.expose(),
                    &common::identity().resource(),
                )
                .await
                .expect("refresh without agent");
            assert_eq!(
                store
                    .authenticate_access(pair.access_token.expose())
                    .await
                    .expect("access")
                    .subject,
                OWNER
            );
            pool.close().await;
            // Compatible fixed result consumed by run_restart_test.py, with no credential values.
            println!("{{\"restart_refresh\":\"PASS\",\"agent_connected\":false}}");
        }
        _ => panic!("only disposable seed/verify modes supported"),
    }
}
