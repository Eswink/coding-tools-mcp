//! Owner-selected managed roots create separate native profiles, never root substitution.
use super::native_owner::{confirm, unavailable};
use crate::{
    app_state::{bootstrap_workspace, AppState},
    error::AppResult,
    harness::{worktree::WorktreeManager, Harness},
    workspace::WorkspaceProfile,
};
use serde::Serialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::path::Path;
use tauri::{AppHandle, Manager, State};
#[derive(Serialize)]
pub(crate) struct NativeManagedWorktree {
    id: String,
    display_path: String,
    head: String,
    detached: bool,
    native_profile_id: Option<String>,
}
pub(crate) struct NativeSourceLease {
    root: std::path::PathBuf,
    guard: crate::tools::root_work::RootRestoreGuard,
}
pub(crate) fn source_lease(state: &AppState, source: &str) -> AppResult<NativeSourceLease> {
    let root = state.with_workspaces(|store| {
        store
            .get(source)
            .map(|p| Path::new(&p.path).canonicalize().map_err(|_| unavailable()))
            .ok_or_else(unavailable)?
    })?;
    let tracker = crate::tools::root_work::RootWorkTracker::for_workspace(&root)
        .map_err(|_| unavailable())?;
    Ok(NativeSourceLease {
        root,
        guard: tracker.restore().map_err(|_| unavailable())?,
    })
}
fn managers(
    state: &AppState,
    source: &str,
    proof: &NativeSourceLease,
) -> AppResult<Vec<WorktreeManager>> {
    let (profile, profiles) = state.with_workspaces(|store| {
        Ok((
            store.get(source).cloned().ok_or_else(unavailable)?,
            store.list().to_vec(),
        ))
    })?;
    let source_root = Path::new(&profile.path)
        .canonicalize()
        .map_err(|_| unavailable())?;
    if proof.root != source_root {
        return Err(unavailable());
    }
    proof.guard.validate().map_err(|_| unavailable())?;
    let harness = Harness::new(
        source_root.clone(),
        Harness::default_root().map_err(|_| unavailable())?,
    )
    .map_err(|_| unavailable())?;
    let base = harness
        .store_root()
        .canonicalize()
        .map_err(|_| unavailable())?;
    let mut roots = std::collections::BTreeSet::from([base.clone()]);
    if let Some(lease) = state.with_runtime(|runtime| Ok(runtime.mcp_context_lease(source)))? {
        let context = lease
            .with_live(std::sync::Arc::clone)
            .map_err(|_| unavailable())?;
        if context.workspace.root() != source_root {
            return Err(unavailable());
        }
        for domain in context
            .chat_domains
            .native_harnesses()
            .map_err(|_| unavailable())?
        {
            if domain.workspace_id() == harness.workspace_id() {
                roots.insert(domain.store_root().to_path_buf());
            }
        }
    }
    // A separate native profile plus the broker's private pin is persistent
    // owner evidence after listener stop/restart. Never follow source Git links
    // to select a namespace or accept an IPC-supplied filesystem path.
    for profile in profiles {
        let Ok(root) = Path::new(&profile.path).canonicalize() else {
            continue;
        };
        let Ok(relative) = root.strip_prefix(&base) else {
            continue;
        };
        let parts: Vec<_> = relative
            .components()
            .map(|c| c.as_os_str().to_string_lossy().into_owned())
            .collect();
        let candidate = match parts.as_slice() {
            [kind, workspace, id]
                if kind == "worktrees-v1" && workspace == harness.workspace_id() =>
            {
                Some((base.clone(), id))
            }
            [chat, key, kind, workspace, id]
                if chat == "chat-v1"
                    && kind == "worktrees-v1"
                    && workspace == harness.workspace_id()
                    && key.len() == 64
                    && key.bytes().all(|b| b.is_ascii_hexdigit()) =>
            {
                Some((base.join(chat).join(key), id))
            }
            _ => None,
        };
        if let Some((namespace, id)) = candidate {
            let manager = WorktreeManager::new(&source_root, &namespace, harness.workspace_id())
                .map_err(|_| unavailable())?;
            if manager
                .native_profile(id)
                .map_err(|_| unavailable())?
                .as_deref()
                == Some(&profile.id)
                && manager.snapshot_target(id).map_err(|_| unavailable())?.root == root
            {
                roots.insert(namespace);
            }
        }
    }
    roots
        .into_iter()
        .map(|root| {
            WorktreeManager::new(&source_root, &root, harness.workspace_id())
                .map_err(|_| unavailable())
        })
        .collect()
}
pub(crate) fn manager(
    state: &AppState,
    source: &str,
    id: &str,
    proof: &NativeSourceLease,
) -> AppResult<WorktreeManager> {
    let source_root = state.with_workspaces(|store| {
        store
            .get(source)
            .map(|p| Path::new(&p.path).canonicalize().map_err(|_| unavailable()))
            .ok_or_else(unavailable)?
    })?;
    if proof.root != source_root {
        return Err(unavailable());
    }
    proof.guard.validate().map_err(|_| unavailable())?;
    let workspace = Harness::new(
        source_root,
        Harness::default_root().map_err(|_| unavailable())?,
    )
    .map_err(|_| unavailable())?;
    if let Some((registered_workspace, manager)) = state
        .native_controls
        .targets
        .lock()
        .map_err(|_| unavailable())?
        .get(&(source.into(), id.into()))
        .cloned()
    {
        if registered_workspace == workspace.workspace_id() {
            manager
                .snapshot_target(id)
                .map_err(|_| unavailable())?
                .verify()
                .map_err(|_| unavailable())?;
            return Ok(manager);
        }
        return Err(unavailable());
    }
    let mut found = None;
    for manager in managers(state, source, proof)? {
        if manager
            .list()
            .map_err(|_| unavailable())?
            .iter()
            .any(|entry| entry.id == id)
        {
            if found.is_some() {
                return Err(unavailable());
            }
            found = Some(manager);
        }
    }
    found.ok_or_else(unavailable)
}
#[tauri::command]
pub async fn list_managed_workspaces(
    state: State<'_, AppState>,
    source_id: String,
) -> AppResult<Vec<NativeManagedWorktree>> {
    let proof = source_lease(&state, &source_id)?;
    let managers = managers(&state, &source_id, &proof)?;
    let found = tauri::async_runtime::spawn_blocking(move || {
        let _source_proof = proof;
        let mut result = Vec::new();
        let mut ids = std::collections::HashSet::new();
        for manager in managers {
            let rows = manager
                .with_lifecycle(|| {
                    manager
                        .list()?
                        .into_iter()
                        .map(|item| {
                            Ok(NativeManagedWorktree {
                                native_profile_id: manager.native_profile(&item.id)?,
                                id: item.id,
                                display_path: item.display_path,
                                head: item.head,
                                detached: item.detached,
                            })
                        })
                        .collect::<crate::harness::worktree::WorktreeResult<Vec<_>>>()
                })
                .map_err(|_| unavailable())?;
            for row in rows {
                if !ids.insert(row.id.clone()) {
                    return Err(unavailable());
                }
                let workspace = manager
                    .snapshot_target(&row.id)
                    .map_err(|_| unavailable())?
                    .workspace_id;
                result.push((row, manager.clone(), workspace));
            }
        }
        Ok::<_, crate::error::AppError>(result)
    })
    .await
    .map_err(|_| unavailable())??;
    let mut cache = state
        .native_controls
        .targets
        .lock()
        .map_err(|_| unavailable())?;
    cache.retain(|(source, _), _| source != &source_id);
    if cache.len() + found.len() > 256 {
        return Err(unavailable());
    }
    Ok(found
        .into_iter()
        .map(|(row, manager, workspace)| {
            cache.insert((source_id.clone(), row.id.clone()), (workspace, manager));
            row
        })
        .collect())
}
#[tauri::command]
pub async fn register_managed_workspace(
    app: AppHandle,
    source_id: String,
    worktree_id: String,
) -> AppResult<Option<WorkspaceProfile>> {
    let state = app.state::<AppState>();
    let proof = source_lease(&state, &source_id)?;
    let manager = manager(&state, &source_id, &worktree_id, &proof)?;
    let target = manager
        .snapshot_target(&worktree_id)
        .map_err(|_| unavailable())?;
    if manager
        .native_profile(&worktree_id)
        .map_err(|_| unavailable())?
        .is_some()
    {
        return Err(unavailable());
    }
    let summary = registration_summary(&source_id, &target);
    let digest = registration_digest(&source_id, &target)?;
    drop(proof);
    let Some(approval) = confirm(
        &app,
        "managed_workspace",
        "注册独立的受管工作区",
        summary,
        &digest,
    )
    .await?
    else {
        return Ok(None);
    };
    let _gate = super::runtime::RESTART_GATE.lock().await;
    Ok(Some(register_approved(
        &state, &source_id, &target, &approval,
    )?))
}

fn registration_summary(
    source: &str,
    target: &crate::harness::worktree::SnapshotTarget,
) -> serde_json::Value {
    json!({"operation":"register_separate_native_workspace","source_id":source,"worktree_id":target.worktree_id,
        "root":target.root,"head":target.head,"inherits_authority":false,"automatic_start":false,
        "cloud_connection":"requires separate explicit native enrollment; original journals unchanged",
        "git_metadata":"parent repository remains outside execution sandbox authority",
        "root_confinement":"all native contexts for this managed root use workspace-only reading"})
}
pub(super) fn registration_digest(
    source: &str,
    target: &crate::harness::worktree::SnapshotTarget,
) -> AppResult<String> {
    Ok(format!(
        "{:x}",
        Sha256::digest(
            serde_json::to_vec(&registration_summary(source, target)).map_err(|_| unavailable())?
        )
    ))
}
pub(super) fn register_approved(
    state: &AppState,
    source_id: &str,
    target: &crate::harness::worktree::SnapshotTarget,
    approval: &super::native_owner::OwnerApproval,
) -> AppResult<WorkspaceProfile> {
    let worktree_id = &target.worktree_id;
    let digest = registration_digest(source_id, target)?;
    if !approval.validates("managed_workspace", &digest) {
        return Err(unavailable());
    }
    let proof = source_lease(state, source_id)?;
    let current = super::managed_workspace::manager(state, source_id, worktree_id, &proof)?
        .snapshot_target(worktree_id)
        .map_err(|_| unavailable())?;
    if current.root != target.root
        || current.head != target.head
        || current.workspace_id != target.workspace_id
    {
        return Err(unavailable());
    }
    target.verify().map_err(|_| unavailable())?;
    let mut profile = WorkspaceProfile::new(
        target.root.to_str().ok_or_else(unavailable)?.into(),
        Some(format!("Managed {}", &worktree_id[..8])),
    );
    profile.tunnel.tunnel_type = "none".into();
    profile.actions.tunnel_type = "none".into();
    state.with_workspaces(|store| {
        crate::workspace::resources::assign_free_workspace_ports(store.list(), &mut profile)
    })?;
    crate::tools::root_work::RootWorkTracker::enroll_managed(&target.root)
        .map_err(|_| unavailable())?;
    // Pin before saving the new profile. An interrupted save remains pinned and
    // cannot be remotely removed/reused; it never inherits the source profile.
    manager(state, source_id, worktree_id, &proof)?
        .pin_native_profile(worktree_id, &profile.id)
        .map_err(|_| unavailable())?;
    target.verify().map_err(|_| unavailable())?;
    state.with_workspaces(|store| {
        bootstrap_workspace(store, &profile.id)?;
        store.add(profile.clone())?;
        Ok(())
    })?;
    Ok(profile)
}
