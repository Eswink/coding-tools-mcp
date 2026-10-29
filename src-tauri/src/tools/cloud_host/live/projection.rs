//! Encrypted native projection transition journal. Receipts are not grants.
use super::*;
use crate::data::AuthDocument;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    epoch: i64,
    phase: ProjectionPhase,
    grant: Option<LocalLease>,
    drained: Option<uuid::Uuid>,
    native_epoch: Option<u64>,
}
impl Intent {
    fn free(epoch: i64, drained: Option<uuid::Uuid>) -> Self {
        Self {
            epoch,
            phase: ProjectionPhase::Free,
            grant: None,
            drained,
            native_epoch: None,
        }
    }
    fn matches(&self, view: &HostAuthoritySnapshot) -> bool {
        self.epoch == view.epoch()
            && self.phase == view.phase()
            && self.grant.as_ref() == view.grant()
            && self.drained == view.drained_grant()
    }
    fn validate(&self) -> Result<(), AgentError> {
        HostAuthoritySnapshot::new(
            self.epoch,
            1,
            1,
            self.phase,
            ExecutionState::Offline,
            self.grant.clone(),
            self.drained,
        )?;
        if (self.phase == ProjectionPhase::Active && self.native_epoch.is_none_or(|e| e == 0))
            || (self.phase == ProjectionPhase::Free && self.native_epoch.is_some())
        {
            return Err(AgentError::Journal);
        }
        Ok(())
    }
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    version: u32,
    binding: String,
    intent: Intent,
    acknowledged: Option<Intent>,
    conversations: BTreeSet<String>,
}
pub(super) struct ObservedGrant {
    pub lease: LocalLease,
    pub native_epoch: u64,
    pub execution: ExecutionState,
}
pub(super) struct ProjectionJournal {
    disk: AuthDocument,
    document: Document,
    poisoned: bool,
}
impl ProjectionJournal {
    pub(super) fn open(
        storage: &Path,
        binding: &str,
        initialize: bool,
        epoch: i64,
    ) -> Result<Self, AgentError> {
        if epoch <= 0 || binding.len() != 64 || !binding.bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(AgentError::Journal);
        }
        let mut disk = AuthDocument::open(storage).map_err(|_| AgentError::Journal)?;
        let previous: Option<Document> = disk.load().map_err(|_| AgentError::Journal)?;
        let document = match (previous, initialize) {
            (None, true) => {
                let d = Document {
                    version: 1,
                    binding: binding.into(),
                    intent: Intent::free(epoch, None),
                    acknowledged: None,
                    conversations: BTreeSet::new(),
                };
                disk.save(&d).map_err(|_| AgentError::Journal)?;
                d
            }
            (Some(d), false) => d,
            _ => return Err(AgentError::Journal),
        };
        if document.version != 1
            || document.binding != binding
            || document.intent.epoch < epoch
            || document.conversations.len() > 64
            || document
                .conversations
                .iter()
                .any(|s| !valid_conversation(s))
        {
            return Err(AgentError::Journal);
        }
        document.intent.validate()?;
        if let Some(ack) = &document.acknowledged {
            ack.validate()?;
            if ack.epoch > document.intent.epoch {
                return Err(AgentError::Journal);
            }
        }
        if document
            .intent
            .grant
            .as_ref()
            .is_some_and(|g| !document.conversations.contains(&g.conversation))
        {
            return Err(AgentError::Journal);
        }
        Ok(Self {
            disk,
            document,
            poisoned: false,
        })
    }
    fn save(&mut self, next: Document) -> Result<(), AgentError> {
        if self.poisoned {
            return Err(AgentError::Journal);
        }
        if self.disk.save(&next).is_err() {
            self.poisoned = true;
            return Err(AgentError::Journal);
        }
        self.document = next;
        Ok(())
    }
    pub(super) fn conversations(&self) -> impl Iterator<Item = &str> {
        self.document.conversations.iter().map(String::as_str)
    }
    pub(super) fn register(&mut self, conversation: &str) -> Result<(), AgentError> {
        if self.poisoned || !valid_conversation(conversation) {
            return Err(AgentError::Journal);
        }
        if self.document.conversations.contains(conversation) {
            return Ok(());
        }
        if self.document.conversations.len() >= 64 {
            return Err(AgentError::Capacity);
        }
        let mut next = self.document.clone();
        next.conversations.insert(conversation.into());
        self.save(next)
    }
    pub(super) fn acknowledge(&mut self, view: &HostAuthoritySnapshot) -> Result<(), AgentError> {
        if self.poisoned || !self.document.intent.matches(view) {
            return Err(AgentError::Journal);
        }
        if self.document.acknowledged.as_ref() == Some(&self.document.intent) {
            return Ok(());
        }
        let mut next = self.document.clone();
        next.acknowledged = Some(next.intent.clone());
        self.save(next)
    }
    pub(super) fn observe(
        &mut self,
        observed: Option<ObservedGrant>,
        local_free: bool,
        recovery: bool,
        revision: u64,
        generation: u64,
    ) -> Result<HostAuthoritySnapshot, AgentError> {
        if self.poisoned {
            return Err(AgentError::Journal);
        }
        let old = &self.document.intent;
        let acked = self.document.acknowledged.as_ref() == Some(old);
        let mut next = old.clone();
        match old.phase {
            ProjectionPhase::Active => {
                let same = observed.as_ref().is_some_and(|g| {
                    Some(&g.lease) == old.grant.as_ref() && Some(g.native_epoch) == old.native_epoch
                });
                if !same || recovery {
                    next.phase = ProjectionPhase::Draining;
                    next.drained = None;
                }
            }
            ProjectionPhase::Draining => {
                // A successor's native approval is also evidence that the
                // existing exclusive authorizer completed the old owner's drain.
                let successor = observed
                    .as_ref()
                    .is_some_and(|g| old.grant.as_ref().is_some_and(|old| old.id != g.lease.id));
                if acked && !recovery && (local_free || successor) {
                    next = Intent::free(old.epoch, old.grant.as_ref().map(|g| g.id));
                }
            }
            ProjectionPhase::Free => {
                if acked {
                    if let Some(g) = observed.as_ref().filter(|_| !recovery) {
                        next = Intent {
                            epoch: old.epoch.checked_add(1).ok_or(AgentError::Journal)?,
                            phase: ProjectionPhase::Active,
                            grant: Some(g.lease.clone()),
                            drained: None,
                            native_epoch: Some(g.native_epoch),
                        };
                    } else if !local_free {
                        next.phase = ProjectionPhase::RecoveryRequired;
                        next.drained = None;
                    }
                }
            }
            ProjectionPhase::RecoveryRequired => {
                if old.grant.is_some() {
                    return Err(AgentError::Journal);
                }
                // Empty recovery is not a release of any projected grant.
                // A new active owner is introduced only after an acknowledged
                // Free state, at a strictly newer persisted epoch.
                if !recovery && (local_free || observed.is_some()) {
                    next = Intent::free(old.epoch, None);
                }
            }
        }
        next.validate()?;
        if next != self.document.intent {
            let mut d = self.document.clone();
            d.intent = next.clone();
            self.save(d)?;
        }
        let execution = if next.phase == ProjectionPhase::Active {
            observed
                .as_ref()
                .filter(|g| {
                    Some(&g.lease) == next.grant.as_ref()
                        && Some(g.native_epoch) == next.native_epoch
                })
                .map(|g| g.execution)
                .ok_or(AgentError::LocalAuthority)?
        } else {
            ExecutionState::Offline
        };
        HostAuthoritySnapshot::new(
            next.epoch,
            revision,
            generation,
            next.phase,
            execution,
            next.grant,
            next.drained,
        )
    }
}
fn valid_conversation(s: &str) -> bool {
    use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
    URL_SAFE_NO_PAD
        .decode(s)
        .is_ok_and(|v| v.len() == 32 && URL_SAFE_NO_PAD.encode(v) == s)
}
