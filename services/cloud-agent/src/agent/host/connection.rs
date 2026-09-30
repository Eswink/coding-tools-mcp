//! Exact configured WSS, public-key proof, bounded frame codec, no insecure fallback.
use super::super::{config::read_ca, signer::RecoverySigner, AgentConfig, AgentError};
use crate::{
    channel::{ConnectChallenge, ControlMessage, MAX_MESSAGE, SUBPROTOCOL},
    execution::{ExecutionRequest, PeerBinding},
};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use std::{sync::Arc, time::Duration};
use tokio::net::TcpStream;
use tokio_tungstenite::{
    connect_async_tls_with_config,
    tungstenite::{
        self,
        client::IntoClientRequest,
        protocol::{Message, WebSocketConfig},
    },
    Connector, MaybeTlsStream, WebSocketStream,
};
use uuid::Uuid;

pub(super) type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;
#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum Incoming {
    ConnectChallenge {
        challenge: ConnectChallenge,
    },
    Connected {
        heartbeat_seconds: u64,
        lease_seconds: i64,
    },
    HeartbeatAck {
        seq: i64,
    },
    ProjectionChallenge {
        seq: i64,
        gateway_boot: Uuid,
        nonce: String,
        expires_at: i64,
        snapshot_valid_until: i64,
    },
    ProjectionAck {
        seq: i64,
    },
    ExecutionReadyAck {
        seq: i64,
        peer: PeerBinding,
    },
    ExecutionRequest {
        request: ExecutionRequest,
    },
    ExecutionReplyAck {
        seq: i64,
    },
    ApprovalReadyAck {
        seq: i64,
        version: u8,
    },
    ApprovalRequest {
        request: crate::approval::ApprovalRequest,
    },
    ApprovalReplyAck {
        seq: i64,
    },
}
pub(super) async fn connect(
    cfg: &AgentConfig,
    signer: &RecoverySigner,
) -> Result<(Socket, Uuid), AgentError> {
    let connector = if let Some(path) = &cfg.ca_der_file {
        let mut roots = rustls::RootCertStore::empty();
        roots
            .add(rustls::pki_types::CertificateDer::from(read_ca(path)?))
            .map_err(|_| AgentError::Configuration)?;
        let config = rustls::ClientConfig::builder_with_provider(Arc::new(
            rustls::crypto::ring::default_provider(),
        ))
        .with_safe_default_protocol_versions()
        .map_err(|_| AgentError::Tls)?
        .with_root_certificates(roots)
        .with_no_client_auth();
        Some(Connector::Rustls(Arc::new(config)))
    } else {
        None
    };
    let mut request = cfg
        .endpoint()?
        .into_client_request()
        .map_err(|_| AgentError::Configuration)?;
    request.headers_mut().insert(
        "sec-websocket-protocol",
        SUBPROTOCOL.parse().map_err(|_| AgentError::Configuration)?,
    );
    let ws_config = WebSocketConfig::default()
        .max_message_size(Some(MAX_MESSAGE))
        .max_frame_size(Some(MAX_MESSAGE))
        .write_buffer_size(0)
        .max_write_buffer_size(MAX_MESSAGE * 2);
    let (mut socket, response) = tokio::time::timeout(
        Duration::from_secs(10),
        connect_async_tls_with_config(request, Some(ws_config), false, connector),
    )
    .await
    .map_err(|_| AgentError::Transport)?
    .map_err(classify)?;
    if response
        .headers()
        .get_all("sec-websocket-protocol")
        .iter()
        .count()
        != 1
        || response
            .headers()
            .get("sec-websocket-protocol")
            .and_then(|v| v.to_str().ok())
            != Some(SUBPROTOCOL)
    {
        return Err(AgentError::Protocol);
    }
    let Incoming::ConnectChallenge { challenge } = receive(&mut socket).await? else {
        return Err(AgentError::Protocol);
    };
    let (boot, proof) = signer.connect(challenge, super::now()?)?;
    send(&mut socket, &proof).await?;
    match receive(&mut socket).await? {
        Incoming::Connected {
            heartbeat_seconds: 10,
            lease_seconds: 30,
        } => Ok((socket, boot)),
        _ => Err(AgentError::Authentication),
    }
}
pub(super) async fn send(s: &mut Socket, value: &impl Serialize) -> Result<(), AgentError> {
    let text = serde_json::to_string(value).map_err(|_| AgentError::Protocol)?;
    if text.len() > MAX_MESSAGE {
        return Err(AgentError::Protocol);
    }
    tokio::time::timeout(Duration::from_secs(2), s.send(Message::Text(text.into())))
        .await
        .map_err(|_| AgentError::Transport)?
        .map_err(classify)
}
pub(super) async fn receive(s: &mut Socket) -> Result<Incoming, AgentError> {
    tokio::time::timeout(Duration::from_secs(12), async {
        for _ in 0..16 {
            match s
                .next()
                .await
                .ok_or(AgentError::Transport)?
                .map_err(classify)?
            {
                Message::Text(t) if !t.is_empty() && t.len() <= MAX_MESSAGE => {
                    return serde_json::from_str(&t).map_err(|_| AgentError::Protocol)
                }
                Message::Close(_) => return Err(AgentError::Transport),
                Message::Ping(_) | Message::Pong(_) => {
                    tokio::time::timeout(Duration::from_secs(2), s.flush())
                        .await
                        .map_err(|_| AgentError::Transport)?
                        .map_err(classify)?;
                }
                _ => return Err(AgentError::Protocol),
            }
        }
        Err(AgentError::Protocol)
    })
    .await
    .map_err(|_| AgentError::Transport)?
}
pub(super) fn classify(e: tungstenite::Error) -> AgentError {
    match e {
        tungstenite::Error::Io(ref e)
            if matches!(
                e.kind(),
                std::io::ErrorKind::InvalidData | std::io::ErrorKind::InvalidInput
            ) =>
        {
            AgentError::Tls
        }
        tungstenite::Error::Io(_)
        | tungstenite::Error::ConnectionClosed
        | tungstenite::Error::AlreadyClosed => AgentError::Transport,
        tungstenite::Error::Tls(_) => AgentError::Tls,
        tungstenite::Error::Http(r) if [429, 502, 503, 504].contains(&r.status().as_u16()) => {
            AgentError::Transport
        }
        tungstenite::Error::Http(_) => AgentError::Authentication,
        _ => AgentError::Protocol,
    }
}
pub(super) async fn send_control(
    s: &mut Socket,
    seq: &mut i64,
    next_send: &mut tokio::time::Instant,
    message: impl FnOnce(i64) -> ControlMessage,
) -> Result<i64, AgentError> {
    // At most seven control frames in any one-second window, including replies.
    tokio::time::sleep_until(*next_send).await;
    *seq = seq.checked_add(1).ok_or(AgentError::Protocol)?;
    send(s, &message(*seq)).await?;
    *next_send = tokio::time::Instant::now() + Duration::from_millis(160);
    Ok(*seq)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ready() -> serde_json::Value {
        let peer = PeerBinding {
            connector: Uuid::new_v4(),
            device: Uuid::new_v4(),
            device_epoch: 1,
            gateway_boot: Uuid::new_v4(),
            channel_session: Uuid::new_v4(),
            channel_generation: 1,
        };
        serde_json::json!({"type":"execution_ready_ack","seq":4,"peer":peer})
    }
    #[test]
    fn strict_ready_ack_matches_the_actual_controller_wire_shape() {
        assert!(
            serde_json::from_value::<Incoming>(ready()).is_ok(),
            "CONTROLLER_ACK_CODEC_MISMATCH"
        );
    }
    #[test]
    fn unexpected_ready_ack_fields_are_still_rejected() {
        let mut value = ready();
        value["grant"] = serde_json::json!("remote-override");
        assert!(serde_json::from_value::<Incoming>(value).is_err());
    }
}
