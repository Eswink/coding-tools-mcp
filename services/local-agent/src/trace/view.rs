use crate::ToolErrorKind;
use serde::Serialize;
use std::collections::BTreeMap;

/// Allowlisted categories only; never the executor's message or payload.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum TraceToolError {
    InvalidInput,
    Unauthorized,
    CapabilityDenied,
    NotFound,
    ExecutorMismatch,
    OutputTooLarge,
    Execution,
}

impl From<ToolErrorKind> for TraceToolError {
    fn from(kind: ToolErrorKind) -> Self {
        match kind {
            ToolErrorKind::InvalidInput => Self::InvalidInput,
            ToolErrorKind::Unauthorized => Self::Unauthorized,
            ToolErrorKind::CapabilityDenied => Self::CapabilityDenied,
            ToolErrorKind::NotFound => Self::NotFound,
            ToolErrorKind::ExecutorMismatch => Self::ExecutorMismatch,
            ToolErrorKind::OutputTooLarge => Self::OutputTooLarge,
            ToolErrorKind::Execution => Self::Execution,
        }
    }
}

/// Adapter entry/return observation, not proof of dispatch or side effects.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum TracePhase {
    Entered,
    ReturnedOk,
    ReturnedError { kind: TraceToolError },
    OutcomeUnknown,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct TraceEvent {
    pub sequence: u64,
    pub invocation: u64,
    pub phase: TracePhase,
}

/// Exportable but not importable: no public constructor or Deserialize authority.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct TraceSnapshot {
    pub(super) events: Vec<TraceEvent>,
    pub(super) active_invocations: Vec<u64>,
    pub(super) next_sequence: u64,
    pub(super) dropped_events: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum RecoveryState {
    InFlight,
    ReturnedOk,
    ReturnedError { kind: TraceToolError },
    OutcomeUnknown,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RecoveryItem {
    pub invocation: u64,
    pub entry_retained: bool,
    pub observation: RecoveryState,
}

/// A diagnostic projection, never a command queue or a replacement for a ledger.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RecoveryView {
    pub items: Vec<RecoveryItem>,
    pub dropped_events: u64,
    pub history_complete: bool,
    pub local_only: bool,
    pub durable: bool,
    pub automatic_replay_allowed: bool,
    pub reconciliation_required: bool,
}

impl TraceSnapshot {
    pub fn events(&self) -> &[TraceEvent] {
        &self.events
    }
    pub fn active_invocations(&self) -> &[u64] {
        &self.active_invocations
    }
    pub fn next_sequence(&self) -> u64 {
        self.next_sequence
    }
    pub fn dropped_events(&self) -> u64 {
        self.dropped_events
    }

    /// A missing event is never a completed request. ReturnedOk describes a tool
    /// return, not externally verified side effects. This method cannot replay.
    pub fn recovery_view(&self) -> RecoveryView {
        let mut items = BTreeMap::new();
        for event in &self.events {
            let item = items.entry(event.invocation).or_insert(RecoveryItem {
                invocation: event.invocation,
                entry_retained: false,
                observation: RecoveryState::OutcomeUnknown,
            });
            item.observation = match event.phase {
                TracePhase::Entered => {
                    item.entry_retained = true;
                    RecoveryState::InFlight
                }
                TracePhase::ReturnedOk => RecoveryState::ReturnedOk,
                TracePhase::ReturnedError { kind } => RecoveryState::ReturnedError { kind },
                TracePhase::OutcomeUnknown => RecoveryState::OutcomeUnknown,
            };
        }
        // The active set survives ring eviction and shares the snapshot lock.
        for &invocation in &self.active_invocations {
            items
                .entry(invocation)
                .or_insert(RecoveryItem {
                    invocation,
                    entry_retained: false,
                    observation: RecoveryState::InFlight,
                })
                .observation = RecoveryState::InFlight;
        }
        let reconciliation_required = self.dropped_events != 0
            || items
                .values()
                .any(|item| !item.entry_retained || item.observation != RecoveryState::ReturnedOk);
        RecoveryView {
            items: items.into_values().collect(),
            dropped_events: self.dropped_events,
            history_complete: self.dropped_events == 0,
            local_only: true,
            durable: false,
            automatic_replay_allowed: false,
            reconciliation_required,
        }
    }
}
