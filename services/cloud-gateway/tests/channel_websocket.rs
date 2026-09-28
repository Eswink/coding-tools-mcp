//! Real loopback TCP/WebSocket tests; no external endpoint, workstation or TLS ingress.
#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use channel_support::*;
use coding_tools_cloud_gateway::{
    channel::*,
    projection::{ExecutionState, ProjectionClaims, ProjectionDecision, ProjectionPhase},
};
use futures_util::{SinkExt, StreamExt};
use projection_support::{clock, Harness};
use serde_json::{json, Value};
use std::time::Duration;
use tokio::{
    net::{TcpListener, TcpStream},
    task::JoinHandle,
};
use tokio_tungstenite::{
    tungstenite::{client::IntoClientRequest, Message},
    WebSocketStream,
};
type Client = WebSocketStream<TcpStream>;
struct Server {
    h: Harness,
    c: ChannelController,
    addr: std::net::SocketAddr,
    task: JoinHandle<()>,
}
impl Drop for Server {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Server {
    async fn start() -> Self {
        let (h, c) = setup().await;
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let routes = agent_channel_routes(c.clone());
        let task = tokio::spawn(async move {
            axum::serve(listener, routes).await.unwrap();
        });
        Self { h, c, addr, task }
    }
    async fn socket(
        &self,
        extra: Option<(&str, &str)>,
        query: bool,
    ) -> Result<Client, Box<tokio_tungstenite::tungstenite::Error>> {
        let mut request = format!(
            "ws://{}/coding-tools/agent{}",
            self.addr,
            if query { "?token=canary" } else { "" }
        )
        .into_client_request()
        .unwrap();
        request
            .headers_mut()
            .insert("host", common::identity().authority().parse().unwrap());
        request
            .headers_mut()
            .insert("sec-websocket-protocol", SUBPROTOCOL.parse().unwrap());
        if let Some((k, v)) = extra {
            request.headers_mut().insert(
                tokio_tungstenite::tungstenite::http::HeaderName::from_bytes(k.as_bytes()).unwrap(),
                v.parse().unwrap(),
            );
        }
        let stream = TcpStream::connect(self.addr).await.unwrap();
        tokio_tungstenite::client_async(request, stream)
            .await
            .map_err(Box::new)
            .map(|(s, r)| {
                assert_eq!(r.status(), 101);
                s
            })
    }
    async fn connected(&self) -> Client {
        let mut ws = self.socket(None, false).await.unwrap();
        let challenge: ConnectChallenge =
            serde_json::from_value(read(&mut ws).await["challenge"].clone()).unwrap();
        let proof = sign(
            &claims(&challenge, self.h.device.id, self.h.device.epoch),
            &self.h.key,
        );
        write(&mut ws, &serde_json::to_value(proof).unwrap()).await;
        assert_eq!(read(&mut ws).await["type"], "connected");
        ws
    }
    async fn project(&self, ws: &mut Client, seq: i64, revision: i64) {
        write(ws, &json!({"type":"projection_challenge","seq":seq})).await;
        let r = read(ws).await;
        assert_eq!(r["type"], "projection_challenge");
        let at = clock(&self.h.f).await;
        let claims = ProjectionClaims {
            version: 1,
            issuer: common::identity().issuer(),
            resource: common::identity().resource(),
            connector: common::identity().connector(),
            device: self.h.device.id,
            device_epoch: self.h.device.epoch,
            gateway_boot: serde_json::from_value(r["gateway_boot"].clone()).unwrap(),
            challenge: r["nonce"].as_str().unwrap().into(),
            revision,
            authority_epoch: 1,
            issued_at: at,
            valid_until: r["snapshot_valid_until"].as_i64().unwrap(),
            phase: ProjectionPhase::Active,
            execution: ExecutionState::Online,
            grant: Some(self.h.lease.clone()),
            drained_grant: None,
        };
        let (p, s) = self.h.signed(&claims);
        write(ws,&json!({"type":"projection","seq":seq+1,"proof":{"payload":URL_SAFE_NO_PAD.encode(p),"signature":URL_SAFE_NO_PAD.encode(s)}})).await;
        assert_eq!(read(ws).await["type"], "projection_ack");
    }
}
async fn write(ws: &mut Client, value: &Value) {
    tokio::time::timeout(
        Duration::from_secs(3),
        ws.send(Message::Text(value.to_string().into())),
    )
    .await
    .unwrap()
    .unwrap();
}
async fn read(ws: &mut Client) -> Value {
    let frame = tokio::time::timeout(Duration::from_secs(4), ws.next())
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    let Message::Text(text) = frame else {
        panic!("expected bounded text frame");
    };
    serde_json::from_str(&text).unwrap()
}
async fn closed(ws: &mut Client) {
    let r = tokio::time::timeout(Duration::from_secs(7), ws.next())
        .await
        .expect("socket must close in bounded time");
    assert!(!matches!(r, Some(Ok(Message::Text(_)))));
}
#[tokio::test]
async fn websocket_authenticated_heartbeat_and_projection_roundtrip() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    write(&mut w, &json!({"type":"heartbeat","seq":1})).await;
    assert_eq!(read(&mut w).await["type"], "heartbeat_ack");
    s.project(&mut w, 2, 1).await;
    assert_eq!(
        s.c.assess(&s.h.a, "files.read").await.unwrap(),
        ProjectionDecision::Eligible
    );
    assert_eq!(
        s.c.assess(&s.h.b, "files.read").await.unwrap(),
        ProjectionDecision::AuthorizationUnavailable
    );
    w.close(None).await.unwrap();
}
#[tokio::test]
async fn websocket_rejects_browser_origin() {
    let s = Server::start().await;
    assert!(s
        .socket(Some(("origin", common::identity().origin())), false)
        .await
        .is_err());
}
#[tokio::test]
async fn websocket_rejects_cookie_authentication() {
    let s = Server::start().await;
    assert!(s
        .socket(Some(("cookie", "session=canary")), false)
        .await
        .is_err());
}
#[tokio::test]
async fn websocket_rejects_oauth_in_agent_handshake() {
    let s = Server::start().await;
    assert!(s
        .socket(Some(("authorization", "Bearer canary")), false)
        .await
        .is_err());
}
#[tokio::test]
async fn websocket_rejects_query_credentials() {
    let s = Server::start().await;
    assert!(s.socket(None, true).await.is_err());
}
#[tokio::test]
async fn websocket_rejects_foreign_host() {
    let s = Server::start().await;
    assert!(s
        .socket(Some(("host", "foreign.invalid")), false)
        .await
        .is_err());
}
#[tokio::test]
async fn websocket_requires_exact_protocol() {
    let s = Server::start().await;
    assert!(s
        .socket(Some(("sec-websocket-protocol", "unrecognized")), false)
        .await
        .is_err());
}
#[tokio::test]
async fn captured_connect_proof_fails_on_other_socket() {
    let s = Server::start().await;
    let mut a = s.socket(None, false).await.unwrap();
    let ca: ConnectChallenge =
        serde_json::from_value(read(&mut a).await["challenge"].clone()).unwrap();
    let proof = sign(&claims(&ca, s.h.device.id, 1), &s.h.key);
    let mut b = s.socket(None, false).await.unwrap();
    read(&mut b).await;
    write(&mut b, &serde_json::to_value(proof).unwrap()).await;
    closed(&mut b).await;
}
#[tokio::test]
async fn control_before_authentication_is_rejected() {
    let s = Server::start().await;
    let mut w = s.socket(None, false).await.unwrap();
    read(&mut w).await;
    write(&mut w, &json!({"type":"heartbeat","seq":1})).await;
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_stale_generation_does_not_close_replacement() {
    let s = Server::start().await;
    let mut a = s.connected().await;
    s.project(&mut a, 1, 1).await;
    let mut b = s.connected().await;
    s.project(&mut b, 1, 2).await;
    write(&mut a, &json!({"type":"heartbeat","seq":3})).await;
    closed(&mut a).await;
    write(&mut b, &json!({"type":"heartbeat","seq":3})).await;
    assert_eq!(read(&mut b).await["type"], "heartbeat_ack");
    assert_eq!(
        s.c.assess(&s.h.a, "files.read").await.unwrap(),
        ProjectionDecision::Eligible
    );
}
#[tokio::test]
async fn websocket_revoked_device_cannot_heartbeat() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    s.h.f.store.revoke_device(s.h.device.id).await.unwrap();
    write(&mut w, &json!({"type":"heartbeat","seq":1})).await;
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_oversized_message_is_rejected() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    let _ = w
        .send(Message::Text("x".repeat(MAX_MESSAGE + 1).into()))
        .await;
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_unknown_execution_action_is_rejected() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    write(
        &mut w,
        &json!({"type":"exec_command","seq":1,"cmd":"canary"}),
    )
    .await;
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_missing_authentication_times_out() {
    let s = Server::start().await;
    let mut w = s.socket(None, false).await.unwrap();
    read(&mut w).await;
    let r = tokio::time::timeout(Duration::from_secs(12), w.next())
        .await
        .expect("auth deadline enforced");
    assert!(!matches!(r, Some(Ok(Message::Text(_)))));
}
#[tokio::test]
async fn websocket_binary_control_is_rejected() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    w.send(Message::Binary(vec![1, 2].into())).await.unwrap();
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_expired_presence_cannot_be_renewed() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    sqlx::query("UPDATE ctm_agent_channel SET lease_until=0")
        .execute(&s.h.f.pool)
        .await
        .unwrap();
    write(&mut w, &json!({"type":"heartbeat","seq":1})).await;
    closed(&mut w).await;
}
#[tokio::test]
async fn websocket_upgrade_pool_is_bounded() {
    let s = Server::start().await;
    let mut sockets = Vec::new();
    for _ in 0..8 {
        let mut w = s.socket(None, false).await.unwrap();
        read(&mut w).await;
        sockets.push(w);
    }
    tokio::time::sleep(Duration::from_millis(1100)).await;
    assert!(s.socket(None, false).await.is_err());
}

#[tokio::test]
async fn websocket_application_frame_rate_is_bounded() {
    let s = Server::start().await;
    let mut w = s.connected().await;
    for seq in 1..=8 {
        write(&mut w, &json!({"type":"heartbeat","seq":seq})).await;
        assert_eq!(read(&mut w).await["type"], "heartbeat_ack");
    }
    write(&mut w, &json!({"type":"heartbeat","seq":9})).await;
    closed(&mut w).await;
}
