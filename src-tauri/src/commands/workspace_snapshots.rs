//! Native-only snapshot control. IPC carries IDs, never a deserialized root or lease.
use super::native_owner::{confirm, unavailable, OwnerApproval, PendingRestore};
use crate::{
    app_state::AppState,
    error::{AppError, AppResult},
    harness::{
        worktree::{SnapshotTarget, WorktreeManager},
        Harness,
    },
    snapshots::{RestorePlan, RestoreReport, SnapshotError, SnapshotStore, TargetAuthority},
    tools::{
        exec_tasks::TaskAdmissionGuard,
        root_work::{RootRestoreGuard, RootWorkTracker},
    },
};
use serde_json::json;
use std::{
    path::{Path, PathBuf},
    sync::Arc,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, State};

impl TargetAuthority for SnapshotTarget {
    fn root(&self) -> &Path {
        &self.root
    }
    fn workspace_id(&self) -> &str {
        &self.workspace_id
    }
    fn worktree_id(&self) -> &str {
        &self.worktree_id
    }
    fn head(&self) -> &str {
        &self.head
    }
    fn verify(&self) -> Result<(), SnapshotError> {
        SnapshotTarget::verify(self).map_err(|_| SnapshotError::Boundary)
    }
}
fn target(
    state: &AppState,
    source: &str,
    id: &str,
) -> AppResult<(
    WorktreeManager,
    SnapshotTarget,
    super::managed_workspace::NativeSourceLease,
)> {
    let proof = super::managed_workspace::source_lease(state, source)?;
    let manager = super::managed_workspace::manager(state, source, id, &proof)?;
    let target = manager.snapshot_target(id).map_err(|_| unavailable())?;
    let profile = manager
        .native_profile(id)
        .map_err(|_| unavailable())?
        .ok_or_else(unavailable)?;
    state.with_workspaces(|store| {
        let profile = store.get(&profile).ok_or_else(unavailable)?;
        if Path::new(&profile.path)
            .canonicalize()
            .map_err(|_| unavailable())?
            != target.root
        {
            return Err(unavailable());
        }
        Ok(())
    })?;
    Ok((manager, target, proof))
}
fn private_parent() -> AppResult<PathBuf> {
    let path = Harness::default_root()
        .map_err(|_| unavailable())?
        .join("snapshots-v1");
    for ancestor in path.ancestors() {
        if let Ok(m) = std::fs::symlink_metadata(ancestor) {
            if m.file_type().is_symlink() {
                return Err(unavailable());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if m.file_attributes() & 0x400 != 0 {
                    return Err(unavailable());
                }
            }
        }
    }
    let mut builder = std::fs::DirBuilder::new();
    builder.recursive(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    builder.create(&path).map_err(|_| unavailable())?;
    Ok(path)
}
fn store(target: &SnapshotTarget, create: bool) -> AppResult<Option<SnapshotStore>> {
    let parent = private_parent()?;
    let name = format!("{}-{}", target.workspace_id, target.worktree_id);
    let path = parent.join(&name);
    match std::fs::symlink_metadata(&path) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            if create {
                SnapshotStore::create(&parent, &name)
                    .map(Some)
                    .map_err(snapshot_error)
            } else {
                Ok(None)
            }
        }
        Err(_) => Err(unavailable()),
        Ok(_) => SnapshotStore::open(&path).map(Some).map_err(snapshot_error),
    }
}
fn public_metadata(value: impl serde::Serialize) -> AppResult<serde_json::Value> {
    let mut value = serde_json::to_value(value).map_err(|_| unavailable())?;
    if let Some(object) = value.as_object_mut() {
        object.remove("root_identity");
        for field in ["entries", "before"] {
            if let Some(entries) = object
                .get_mut(field)
                .and_then(serde_json::Value::as_array_mut)
            {
                for entry in entries {
                    if let Some(object) = entry.as_object_mut() {
                        object.remove("security");
                    }
                }
            }
        }
    }
    Ok(value)
}
fn snapshot_error(error: SnapshotError) -> AppError {
    AppError::Message(error.to_string())
}
fn tracker(target: &SnapshotTarget) -> AppResult<Arc<RootWorkTracker>> {
    // Preserve Harness storage validation/initialization before root admission.
    let _harness = Harness::new(
        target.root.clone(),
        Harness::default_root().map_err(|_| unavailable())?,
    )
    .map_err(|_| unavailable())?;
    RootWorkTracker::for_workspace(&target.root).map_err(|_| unavailable())
}
/// This capability is neither serializable nor cloneable. It owns actual native
/// exclusion throughout the synchronous engine call, not just a preflight flag.
struct NativeRestoreLease {
    _lifecycle: tokio::sync::MutexGuard<'static, ()>,
    _tasks: Vec<TaskAdmissionGuard>,
    root: RootRestoreGuard,
    target: SnapshotTarget,
    digest: String,
}
impl NativeRestoreLease {
    async fn acquire(
        state: &AppState,
        target: SnapshotTarget,
        plan: &RestorePlan,
        approval: OwnerApproval,
    ) -> AppResult<Self> {
        if !approval.validates("snapshot_restore", &plan.approval_digest) {
            return Err(unavailable());
        }
        let lifecycle = super::runtime::RESTART_GATE.lock().await;
        let profiles = state.with_workspaces(|store| {
            Ok(store
                .list()
                .iter()
                .filter(|profile| {
                    Path::new(&profile.path).canonicalize().is_ok_and(|root| {
                        root.starts_with(&target.root) || target.root.starts_with(root)
                    })
                })
                .cloned()
                .collect::<Vec<_>>())
        })?;
        if profiles.is_empty() {
            return Err(unavailable());
        }
        let mut tasks = Vec::new();
        for profile in &profiles {
            state.with_runtime(|runtime| {
                if runtime.mcp_status(profile).state != "stopped"
                    || runtime.actions_status(profile).state != "stopped"
                {
                    return Err(unavailable());
                }
                Ok(())
            })?;
            state.cloud_agents.ensure_quiescent(&profile.id)?;
            tasks.extend(super::exec_tasks::pause_workspace_tasks(profile)?);
            // Materialize each overlapping registered root's durable fence. A
            // crashed ancestor process cannot be hidden by selecting its child.
            // Preserve Harness storage validation/initialization before root admission.
            let _harness = Harness::new(
                profile.path.clone().into(),
                Harness::default_root().map_err(|_| unavailable())?,
            )
            .map_err(|_| unavailable())?;
            RootWorkTracker::for_workspace(Path::new(&profile.path)).map_err(|_| unavailable())?;
        }
        target.verify().map_err(|_| unavailable())?;
        if target.worktree_id != plan.worktree_id
            || target.workspace_id != plan.workspace_id
            || target.head != plan.head
        {
            return Err(unavailable());
        }
        let root = tracker(&target)?.restore().map_err(|_| unavailable())?;
        Ok(Self {
            _lifecycle: lifecycle,
            _tasks: tasks,
            root,
            target,
            digest: plan.approval_digest.clone(),
        })
    }
    fn validate(&mut self, plan: &RestorePlan) -> Result<(), SnapshotError> {
        if plan.approval_digest != self.digest
            || plan.worktree_id != self.target.worktree_id
            || plan.workspace_id != self.target.workspace_id
            || plan.head != self.target.head
        {
            return Err(SnapshotError::Approval);
        }
        self.target.verify().map_err(|_| SnapshotError::Boundary)?;
        self.root
            .before_write()
            .map_err(|_| SnapshotError::Approval)
    }
    fn finish(&mut self) -> AppResult<()> {
        self.root.commit().map_err(|_| unavailable())
    }
}
#[tauri::command]
pub async fn snapshot_list(
    state: State<'_, AppState>,
    source_id: String,
    worktree_id: String,
) -> AppResult<Vec<serde_json::Value>> {
    let (manager, target, source_proof) = target(&state, &source_id, &worktree_id)?;
    tauri::async_runtime::spawn_blocking(move || {
        let _source_proof = source_proof;
        manager
            .with_lifecycle(|| {
                Ok((|| match store(&target, false) {
                    Ok(Some(store)) => store
                        .list(&target)
                        .map_err(snapshot_error)?
                        .into_iter()
                        .map(public_metadata)
                        .collect(),
                    Ok(None) => Ok(Vec::new()),
                    Err(error) => Err(error),
                })())
            })
            .map_err(|_| unavailable())?
    })
    .await
    .map_err(|_| unavailable())?
}
#[tauri::command]
pub async fn snapshot_capture(
    state: State<'_, AppState>,
    source_id: String,
    worktree_id: String,
) -> AppResult<serde_json::Value> {
    let (manager, target, source_proof) = target(&state, &source_id, &worktree_id)?;
    tauri::async_runtime::spawn_blocking(move || {
        let _source_proof = source_proof;
        manager
            .with_lifecycle(|| {
                Ok((|| {
                    let owner = tracker(&target)?;
                    let _read_fence = owner.restore().map_err(|_| unavailable())?;
                    store(&target, true)?
                        .ok_or_else(unavailable)?
                        .capture(&target)
                        .map_err(snapshot_error)
                        .and_then(public_metadata)
                })())
            })
            .map_err(|_| unavailable())?
    })
    .await
    .map_err(|_| unavailable())?
}
#[tauri::command]
pub async fn snapshot_plan_restore(
    state: State<'_, AppState>,
    source_id: String,
    worktree_id: String,
    snapshot_id: String,
) -> AppResult<serde_json::Value> {
    let (manager, target, source_proof) = target(&state, &source_id, &worktree_id)?;
    let saved = target.clone();
    let plan = tauri::async_runtime::spawn_blocking(move || {
        let _source_proof = source_proof;
        manager
            .with_lifecycle(|| {
                Ok((|| {
                    store(&target, false)?
                        .ok_or_else(unavailable)?
                        .plan_restore(&target, &snapshot_id)
                        .map_err(snapshot_error)
                })())
            })
            .map_err(|_| unavailable())?
    })
    .await
    .map_err(|_| unavailable())??;
    let mut pending = state
        .native_controls
        .restores
        .lock()
        .map_err(|_| unavailable())?;
    pending.retain(|_, value| Instant::now() < value.expires);
    if pending.len() >= 32 {
        return Err(unavailable());
    }
    pending.insert(
        plan.id.clone(),
        PendingRestore {
            source: source_id,
            target: saved,
            plan: plan.clone(),
            expires: Instant::now() + Duration::from_secs(60),
        },
    );
    public_metadata(plan)
}
#[tauri::command]
pub async fn snapshot_restore(
    app: AppHandle,
    source_id: String,
    worktree_id: String,
    plan_id: String,
    approval_digest: String,
) -> AppResult<Option<RestoreReport>> {
    let state = app.state::<AppState>();
    let pending = state
        .native_controls
        .restores
        .lock()
        .map_err(|_| unavailable())?
        .remove(&plan_id)
        .ok_or_else(unavailable)?;
    if pending.source != source_id
        || pending.target.worktree_id != worktree_id
        || pending.plan.approval_digest != approval_digest
        || Instant::now() >= pending.expires
    {
        return Err(unavailable());
    }
    let summary = json!({"operation":"restore_contents_and_permissions","root":pending.target.root,"worktree_id":worktree_id,
        "snapshot_id":pending.plan.snapshot_id,"head":pending.plan.head,"changes":pending.plan.changes,
        "approval_digest":approval_digest,"backup":"displaced files are retained; conflicts refuse destructive continuation",
        "external_writers":"external editors and other writers are NOT proven stopped; current tree is rechecked before each move"});
    let Some(approval) = confirm(
        &app,
        "snapshot_restore",
        "恢复受管工作区内容和权限",
        summary,
        &approval_digest,
    )
    .await?
    else {
        return Ok(None);
    };
    if Instant::now() >= pending.expires {
        return Err(unavailable());
    }
    let (manager, current, source_proof) = target(&state, &source_id, &worktree_id)?;
    if current.root != pending.target.root
        || current.head != pending.target.head
        || current.workspace_id != pending.target.workspace_id
    {
        return Err(unavailable());
    }
    let mut lease =
        NativeRestoreLease::acquire(&state, pending.target.clone(), &pending.plan, approval)
            .await?;
    let report = tauri::async_runtime::spawn_blocking(move || {
        let _source_proof = source_proof;
        manager
            .with_lifecycle(|| {
                Ok((|| {
                    let store = store(&pending.target, false)?.ok_or_else(unavailable)?;
                    let result =
                        store.restore(&pending.target, &pending.plan, |plan| lease.validate(plan));
                    match result {
                        Ok(report) => {
                            lease.finish()?;
                            Ok(report)
                        }
                        Err(error) => {
                            // Only the joined engine's explicit no-recovery result proves
                            // refusal happened before durable mutation intent. Unknown or
                            // partial transactions keep BOTH disk fences; never auto reset.
                            if store.recovery_required() == Ok(false) {
                                lease.finish()?;
                            }
                            Err(snapshot_error(error))
                        }
                    }
                })())
            })
            .map_err(|_| unavailable())?
    })
    .await
    .map_err(|_| unavailable())??;
    Ok(Some(report))
}

#[cfg(test)]
#[path = "workspace_snapshot_control_tests.rs"]
mod native_tests;
