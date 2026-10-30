//! A1 C5 (SPEC-A1 v5.2 §5 steps 2-5, §5.2, §5.3; v5.1 NB-b): the integrate
//! lifecycle. A remote `subagent_integrate` only records an `integrate_pending`
//! request; the files are written solely by the native confirm path, which needs
//! an `OwnerApproval` for this integration's digest and runs under the drain +
//! main-root exclusive guard.
use super::HostRoots;
use super::{
    busy, drain_for_integrate,
    integrate::{files_value, worker_diff_of},
    journal::{check_size, sha_hex, Journal, JournalDoc, JournalEntry, JournalState},
    mainfs::{self, Current, Parents, Step},
    now, open, state_error, Document, Inner, WorkerError, WorkerId, WorkerOp, WorkerOwner,
    WorkerRecord, WorkerState, DRAIN_BUDGET, MAX_OPS,
};
use crate::commands::native_owner::OwnerApproval;
use crate::harness::worktree::{FileChange, WorkerDiff, WorktreeManager};
use crate::tools::ToolContext;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::Path;

/// §5 step 3: an unanswered request expires after 10 minutes.
pub(crate) const PENDING_TTL_SECS: u64 = 600;
/// Integrations kept per worker; pending and committed ones are never trimmed.
const MAX_INTEGRATIONS: usize = 8;
/// Conflicts and paths listed in one error; the totals are always given.
const MAX_LISTED: usize = 32;
/// The native confirm scope and digest domain of an integration.
pub(crate) const INTEGRATE_SCOPE: &str = "subagent_integrate";
const DIGEST_DOMAIN: &str = "subagent_integrate/v1";
const MAX_SUMMARY: usize = 65_536;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum IntegrationState {
    Pending,
    Rejected,
    Expired,
    Failed,
    Committed,
    RollbackPending,
    RolledBack,
}
impl IntegrationState {
    pub(crate) fn label(self) -> &'static str {
        match self {
            Self::Pending => "integrate_pending",
            Self::Rejected => "rejected",
            Self::Expired => "expired",
            Self::Failed => "failed",
            Self::Committed => "integrated",
            Self::RollbackPending => "rollback_pending",
            Self::RolledBack => "rolled_back",
        }
    }
    fn kept(self) -> bool {
        matches!(
            self,
            Self::Pending | Self::Committed | Self::RollbackPending
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct IntegrationRecord {
    pub(crate) integration_id: String,
    pub(crate) request_id: String,
    pub(crate) diff_sha256: String,
    pub(crate) state: IntegrationState,
    /// The worker state restored on reject, expiry, failure or rollback.
    pub(crate) prior_state: WorkerState,
    pub(crate) created_at: u64,
    pub(crate) expires_at: u64,
    pub(crate) files: u64,
    pub(crate) main_changed_since_spawn: bool,
    /// Set in the write that commits (§5.3: `(integration_id, journal_epoch)`).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) journal_epoch: Option<String>,
    /// §5.4 ①: the recorded reason the rollback window closed.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) closed_reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) error_code: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) rollback_request_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub(crate) rollback_expires_at: Option<u64>,
}

pub(crate) fn integrate_error(code: &'static str, message: &'static str) -> WorkerError {
    WorkerError::new(code, message)
}
fn stale() -> WorkerError {
    integrate_error(
        "INTEGRATE_STALE",
        "diff_sha256 is not the worker's current diff; collect again.",
    )
}
fn unsupported(details: Value) -> WorkerError {
    integrate_error(
        "INTEGRATE_UNSUPPORTED",
        "The change set cannot be integrated by A1.",
    )
    .with_details(details)
}
fn conflict(conflicts: Vec<Value>) -> WorkerError {
    let total = conflicts.len();
    let listed: Vec<Value> = conflicts.into_iter().take(MAX_LISTED).collect();
    integrate_error(
        "INTEGRATE_CONFLICT",
        "The main workspace no longer matches the worker's base for these files.",
    )
    .with_details(json!({"conflicts": listed, "conflicts_total": total}))
}
fn not_pending() -> WorkerError {
    integrate_error("WORKER_STATE", "No pending integration with this id.")
}
fn confirmation_required() -> WorkerError {
    integrate_error(
        "OWNER_CONFIRMATION_REQUIRED",
        "The integration needs the owner's native confirmation.",
    )
}
fn new_id() -> String {
    uuid::Uuid::new_v4().simple().to_string()
}
pub(crate) fn digest(integration_id: &str, diff_sha256: &str) -> String {
    let doc = json!([DIGEST_DOMAIN, integration_id, diff_sha256]);
    sha_hex(doc.to_string().as_bytes())
}

pub(crate) fn audit(record: &mut WorkerRecord, tool: &str, error: Option<&str>, files: u64) {
    let at = now();
    record.ops_seq += 1;
    record.ops.push(WorkerOp {
        seq: record.ops_seq,
        at,
        tool: tool.to_owned(),
        ok: error.is_none(),
        error_code: error.map(str::to_owned),
        affected_files: Some(files),
    });
    let excess = record.ops.len().saturating_sub(MAX_OPS);
    record.ops.drain(..excess);
    record.last_activity_at = at;
}
fn trim(record: &mut WorkerRecord) {
    while record.integrations.len() > MAX_INTEGRATIONS {
        let Some(oldest) = record.integrations.iter().position(|i| !i.state.kept()) else {
            break;
        };
        record.integrations.remove(oldest);
    }
}

/// Write paths (§5 step 3): an expired pending request returns the worker to its
/// prior state; an expired rollback request returns to `committed`.
pub(crate) fn expire_due(record: &mut WorkerRecord, at: u64) -> bool {
    let mut changed = Vec::new();
    for integration in &mut record.integrations {
        match integration.state {
            IntegrationState::Pending if integration.expires_at <= at => {
                integration.state = IntegrationState::Expired;
                changed.push(("integrate_expired", Some(integration.prior_state)));
            }
            IntegrationState::RollbackPending
                if integration.rollback_expires_at.is_some_and(|t| t <= at) =>
            {
                integration.state = IntegrationState::Committed;
                integration.rollback_expires_at = None;
                changed.push(("rollback_expired", None));
            }
            _ => {}
        }
    }
    for (tool, prior) in &changed {
        if let Some(prior) = prior {
            if record.state == WorkerState::IntegratePending {
                record.state = *prior;
            }
        }
        audit(record, tool, None, 0);
    }
    !changed.is_empty()
}
fn expire_all(doc: &mut Document, at: u64) -> bool {
    let mut any = false;
    for record in &mut doc.workers {
        any |= expire_due(record, at);
    }
    any
}

/// Read-only view (status never writes): the effective state with expiry applied.
pub(crate) fn effective(record: &WorkerRecord, at: u64) -> WorkerRecord {
    let mut copy = record.clone();
    expire_due(&mut copy, at);
    copy
}
pub(crate) fn view(integration: &IntegrationRecord) -> Value {
    json!({
        "integration_id": integration.integration_id,
        "state": integration.state.label(),
        "diff_sha256": integration.diff_sha256,
        "files": integration.files,
        "main_changed_since_spawn": integration.main_changed_since_spawn,
        "expires_at": integration.expires_at,
    })
}

/// §5 step 2, the strict three-way check: the main workspace must hold the
/// base blob (added: absent; deleted: equal to base) for every changed path.
pub(crate) fn three_way(root: &Path, changes: &[FileChange]) -> Vec<Value> {
    let mut out = Vec::new();
    for change in changes {
        let reason = if !mainfs::safe_path(&change.path) {
            Some("path")
        } else {
            let current = mainfs::current(root, &change.path);
            let want = change
                .pre
                .as_ref()
                .map(|(bytes, exec)| (sha_hex(bytes), *exec));
            let wanted = want.as_ref().map(|(sha, exec)| (sha.as_str(), *exec));
            if mainfs::same(&current, wanted) {
                None
            } else {
                Some(match (&current, &want) {
                    (Current::Other, _) => "not_regular",
                    (Current::Absent, Some(_)) => "missing",
                    (Current::File { .. }, None) => "exists",
                    (Current::File { sha256, .. }, Some((sha, _))) if sha256 == sha => "mode",
                    _ => "changed",
                })
            }
        };
        if let Some(reason) = reason {
            out.push(json!({"path": change.path, "reason": reason}));
        }
    }
    out
}

/// §5.1 / §5.3 ④ checks that need only the diff; nothing is written.
fn supported(host: &HostRoots, diff: &WorkerDiff) -> Result<(), WorkerError> {
    if let Some((path, reason)) = diff.unsupported.first() {
        return Err(unsupported(json!({
            "path": path,
            "reason": reason,
            "paths_total": diff.unsupported.len(),
        })));
    }
    if diff.changes.is_empty() {
        return Err(unsupported(json!({"reason": "empty"})));
    }
    let doc = JournalDoc {
        state: JournalState::Prepared,
        integration_id: Some("0".repeat(32)),
        entries: diff.changes.iter().map(JournalEntry::from_change).collect(),
        ..JournalDoc::fresh(host)
    };
    check_size(&diff.changes, &doc)
}

fn main_changed(manager: &WorktreeManager, record: &WorkerRecord) -> bool {
    record
        .main_fingerprint
        .as_deref()
        .is_some_and(|print| manager.main_fingerprint().map_or(true, |now| now != print))
}

fn request_view(integration: &IntegrationRecord, diff: Option<&WorkerDiff>) -> Value {
    let mut out = view(integration);
    out["conflicts"] = json!([]);
    if let Some(diff) = diff {
        let (files, total) = files_value(diff);
        out["files"] = json!(files);
        out["files_total"] = json!(total);
    }
    out
}

/// `subagent_integrate` (§2.1, §5 steps 2-3): validates and records the request;
/// never writes the main workspace.
pub(crate) fn request(
    ctx: &ToolContext,
    worker_id: &str,
    diff_sha256: &str,
    request_id: &str,
) -> Result<Value, WorkerError> {
    let id = WorkerId::parse(worker_id)?;
    super::validate_request(request_id, "")?;
    let owner = WorkerOwner::from_context(ctx)?;
    let (manager, store) = open(ctx)?;
    if store.draining() {
        return Err(busy());
    }
    let record = {
        let mut inner = store.lock()?;
        inner.update(&owner, &id, |record| {
            expire_due(record, now());
            Ok(record.clone())
        })?
    };
    if let Some(done) = replay(&record, diff_sha256, request_id)? {
        return Ok(done);
    }
    if !matches!(record.state, WorkerState::Ready | WorkerState::Cancelled) {
        return Err(state_error());
    }
    let diff = worker_diff_of(&manager, &record)?;
    if diff.sha256 != diff_sha256 {
        return Err(stale());
    }
    supported(&ctx.host, &diff)?;
    let conflicts = three_way(manager.repository_root(), &diff.changes);
    if !conflicts.is_empty() {
        return Err(conflict(conflicts));
    }
    let changed = main_changed(&manager, &record);
    let mut inner = store.lock()?;
    inner.update(&owner, &id, |record| {
        let at = now();
        expire_due(record, at);
        if let Some(done) = replay(record, diff_sha256, request_id)? {
            return Ok(done);
        }
        if !matches!(record.state, WorkerState::Ready | WorkerState::Cancelled) {
            return Err(state_error());
        }
        let integration = IntegrationRecord {
            integration_id: new_id(),
            request_id: request_id.to_owned(),
            diff_sha256: diff.sha256.clone(),
            state: IntegrationState::Pending,
            prior_state: record.state,
            created_at: at,
            expires_at: at + PENDING_TTL_SECS,
            files: diff.changes.len() as u64,
            main_changed_since_spawn: changed,
            journal_epoch: None,
            closed_reason: None,
            error_code: None,
            rollback_request_id: None,
            rollback_expires_at: None,
        };
        let out = request_view(&integration, Some(&diff));
        record.integrations.push(integration);
        trim(record);
        record.state = WorkerState::IntegratePending;
        audit(
            record,
            "integrate_requested",
            None,
            diff.changes.len() as u64,
        );
        Ok(out)
    })
}
/// request_id idempotency: the same request answers with its recorded result.
fn replay(
    record: &WorkerRecord,
    diff_sha256: &str,
    request_id: &str,
) -> Result<Option<Value>, WorkerError> {
    let Some(existing) = record
        .integrations
        .iter()
        .find(|i| i.request_id == request_id)
    else {
        return Ok(None);
    };
    if existing.diff_sha256 != diff_sha256 {
        return Err(integrate_error(
            "REQUEST_ID_CONFLICT",
            "request_id was already used with different arguments.",
        ));
    }
    let mut out = request_view(existing, None);
    out["deduplicated"] = json!(true);
    Ok(Some(out))
}

fn locate(doc: &Document, integration_id: &str) -> Option<(usize, usize)> {
    doc.workers.iter().enumerate().find_map(|(w, record)| {
        record
            .integrations
            .iter()
            .position(|i| i.integration_id == integration_id)
            .map(|i| (w, i))
    })
}

/// Native: every pending integration of this main root (all sessions; the
/// device owner decides). Expired requests are closed first.
pub(crate) fn pending(ctx: &ToolContext) -> Result<Vec<Value>, WorkerError> {
    let (_, store) = open(ctx)?;
    let mut inner = store.lock()?;
    inner.apply(|doc| {
        expire_all(doc, now());
        Ok(())
    })?;
    let mut out = Vec::new();
    for record in &inner.doc.workers {
        for integration in &record.integrations {
            if integration.state == IntegrationState::Pending {
                let mut item = view(integration);
                item["worker_id"] = json!(record.worker_id.as_str());
                item["label"] = json!(record.label);
                item["digest"] = json!(digest(
                    &integration.integration_id,
                    &integration.diff_sha256
                ));
                out.push(item);
            }
        }
    }
    Ok(out)
}

/// What the owner saw in the native dialog: re-compared under the exclusive
/// guard before anything is written (§5 step 4, v4).
#[derive(Clone, Debug)]
pub(crate) struct Confirmation {
    pub(crate) integration_id: String,
    pub(crate) diff_sha256: String,
    pub(crate) digest: String,
    pub(crate) title: String,
    pub(crate) summary: Value,
    seen: Vec<(String, Current)>,
}

fn pending_record(inner: &mut Inner, integration_id: &str) -> Result<WorkerRecord, WorkerError> {
    inner.apply(|doc| {
        expire_all(doc, now());
        Ok(())
    })?;
    let (w, i) = locate(&inner.doc, integration_id).ok_or_else(not_pending)?;
    let record = &inner.doc.workers[w];
    if record.integrations[i].state != IntegrationState::Pending
        || record.state != WorkerState::IntegratePending
    {
        return Err(not_pending());
    }
    Ok(record.clone())
}
fn fresh_diff(
    manager: &WorktreeManager,
    record: &WorkerRecord,
    diff_sha256: &str,
) -> Result<WorkerDiff, WorkerError> {
    let diff = worker_diff_of(manager, record)?;
    if diff.sha256 != diff_sha256 {
        return Err(stale());
    }
    Ok(diff)
}
fn summary(record: &WorkerRecord, integration: &IntegrationRecord, diff: &WorkerDiff) -> Value {
    let mut files = Vec::new();
    let mut size = 0;
    for change in &diff.changes {
        size += change.path.len() + 32;
        if size > MAX_SUMMARY / 2 {
            break;
        }
        files.push(json!({"path": change.path, "status": change.kind.label()}));
    }
    json!({
        "worker": record.label,
        "diff_sha256_prefix": &integration.diff_sha256[..12],
        "files": files,
        "files_total": diff.changes.len(),
        "withheld_total": diff.withheld.len(),
        "main_changed_since_spawn": integration.main_changed_since_spawn,
        "stages_or_commits": false,
    })
}

/// Native, before the dialog: re-verifies the request and snapshots what the
/// owner is about to approve.
pub(crate) fn prepare(
    ctx: &ToolContext,
    integration_id: &str,
) -> Result<Confirmation, WorkerError> {
    let (manager, store) = open(ctx)?;
    let record = pending_record(&mut *store.lock()?, integration_id)?;
    let integration = record
        .integrations
        .iter()
        .find(|i| i.integration_id == integration_id)
        .cloned()
        .ok_or_else(not_pending)?;
    let diff = fresh_diff(&manager, &record, &integration.diff_sha256)?;
    supported(&ctx.host, &diff)?;
    let root = manager.repository_root();
    let conflicts = three_way(root, &diff.changes);
    if !conflicts.is_empty() {
        return Err(conflict(conflicts));
    }
    let seen = diff
        .changes
        .iter()
        .map(|c| (c.path.clone(), mainfs::current(root, &c.path)))
        .collect();
    Ok(Confirmation {
        digest: digest(integration_id, &integration.diff_sha256),
        title: format!("Integrate worker \u{201c}{}\u{201d}", record.label),
        summary: summary(&record, &integration, &diff),
        integration_id: integration_id.to_owned(),
        diff_sha256: integration.diff_sha256,
        seen,
    })
}

/// The journal, opened read-write on first use or re-read (a deleted document
/// is rebuilt with a new epoch).
pub(super) fn journal_rw<'a>(
    inner: &'a mut Inner,
    host: &HostRoots,
) -> Result<&'a mut Journal, WorkerError> {
    match inner.journal.as_mut() {
        Some(journal) => journal.refresh(host)?,
        None => inner.journal = Some(Journal::open(host)?),
    }
    inner.journal.as_mut().ok_or_else(super::unavailable)
}

fn busy_from(value: &Value) -> WorkerError {
    busy().with_details(
        value
            .pointer("/error/details")
            .cloned()
            .unwrap_or_else(|| json!({})),
    )
}

/// NB-b: before the journal is overwritten, the previous integration still
/// `committed` records `superseded`. Best effort: the id check covers a failure.
fn mark_superseded(inner: &mut Inner, previous: Option<&str>) {
    let Some(previous) = previous else {
        return;
    };
    let _ = inner.apply(|doc| {
        if let Some((w, i)) = locate(doc, previous) {
            let integration = &mut doc.workers[w].integrations[i];
            if integration.state == IntegrationState::Committed
                && integration.closed_reason.is_none()
            {
                integration.closed_reason = Some("superseded".into());
            }
        }
        Ok(())
    });
}

fn finish(
    inner: &mut Inner,
    integration_id: &str,
    state: IntegrationState,
    error: Option<&'static str>,
    epoch: Option<String>,
) -> Result<(), WorkerError> {
    inner.apply(|doc| {
        let (w, i) = locate(doc, integration_id).ok_or_else(not_pending)?;
        let record = &mut doc.workers[w];
        let integration = &mut record.integrations[i];
        integration.state = state;
        integration.error_code = error.map(str::to_owned);
        integration.journal_epoch = epoch;
        let files = integration.files;
        let prior = integration.prior_state;
        record.state = if state == IntegrationState::Committed {
            WorkerState::Integrated
        } else {
            prior
        };
        let tool = match state {
            IntegrationState::Committed => "integrate_committed",
            IntegrationState::Rejected => "integrate_rejected",
            _ => "integrate_failed",
        };
        audit(record, tool, error, files);
        Ok(())
    })
}

/// Native, after the owner approved (§5 steps 4-5): drain, re-verify under the
/// exclusive guard, journal, write, commit. Never stages or commits in Git.
pub(crate) fn apply(
    ctx: &ToolContext,
    confirmation: &Confirmation,
    approval: &OwnerApproval,
) -> Result<Value, WorkerError> {
    if !approval.validates(INTEGRATE_SCOPE, &confirmation.digest)
        || confirmation.digest != digest(&confirmation.integration_id, &confirmation.diff_sha256)
    {
        return Err(confirmation_required());
    }
    let drain = drain_for_integrate(ctx, DRAIN_BUDGET).map_err(|v| busy_from(&v))?;
    let (manager, store) = open(ctx)?;
    let root = manager.repository_root().to_path_buf();
    let id = confirmation.integration_id.as_str();
    let record = pending_record(&mut *store.lock()?, id)?;
    let diff = fresh_diff(&manager, &record, &confirmation.diff_sha256)?;
    supported(&ctx.host, &diff)?;
    let conflicts = three_way(&root, &diff.changes);
    if !conflicts.is_empty() {
        return Err(conflict(conflicts));
    }
    let moved: Vec<Value> = diff
        .changes
        .iter()
        .filter(|c| {
            let now = mainfs::current(&root, &c.path);
            !confirmation
                .seen
                .iter()
                .any(|(path, seen)| *path == c.path && *seen == now)
        })
        .map(|c| json!({"path": c.path, "reason": "changed_since_confirm"}))
        .collect();
    if !moved.is_empty() || confirmation.seen.len() != diff.changes.len() {
        return Err(conflict(moved));
    }
    let mut inner = store.lock()?;
    let previous = {
        let journal = journal_rw(&mut inner, &ctx.host)?;
        match journal.doc().state {
            JournalState::None | JournalState::Committed => {}
            JournalState::NeedsAttention => {
                return Err(state_error().with_details(json!({"reason": "needs_attention"})))
            }
            JournalState::Prepared | JournalState::RollingBack => return Err(busy()),
        }
        journal.doc().integration_id.clone()
    };
    mark_superseded(&mut inner, previous.as_deref());
    let (entries, steps) = plan(&root, &diff.changes)?;
    let journal = journal_rw(&mut inner, &ctx.host)?;
    let base = journal.doc().idle();
    let prepared = JournalDoc {
        state: JournalState::Prepared,
        integration_id: Some(id.to_owned()),
        worker_id: Some(record.worker_id.clone()),
        owner: Some(record.owner.clone()),
        entries,
        ..base.clone()
    };
    check_size(&diff.changes, &prepared)?;
    journal.write(prepared.clone())?;
    if let Err(failed) = mainfs::transact(&root, &steps) {
        let detail = json!({"path": failed.path, "restored": failed.restored});
        if failed.restored {
            let _ = journal.write(base);
        }
        finish(
            &mut inner,
            id,
            IntegrationState::Failed,
            Some("INTEGRATE_FAILED"),
            None,
        )?;
        drop(drain);
        return Err(integrate_error(
            "INTEGRATE_FAILED",
            "Writing the main workspace failed; the change was undone.",
        )
        .with_details(detail));
    }
    let (head, branch) = manager.main_head_branch().unwrap_or_default();
    let committed = JournalDoc {
        state: JournalState::Committed,
        head_at_commit: (head.len() == 40).then_some(head),
        branch_at_commit: Some(branch),
        ..prepared
    };
    let epoch = committed.journal_epoch.clone();
    if let Err(error) = journal.write(committed) {
        // Not durably committed: undo in-process so the journal never lies.
        let undo: Vec<Step> = steps.iter().map(Step::reversed).collect();
        if mainfs::transact(&root, &undo).is_ok() {
            let _ = journal.write(base);
        }
        finish(
            &mut inner,
            id,
            IntegrationState::Failed,
            Some(error.code()),
            None,
        )?;
        return Err(error);
    }
    finish(
        &mut inner,
        id,
        IntegrationState::Committed,
        None,
        Some(epoch),
    )?;
    drop(inner);
    drop(drain);
    let mode_ignored: Vec<&str> = if cfg!(windows) {
        diff.changes
            .iter()
            .filter(|c| match (&c.pre, &c.post) {
                (Some((_, a)), Some((_, b))) => a != b,
                (None, Some((_, exec))) => *exec,
                _ => false,
            })
            .map(|c| c.path.as_str())
            .collect()
    } else {
        Vec::new()
    };
    Ok(json!({
        "integration_id": id,
        "state": "integrated",
        "files": diff.changes.len(),
        "mode_ignored": mode_ignored,
        "staged": false,
    }))
}

/// Journal entries (with NB-c `created_dirs`, each directory owned by the first
/// entry that needs it) and the write steps, in diff order.
fn plan(
    root: &Path,
    changes: &[FileChange],
) -> Result<(Vec<JournalEntry>, Vec<Step>), WorkerError> {
    let mut entries = Vec::new();
    let mut steps = Vec::new();
    let mut planned: Vec<String> = Vec::new();
    for change in changes {
        let mut entry = JournalEntry::from_change(change);
        if change.post.is_some() {
            match mainfs::parents(root, &change.path) {
                Parents::Ready => {}
                Parents::Missing(dirs) => {
                    for dir in dirs {
                        if !planned.contains(&dir) {
                            planned.push(dir.clone());
                            entry.created_dirs.push(dir);
                        }
                    }
                }
                Parents::Blocked => {
                    return Err(conflict(vec![
                        json!({"path": change.path, "reason": "not_regular"}),
                    ]))
                }
            }
        }
        steps.push(Step {
            path: change.path.clone(),
            target: change.post.clone(),
            prior: change.pre.clone(),
            create_dirs: entry.created_dirs.clone(),
            remove_dirs: Vec::new(),
        });
        entries.push(entry);
    }
    Ok((entries, steps))
}

impl Step {
    /// The inverse step: write back `prior`, then drop the created parents.
    pub(crate) fn reversed(&self) -> Step {
        Step {
            path: self.path.clone(),
            target: self.prior.clone(),
            prior: self.target.clone(),
            create_dirs: Vec::new(),
            remove_dirs: self.create_dirs.clone(),
        }
    }
}

/// Native "reject" on the card: closes the request, the worker returns to its
/// prior state. Nothing is written to the main workspace.
pub(crate) fn reject(ctx: &ToolContext, integration_id: &str) -> Result<Value, WorkerError> {
    let (_, store) = open(ctx)?;
    let mut inner = store.lock()?;
    pending_record(&mut inner, integration_id)?;
    finish(
        &mut inner,
        integration_id,
        IntegrationState::Rejected,
        None,
        None,
    )?;
    Ok(json!({"integration_id": integration_id, "state": "rejected"}))
}
