use super::{AgentError, Result};
use crate::channel::{ConnectChallenge, MAX_MESSAGE};
use serde::Deserialize;
use uuid::Uuid;

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub(super) enum ServerMessage {
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
}
impl ServerMessage {
    pub(super) fn parse(text: &str) -> Result<Self> {
        if text.is_empty() || text.len() > MAX_MESSAGE {
            return Err(AgentError::Protocol);
        }
        serde_json::from_str(text).map_err(|_| AgentError::Protocol)
    }
}
pub(super) struct SnapshotChallenge {
    pub boot: Uuid,
    pub nonce: String,
    pub expires_at: i64,
    pub ceiling: i64,
}
pub(super) fn unix_now() -> Result<i64> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()
        .and_then(|x| i64::try_from(x.as_secs()).ok())
        .ok_or(AgentError::Protocol)
}
