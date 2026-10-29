#[allow(dead_code)]
mod channel_support;
mod common;
#[allow(dead_code)]
mod projection_support;
use axum::{
    body::Body,
    http::{header, Request, StatusCode},
};
use coding_tools_cloud_gateway::{
    mcp::{routes, routes_with_observability, MODERN},
    observability::GatewayObservability,
    projection::ProjectionDecision,
};
use common::identity;
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;
use uuid::Uuid;

fn meta(session: Option<&str>) -> Value {
    let mut m = json!({
        "io.modelcontextprotocol/protocolVersion":MODERN,
        "io.modelcontextprotocol/clientCapabilities":{},
        "io.modelcontextprotocol/clientInfo":{"name":"fixture","version":"1"}
    });
    if let Some(s) = session {
        m["openai/session"] = json!(s)
    }
    m
}
fn message(id: i64, method: &str, session: Option<&str>, extra: Value) -> Value {
    let mut params = extra.as_object().cloned().unwrap_or_default();
    params.insert("_meta".into(), meta(session));
    json!({"jsonrpc":"2.0","id":id,"method":method,"params":params})
}
fn request(token: &str, body: &Value) -> Request<Body> {
    let mut b = Request::builder()
        .method("POST")
        .uri(identity().resource_path())
        .header("host", identity().authority())
        .header(header::AUTHORIZATION, format!("Bearer {token}"))
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::ACCEPT, "application/json, text/event-stream")
        .header("mcp-protocol-version", MODERN)
        .header("mcp-method", body["method"].as_str().unwrap());
    if body["method"] == "tools/call" {
        b = b.header("mcp-name", body["params"]["name"].as_str().unwrap())
    }
    b.body(Body::from(serde_json::to_vec(body).unwrap()))
        .unwrap()
}
async fn json_body(r: axum::response::Response) -> Value {
    serde_json::from_slice(&r.into_body().collect().await.unwrap().to_bytes()).unwrap()
}

#[tokio::test]
async fn oauth_errors_are_transport_auth_not_workspace_offline() {
    let (h, c) = channel_support::setup().await;
    let app = routes(h.f.store.clone(), c);
    let body = message(1, "server/discover", None, json!({}));
    let mut r = request(&"x".repeat(43), &body);
    r.headers_mut().remove(header::AUTHORIZATION);
    let r = app.clone().oneshot(r).await.unwrap();
    assert_eq!(r.status(), StatusCode::UNAUTHORIZED);
    assert!(r.headers().contains_key(header::WWW_AUTHENTICATE));
    let v = json_body(r).await;
    assert_eq!(v["error"], "invalid_token");
    let r = app.oneshot(request(&"x".repeat(43), &body)).await.unwrap();
    assert_eq!(r.status(), StatusCode::UNAUTHORIZED);
    assert!(r.headers().contains_key(header::WWW_AUTHENTICATE));
}

#[tokio::test]
async fn discovery_and_catalog_are_stable_without_agent_presence() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());
    let discover = message(1, "server/discover", None, json!({}));
    let r = app
        .clone()
        .oneshot(request(token, &discover))
        .await
        .unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    let d = json_body(r).await;
    assert_eq!(d["result"]["resultType"], "complete");
    let list = message(2, "tools/list", None, json!({}));
    let before = json_body(app.clone().oneshot(request(token, &list)).await.unwrap()).await;
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();
    let after = json_body(app.oneshot(request(token, &list)).await.unwrap()).await;
    assert_eq!(before["result"]["tools"], after["result"]["tools"]);
    assert_eq!(after["result"]["tools"].as_array().unwrap().len(), 49);
}

#[tokio::test]
async fn authorized_agent_offline_is_tool_error_not_oauth_or_foreign_metadata() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();
    let owner = message(
        3,
        "tools/call",
        Some("host-session-A"),
        json!({"name":"workspace_probe","arguments":{}}),
    );
    let r = app.clone().oneshot(request(token, &owner)).await.unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    assert!(!r.headers().contains_key(header::WWW_AUTHENTICATE));
    let v = json_body(r).await;
    assert_eq!(v["result"]["isError"], true);
    assert_eq!(
        v["result"]["structuredContent"]["error"]["code"],
        "WORKSPACE_OFFLINE"
    );
    let foreign = message(
        4,
        "tools/call",
        Some("host-session-B"),
        json!({"name":"workspace_probe","arguments":{}}),
    );
    let v = json_body(app.oneshot(request(token, &foreign)).await.unwrap()).await;
    assert_eq!(
        v["result"]["structuredContent"]["error"]["code"],
        "CHAT_AUTHORIZATION_REQUIRED"
    );
    assert!(v["result"]["structuredContent"]
        .to_string()
        .find("offline")
        .is_none());
}

#[tokio::test]
async fn offline_foreign_authorization_request_is_suppressed_without_state_or_channel_noise() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());

    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();

    let channel_before: (i64, Option<Uuid>, bool, i64, i64, i64) = sqlx::query_as(
        "SELECT generation,session,connected,last_seq,lease_until,absolute_until FROM ctm_agent_channel",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    let projection_before: (i64, bool, i64, Option<Vec<u8>>) = sqlx::query_as(
        "SELECT revision,reconciled,snapshot_until,last_digest FROM ctm_grant_projection",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    let ledger_before: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();

    let foreign = message(
        5,
        "tools/call",
        Some("host-session-B"),
        json!({"name":"request_chat_authorization","arguments":{"scopes":["files.read"]}}),
    );
    for _ in 0..2 {
        let r = app.clone().oneshot(request(token, &foreign)).await.unwrap();
        assert_eq!(r.status(), StatusCode::OK);
        assert!(!r.headers().contains_key(header::WWW_AUTHENTICATE));
        let v = json_body(r).await;
        let result = &v["result"]["structuredContent"];
        assert_eq!(v["result"]["isError"], true, "{v}");
        assert_eq!(
            result["error"]["code"], "CHAT_AUTHORIZATION_UNAVAILABLE",
            "{v}"
        );
        assert_eq!(result["error"]["category"], "permission", "{v}");
        assert_eq!(result["error"]["retryable"], false, "{v}");
        assert_eq!(result["requires_local_action"], false, "{v}");
        assert!(result.get("authorization").is_none(), "{v}");
        let text = result.to_string().to_ascii_lowercase();
        for forbidden in [
            "offline",
            "paused",
            "workspace",
            "owner",
            "grant",
            "request_id",
        ] {
            assert!(
                !text.contains(forbidden),
                "foreign response leaked {forbidden}: {v}"
            );
        }
    }

    let channel_after: (i64, Option<Uuid>, bool, i64, i64, i64) = sqlx::query_as(
        "SELECT generation,session,connected,last_seq,lease_until,absolute_until FROM ctm_agent_channel",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    let projection_after: (i64, bool, i64, Option<Vec<u8>>) = sqlx::query_as(
        "SELECT revision,reconciled,snapshot_until,last_digest FROM ctm_grant_projection",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    let ledger_after: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    let projection_rows: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_grant_projection")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();

    assert_eq!(
        channel_before, channel_after,
        "suppression mutated channel state"
    );
    assert_eq!(
        projection_before, projection_after,
        "suppression mutated local authority projection"
    );
    assert_eq!(
        ledger_before, ledger_after,
        "suppression allocated request state"
    );
    assert_eq!(
        projection_rows, 1,
        "foreign request allocated per-chat projection state"
    );
}

#[tokio::test]
async fn offline_owner_authorization_remains_active_without_new_pending_state() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());

    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();

    let ledger_before: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    let owner = message(
        6,
        "tools/call",
        Some("host-session-A"),
        json!({"name":"request_chat_authorization","arguments":{}}),
    );
    let r = app.oneshot(request(token, &owner)).await.unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    assert!(!r.headers().contains_key(header::WWW_AUTHENTICATE));
    let v = json_body(r).await;
    let result = &v["result"]["structuredContent"];
    assert_eq!(v["result"]["isError"], false, "{v}");
    assert_eq!(result["ok"], true, "{v}");
    assert_eq!(result["authorization"]["status"], "active", "{v}");
    assert_eq!(result["execution"], "offline", "{v}");
    assert!(result.get("error").is_none(), "{v}");

    let ledger_after: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(
        ledger_before, ledger_after,
        "owner authorization check allocated request state"
    );
}

#[tokio::test]
async fn online_call_enters_ledger_once_then_stops_before_local_side_effect() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    let call = message(
        7,
        "tools/call",
        Some("host-session-A"),
        json!({"name":"workspace_probe","arguments":{}}),
    );
    for _ in 0..2 {
        let v = json_body(app.clone().oneshot(request(token, &call)).await.unwrap()).await;
        assert_eq!(
            v["result"]["structuredContent"]["error"]["code"],
            "EXECUTION_NOT_CONNECTED"
        );
    }
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(count, 1);
    let state: String = sqlx::query_scalar("SELECT state FROM ctm_request_ledger LIMIT 1")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(state, "cancelled");
    assert_eq!(
        c.assess(&h.a, "files.read").await.unwrap(),
        ProjectionDecision::Eligible
    );
}

#[tokio::test]
async fn legacy_initialize_list_and_tool_call_keep_same_auth_boundary() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    let init = json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"legacy","version":"1"}}});
    let mut r = request(token, &init);
    r.headers_mut().remove("mcp-protocol-version");
    r.headers_mut().remove("mcp-method");
    let r = app.clone().oneshot(r).await.unwrap();
    assert_eq!(r.status(), StatusCode::OK);
    let v = json_body(r).await;
    assert_eq!(v["result"]["protocolVersion"], "2025-06-18");
    let list = json!({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}});
    let mut r = request(token, &list);
    r.headers_mut()
        .insert("mcp-protocol-version", "2025-06-18".parse().unwrap());
    r.headers_mut().remove("mcp-method");
    let v = json_body(app.oneshot(r).await.unwrap()).await;
    assert_eq!(v["result"]["tools"].as_array().unwrap().len(), 49);
}

#[tokio::test]
async fn host_session_never_comes_from_tool_arguments() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    let call = message(
        9,
        "tools/call",
        None,
        json!({"name":"workspace_probe","arguments":{"openai/session":"host-session-A"}}),
    );
    let v = json_body(app.oneshot(request(token, &call)).await.unwrap()).await;
    assert_eq!(
        v["result"]["structuredContent"]["error"]["code"],
        "CHAT_CONTEXT_REQUIRED"
    );
}

#[tokio::test]
async fn observability_separates_auth_permission_availability_and_ingress_without_labels() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let metrics = GatewayObservability::default();
    let app = routes_with_observability(h.f.store.clone(), c.clone(), metrics.clone());

    let discover = message(20, "server/discover", None, json!({}));
    let invalid = app
        .clone()
        .oneshot(request(&"x".repeat(43), &discover))
        .await
        .unwrap();
    assert_eq!(invalid.status(), StatusCode::UNAUTHORIZED);

    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();

    let foreign = message(
        21,
        "tools/call",
        Some("host-session-B"),
        json!({"name":"workspace_probe","arguments":{}}),
    );
    let foreign_response = app.clone().oneshot(request(token, &foreign)).await.unwrap();
    assert_eq!(foreign_response.status(), StatusCode::OK);
    let foreign_json = json_body(foreign_response).await;
    assert_eq!(
        foreign_json["result"]["structuredContent"]["error"]["category"],
        "permission"
    );

    let owner = message(
        22,
        "tools/call",
        Some("host-session-A"),
        json!({"name":"workspace_probe","arguments":{}}),
    );
    let owner_response = app.clone().oneshot(request(token, &owner)).await.unwrap();
    assert_eq!(owner_response.status(), StatusCode::OK);
    let owner_json = json_body(owner_response).await;
    assert_eq!(
        owner_json["result"]["structuredContent"]["error"]["category"],
        "availability"
    );

    let mut bad_host = request(token, &discover);
    bad_host
        .headers_mut()
        .insert(header::HOST, "foreign.invalid".parse().unwrap());
    let rejected = app.oneshot(bad_host).await.unwrap();
    assert_eq!(rejected.status(), StatusCode::FORBIDDEN);

    let snapshot = metrics.snapshot();
    assert_eq!(snapshot.auth_invalid, 1);
    assert_eq!(snapshot.mcp_permission, 1);
    assert_eq!(snapshot.mcp_availability, 1);
    assert_eq!(snapshot.reject_host_or_origin, 1);
    let rendered = serde_json::to_string(&snapshot)
        .unwrap()
        .to_ascii_lowercase();
    assert!(!rendered.contains("host-session"));
    assert!(!rendered.contains("bearer "));
    assert!(!rendered.contains("workspace_probe"));
}

#[tokio::test]
async fn full_catalog_foreign_calls_never_disclose_offline_workspace_or_enter_ledger() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c.clone());
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();
    for (index, spec) in coding_tools_cloud_agent::catalog::tools()
        .iter()
        .enumerate()
    {
        let mut arguments = json!({});
        if let Some(required) = spec.schema["required"].as_array() {
            for key in required.iter().filter_map(Value::as_str) {
                arguments[key] = if spec.schema["properties"][key]["pattern"] == "^[0-9a-f]{32}$" {
                    json!("a".repeat(32))
                } else {
                    json!("placeholder")
                };
            }
        }
        let body = message(
            9000 + index as i64,
            "tools/call",
            Some("host-session-B"),
            json!({"name":spec.name,"arguments":arguments}),
        );
        let result = json_body(app.clone().oneshot(request(token, &body)).await.unwrap()).await;
        let data = &result["result"]["structuredContent"];
        assert_eq!(
            data["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED",
            "{}: {data}",
            spec.name
        );
        for private in ["offline", "device", "workspace_root", "owner", "grant_id"] {
            assert!(!data.to_string().contains(private), "{}: {data}", spec.name);
        }
    }
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
}

#[tokio::test]
async fn offline_authorization_does_not_report_ungranted_requested_scopes_active() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let app = routes(h.f.store.clone(), c.clone());
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    c.disconnect(&session).await.unwrap();
    let body = message(
        9200,
        "tools/call",
        Some("host-session-A"),
        json!({"name":"request_chat_authorization","arguments":{"scopes":["files.read","files.write"]}}),
    );
    let result = json_body(
        app.oneshot(request(pair.access_token.expose(), &body))
            .await
            .unwrap(),
    )
    .await;
    assert_eq!(
        result["result"]["structuredContent"]["error"]["code"],
        "CHAT_SCOPE_REQUIRED"
    );
    assert!(!result["result"]["structuredContent"]
        .to_string()
        .contains("offline"));
}

#[tokio::test]
async fn history_read_validation_is_admitted_read_only_but_repair_requires_write_scope() {
    let (mut h, c) = channel_support::setup().await;
    h.lease.scopes = vec!["history.read".into()];
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let app = routes(h.f.store.clone(), c.clone());
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    for (id, args, expected) in [
        (9300, json!({}), "EXECUTION_NOT_CONNECTED"),
        (9301, json!({"repair":true}), "CHAT_SCOPE_REQUIRED"),
    ] {
        let body = message(
            id,
            "tools/call",
            Some("host-session-A"),
            json!({"name":"history_session_validate","arguments":args}),
        );
        let result = json_body(
            app.clone()
                .oneshot(request(pair.access_token.expose(), &body))
                .await
                .unwrap(),
        )
        .await;
        assert_eq!(
            result["result"]["structuredContent"]["error"]["code"], expected,
            "{result}"
        );
    }
    let rows: Vec<(String, String)> =
        sqlx::query_as("SELECT scope, request_class FROM ctm_request_ledger")
            .fetch_all(&h.f.pool)
            .await
            .unwrap();
    assert_eq!(rows, vec![("history.read".into(), "read_only".into())]);
}

#[path = "mcp_protocol_matrix/mod.rs"]
mod protocol_matrix;
