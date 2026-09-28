use super::{
    config::read_ca,
    journal::RevisionJournal,
    signer::RecoverySigner,
    wire::{unix_now, ServerMessage, SnapshotChallenge},
    AgentConfig, AgentError, Result,
};
use crate::channel::{ControlMessage, MAX_MESSAGE, SUBPROTOCOL};
use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use std::{
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::{net::TcpStream, sync::watch};
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

type Socket = WebSocketStream<MaybeTlsStream<TcpStream>>;
pub(super) async fn drive(
    cfg: &AgentConfig,
    signer: &RecoverySigner,
    journal: &mut RevisionJournal,
    mut stop: watch::Receiver<bool>,
) -> Result<()> {
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
    let end = tokio::time::sleep(Duration::from_secs(cfg.run_seconds));
    tokio::pin!(end);
    let mut attempts = 0u32;
    loop {
        if *stop.borrow() {
            return Ok(());
        }
        let result = tokio::select! {
            biased;
            _=stop.changed()=>return Ok(()),
            _=&mut end=>return Ok(()),
            r=one_session(cfg,signer,journal,connector.clone())=>r,
        };
        if result != Err(AgentError::Transport) {
            return result;
        }
        attempts += 1;
        if attempts > 8 {
            return Err(AgentError::Exhausted);
        }
        let delay = backoff(attempts)?;
        println!(
            "{}",
            serde_json::json!({"event":"agent_reconnecting","attempt":attempts})
        );
        tokio::select! {biased;_ = stop.changed()=>return Ok(()),_ = &mut end=>return Ok(()),_ = tokio::time::sleep(delay)=>{}}
    }
}
fn backoff(attempt: u32) -> Result<Duration> {
    use ring::rand::SecureRandom;
    let mut bytes = [0; 2];
    ring::rand::SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| AgentError::Transport)?;
    let seconds = (1u64 << attempt.saturating_sub(1).min(5)).min(30);
    Ok(Duration::from_millis(
        seconds * 1000 + u16::from_be_bytes(bytes) as u64 % 501,
    ))
}
async fn one_session(
    cfg: &AgentConfig,
    signer: &RecoverySigner,
    journal: &mut RevisionJournal,
    connector: Option<Connector>,
) -> Result<()> {
    let mut request = cfg
        .endpoint()?
        .into_client_request()
        .map_err(|_| AgentError::Configuration)?;
    request.headers_mut().insert(
        "sec-websocket-protocol",
        SUBPROTOCOL.parse().map_err(|_| AgentError::Configuration)?,
    );
    let config = WebSocketConfig::default()
        .max_message_size(Some(MAX_MESSAGE))
        .max_frame_size(Some(MAX_MESSAGE))
        .write_buffer_size(0)
        .max_write_buffer_size(MAX_MESSAGE * 2);
    // tokio-tungstenite 0.26.2 does not follow redirects in this path. HTTP non-101 is an error.
    let (mut socket, response) = tokio::time::timeout(
        Duration::from_secs(10),
        connect_async_tls_with_config(request, Some(config), false, connector),
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
    let ServerMessage::ConnectChallenge { challenge } = receive(&mut socket).await? else {
        return Err(AgentError::Protocol);
    };
    let (boot, proof) = signer.connect(challenge, unix_now()?)?;
    send(&mut socket, &proof).await?;
    let connected = receive(&mut socket).await.map_err(|e| {
        if e == AgentError::Transport {
            AgentError::Authentication
        } else {
            e
        }
    })?;
    match connected {
        ServerMessage::Connected {
            heartbeat_seconds: 10,
            lease_seconds: 30,
        } => {}
        _ => return Err(AgentError::Protocol),
    }
    println!(
        "{}",
        serde_json::json!({"event":"agent_connected","execution":"recovery_required"})
    );
    let mut sequence = 0i64;
    heartbeat(&mut socket, &mut sequence).await?;
    snapshot(&mut socket, signer, journal, boot, &mut sequence).await?;
    let mut snapshot_at = Instant::now();
    let mut ticks = tokio::time::interval(Duration::from_secs(8));
    ticks.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    ticks.tick().await;
    loop {
        ticks.tick().await;
        heartbeat(&mut socket, &mut sequence).await?;
        if snapshot_at.elapsed() >= Duration::from_secs(16) {
            snapshot(&mut socket, signer, journal, boot, &mut sequence).await?;
            snapshot_at = Instant::now();
        }
    }
}
fn next(seq: &mut i64) -> Result<i64> {
    *seq = seq.checked_add(1).ok_or(AgentError::Protocol)?;
    Ok(*seq)
}
async fn heartbeat(s: &mut Socket, seq: &mut i64) -> Result<()> {
    let n = next(seq)?;
    send(s, &ControlMessage::Heartbeat { seq: n }).await?;
    match receive(s).await? {
        ServerMessage::HeartbeatAck { seq } if seq == n => Ok(()),
        _ => Err(AgentError::Protocol),
    }
}
async fn snapshot(
    s: &mut Socket,
    signer: &RecoverySigner,
    journal: &mut RevisionJournal,
    boot: Uuid,
    seq: &mut i64,
) -> Result<()> {
    let n = next(seq)?;
    send(s, &ControlMessage::ProjectionChallenge { seq: n }).await?;
    let challenge = match receive(s).await? {
        ServerMessage::ProjectionChallenge {
            seq,
            gateway_boot,
            nonce,
            expires_at,
            snapshot_valid_until,
        } if seq == n => SnapshotChallenge {
            boot: gateway_boot,
            nonce,
            expires_at,
            ceiling: snapshot_valid_until,
        },
        _ => return Err(AgentError::Protocol),
    };
    // Persist a never-reused local revision BEFORE emitting proof. Invalid challenges consume
    // at most one revision and terminate; no externally supplied journal offset is honored.
    let revision = journal.next(signer)?;
    let proof = signer.snapshot(challenge, boot, revision, unix_now()?)?;
    let n = next(seq)?;
    send(s, &ControlMessage::Projection { seq: n, proof }).await?;
    match receive(s).await.map_err(|e| {
        if e == AgentError::Transport {
            AgentError::Protocol
        } else {
            e
        }
    })? {
        ServerMessage::ProjectionAck { seq } if seq == n => {
            println!(
                "{}",
                serde_json::json!({"event":"agent_recovery_projected","revision":revision})
            );
            Ok(())
        }
        _ => Err(AgentError::Protocol),
    }
}
async fn send(s: &mut Socket, value: &impl Serialize) -> Result<()> {
    let text = serde_json::to_string(value).map_err(|_| AgentError::Protocol)?;
    if text.len() > MAX_MESSAGE {
        return Err(AgentError::Protocol);
    }
    tokio::time::timeout(Duration::from_secs(2), s.send(Message::Text(text.into())))
        .await
        .map_err(|_| AgentError::Transport)?
        .map_err(classify)
}
async fn receive(s: &mut Socket) -> Result<ServerMessage> {
    tokio::time::timeout(Duration::from_secs(10), async {
        for _ in 0..16 {
            match s
                .next()
                .await
                .ok_or(AgentError::Transport)?
                .map_err(classify)?
            {
                Message::Text(t) => return ServerMessage::parse(&t),
                Message::Close(_) => return Err(AgentError::Transport),
                Message::Ping(_) | Message::Pong(_) => {
                    s.flush().await.map_err(classify)?;
                }
                _ => return Err(AgentError::Protocol),
            }
        }
        Err(AgentError::Protocol)
    })
    .await
    .map_err(|_| AgentError::Transport)?
}
fn classify(e: tungstenite::Error) -> AgentError {
    match e {
        // tokio-rustls propagates certificate/name failure as io::InvalidData, not
        // necessarily tungstenite::Error::Tls. Such failures must never back off/retry.
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
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn invalid_tls_data_is_not_a_transport_retry() {
        let e = std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "fixture certificate rejected",
        );
        assert_eq!(classify(tungstenite::Error::Io(e)), AgentError::Tls);
    }
    #[test]
    fn backoff_is_bounded() {
        for n in [1, 2, 6, 30, 100] {
            let t = backoff(n).unwrap();
            assert!((1000..=30500).contains(&t.as_millis()));
        }
    }
    #[test]
    fn auth_and_redirect_are_not_retryable() {
        for s in [301, 302, 307, 308, 401, 403] {
            let r = tungstenite::http::Response::builder()
                .status(s)
                .body(None)
                .unwrap();
            assert_eq!(
                classify(tungstenite::Error::Http(r)),
                AgentError::Authentication
            );
        }
    }
    #[test]
    fn unavailable_is_bounded_retryable() {
        let r = tungstenite::http::Response::builder()
            .status(503)
            .body(None)
            .unwrap();
        assert_eq!(classify(tungstenite::Error::Http(r)), AgentError::Transport);
    }
}
