//! Payloads invalidate a local snapshot. Never transport OAuth tokens or raw host IDs.
use serde::Serialize;
#[derive(Clone, Debug, Serialize)]
pub(crate) struct ChatEvent {
    pub revision: u64,
    pub profile: String,
    pub kind: &'static str,
    pub request_id: Option<String>,
}

pub(crate) struct PendingEntry {
    pub profile: String,
    pub exclusive: bool,
    pub grant: super::chat::GrantView,
}
pub(crate) struct PendingSnapshot {
    pub revision: u64,
    pub entries: Vec<PendingEntry>,
}
