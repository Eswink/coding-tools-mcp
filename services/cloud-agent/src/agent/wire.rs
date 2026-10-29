use super::{AgentError, Result};
use uuid::Uuid;
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
