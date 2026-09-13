//! Lease state is independent of OAuth credential lifetime.
use serde::Serialize;
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum Phase { Reserved, Active, Draining }
#[derive(Clone)]
pub(super) struct Owner {
    pub binding: String,
    pub request_id: String,
    pub phase: Phase,
}
