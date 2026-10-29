use super::{RecoveryState, TraceSnapshot};
use serde::Serialize;

/// Structured, redacted evidence derived from an already-authorized local trace.
///
/// A returned tool result is not proof that external side effects happened. This
/// projection is descriptive only and never carries execution or replay authority.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct VerificationEvidence {
    pub records: Vec<VerificationRecord>,
    pub observed_events: usize,
    pub dropped_events: u64,
    pub history_complete: bool,
    pub local_only: bool,
    pub durable: bool,
    pub automatic_replay_allowed: bool,
    pub external_effects_verified: bool,
    pub reconciliation_required: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct VerificationRecord {
    pub invocation: u64,
    pub entry_retained: bool,
    pub observation: RecoveryState,
}

impl TraceSnapshot {
    pub fn verification_evidence(&self) -> VerificationEvidence {
        let recovery = self.recovery_view();
        VerificationEvidence {
            records: recovery
                .items
                .into_iter()
                .map(|item| VerificationRecord {
                    invocation: item.invocation,
                    entry_retained: item.entry_retained,
                    observation: item.observation,
                })
                .collect(),
            observed_events: self.events().len(),
            dropped_events: recovery.dropped_events,
            history_complete: recovery.history_complete,
            local_only: true,
            durable: false,
            automatic_replay_allowed: false,
            external_effects_verified: false,
            reconciliation_required: recovery.reconciliation_required,
        }
    }
}
