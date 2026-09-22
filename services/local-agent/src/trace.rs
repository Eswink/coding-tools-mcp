//! Opt-in, bounded local diagnostics. This module never grants or replays work.
use crate::{LocalAdmission, ToolCall, ToolError, ToolErrorKind, ToolFuture, ToolRegistry};
use std::collections::{BTreeSet, VecDeque};
use std::error::Error;
use std::fmt;
use std::sync::{Mutex, MutexGuard};

mod view;
pub use view::{
    RecoveryItem, RecoveryState, RecoveryView, TraceEvent, TracePhase, TraceSnapshot,
    TraceToolError,
};

const MAX_EVENTS: usize = 4096;
const MAX_ACTIVE: usize = 64;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TraceError {
    InvalidLimits,
    Unauthorized,
    Capacity,
    SequenceExhausted,
    Unavailable,
}

impl fmt::Display for TraceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Self::InvalidLimits => "invalid local trace limits",
            Self::Unauthorized => "local trace admission rejected",
            Self::Capacity => "local trace capacity exhausted",
            Self::SequenceExhausted => "local trace sequence exhausted",
            Self::Unavailable => "local trace unavailable",
        })
    }
}
impl Error for TraceError {}

impl TraceError {
    fn tool_error(self) -> ToolError {
        let kind = if self == Self::Unauthorized {
            ToolErrorKind::Unauthorized
        } else {
            ToolErrorKind::Execution
        };
        ToolError::new(
            kind,
            match self {
                Self::InvalidLimits => "invalid local trace limits",
                Self::Unauthorized => "local trace admission rejected",
                Self::Capacity => "local trace capacity exhausted",
                Self::SequenceExhausted => "local trace sequence exhausted",
                Self::Unavailable => "local trace unavailable",
            },
        )
    }
}

/// Private local scope, never accepted from a serialized trace or cloud payload.
/// The caller remains responsible for supplying current local admission and time.
pub struct TraceJournal {
    conversation: String,
    workspace: String,
    generation: u64,
    event_capacity: usize,
    max_active: usize,
    state: Mutex<State>,
}

struct State {
    next_sequence: u64,
    dropped_events: u64,
    events: VecDeque<TraceEvent>,
    active: BTreeSet<u64>,
    failed: bool,
}

impl fmt::Debug for TraceJournal {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Do not lock or print private identity, generation, events or presence.
        f.debug_struct("TraceJournal")
            .field("scope", &"<local-authority>")
            .field("event_capacity", &self.event_capacity)
            .field("max_active", &self.max_active)
            .finish_non_exhaustive()
    }
}

impl TraceJournal {
    pub fn new(
        admission: &LocalAdmission,
        event_capacity: usize,
        max_active: usize,
        now_unix_ms: u64,
    ) -> Result<Self, TraceError> {
        if event_capacity == 0
            || event_capacity > MAX_EVENTS
            || max_active == 0
            || max_active > MAX_ACTIVE
        {
            return Err(TraceError::InvalidLimits);
        }
        let valid_id = |id: &str| {
            !id.is_empty()
                && id.len() <= crate::model::MAX_CONTEXT_ID_BYTES
                && !id.chars().any(char::is_control)
        };
        if !valid_id(&admission.conversation_id)
            || !valid_id(&admission.workspace_id)
            || now_unix_ms > admission.expires_at_unix_ms
        {
            return Err(TraceError::Unauthorized);
        }
        Ok(Self {
            conversation: admission.conversation_id.clone(),
            workspace: admission.workspace_id.clone(),
            generation: admission.generation,
            event_capacity,
            max_active,
            state: Mutex::new(State {
                next_sequence: 1,
                dropped_events: 0,
                events: VecDeque::with_capacity(event_capacity),
                active: BTreeSet::new(),
                failed: false,
            }),
        })
    }

    fn authorize(&self, admission: &LocalAdmission, now_unix_ms: u64) -> Result<(), TraceError> {
        if admission.conversation_id != self.conversation
            || admission.workspace_id != self.workspace
            || admission.generation != self.generation
            || now_unix_ms > admission.expires_at_unix_ms
        {
            return Err(TraceError::Unauthorized);
        }
        Ok(())
    }

    fn state(&self) -> Result<MutexGuard<'_, State>, TraceError> {
        let state = self.state.lock().map_err(|_| TraceError::Unavailable)?;
        if state.failed {
            return Err(TraceError::Unavailable);
        }
        Ok(state)
    }

    /// Wrap the existing registry exactly once. No input, output or error message
    /// is copied into diagnostics. A trace failure before entry prevents dispatch;
    /// after entry, the original registry result is never hidden by diagnostics.
    pub fn invoke<'a>(
        &'a self,
        registry: &'a ToolRegistry,
        call: &'a ToolCall,
        admission: &'a LocalAdmission,
        now_unix_ms: u64,
    ) -> ToolFuture<'a> {
        Box::pin(async move {
            let observation = self
                .begin(call, admission, now_unix_ms)
                .map_err(TraceError::tool_error)?;
            let result = registry.invoke(call, admission, now_unix_ms).await;
            let phase = match &result {
                Ok(_) => TracePhase::ReturnedOk,
                Err(error) => TracePhase::ReturnedError {
                    kind: error.kind.into(),
                },
            };
            observation.returned(phase);
            result
        })
    }

    fn begin(
        &self,
        call: &ToolCall,
        admission: &LocalAdmission,
        now_unix_ms: u64,
    ) -> Result<Observation<'_>, TraceError> {
        self.authorize(admission, now_unix_ms)?;
        if call.conversation_id != self.conversation || call.workspace_id != self.workspace {
            return Err(TraceError::Unauthorized);
        }
        let mut state = self.state()?;
        if state.active.len() >= self.max_active {
            return Err(TraceError::Capacity);
        }
        // Reserve one start and one terminal, plus terminals for active calls.
        if state
            .next_sequence
            .checked_add(state.active.len() as u64 + 2)
            .is_none()
        {
            return Err(TraceError::SequenceExhausted);
        }
        let invocation = state.next_sequence;
        if !state.append(invocation, TracePhase::Entered, self.event_capacity) {
            return Err(TraceError::Unavailable);
        }
        state.active.insert(invocation);
        Ok(Observation {
            journal: self,
            invocation,
            finished: false,
        })
    }

    fn finish(&self, invocation: u64, phase: TracePhase) {
        // Poison stays observable on snapshots. Drop never panics or retries.
        if let Ok(mut state) = self.state() {
            if !state.active.remove(&invocation) {
                state.failed = true;
                return;
            }
            state.append(invocation, phase, self.event_capacity);
        }
    }

    /// Export only this journal's bounded, redacted local view. Not durable state.
    pub fn snapshot(
        &self,
        admission: &LocalAdmission,
        now_unix_ms: u64,
    ) -> Result<TraceSnapshot, TraceError> {
        // Scope/expiry checks precede any availability or presence disclosure.
        self.authorize(admission, now_unix_ms)?;
        let state = self.state()?;
        Ok(TraceSnapshot {
            events: state.events.iter().cloned().collect(),
            active_invocations: state.active.iter().copied().collect(),
            next_sequence: state.next_sequence,
            dropped_events: state.dropped_events,
        })
    }
}

impl State {
    fn append(&mut self, invocation: u64, phase: TracePhase, capacity: usize) -> bool {
        let Some(next) = self.next_sequence.checked_add(1) else {
            self.failed = true;
            return false;
        };
        if self.events.len() == capacity {
            let Some(dropped) = self.dropped_events.checked_add(1) else {
                self.failed = true;
                return false;
            };
            self.events.pop_front();
            self.dropped_events = dropped;
        }
        self.events.push_back(TraceEvent {
            sequence: self.next_sequence,
            invocation,
            phase,
        });
        self.next_sequence = next;
        true
    }
}

struct Observation<'a> {
    journal: &'a TraceJournal,
    invocation: u64,
    finished: bool,
}

impl Observation<'_> {
    fn returned(mut self, phase: TracePhase) {
        self.finished = true;
        self.journal.finish(self.invocation, phase);
    }
}

impl Drop for Observation<'_> {
    fn drop(&mut self) {
        if !self.finished {
            self.journal
                .finish(self.invocation, TracePhase::OutcomeUnknown);
        }
    }
}

#[cfg(test)]
mod tests;
