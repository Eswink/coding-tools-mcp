//! These exercise the shipped Rust router, OAuth store and PostgreSQL ledger.
//! No JavaScript prototype is imported or treated as production evidence.
use super::*;
use axum::http::HeaderValue;
use coding_tools_cloud_gateway::mcp::VERSIONS;

const VERSION: &str = "io.modelcontextprotocol/protocolVersion";
const CAPS: &str = "io.modelcontextprotocol/clientCapabilities";
const INFO: &str = "io.modelcontextprotocol/serverInfo";

fn wire(version: &str, method: &str, mut params: Value) -> Value {
    if version == MODERN {
        params["_meta"] = meta(None);
    }
    json!({"jsonrpc":"2.0","id":"protocol-matrix","method":method,"params":params})
}
fn transport(token: &str, version: &str, body: &Value) -> Request<Body> {
    let mut request = Request::builder()
        .method("POST")
        .uri(identity().resource_path())
        .header("host", identity().authority())
        .header(header::AUTHORIZATION, format!("Bearer {token}"))
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::ACCEPT, "application/json, text/event-stream")
        .header("mcp-protocol-version", version);
    if version == MODERN {
        request = request.header(
            "mcp-method",
            HeaderValue::from_str(body["method"].as_str().unwrap_or("tools/list"))
                .unwrap_or_else(|_| HeaderValue::from_static("tools/list")),
        );
        if body["method"] == "tools/call" {
            request = request.header(
                "mcp-name",
                body["params"]["name"].as_str().unwrap_or("auth_status"),
            );
        }
    }
    request.body(Body::from(body.to_string())).unwrap()
}
async fn checked(response: axum::response::Response, status: u16) -> Value {
    assert_eq!(response.status().as_u16(), status);
    assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
    assert_eq!(
        response.headers()[header::X_CONTENT_TYPE_OPTIONS],
        "nosniff"
    );
    assert!(!response.headers().contains_key("mcp-session-id"));
    assert!(!response.headers().contains_key(header::WWW_AUTHENTICATE));
    json_body(response).await
}
async fn rejected(app: &axum::Router, request: Request<Body>, status: u16, code: i64, id: bool) {
    let result = checked(app.clone().oneshot(request).await.unwrap(), status).await;
    assert_eq!(result["jsonrpc"], "2.0", "{result}");
    assert_eq!(result["error"]["code"], code, "{result}");
    assert!(result.get("result").is_none(), "{result}");
    assert_eq!(result.get("id").is_some(), id, "{result}");
    if id {
        assert_eq!(result["id"], "protocol-matrix", "{result}");
    }
}
async fn ledger_empty(h: &projection_support::Harness) {
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(
        count, 0,
        "protocol rejection/control plane must not admit execution"
    );
}
fn completion(result: &Value, version: &str) {
    if version == MODERN {
        assert_eq!(result["resultType"], "complete", "{result}");
        assert_eq!(result["_meta"][INFO]["name"], "coding-tools-cloud-gateway");
    } else {
        assert!(result.get("resultType").is_none(), "{result}");
        assert!(result.get("_meta").is_none(), "{result}");
    }
}

#[tokio::test]
async fn production_all_versions_handshake_catalog_and_tool_error_envelopes() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    for version in VERSIONS {
        let body = if version == MODERN {
            wire(version, "server/discover", json!({}))
        } else {
            wire(
                version,
                "initialize",
                json!({"protocolVersion":version,"capabilities":{},"clientInfo":{"name":"matrix","version":"1"}}),
            )
        };
        let mut request = transport(token, version, &body);
        if version != MODERN {
            request.headers_mut().remove("mcp-protocol-version");
        }
        let result = checked(app.clone().oneshot(request).await.unwrap(), 200).await;
        assert_eq!(result["id"], "protocol-matrix");
        completion(&result["result"], version);
        if version == MODERN {
            assert_eq!(result["result"]["supportedVersions"], json!(VERSIONS));
            assert!(result["result"].get("protocolVersion").is_none());
            assert!(result["result"].get("serverInfo").is_none());
        } else {
            assert_eq!(result["result"]["protocolVersion"], version);
            assert_eq!(
                result["result"]["capabilities"]["tools"]["listChanged"],
                false
            );
        }
        let list = wire(version, "tools/list", json!({}));
        let mut request = transport(token, version, &list);
        request
            .headers_mut()
            .insert("mcp-session-id", HeaderValue::from_static("not-authority"));
        let result = checked(app.clone().oneshot(request).await.unwrap(), 200).await;
        completion(&result["result"], version);
        assert_eq!(
            result["result"]["tools"],
            json!(coding_tools_cloud_gateway::mcp::catalog())
        );
        let call = wire(
            version,
            "tools/call",
            json!({"name":"auth_status","arguments":{}}),
        );
        let result = checked(
            app.clone()
                .oneshot(transport(token, version, &call))
                .await
                .unwrap(),
            200,
        )
        .await;
        completion(&result["result"], version);
        assert_eq!(result["result"]["isError"], true);
        assert_eq!(
            result["result"]["structuredContent"]["error"]["code"],
            "CHAT_CONTEXT_REQUIRED"
        );
        let text: Value =
            serde_json::from_str(result["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
        assert_eq!(text, result["result"]["structuredContent"]);
    }
    ledger_empty(&h).await;
}

#[tokio::test]
async fn production_legacy_notifications_have_no_response_body() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let app = routes(h.f.store.clone(), c);
    // Both pinned Streamable HTTP specifications require 202 with no body for
    // accepted notifications, not a JSON object or fabricated RPC response.
    let mut accepted = Vec::new();
    for version in &VERSIONS[1..] {
        let mut body = wire(version, "notifications/initialized", json!({}));
        body.as_object_mut().unwrap().remove("id");
        let response = app
            .clone()
            .oneshot(transport(pair.access_token.expose(), version, &body))
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
        let bytes = response.into_body().collect().await.unwrap().to_bytes();
        accepted.push((*version, bytes));
    }
    assert!(
        accepted.iter().all(|(_, bytes)| bytes.is_empty()),
        "accepted notification bodies: {accepted:?}"
    );
    ledger_empty(&h).await;
}

#[tokio::test]
async fn production_modern_header_capability_and_name_matrix_rejects_before_admission() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    let call = wire(
        MODERN,
        "tools/call",
        json!({"name":"auth_status","arguments":{}}),
    );
    for name in ["mcp-protocol-version", "mcp-method", "mcp-name"] {
        let mut r = transport(token, MODERN, &call);
        r.headers_mut().remove(name);
        rejected(&app, r, 400, -32020, true).await;
        let mut r = transport(token, MODERN, &call);
        let value = r.headers()[name].clone();
        r.headers_mut().append(name, value);
        rejected(&app, r, 400, -32020, false).await;
    }
    for (name, value) in [
        ("mcp-method", "tools/list"),
        ("mcp-name", "workspace_probe"),
        ("mcp-name", "=?base64?%%%?="),
        ("mcp-name", "=?base64?/w==?="),
        ("mcp-name", "=?base64?Zh==?="),
    ] {
        let mut r = transport(token, MODERN, &call);
        r.headers_mut()
            .insert(name, HeaderValue::from_str(value).unwrap());
        rejected(&app, r, 400, -32020, true).await;
    }
    let mut r = transport(token, MODERN, &wire(MODERN, "tools/list", json!({})));
    r.headers_mut()
        .insert("mcp-name", HeaderValue::from_static("auth_status"));
    rejected(&app, r, 400, -32020, true).await;
    let discovery = wire(MODERN, "server/discover", json!({}));
    checked(
        app.clone()
            .oneshot(transport(token, MODERN, &discovery))
            .await
            .unwrap(),
        200,
    )
    .await;
    for bad in [Value::Null, json!([]), json!(true), json!("inherited")] {
        let mut body = call.clone();
        body["params"]["_meta"][CAPS] = bad;
        rejected(&app, transport(token, MODERN, &body), 400, -32602, true).await;
    }
    let mut body = call.clone();
    body["params"]["_meta"]
        .as_object_mut()
        .unwrap()
        .remove(CAPS);
    rejected(&app, transport(token, MODERN, &body), 400, -32602, true).await;
    for bad in [
        Value::Null,
        json!([]),
        json!({}),
        json!({"name":"x","version":1}),
    ] {
        let mut body = call.clone();
        body["params"]["_meta"]["io.modelcontextprotocol/clientInfo"] = bad;
        rejected(&app, transport(token, MODERN, &body), 400, -32602, true).await;
    }
    let mut body = call.clone();
    body["params"]["_meta"][VERSION] = json!(VERSIONS[1]);
    rejected(&app, transport(token, MODERN, &body), 400, -32020, true).await;
    let mut r = transport(token, MODERN, &call);
    r.headers_mut().insert(
        "mcp-name",
        HeaderValue::from_static("=?base64?YXV0aF9zdGF0dXM=?="),
    );
    let out = checked(app.oneshot(r).await.unwrap(), 200).await;
    assert_eq!(
        out["result"]["structuredContent"]["error"]["code"],
        "CHAT_CONTEXT_REQUIRED"
    );
    ledger_empty(&h).await;
}

#[tokio::test]
async fn production_legacy_negotiation_and_mixed_era_matrix() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    for version in &VERSIONS[1..] {
        let init = wire(
            version,
            "initialize",
            json!({"protocolVersion":version,"capabilities":{},"clientInfo":{"name":"matrix","version":"1"}}),
        );
        for (field, bad) in [
            ("capabilities", Value::Null),
            ("capabilities", json!([])),
            ("clientInfo", json!({})),
            ("clientInfo", json!({"name":1,"version":"1"})),
        ] {
            let mut body = init.clone();
            body["params"][field] = bad;
            rejected(&app, transport(token, version, &body), 400, -32602, true).await;
        }
        let mut mismatch = init.clone();
        mismatch["params"]["protocolVersion"] = json!(MODERN);
        rejected(
            &app,
            transport(token, version, &mismatch),
            400,
            -32020,
            true,
        )
        .await;
        for key in [VERSION, CAPS] {
            let body = wire(
                version,
                "tools/list",
                json!({"_meta":{key: if key == CAPS { json!({}) } else { json!(MODERN) }}}),
            );
            rejected(&app, transport(token, version, &body), 400, -32020, true).await;
        }
        let list = wire(version, "tools/list", json!({}));
        let mut r = transport(token, version, &list);
        r.headers_mut().remove("mcp-protocol-version");
        rejected(&app, r, 400, -32020, true).await;
    }
    ledger_empty(&h).await;
}

#[tokio::test]
async fn production_methods_versions_and_notifications_are_not_tool_results() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    for version in VERSIONS {
        for method in [
            "unknown/method",
            if version == MODERN {
                "initialize"
            } else {
                "server/discover"
            },
        ] {
            let body = wire(version, method, json!({}));
            rejected(
                &app,
                transport(token, version, &body),
                if version == MODERN { 404 } else { 400 },
                -32601,
                true,
            )
            .await;
        }
        let ping = wire(version, "ping", json!({}));
        if version == MODERN {
            rejected(&app, transport(token, version, &ping), 404, -32601, true).await;
        } else {
            let out = checked(
                app.clone()
                    .oneshot(transport(token, version, &ping))
                    .await
                    .unwrap(),
                200,
            )
            .await;
            assert_eq!(out["result"], json!({}));
        }
        let mut body = wire(version, "tools/call", json!({"name":"auth_status"}));
        body.as_object_mut().unwrap().remove("id");
        rejected(&app, transport(token, version, &body), 400, -32600, false).await;
        let cursor = wire(version, "tools/list", json!({"cursor":"unsupported"}));
        rejected(&app, transport(token, version, &cursor), 400, -32602, true).await;
    }
    let body = wire(MODERN, "tools/list", json!({}));
    let requested = "9".repeat(200);
    let r = checked(
        app.clone()
            .oneshot(transport(token, &requested, &body))
            .await
            .unwrap(),
        400,
    )
    .await;
    assert_eq!(r["error"]["code"], -32022);
    assert_eq!(r["error"]["data"]["supported"], json!(VERSIONS));
    assert_eq!(r["error"]["data"]["requested"], "9".repeat(128));
    ledger_empty(&h).await;
}

#[tokio::test]
async fn production_invalid_envelopes_are_bounded_rpc_errors_without_ids() {
    let (h, c) = channel_support::setup().await;
    let pair = h.f.tokens(Uuid::from_u128(8)).await;
    let token = pair.access_token.expose();
    let app = routes(h.f.store.clone(), c);
    for version in VERSIONS {
        let good = wire(version, "tools/list", json!({}));
        let mut invalid = vec![Value::Null, json!([]), json!(1)];
        for id in [
            Value::Null,
            json!(true),
            json!(1.5),
            json!(9_007_199_254_740_992i64),
            json!("x".repeat(257)),
            json!("bad\nid"),
        ] {
            let mut body = good.clone();
            body["id"] = id;
            invalid.push(body);
        }
        for (field, bad) in [
            ("params", json!([])),
            ("method", json!("")),
            ("method", json!("x".repeat(129))),
            ("method", json!("bad\nmethod")),
            ("jsonrpc", json!("1.0")),
            ("unexpected", json!(true)),
        ] {
            let mut body = good.clone();
            body[field] = bad;
            invalid.push(body);
        }
        for body in invalid {
            rejected(&app, transport(token, version, &body), 400, -32600, false).await;
        }
        for raw in [b"{".as_slice(), &[0xff]] {
            let mut r = transport(token, version, &good);
            *r.body_mut() = Body::from(raw.to_vec());
            rejected(&app, r, 400, -32700, false).await;
        }
        for id in [
            json!(0),
            json!(9_007_199_254_740_991i64),
            json!(-9_007_199_254_740_991i64),
            json!("x".repeat(256)),
        ] {
            let mut body = good.clone();
            body["id"] = id.clone();
            let result = checked(
                app.clone()
                    .oneshot(transport(token, version, &body))
                    .await
                    .unwrap(),
                200,
            )
            .await;
            assert_eq!(result["id"], id);
        }
    }
    ledger_empty(&h).await;
}
