//! A1 C5 (SPEC-A1 v5.2 §2.2, §5): `subagent_collect`, `subagent_integrate`,
//! `subagent_rollback`, the integration journal and the native confirm/apply
//! steps. The worker diff is always computed outside the worker sandbox by the
//! native process with config-free git2 (the worker's private gitdir is only
//! read, never written).
use super::{
    export_policy::worker_export_policy, manager, open, state_error, WorkerError, WorkerId,
    WorkerOwner, WorkerRecord, WorkerState,
};
use crate::harness::worktree::{WorkerDiff, WorktreeManager};
use crate::tools::ToolContext;
use base64::{
    engine::general_purpose::{STANDARD, URL_SAFE_NO_PAD},
    Engine,
};
use serde_json::{json, Value};

/// Chunk bounds (§2.2: remote results are capped at 8192 bytes after JSON escaping).
pub(crate) const MIN_CHUNK: usize = 256;
pub(crate) const MAX_CHUNK: usize = 4096;
/// `files` entries listed with a collect answer; the patch itself names every file.
pub(crate) const MAX_LISTED_FILES: usize = 32;

fn cursor_stale() -> WorkerError {
    WorkerError::new(
        "CURSOR_STALE",
        "The collect cursor no longer matches the worker's diff; collect again without a cursor.",
    )
}

pub(crate) fn encode_cursor(worker_id: &str, sha: &str, offset: usize) -> String {
    URL_SAFE_NO_PAD.encode(format!("v1:{worker_id}:{sha}:{offset}"))
}
/// `(diff_sha256, offset)` of a cursor issued for `worker_id`.
pub(crate) fn decode_cursor(cursor: &str, worker_id: &str) -> Result<(String, usize), WorkerError> {
    if cursor.len() > 256 {
        return Err(cursor_stale());
    }
    let raw = URL_SAFE_NO_PAD
        .decode(cursor)
        .ok()
        .and_then(|raw| String::from_utf8(raw).ok())
        .ok_or_else(cursor_stale)?;
    let mut parts = raw.splitn(4, ':');
    let (Some("v1"), Some(id), Some(sha), Some(offset)) =
        (parts.next(), parts.next(), parts.next(), parts.next())
    else {
        return Err(cursor_stale());
    };
    let offset = offset.parse::<usize>().map_err(|_| cursor_stale())?;
    // Canonical form only (no leading zeros, no aliases of one position).
    if id != worker_id || sha.len() != 64 || encode_cursor(id, sha, offset) != cursor {
        return Err(cursor_stale());
    }
    Ok((sha.to_owned(), offset))
}

/// The record's worktree (owned, not creating/failed/discarded) and its diff.
pub(crate) fn worker_diff_of(
    manager: &WorktreeManager,
    record: &WorkerRecord,
) -> Result<WorkerDiff, WorkerError> {
    let tree = record.worktree_id.as_deref().ok_or_else(state_error)?;
    let base = record.base_head.as_deref().ok_or_else(state_error)?;
    let target = manager.snapshot_target(tree).map_err(|_| state_error())?;
    Ok(manager.worker_diff(&target, base, worker_export_policy)?)
}

pub(crate) fn collectable(state: WorkerState) -> bool {
    matches!(state, WorkerState::Ready | WorkerState::Cancelled)
}

fn owned_record(ctx: &ToolContext, id: &WorkerId) -> Result<WorkerRecord, WorkerError> {
    let owner = WorkerOwner::from_context(ctx)?;
    let (_, store) = open(ctx)?;
    let inner = store.lock()?;
    inner.owned(&owner, id).cloned()
}

pub(crate) fn files_value(diff: &WorkerDiff) -> (Vec<Value>, usize) {
    let mut files: Vec<Value> = diff
        .changes
        .iter()
        .map(|c| json!({"path": c.path, "status": c.kind.label()}))
        .collect();
    files.extend(
        diff.withheld
            .iter()
            .map(|(p, r)| json!({"path": p, "status": "withheld", "reason": r})),
    );
    files.extend(
        diff.unsupported
            .iter()
            .filter(|(p, _)| !diff.withheld.iter().any(|(w, _)| w == p))
            .map(|(p, r)| json!({"path": p, "status": "unsupported", "reason": r})),
    );
    let total = files.len();
    files.truncate(MAX_LISTED_FILES);
    (files, total)
}

/// One chunk starting at `offset`: UTF-8 text cut on a character boundary, or
/// base64 when the patch is not valid UTF-8 (encoded length ≤ `max_bytes`).
fn chunk(patch: &[u8], offset: usize, max_bytes: usize) -> (String, &'static str, usize) {
    if let Ok(text) = std::str::from_utf8(patch) {
        let mut end = (offset + max_bytes).min(text.len());
        while !text.is_char_boundary(end) {
            end -= 1;
        }
        return (text[offset..end].to_owned(), "utf-8", end);
    }
    let end = (offset + max_bytes / 4 * 3).min(patch.len());
    (STANDARD.encode(&patch[offset..end]), "base64", end)
}

/// `subagent_collect` (§2.2). Stateless: the diff is regenerated on every call
/// and the cursor only carries `(worker_id, diff_sha256, offset)`.
pub(crate) fn collect(
    ctx: &ToolContext,
    worker_id: &str,
    max_bytes: usize,
    cursor: Option<&str>,
) -> Result<Value, WorkerError> {
    // The schema already bounds max_bytes; clamp again for direct callers.
    let max_bytes = max_bytes.clamp(MIN_CHUNK, MAX_CHUNK);
    let id = WorkerId::parse(worker_id)?;
    let resume = cursor.map(|c| decode_cursor(c, id.as_str())).transpose()?;
    let record = owned_record(ctx, &id)?;
    if !collectable(record.state) {
        return Err(state_error());
    }
    let manager = manager(ctx)?;
    let diff = worker_diff_of(&manager, &record)?;
    let offset = match resume {
        Some((sha, offset)) if sha == diff.sha256 && offset <= diff.patch.len() => offset,
        Some(_) => return Err(cursor_stale()),
        None => 0,
    };
    if std::str::from_utf8(&diff.patch).is_ok_and(|t| !t.is_char_boundary(offset)) {
        return Err(cursor_stale());
    }
    let (text, encoding, end) = chunk(&diff.patch, offset, max_bytes);
    let mut out = json!({
        "diff_sha256": diff.sha256,
        "total_bytes": diff.patch.len(),
        "offset": offset,
        "chunk": text,
        "encoding": encoding,
    });
    if end < diff.patch.len() {
        out["next_cursor"] = json!(encode_cursor(id.as_str(), &diff.sha256, end));
    }
    if offset == 0 {
        let (files, total) = files_value(&diff);
        out["files"] = json!(files);
        out["files_total"] = json!(total);
    }
    Ok(out)
}

#[cfg(test)]
mod cursor_tests {
    use super::*;
    #[test]
    fn cursors_round_trip_and_reject_foreign_or_malformed_values() {
        let id = "0123456789abcdef0123456789abcdef";
        let sha = "a".repeat(64);
        let c = encode_cursor(id, &sha, 4096);
        assert_eq!(decode_cursor(&c, id).unwrap(), (sha.clone(), 4096));
        let other = "f".repeat(32);
        assert_eq!(
            decode_cursor(&c, &other).unwrap_err().code(),
            "CURSOR_STALE"
        );
        for bad in [
            "",
            "!!",
            &URL_SAFE_NO_PAD.encode("v2:x:y:1"),
            &URL_SAFE_NO_PAD.encode(format!("v1:{id}:{sha}:01")),
        ] {
            assert_eq!(
                decode_cursor(bad, id).unwrap_err().code(),
                "CURSOR_STALE",
                "{bad}"
            );
        }
    }
    #[test]
    fn chunks_cut_on_utf8_boundaries_and_base64_fits_the_budget() {
        let text = "é".repeat(300); // 600 bytes
        let (c, enc, end) = chunk(text.as_bytes(), 0, 257);
        assert_eq!((enc, end, c.len()), ("utf-8", 256, 256));
        let bin = vec![0xffu8; 1000];
        let (c, enc, end) = chunk(&bin, 0, 256);
        assert_eq!(enc, "base64");
        assert!(c.len() <= 256 && end == 192, "{} {end}", c.len());
    }
}
