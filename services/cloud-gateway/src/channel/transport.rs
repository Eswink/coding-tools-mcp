//! Opt-in native-agent router. Not mounted by the identity-only service.
use super::{protocol::*, ChannelController, ChannelSession};
use crate::{IdentityError, Result};
use axum::{
    extract::{
        ws::{Message, WebSocket},
        State, WebSocketUpgrade,
    },
    http::{header, HeaderMap, StatusCode, Uri},
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use serde::Serialize;
use serde_json::json;
use std::{
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tokio::sync::{watch, Semaphore};

#[derive(Clone)]
struct TransportState {
    control: ChannelController,
    connections: Arc<Semaphore>,
    attempts: Arc<Mutex<(Instant, u32)>>,
    stop: Arc<watch::Sender<bool>>,
}
/// The caller must enforce loopback-only binding behind trusted TLS/WSS ingress,
/// request-header deadlines and graceful socket shutdown. No private signing key is accepted.
pub fn agent_channel_routes(control: ChannelController) -> Router {
    managed_agent_channel_routes(control).0
}

/// Explicit shutdown ownership for upgraded sockets; HTTP connection tasks alone do not own them.
pub struct ChannelShutdown {
    stop: Arc<watch::Sender<bool>>,
    connections: Arc<Semaphore>,
    control: ChannelController,
}
impl ChannelShutdown {
    pub fn signal(&self) {
        self.stop.send_replace(true);
    }
    pub async fn drain(&self) -> Result<()> {
        self.signal();
        let _permits = tokio::time::timeout(
            Duration::from_secs(6),
            self.connections.clone().acquire_many_owned(8),
        )
        .await
        .map_err(|_| IdentityError::InvalidRequest)?
        .map_err(|_| IdentityError::InvalidRequest)?;
        tokio::time::timeout(Duration::from_secs(3), self.control.deactivate())
            .await
            .map_err(|_| IdentityError::InvalidRequest)?
    }
}
pub fn managed_agent_channel_routes(control: ChannelController) -> (Router, ChannelShutdown) {
    let path = format!("{}/agent", control.identity().prefix());
    let (stop, _) = watch::channel(false);
    let stop = Arc::new(stop);
    let connections = Arc::new(Semaphore::new(8));
    let handle = ChannelShutdown {
        stop: stop.clone(),
        connections: connections.clone(),
        control: control.clone(),
    };
    let state = TransportState {
        control,
        stop,
        connections,
        attempts: Arc::new(Mutex::new((Instant::now(), 0))),
    };
    (
        Router::new().route(&path, get(upgrade)).with_state(state),
        handle,
    )
}
fn allowed_headers(headers: &HeaderMap, uri: &Uri, authority: &str) -> bool {
    if uri.query().is_some()
        || headers.get_all(header::HOST).iter().count() != 1
        || headers.get(header::HOST).and_then(|v| v.to_str().ok()) != Some(authority)
        || headers.contains_key(header::ORIGIN)
        || headers.contains_key(header::COOKIE)
        || headers.contains_key(header::AUTHORIZATION)
        || headers.get_all("sec-websocket-protocol").iter().count() != 1
        || headers
            .get("sec-websocket-protocol")
            .and_then(|v| v.to_str().ok())
            != Some(SUBPROTOCOL)
    {
        return false;
    }
    [
        "sec-websocket-key",
        "sec-websocket-version",
        "upgrade",
        "connection",
    ]
    .iter()
    .all(|name| headers.get_all(*name).iter().count() == 1)
}
async fn upgrade(
    State(s): State<TransportState>,
    headers: HeaderMap,
    uri: Uri,
    ws: WebSocketUpgrade,
) -> Response {
    if *s.stop.borrow() || !allowed_headers(&headers, &uri, s.control.identity().authority()) {
        return denied(StatusCode::FORBIDDEN);
    }
    let admitted = s.attempts.lock().is_ok_and(|mut b| {
        if b.0.elapsed() >= Duration::from_secs(1) {
            *b = (Instant::now(), 0);
        }
        if b.1 >= 8 {
            false
        } else {
            b.1 += 1;
            true
        }
    });
    if !admitted {
        return denied(StatusCode::TOO_MANY_REQUESTS);
    }
    let Ok(permit) = s.connections.clone().try_acquire_owned() else {
        return denied(StatusCode::TOO_MANY_REQUESTS);
    };
    let Ok(pending) = s.control.pending() else {
        return denied(StatusCode::SERVICE_UNAVAILABLE);
    };
    ws.protocols([SUBPROTOCOL])
        .max_frame_size(MAX_MESSAGE)
        .max_message_size(MAX_MESSAGE)
        .write_buffer_size(0)
        .max_write_buffer_size(MAX_MESSAGE * 2)
        .on_upgrade(move |mut socket| async move {
            let _permit = permit;
            let mut session = None;
            let mut stop = s.stop.subscribe();
            if !*stop.borrow() {
                tokio::select! {
                    biased;
                    _ = stop.changed() => {},
                    _ = run_socket(&s.control, &mut socket, pending, &mut session) => {},
                }
            }
            if let Some(session) = session {
                let _ =
                    tokio::time::timeout(Duration::from_secs(3), s.control.disconnect(&session))
                        .await;
            }
            let _ = tokio::time::timeout(Duration::from_secs(2), socket.send(Message::Close(None)))
                .await;
        })
}
fn denied(status: StatusCode) -> Response {
    (
        status,
        [(header::CACHE_CONTROL, "no-store")],
        "agent_connection_rejected",
    )
        .into_response()
}
async fn send(socket: &mut WebSocket, value: &impl Serialize) -> Result<()> {
    let text = serde_json::to_string(value).map_err(|_| IdentityError::InvalidRequest)?;
    if text.len() > MAX_MESSAGE {
        return Err(IdentityError::InvalidRequest);
    }
    tokio::time::timeout(
        Duration::from_secs(2),
        socket.send(Message::Text(text.into())),
    )
    .await
    .map_err(|_| IdentityError::InvalidRequest)?
    .map_err(|_| IdentityError::InvalidRequest)
}
async fn run_socket(
    c: &ChannelController,
    socket: &mut WebSocket,
    pending: super::PendingConnection,
    session: &mut Option<ChannelSession>,
) -> Result<()> {
    send(
        socket,
        &json!({"type":"connect_challenge","challenge":pending.challenge()}),
    )
    .await?;
    let frame = tokio::time::timeout(Duration::from_secs(AUTH_SECONDS as u64), socket.recv())
        .await
        .map_err(|_| IdentityError::InvalidProof)?
        .ok_or(IdentityError::InvalidProof)?
        .map_err(|_| IdentityError::InvalidProof)?;
    let Message::Text(text) = frame else {
        return Err(IdentityError::InvalidProof);
    };
    let proof: SignedPayload =
        serde_json::from_str(&text).map_err(|_| IdentityError::InvalidProof)?;
    let s = tokio::time::timeout(Duration::from_secs(3), c.authenticate(pending, &proof))
        .await
        .map_err(|_| IdentityError::InvalidProof)??;
    *session = Some(s.clone());
    send(
        socket,
        &json!({"type":"connected","heartbeat_seconds":10,"lease_seconds":LEASE_SECONDS}),
    )
    .await?;
    let mut budget = (Instant::now(), 0_u32);
    let mut checks = tokio::time::interval(Duration::from_secs(5));
    checks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let end = tokio::time::sleep(Duration::from_secs(MAX_AGE_SECONDS as u64));
    tokio::pin!(end);
    loop {
        tokio::select! {
            _ = &mut end => return Err(IdentityError::InvalidProof),
            _ = checks.tick() => {
                tokio::time::timeout(Duration::from_secs(3),c.validate(&s)).await.map_err(|_|IdentityError::InvalidProof)??;
            },
            frame=socket.recv()=> {
                let frame=frame.ok_or(IdentityError::InvalidRequest)?.map_err(|_|IdentityError::InvalidRequest)?;
                if budget.0.elapsed()>=Duration::from_secs(1){budget=(Instant::now(),0);}
                budget.1+=1;
                if budget.1>8{return Err(IdentityError::InvalidRequest);}
                match frame {
                    Message::Close(_)=>return Ok(()),
                    Message::Ping(_) | Message::Pong(_)=>{}, // Not an application heartbeat, no renewal.
                    Message::Text(text)=>{
                        let msg:ControlMessage=serde_json::from_str(&text).map_err(|_|IdentityError::InvalidRequest)?;
                        let reply=tokio::time::timeout(Duration::from_secs(3),c.control(&s,msg)).await
                            .map_err(|_|IdentityError::InvalidProof)??;
                        send(socket,&reply).await?;
                    },
                    _=>return Err(IdentityError::InvalidRequest),
                }
            }
        }
    }
}
