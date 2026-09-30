//! Exact pending manifests + actual native owner dialog, bound to the current listener.
use super::native_owner::{confirm, unavailable, PendingHooks};
use crate::{app_state::AppState, error::AppResult, tools::policy_hooks::HookSpec};
use serde_json::{json, Value};
use std::{
    sync::Arc,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager, State};
fn lease(
    state: &AppState,
    id: &str,
) -> AppResult<crate::tools::listener_context::ListenerContextLease> {
    state.with_runtime(|runtime| runtime.mcp_context_lease(id).ok_or_else(unavailable))
}
#[tauri::command]
pub async fn preview_policy_hooks(
    state: State<'_, AppState>,
    id: String,
    specs: Vec<HookSpec>,
) -> AppResult<Value> {
    super::runtime::ensure_service_start_allowed()?;
    let lease = lease(&state, &id)?;
    let context = lease.with_live(Arc::clone).map_err(|_| unavailable())?;
    let ctx = context.clone();
    let prepared =
        tauri::async_runtime::spawn_blocking(move || ctx.policy_hooks.prepare(&ctx, specs))
            .await
            .map_err(|_| unavailable())?
            .map_err(|_| unavailable())?;
    if !lease.is_live() {
        return Err(unavailable());
    }
    let preview = prepared.preview();
    let token = uuid::Uuid::new_v4().to_string();
    let mut pending = state
        .native_controls
        .hooks
        .lock()
        .map_err(|_| unavailable())?;
    pending.retain(|_, v| Instant::now() < v.expires && v.lease.is_live());
    if pending.len() >= 32 {
        return Err(unavailable());
    }
    pending.insert(
        token.clone(),
        PendingHooks {
            profile: id,
            lease,
            context,
            prepared,
            expires: Instant::now() + Duration::from_secs(60),
        },
    );
    Ok(
        json!({"pending_id":token,"preview":preview,"expires_in_seconds":60,"native_dialog_required":true}),
    )
}
#[tauri::command]
pub async fn approve_policy_hooks(
    app: AppHandle,
    id: String,
    pending_id: String,
    digest: String,
) -> AppResult<Option<Value>> {
    let state = app.state::<AppState>();
    let mut pending = state
        .native_controls
        .hooks
        .lock()
        .map_err(|_| unavailable())?
        .remove(&pending_id)
        .ok_or_else(unavailable)?;
    if pending.profile != id
        || pending.prepared.digest() != digest
        || Instant::now() >= pending.expires
        || !pending.lease.is_live()
    {
        return Err(unavailable());
    }
    let summary = state.with_workspaces(|store| {
        let profile = store.get(&id).ok_or_else(unavailable)?;
        approval_summary(&pending, profile)
    })?;
    let Some(approval) = confirm(&app, "hooks", "批准本机策略 Hooks", summary, &digest).await?
    else {
        return Ok(None);
    };
    if !approval.validates("hooks", &digest) || Instant::now() >= pending.expires {
        return Err(unavailable());
    }
    let pending = tauri::async_runtime::spawn_blocking(move || {
        pending.prepared.revalidate().map_err(|_| unavailable())?;
        Ok::<_, crate::error::AppError>(pending)
    })
    .await
    .map_err(|_| unavailable())??;
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let current = lease(&state, &id)?;
    Ok(Some(commit_pending(
        pending, &current, &approval, &id, &digest,
    )?))
}
// Resolve display identity from native profile state and the exact retained listener,
// never from a remote tool label or the currently selected frontend workspace.
fn approval_summary(
    pending: &PendingHooks,
    profile: &crate::workspace::WorkspaceProfile,
) -> AppResult<Value> {
    let root = std::path::Path::new(&profile.path)
        .canonicalize()
        .map_err(|_| unavailable())?;
    if profile.id != pending.profile || root != pending.context.workspace.root() {
        return Err(unavailable());
    }
    // The shared native dialog caps this entire serialized wrapper at 64 KiB.
    // Large otherwise-valid manifests are refused, never truncated for approval.
    Ok(
        json!({"operation":"approve_policy_hooks", "profile_id":profile.id,
        "profile_name":profile.name, "canonical_root":root,
        "manifest":pending.prepared.preview()}),
    )
}
fn commit_pending(
    pending: PendingHooks,
    current: &crate::tools::listener_context::ListenerContextLease,
    approval: &super::native_owner::OwnerApproval,
    id: &str,
    digest: &str,
) -> AppResult<Value> {
    if !approval.validates("hooks", digest)
        || pending.profile != id
        || pending.prepared.digest() != digest
        || Instant::now() >= pending.expires
    {
        return Err(unavailable());
    }
    if current.generation() != pending.lease.generation() {
        return Err(unavailable());
    }
    let result = current
        .with_live(|context| {
            if !Arc::ptr_eq(&context.policy_hooks, &pending.context.policy_hooks) {
                return Err("HOOK_CONTEXT_CHANGED");
            }
            context.policy_hooks.install_prevalidated(pending.prepared)
        })
        .map_err(|_| unavailable())?
        .map_err(|_| unavailable())?;
    Ok(result)
}
#[tauri::command]
pub fn get_policy_hooks(state: State<'_, AppState>, id: String) -> AppResult<Value> {
    lease(&state, &id)?
        .with_live(|context| context.policy_hooks.status())
        .map_err(|_| unavailable())
}
#[tauri::command]
pub fn disable_policy_hooks(state: State<'_, AppState>, id: String) -> AppResult<Value> {
    lease(&state, &id)?
        .with_live(|context| context.policy_hooks.disable())
        .map_err(|_| unavailable())?
        .map_err(|_| unavailable())
}

#[cfg(all(test, target_os = "linux"))]
mod native_tests {
    use super::*;
    use crate::commands::native_owner::OwnerApproval;
    use crate::tools::{listener_context::ListenerContextLease, ToolContext};
    #[test]
    fn model_digest_and_replaced_listener_cannot_commit_native_hook_preview() {
        let root = tempfile::tempdir().unwrap();
        let storage = tempfile::tempdir().unwrap();
        let ctx =
            Arc::new(ToolContext::for_test(root.path().into(), storage.path().into()).unwrap());
        let lease = ListenerContextLease::new(ctx.clone());
        let pending = || {
            let mut prepared = ctx.policy_hooks.prepare(&ctx, Vec::new()).unwrap();
            prepared.revalidate().unwrap();
            PendingHooks {
                profile: "native".into(),
                lease: lease.clone(),
                context: ctx.clone(),
                prepared,
                expires: Instant::now() + Duration::from_secs(60),
            }
        };
        let p = pending();
        let digest = p.prepared.digest().to_owned();
        assert!(commit_pending(
            p,
            &lease,
            &OwnerApproval::for_test("hooks", &"0".repeat(64)),
            "native",
            &digest
        )
        .is_err());
        let p = pending();
        let other = ListenerContextLease::new(ctx.clone());
        assert!(commit_pending(
            p,
            &other,
            &OwnerApproval::for_test("hooks", &digest),
            "native",
            &digest
        )
        .is_err());
        let p = pending();
        assert!(commit_pending(
            p,
            &lease,
            &OwnerApproval::for_test("hooks", &digest),
            "native",
            &digest
        )
        .is_ok());
        let p = pending();
        let digest = p.prepared.digest().to_owned();
        lease.close();
        assert!(commit_pending(
            p,
            &lease,
            &OwnerApproval::for_test("hooks", &digest),
            "native",
            &digest
        )
        .is_err());
    }
    #[test]
    fn hook_dialog_identifies_native_profile_and_rejects_changed_target() {
        let root = tempfile::tempdir().unwrap();
        let storage = tempfile::tempdir().unwrap();
        let ctx =
            Arc::new(ToolContext::for_test(root.path().into(), storage.path().into()).unwrap());
        let mut profile = crate::workspace::WorkspaceProfile::new(
            root.path().to_string_lossy().into_owned(),
            Some("native selected workspace".into()),
        );
        let pending = PendingHooks {
            profile: profile.id.clone(),
            lease: ListenerContextLease::new(ctx.clone()),
            context: ctx.clone(),
            prepared: ctx.policy_hooks.prepare(&ctx, Vec::new()).unwrap(),
            expires: Instant::now() + Duration::from_secs(60),
        };
        let summary = approval_summary(&pending, &profile).unwrap();
        assert_eq!(summary["profile_id"], profile.id);
        assert_eq!(summary["profile_name"], profile.name);
        assert_eq!(summary["canonical_root"], json!(ctx.workspace.root()));
        assert_eq!(summary["manifest"], pending.prepared.preview());
        profile.path = storage.path().to_string_lossy().into_owned();
        assert!(approval_summary(&pending, &profile).is_err());
        profile.path = root.path().to_string_lossy().into_owned();
        profile.id = "other-native-profile".into();
        assert!(approval_summary(&pending, &profile).is_err());
    }
}
