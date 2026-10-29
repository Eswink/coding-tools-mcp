//! Explicit disposable integration fixture, never shipped as a gateway mode.
//! Only stdout's bounded bootstrap contains synthetic credentials for the parent
//! native test process. No native grant or tool result is fabricated here.
use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use coding_tools_cloud_gateway::{
    channel::{agent_channel_routes, ChannelController},
    device::enrollment_message,
    http, mcp,
    projection::{ConversationBinding, ProjectionDecision, ProjectionStore},
    AuthorizationRequest, ClientCredential, IdentityStore, Lifetimes, OAuthPrincipal,
    PublicIdentity, SecretKey,
};
use ring::signature::{Ed25519KeyPair, KeyPair};
use serde_json::{json, Value};
use sqlx::{postgres::PgPoolOptions, PgPool, Row};
use std::{
    io::{BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, ChildStdin, Command, Stdio},
    sync::{Arc, Mutex},
    time::Duration,
};
use uuid::Uuid;

struct Relay(Child);
impl Drop for Relay {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}
#[derive(Clone)]
struct Inspect {
    token: String,
    pool: PgPool,
    control: ChannelController,
    store: IdentityStore,
    device: Uuid,
    connector: Uuid,
    a: ConversationBinding,
    b: ConversationBinding,
    relay_stdin: Arc<Mutex<Option<ChildStdin>>>,
}
fn authorized(s: &Inspect, headers: &HeaderMap) -> Result<(), StatusCode> {
    if headers.get("authorization").and_then(|v| v.to_str().ok())
        != Some(format!("Bearer {}", s.token).as_str())
    {
        return Err(StatusCode::UNAUTHORIZED);
    }
    Ok(())
}
async fn inspect(State(s): State<Inspect>, headers: HeaderMap) -> Result<Json<Value>, StatusCode> {
    authorized(&s, &headers)?;
    let row: Option<(bool, Option<String>)> =
        sqlx::query_as("SELECT reconciled,state_text FROM ctm_grant_projection")
            .fetch_optional(&s.pool)
            .await
            .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    let projection = row
        .as_ref()
        .and_then(|r| r.1.as_ref())
        .and_then(|s| serde_json::from_str::<Value>(s).ok());
    let channel =
        sqlx::query("SELECT connected,generation FROM ctm_agent_channel WHERE connector=$1")
            .bind(s.connector)
            .fetch_optional(&s.pool)
            .await
            .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    let counts = sqlx::query(
        "SELECT state, count(*)::bigint AS n FROM ctm_request_ledger WHERE connector=$1 GROUP BY state",
    )
    .bind(s.connector)
    .fetch_all(&s.pool)
    .await
    .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    let mut by_state = json!({
        "completed": 0,
        "outcome_unknown": 0,
        "running": 0,
        "admitted": 0,
    });
    let mut total: i64 = 0;
    for c in &counts {
        let state: String = c.get("state");
        let n: i64 = c.get("n");
        total += n;
        if let Some(slot) = by_state.get_mut(&state) {
            *slot = json!(n);
        }
    }
    let last = sqlx::query(
        "SELECT state, result_hash, result_ok FROM ctm_request_ledger WHERE connector=$1 ORDER BY updated_at DESC, request_id DESC LIMIT 1",
    )
    .bind(s.connector)
    .fetch_optional(&s.pool)
    .await
    .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    let last = last.map(|r| {
        let hash: Option<Vec<u8>> = r.get("result_hash");
        json!({
            "state": r.get::<String, _>("state"),
            "result_hash_len": hash.as_ref().map(|h| h.len()).unwrap_or(0),
            "result_ok": r.get::<Option<bool>, _>("result_ok"),
        })
    });
    Ok(Json(json!({
        "ready":row.as_ref().is_some_and(|r|r.0) && s.control.has_native_approval_route(),
        "eligible_a":s.control.assess(&s.a,"files.read").await.ok()==Some(ProjectionDecision::Eligible),
        "eligible_b":s.control.assess(&s.b,"files.read").await.ok()==Some(ProjectionDecision::Eligible),
        "phase":projection.as_ref().and_then(|p|p.get("phase")),
        "authority_epoch":projection.as_ref().and_then(|p|p.get("authority_epoch")),
        "channel": {
            "connected": channel.as_ref().map(|r| r.get::<bool, _>("connected")).unwrap_or(false),
            "generation": channel.as_ref().map(|r| r.get::<i64, _>("generation")).unwrap_or(0),
        },
        "ledger": {
            "total": total,
            "by_state": by_state,
            "last": last,
        },
    })))
}
async fn relay_control(
    State(s): State<Inspect>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Result<Json<Value>, StatusCode> {
    authorized(&s, &headers)?;
    let op = body.get("op").and_then(|v| v.as_str()).unwrap_or("");
    if !matches!(op, "drop" | "refuse" | "hold_up" | "release") {
        return Err(StatusCode::BAD_REQUEST);
    }
    let mut guard = s
        .relay_stdin
        .lock()
        .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    let stdin = guard.as_mut().ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    writeln!(stdin, "{}", json!({"op": op})).map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    stdin.flush().map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    Ok(Json(json!({"ok": true})))
}
async fn revoke_device(
    State(s): State<Inspect>,
    headers: HeaderMap,
    Json(_body): Json<Value>,
) -> Result<Json<Value>, StatusCode> {
    authorized(&s, &headers)?;
    s.store
        .revoke_device(s.device)
        .await
        .map_err(|_| StatusCode::SERVICE_UNAVAILABLE)?;
    Ok(Json(json!({"ok": true})))
}
#[tokio::main]
async fn main() {
    assert_eq!(
        std::env::var("CTM_NATIVE_E2E_FIXTURE").as_deref(),
        Ok("1"),
        "explicit disposable native fixture required"
    );
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(16385)
        .read_to_end(&mut bytes)
        .unwrap();
    assert!(bytes.len() <= 16384);
    let input: Value = serde_json::from_slice(&bytes).unwrap();
    let root = PathBuf::from(input["root"].as_str().unwrap())
        .canonicalize()
        .unwrap();
    assert!(root.is_dir() && root.join(".native-cloud-fixture").is_file());
    assert!(!root.join("host-state.bin").exists());
    let dsn = std::env::var("TEST_DATABASE_URL").unwrap();
    let parsed = url::Url::parse(&dsn).unwrap();
    assert_eq!(parsed.path(), "/coding_tools_identity_test");
    assert!(matches!(parsed.host_str(), Some("localhost" | "127.0.0.1")));
    let mut relay = Relay(
        Command::new("python3")
            .arg("-S")
            .arg(format!(
                "{}/tests/host_agent_support/relay.py",
                env!("CARGO_MANIFEST_DIR")
            ))
            .arg(&root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap(),
    );
    let mut line = String::new();
    BufReader::new(relay.0.stdout.take().unwrap())
        .read_line(&mut line)
        .unwrap();
    let port = serde_json::from_str::<Value>(&line).unwrap()["port"]
        .as_u64()
        .unwrap();
    let identity = PublicIdentity::new(
        &format!("https://localhost:{port}"),
        "/coding-tools",
        Uuid::new_v4(),
    )
    .unwrap();
    let admin = PgPoolOptions::new()
        .max_connections(1)
        .connect(&dsn)
        .await
        .unwrap();
    let schema = format!("ctm_native_{}", Uuid::new_v4().simple());
    sqlx::query(&format!("CREATE SCHEMA {schema}"))
        .execute(&admin)
        .await
        .unwrap();
    let pool = PgPoolOptions::new()
        .max_connections(8)
        .after_connect(move |c, _| {
            let sql = format!("SET search_path TO {schema}");
            Box::pin(async move {
                sqlx::query(&sql).execute(c).await?;
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
        identity.clone(),
        SecretKey::new([7; 32]).unwrap(),
        Lifetimes::default(),
    )
    .await
    .unwrap();
    store
        .register_client(
            "native-fixture-client",
            "https://client.example.invalid/callback",
            None,
        )
        .await
        .unwrap();
    let verifier = "a".repeat(43);
    let code = store
        .issue_after_owner_consent(
            Uuid::from_u128(8),
            AuthorizationRequest {
                client_id: "native-fixture-client",
                redirect_uri: "https://client.example.invalid/callback",
                resource: &identity.resource(),
                code_challenge: &coding_tools_cloud_gateway::crypto::pkce_challenge(&verifier)
                    .unwrap(),
                code_challenge_method: "S256",
            },
        )
        .await
        .unwrap();
    let pair = store
        .exchange_code(
            ClientCredential {
                client_id: "native-fixture-client",
                secret: None,
            },
            code.expose(),
            &verifier,
            "https://client.example.invalid/callback",
            &identity.resource(),
        )
        .await
        .unwrap();
    let access = pair.access_token.expose().to_owned();
    let pkcs8 = Ed25519KeyPair::generate_pkcs8(&ring::rand::SystemRandom::new()).unwrap();
    let key = Ed25519KeyPair::from_pkcs8(pkcs8.as_ref()).unwrap();
    let invite = store.create_device_invitation().await.unwrap();
    let msg =
        enrollment_message(&identity, invite.token.expose(), key.public_key().as_ref()).unwrap();
    let device = store
        .redeem_device_invitation(
            invite.token.expose(),
            key.public_key().as_ref(),
            key.sign(&msg).as_ref(),
        )
        .await
        .unwrap();
    let projection = ProjectionStore::activate(store.clone()).await.unwrap();
    projection.bind_device(device.id).await.unwrap();
    let control = ChannelController::activate(store.clone()).await.unwrap();
    let principal = OAuthPrincipal {
        subject: Uuid::from_u128(8),
        client_id: "native-fixture-client".into(),
        resource: identity.resource(),
    };
    let a = control
        .conversation_binding(&principal, "native-A")
        .unwrap();
    let b = control
        .conversation_binding(&principal, "native-B")
        .unwrap();
    let inspection_token = Uuid::new_v4().to_string();
    let relay_stdin = Arc::new(Mutex::new(relay.0.stdin.take()));
    let inspect_router = Router::new()
        .route("/__native_fixture", get(inspect))
        .route("/__native_fixture/relay", post(relay_control))
        .route("/__native_fixture/revoke_device", post(revoke_device))
        .with_state(Inspect {
            token: inspection_token.clone(),
            pool: pool.clone(),
            control: control.clone(),
            store: store.clone(),
            device: device.id,
            connector: identity.connector(),
            a: a.clone(),
            b: b.clone(),
            relay_stdin: relay_stdin.clone(),
        });
    let router = agent_channel_routes(control.clone())
        .merge(mcp::routes(store.clone(), control))
        .merge(http::identity_routes(store))
        .merge(inspect_router);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    {
        let mut guard = relay_stdin.lock().unwrap();
        let stdin = guard.as_mut().unwrap();
        writeln!(stdin, "{}", listener.local_addr().unwrap().port()).unwrap();
        stdin.flush().unwrap();
    }
    let config = json!({"origin":identity.origin(),"prefix":identity.prefix(),"connector":identity.connector(),
        "device":device.id,"device_epoch":device.epoch,"authority_epoch":1,
        "public_key":URL_SAFE_NO_PAD.encode(key.public_key().as_ref()),
        "revision_file":root.join("legacy-unused-state"),"ca_der_file":root.join("ca.der"),"run_seconds":120});
    let bootstrap = json!({"config":config,"key":{"pkcs8":URL_SAFE_NO_PAD.encode(pkcs8.as_ref())},
        "access_token":access,"refresh_token":pair.refresh_token.expose(),"inspection_token":inspection_token,
        "resource":identity.resource(),"token_endpoint":format!("{}{}",identity.origin(),identity.token_path()),
        "conversation_a":a.as_str(),"conversation_b":b.as_str(),"protocol":mcp::MODERN});
    println!("{bootstrap}");
    std::io::stdout().flush().unwrap();
    let server = axum::serve(listener, router).with_graceful_shutdown(async {
        tokio::time::sleep(Duration::from_secs(120)).await;
    });
    server.await.unwrap();
    drop(relay);
}
