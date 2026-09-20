use std::env;
use std::net::SocketAddr;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::extract::Request;
use axum::http::header::{HOST, ORIGIN};
use axum::http::uri::Authority;
use axum::response::IntoResponse;
use axum::routing::any;
use axum::{Json, Router};
use serde_json::json;

fn parse_port() -> u16 {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if let Some(value) = arg.strip_prefix("--port=") {
            return value.parse().expect("invalid --port");
        }
        if arg == "--port" {
            return args
                .next()
                .expect("missing value after --port")
                .parse()
                .expect("invalid --port");
        }
    }
    28768
}

fn sanitize_authority(value: &str) -> Option<String> {
    Authority::from_maybe_shared(value.trim().to_owned())
        .ok()
        .map(|authority| authority.host().trim_matches(['[', ']']).to_ascii_lowercase())
}

fn header_host(request: &Request) -> Option<String> {
    request
        .headers()
        .get(HOST)
        .and_then(|value| value.to_str().ok())
        .and_then(sanitize_authority)
}

async fn probe(request: Request) -> impl IntoResponse {
    let uri_authority_host = request
        .uri()
        .authority()
        .map(|authority| authority.host().trim_matches(['[', ']']).to_ascii_lowercase());
    let host = header_host(&request);
    let unix_seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);

    // Evidence is intentionally metadata-only. Never print request headers,
    // query strings, authorization, cookies, body bytes, workspace paths,
    // session bindings, or forwarded host values.
    let record = json!({
        "timestamp_unix": unix_seconds,
        "http_version": format!("{:?}", request.version()),
        "method": request.method().as_str(),
        "uri_authority_host": uri_authority_host,
        "host_header_host": host,
        "origin_present": request.headers().contains_key(ORIGIN),
        "x_forwarded_host_present": request.headers().contains_key("x-forwarded-host"),
        "forwarded_present": request.headers().contains_key("forwarded"),
        "x_forwarded_proto_present": request.headers().contains_key("x-forwarded-proto"),
        "cf_ray_present": request.headers().contains_key("cf-ray"),
    });
    println!("{}", record);

    Json(json!({
        "ok": true,
        "probe": "tunnel-header-topology",
    }))
}

#[tokio::main]
async fn main() {
    let port = parse_port();
    let address: SocketAddr = ([127, 0, 0, 1], port).into();
    let listener = tokio::net::TcpListener::bind(address)
        .await
        .expect("bind tunnel header probe");
    eprintln!(
        "tunnel-header-topology probe listening on http://127.0.0.1:{port}; output is sanitized JSONL"
    );

    axum::serve(listener, Router::new().route("/{*path}", any(probe)))
        .await
        .expect("serve tunnel header probe");
}
