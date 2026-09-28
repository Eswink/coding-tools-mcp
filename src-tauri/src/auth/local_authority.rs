//! Local-only authority projection primitives.
//!
//! Cloud OAuth and transport authentication are intentionally absent here.
//! These types can only be minted from already-active desktop authorization
//! state, and admission tickets are opaque, short-lived, process-local values.
use std::collections::BTreeSet;
use std::path::Path;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};

use crate::data::AuthDocument;
use crate::runtime::ExecutionAvailability;

const DOCUMENT_VERSION: u32 = 1;
pub(super) const TICKET_TTL: Duration = Duration::from_secs(5);

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthorityEpochDocument {
    version: u32,
    epoch: u64,
}

struct EpochInner {
    disk: AuthDocument,
    epoch: u64,
}

/// Durable, per-workspace boot epoch. Opening the provider is a security event:
/// every process attachment advances the epoch before authority can be exported.
pub(super) struct AuthorityEpochStore {
    inner: Mutex<EpochInner>,
}

impl AuthorityEpochStore {
    pub(super) fn open(root: &Path) -> Result<Self, String> {
        let namespace = root.join("local-authority-v1");
        let mut disk = AuthDocument::open(&namespace)
            .map_err(|_| "本地授权版本存储不可用；未允许远程执行".to_string())?;
        let previous = disk
            .load::<AuthorityEpochDocument>()
            .map_err(|_| "本地授权版本存储损坏；未允许远程执行".to_string())?
            .unwrap_or(AuthorityEpochDocument {
                version: DOCUMENT_VERSION,
                epoch: 0,
            });
        if previous.version != DOCUMENT_VERSION {
            return Err("本地授权版本存储版本不兼容；未允许远程执行".into());
        }
        let epoch = previous
            .epoch
            .checked_add(1)
            .ok_or("本地授权版本已耗尽；未允许远程执行")?;
        disk.save(&AuthorityEpochDocument {
            version: DOCUMENT_VERSION,
            epoch,
        })
        .map_err(|_| "本地授权版本无法持久化；未允许远程执行".to_string())?;
        Ok(Self {
            inner: Mutex::new(EpochInner { disk, epoch }),
        })
    }

    pub(super) fn epoch(&self) -> Result<u64, &'static str> {
        self.inner
            .lock()
            .map(|inner| {
                // Keep the authenticated document alive for the lifetime of the
                // store; reading never rewrites or extends authority.
                let _ = &inner.disk;
                inner.epoch
            })
            .map_err(|_| "LOCAL_AUTHORITY_UNAVAILABLE")
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum LocalExecutionState {
    Online,
    Offline,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum LocalAuthorityPhase {
    Active,
    Draining,
    RecoveryRequired,
}

impl From<ExecutionAvailability> for LocalExecutionState {
    fn from(value: ExecutionAvailability) -> Self {
        match value {
            ExecutionAvailability::Online => Self::Online,
            ExecutionAvailability::Offline => Self::Offline,
        }
    }
}

/// Read-only locally authoritative view. Serialize-only by design: remote input
/// must never deserialize into an object that can be used as a local permit.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) struct LocalAuthoritySnapshot {
    phase: LocalAuthorityPhase,
    conversation_binding: String,
    grant_id: String,
    scopes: BTreeSet<String>,
    grant_issued_at: u64,
    grant_expires_at: u64,
    idle_expires_at: u64,
    authority_epoch: u64,
    authority_revision: u64,
    execution_generation: u64,
    execution_state: LocalExecutionState,
}

impl LocalAuthoritySnapshot {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn new(
        phase: LocalAuthorityPhase,
        conversation_binding: String,
        grant_id: String,
        scopes: BTreeSet<String>,
        grant_issued_at: u64,
        grant_expires_at: u64,
        idle_expires_at: u64,
        authority_epoch: u64,
        authority_revision: u64,
        execution_generation: u64,
        execution_state: LocalExecutionState,
    ) -> Self {
        Self {
            phase,
            conversation_binding,
            grant_id,
            scopes,
            grant_issued_at,
            grant_expires_at,
            idle_expires_at,
            authority_epoch,
            authority_revision,
            execution_generation,
            execution_state,
        }
    }

    pub(crate) fn scopes(&self) -> &BTreeSet<String> {
        &self.scopes
    }

    pub(crate) fn phase(&self) -> LocalAuthorityPhase {
        self.phase
    }

    pub(crate) fn execution_state(&self) -> LocalExecutionState {
        self.execution_state
    }

    #[cfg(test)]
    pub(super) fn authority_epoch(&self) -> u64 {
        self.authority_epoch
    }

    #[cfg(test)]
    pub(super) fn authority_revision(&self) -> u64 {
        self.authority_revision
    }
}

/// Opaque local hand-off ticket. It is neither serializable nor cloneable and
/// therefore cannot be manufactured from a cloud/model payload. The final
/// commit path rechecks every captured fence before returning execution guards.
pub(crate) struct LocalAdmissionTicket {
    pub(super) profile: String,
    pub(super) binding: String,
    pub(super) grant_id: String,
    pub(super) required_scopes: BTreeSet<String>,
    pub(super) authority_epoch: u64,
    pub(super) authority_revision: u64,
    pub(super) execution_generation: u64,
    pub(super) expires: Instant,
}

impl LocalAdmissionTicket {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn new(
        profile: String,
        binding: String,
        grant_id: String,
        required_scopes: BTreeSet<String>,
        authority_epoch: u64,
        authority_revision: u64,
        execution_generation: u64,
    ) -> Self {
        Self {
            profile,
            binding,
            grant_id,
            required_scopes,
            authority_epoch,
            authority_revision,
            execution_generation,
            expires: Instant::now() + TICKET_TTL,
        }
    }

    pub(super) fn expired(&self) -> bool {
        Instant::now() >= self.expires
    }

    #[cfg(test)]
    pub(super) fn expire_for_test(&mut self) {
        self.expires = Instant::now();
    }
}

/// Guards returned only after the ticket is revalidated at the local
/// linearization point. Dropping the value releases both existing admission
/// fences; already-committed work keeps the repository's established
/// in-flight semantics.
pub(crate) struct LocalAdmissionPermit {
    _chat: super::chat::AdmissionGuard,
    _execution: crate::runtime::ExecutionPermit,
}

impl LocalAdmissionPermit {
    pub(super) fn new(
        chat: super::chat::AdmissionGuard,
        execution: crate::runtime::ExecutionPermit,
    ) -> Self {
        Self {
            _chat: chat,
            _execution: execution,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn epoch_advances_durably_on_each_process_attachment() {
        let root = tempfile::tempdir().unwrap();
        let first = AuthorityEpochStore::open(root.path()).unwrap();
        assert_eq!(first.epoch().unwrap(), 1);
        drop(first);
        let second = AuthorityEpochStore::open(root.path()).unwrap();
        assert_eq!(second.epoch().unwrap(), 2);
    }

    #[test]
    fn concurrent_epoch_owner_fails_closed() {
        let root = tempfile::tempdir().unwrap();
        let first = AuthorityEpochStore::open(root.path()).unwrap();
        assert!(AuthorityEpochStore::open(root.path()).is_err());
        drop(first);
        assert_eq!(
            AuthorityEpochStore::open(root.path())
                .unwrap()
                .epoch()
                .unwrap(),
            2
        );
    }
}
