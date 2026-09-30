//! Shipped Rust HTTP -> authenticated HostAgent WSS -> actual fixture file read.
//! FileHost remains an explicit test host, not native GUI approval evidence.
use super::*;
use axum::{
    body::Body,
    http::{header, Request},
};
use coding_tools_cloud_gateway::mcp::{MODERN, VERSIONS};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

async fn call_version(h: &Harness, version: &str, id: i64, chat: &str) -> Value {
    let mut meta = json!({"openai/session":chat});
    if version == MODERN {
        meta["io.modelcontextprotocol/protocolVersion"] = json!(MODERN);
        meta["io.modelcontextprotocol/clientCapabilities"] = json!({});
    }
    let body = json!({"jsonrpc":"2.0","id":id,"method":"tools/call","params":{"name":"workspace_probe","arguments":{},"_meta":meta}});
    let mut request = Request::builder()
        .method("POST")
        .uri(h.identity.resource_path())
        .header("host", h.identity.authority())
        .header(header::AUTHORIZATION, format!("Bearer {}", h.token))
        .header(header::CONTENT_TYPE, "application/json")
        .header(header::ACCEPT, "application/json, text/event-stream")
        .header("mcp-protocol-version", version);
    if version == MODERN {
        request = request
            .header("mcp-method", "tools/call")
            .header("mcp-name", "workspace_probe");
    }
    let response = h
        .app
        .clone()
        .oneshot(request.body(Body::from(body.to_string())).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    assert!(!response.headers().contains_key(header::WWW_AUTHENTICATE));
    assert!(!response.headers().contains_key("mcp-session-id"));
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    let value: Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(value["jsonrpc"], "2.0");
    assert_eq!(value["id"], id);
    assert!(value.get("error").is_none(), "{value}");
    if version == MODERN {
        assert_eq!(value["result"]["resultType"], "complete");
        assert_eq!(
            value["result"]["_meta"]["io.modelcontextprotocol/serverInfo"]["name"],
            "coding-tools-cloud-gateway"
        );
    } else {
        assert!(value["result"].get("resultType").is_none());
        assert!(value["result"].get("_meta").is_none());
    }
    let text: Value =
        serde_json::from_str(value["result"]["content"][0]["text"].as_str().unwrap()).unwrap();
    assert_eq!(text, value["result"]["structuredContent"]);
    value["result"].clone()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn every_protocol_version_reads_real_file_once_and_preserves_chat_authority() {
    let h = Harness::start().await;
    for (index, version) in VERSIONS.iter().enumerate() {
        let id = 1900 + index as i64;
        let foreign = call_version(&h, version, id + 100, "foreign").await;
        assert_eq!(foreign["isError"], true, "{version}: {foreign}");
        assert_eq!(
            foreign["structuredContent"]["error"]["code"],
            "CHAT_AUTHORIZATION_REQUIRED"
        );
        assert!(!foreign.to_string().contains("actual-local-file-canary"));
        assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), index);
        let result = call_version(&h, version, id, "host-session-A").await;
        assert_eq!(result["isError"], false, "{version}: {result}");
        assert_eq!(
            result["structuredContent"]["ok"], true,
            "{version}: {result}"
        );
        assert_eq!(
            result["structuredContent"]["content"],
            "actual-local-file-canary"
        );
        assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), index + 1);
        // Replaying the same ID through another wire era must not fork authority
        // or repeat a completed local effect.
        let replay = call_version(
            &h,
            VERSIONS[(index + 1) % VERSIONS.len()],
            id,
            "host-session-A",
        )
        .await;
        assert_eq!(replay["isError"], true, "{version}: {replay}");
        assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), index + 1);
    }
    let rows: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.pool)
        .await
        .unwrap();
    assert_eq!(
        rows, 3,
        "only the three locally authorized requests enter the ledger"
    );
}
