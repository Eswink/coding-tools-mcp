//! A1 C5 (SPEC-A1 v5.2 §5.1, §5.3): the integration journal, one fixed-path
//! AuthDocument per main root (`agents-v1/<ws>/integration-journal`). It holds
//! the pre-images (base64) of the single integration that can still be rolled
//! back, plus the state machine none → prepared → committed → rolling_back.
use super::{namespace, unavailable, WorkerError, WorkerId, WorkerOwner};
use crate::data::{AuthDocument, AuthDocumentReader};
use crate::harness::worktree::{ChangeKind, FileChange};
use crate::tools::context::HostRoots;
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::path::PathBuf;

/// §5.3 ①: total raw pre-image bytes of one integration (added files count 0).
pub(crate) const MAX_PREIMAGE_TOTAL: u64 = 524_288;
/// `auth_document.rs` rejects larger serialized documents.
const MAX_DOCUMENT: usize = 1_048_576;
const JOURNAL_DIR: &str = "integration-journal";
const MAX_ENTRIES: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum JournalState {
    None,
    Prepared,
    Committed,
    RollingBack,
    NeedsAttention,
}

/// The pre-image bytes are a base64 string (§5.3 ②), never a number array.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PreImage {
    pub(crate) base64: String,
    pub(crate) exec: bool,
    pub(crate) sha256: String,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PostImage {
    pub(crate) sha256: String,
    pub(crate) exec: bool,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct JournalEntry {
    pub(crate) path: String,
    pub(crate) pre: Option<PreImage>,
    pub(crate) post: Option<PostImage>,
    /// v5.1 NB-c: parent directories integrate created for an added file,
    /// shallow to deep; rollback removes them deep to shallow while empty.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) created_dirs: Vec<String>,
}

pub(crate) fn sha_hex(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|c| matches!(c, b'0'..=b'9' | b'a'..=b'f'))
}

impl PreImage {
    pub(crate) fn new(bytes: &[u8], exec: bool) -> Self {
        Self {
            base64: base64::engine::general_purpose::STANDARD.encode(bytes),
            exec,
            sha256: sha_hex(bytes),
        }
    }
    pub(crate) fn bytes(&self) -> Result<Vec<u8>, WorkerError> {
        let bytes = base64::engine::general_purpose::STANDARD
            .decode(&self.base64)
            .map_err(|_| unavailable())?;
        if sha_hex(&bytes) != self.sha256 {
            return Err(unavailable());
        }
        Ok(bytes)
    }
}
impl JournalEntry {
    pub(crate) fn from_change(change: &FileChange) -> Self {
        Self {
            path: change.path.clone(),
            pre: change
                .pre
                .as_ref()
                .map(|(bytes, exec)| PreImage::new(bytes, *exec)),
            post: change.post.as_ref().map(|(bytes, exec)| PostImage {
                sha256: sha_hex(bytes),
                exec: *exec,
            }),
            created_dirs: Vec::new(),
        }
    }
    pub(crate) fn kind(&self) -> Option<ChangeKind> {
        match (&self.pre, &self.post) {
            (Some(_), Some(_)) => Some(ChangeKind::Modified),
            (Some(_), None) => Some(ChangeKind::Deleted),
            (None, Some(_)) => Some(ChangeKind::Added),
            (None, None) => None,
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct JournalDoc {
    pub(crate) version: u32,
    pub(crate) workspace_id: String,
    pub(crate) journal_epoch: String,
    pub(crate) state: JournalState,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) integration_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) worker_id: Option<WorkerId>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) owner: Option<WorkerOwner>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) head_at_commit: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) branch_at_commit: Option<String>,
    pub(crate) entries: Vec<JournalEntry>,
}
impl JournalDoc {
    pub(crate) fn fresh(host: &HostRoots) -> Self {
        Self {
            version: 1,
            workspace_id: host.workspace_id.clone(),
            journal_epoch: new_epoch(),
            state: JournalState::None,
            integration_id: None,
            worker_id: None,
            owner: None,
            head_at_commit: None,
            branch_at_commit: None,
            entries: Vec::new(),
        }
    }
    /// Back to idle with the same epoch: entries (and their pre-images) released.
    pub(crate) fn idle(&self) -> Self {
        Self {
            state: JournalState::None,
            integration_id: None,
            worker_id: None,
            owner: None,
            head_at_commit: None,
            branch_at_commit: None,
            entries: Vec::new(),
            ..self.clone()
        }
    }
    fn valid(&self, host: &HostRoots) -> bool {
        let idle = self.state == JournalState::None;
        self.version == 1
            && self.workspace_id == host.workspace_id
            && hex(&self.journal_epoch, 32)
            && self.entries.len() <= MAX_ENTRIES
            && (idle == self.integration_id.is_none())
            && (!idle || self.entries.is_empty())
            && self.integration_id.as_deref().is_none_or(|id| hex(id, 32))
            && self.head_at_commit.as_deref().is_none_or(|h| hex(h, 40))
            && self.entries.iter().all(|e| {
                !e.path.is_empty()
                    && e.pre.as_ref().is_none_or(|p| hex(&p.sha256, 64))
                    && e.post.as_ref().is_none_or(|p| hex(&p.sha256, 64))
            })
    }
}

/// 128 random bits as 32 lowercase hex (§5.3, v5).
fn new_epoch() -> String {
    let mut digest = Sha256::new();
    digest.update(b"ctm-journal-epoch-v1\0");
    digest.update(uuid::Uuid::new_v4().as_bytes());
    digest.update(uuid::Uuid::new_v4().as_bytes());
    format!("{:x}", digest.finalize())[..32].to_owned()
}

/// Raw pre-image bytes of `entries` (added files count 0).
pub(crate) fn preimage_total(changes: &[FileChange]) -> u64 {
    changes
        .iter()
        .filter_map(|c| c.pre.as_ref())
        .map(|(bytes, _)| bytes.len() as u64)
        .sum()
}
pub(crate) fn too_large(total_bytes: u64) -> WorkerError {
    WorkerError::new(
        "INTEGRATE_UNSUPPORTED",
        "The change set cannot be integrated by A1.",
    )
    .with_details(json!({"reason": "preimage_too_large", "total_bytes": total_bytes}))
}
/// §5.3 ④: the raw total first, then the serialized document, before any write.
pub(crate) fn check_size(changes: &[FileChange], doc: &JournalDoc) -> Result<(), WorkerError> {
    let total = preimage_total(changes);
    if total > MAX_PREIMAGE_TOTAL {
        return Err(too_large(total));
    }
    let raw = serde_json::to_vec(doc).map_err(|_| unavailable())?;
    if raw.len() > MAX_DOCUMENT {
        return Err(too_large(total));
    }
    Ok(())
}

fn root(host: &HostRoots) -> PathBuf {
    namespace(host).join(JOURNAL_DIR)
}

/// The open journal of one main root, held for the life of the WorkerStore.
pub(crate) struct Journal {
    root: PathBuf,
    disk: Option<AuthDocument>,
    doc: JournalDoc,
}
impl Journal {
    fn file(&self) -> PathBuf {
        self.root.join("auth.json")
    }
    /// Read-write open: creates the document (new epoch) on first use. A corrupt
    /// or foreign document fails closed as STORE_UNAVAILABLE (never reset).
    pub(crate) fn open(host: &HostRoots) -> Result<Self, WorkerError> {
        let root = root(host);
        let mut disk = AuthDocument::open(&root).map_err(|_| unavailable())?;
        let doc = match disk.load::<JournalDoc>().map_err(|_| unavailable())? {
            Some(doc) if doc.valid(host) => doc,
            Some(_) => return Err(unavailable()),
            None => {
                let doc = JournalDoc::fresh(host);
                disk.save(&doc).map_err(|_| unavailable())?;
                doc
            }
        };
        Ok(Self {
            root,
            disk: Some(disk),
            doc,
        })
    }
    /// Read-only open (v5.1 NB-a): `None` when no journal exists; never creates
    /// directories or documents.
    pub(crate) fn open_existing(host: &HostRoots) -> Result<Option<Self>, WorkerError> {
        let root = root(host);
        match std::fs::symlink_metadata(root.join("auth.json")) {
            Ok(meta) if meta.is_file() => {}
            Ok(_) => return Err(unavailable()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(_) => return Err(unavailable()),
        }
        let disk = AuthDocument::open(&root).map_err(|_| unavailable())?;
        let doc = AuthDocumentReader::default()
            .load::<JournalDoc>(&disk)
            .map_err(|_| unavailable())?
            .filter(|doc| doc.valid(host))
            .ok_or_else(unavailable)?;
        Ok(Some(Self {
            root,
            disk: Some(disk),
            doc,
        }))
    }
    pub(crate) fn doc(&self) -> &JournalDoc {
        &self.doc
    }
    /// True when the document file is gone (deleted or moved away): the epoch the
    /// records hold is no longer the journal's (`journal_reset`).
    pub(crate) fn missing(&self) -> bool {
        !std::fs::symlink_metadata(self.file()).is_ok_and(|m| m.is_file())
    }
    /// Re-reads the document so an external replacement is seen (its epoch
    /// differs). A missing file is re-created with a new epoch (read-write only).
    pub(crate) fn refresh(&mut self, host: &HostRoots) -> Result<(), WorkerError> {
        if self.missing() {
            drop(self.disk.take());
            *self = Self::open(host)?;
            return Ok(());
        }
        let disk = self.disk.as_ref().ok_or_else(unavailable)?;
        match disk.load::<JournalDoc>().map_err(|_| unavailable())? {
            Some(doc) if doc.valid(host) => {
                self.doc = doc;
                Ok(())
            }
            _ => Err(unavailable()),
        }
    }
    /// Persists `doc` (same epoch) before returning; the in-memory copy changes
    /// only after the encrypted write succeeded.
    pub(crate) fn write(&mut self, doc: JournalDoc) -> Result<(), WorkerError> {
        if doc.journal_epoch != self.doc.journal_epoch || doc.workspace_id != self.doc.workspace_id
        {
            return Err(unavailable());
        }
        let disk = self.disk.as_mut().ok_or_else(unavailable)?;
        disk.save(&doc).map_err(|_| unavailable())?;
        self.doc = doc;
        Ok(())
    }
}
