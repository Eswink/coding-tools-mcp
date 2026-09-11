//! One awaited lifecycle transaction for configuration and credential changes.
//! No data/runtime mutex is held while awaiting listener or tunnel shutdown.
use crate::app_state::AppState;
use crate::error::{AppError, AppResult};
use crate::runtime::ServiceKind;
use crate::workspace::WorkspaceProfile;
use crate::workspace::resources::validate_workspace_resources_update;
use super::runtime::{self, RESTART_GATE};

type Target = (WorkspaceProfile, ServiceKind);

fn different<T: serde::Serialize>(a: &T, b: &T) -> AppResult<bool> {
    Ok(serde_json::to_value(a)? != serde_json::to_value(b)?)
}

fn changed_services(old: &WorkspaceProfile, new: &WorkspaceProfile) -> AppResult<Vec<ServiceKind>> {
    let mut kinds = Vec::new();
    if old.path != new.path || different(&old.auth, &new.auth)?
        || different(&old.runtime, &new.runtime)? || different(&old.tunnel, &new.tunnel)? {
        kinds.push(ServiceKind::Mcp);
    }
    if old.path != new.path || different(&old.actions, &new.actions)? {
        kinds.push(ServiceKind::Actions);
    }
    Ok(kinds)
}

fn running_targets(state: &AppState, candidates: Vec<Target>) -> AppResult<Vec<Target>> {
    state.with_runtime(|runtime| Ok(candidates.into_iter()
        .filter(|(p, kind)| runtime.is_running(&p.id, *kind)).collect()))
}

/// The caller holds RESTART_GATE across selection, persistence and restart.
/// Failed persistence/application leaves affected listeners stopped, not stale.
async fn apply<T>(state: &AppState, targets: &[Target], persist: impl FnOnce() -> AppResult<T>) -> AppResult<T> {
    for (profile, kind) in targets {
        crate::auth::chat::service().revoke(&profile.id, None);
        match kind {
            ServiceKind::Mcp => { runtime::stop_mcp_service(state, &profile.id).await?; }
            ServiceKind::Actions => { runtime::stop_actions_service(state, &profile.id).await?; }
        }
    }
    let value = persist()?;
    let mut failures = Vec::new();
    for (profile, kind) in targets {
        let result = match kind {
            ServiceKind::Mcp => runtime::start_mcp_service(state, &profile.id).await,
            ServiceKind::Actions => runtime::start_actions_service(state, &profile.id).await,
        };
        match result {
            Ok(status) if status.state == "running" => {},
            Ok(status) => failures.push(format!("{} / {kind:?}: {}", profile.name, status.local_message)),
            Err(error) => failures.push(format!("{} / {kind:?}: {error}", profile.name)),
        }
    }
    if !failures.is_empty() {
        return Err(AppError::Message(format!(
            "配置已保存，但服务应用失败；未回退到旧认证。请修正后重新启动：{}", failures.join("; "))));
    }
    Ok(value)
}

pub(crate) async fn update(state: &AppState, mut next: WorkspaceProfile) -> AppResult<()> {
    let _gate = RESTART_GATE.lock().await;
    let old = state.with_workspaces(|store| {
        let old = store.get(&next.id).cloned()
            .ok_or_else(|| AppError::Message("workspace not found".into()))?;
        crate::workspace::endpoint::normalize_profile_tunnels(&old, &mut next, &store.settings())
            .map_err(AppError::Message)?;
        validate_workspace_resources_update(store.list(), &old, &next)?;
        Ok(old)
    })?;
    let kinds = changed_services(&old, &next)?;
    let targets = running_targets(state, kinds.iter().map(|kind| (old.clone(), *kind)).collect())?;
    let guards = if old.path != next.path { super::exec_tasks::pause_workspace_tasks(&old)? } else { Vec::new() };
    if !kinds.is_empty() { crate::auth::chat::service().revoke(&old.id, None); }
    apply(state, &targets, || state.with_workspaces(|store| {
        let current = store.get(&old.id).ok_or_else(|| AppError::Message("workspace not found".into()))?;
        if different(current, &old)? {
            return Err(AppError::Message("配置已被其他操作更新，请刷新后重试；受影响服务已停止。".into()));
        }
        validate_workspace_resources_update(store.list(), &old, &next)?;
        store.update(next)?;
        for guard in guards { guard.commit(); }
        Ok(())
    })).await
}

fn secret_service(key: &str) -> Option<ServiceKind> {
    match key {
        "oauth_client_id" | "oauth_client_secret" | "oauth_password" | "oauth_token_secret" | "bearer_token" => Some(ServiceKind::Mcp),
        "actions_api_key" | "actions_oauth_client_secret" | "actions_oauth_password" | "actions_oauth_token_secret" => Some(ServiceKind::Actions),
        _ => None,
    }
}

/// `None` value regenerates. Workspace existence and key validation precede this call.
pub(crate) async fn write_secret(state: &AppState, id: Option<&str>, key: &str, value: Option<&str>) -> AppResult<String> {
    let _gate = RESTART_GATE.lock().await;
    let profiles = state.with_workspaces(|store| {
        if let Some(id) = id {
            if store.get(id).is_none() { return Err(AppError::Message("workspace not found".into())); }
        }
        Ok(store.list().to_vec())
    })?;
    if let Some(value) = value {
        let unchanged = state.with_data(|store| Ok(match id {
            Some(id) => store.get_workspace_secret(id, key)?.as_deref() == Some(value),
            None => store.get_shared_secret(key).as_deref() == Some(value),
        }))?;
        if unchanged { return Ok(value.to_string()); }
    }
    let mut candidates = Vec::new();
    if let Some(kind) = secret_service(key) {
        for profile in profiles {
            let shared = match kind { ServiceKind::Mcp => profile.auth.use_shared_secrets, ServiceKind::Actions => profile.actions.use_shared_secrets };
            let selected = match id { Some(id) => !shared && profile.id == id, None => shared };
            if selected {
                crate::auth::chat::service().revoke(&profile.id, None);
                candidates.push((profile, kind));
            }
        }
    }
    let targets = running_targets(state, candidates)?;
    apply(state, &targets, || state.with_data(|store| match (id, value) {
        (Some(id), Some(value)) => { store.set_workspace_secret(id, key, value)?; Ok(value.to_string()) }
        (None, Some(value)) => { store.set_shared_secret(key, value)?; Ok(value.to_string()) }
        (Some(id), None) => store.regenerate_workspace_secret(id, key),
        (None, None) => store.regenerate_shared_secret(key),
    })).await
}

#[cfg(test)]
#[path = "configuration_tests.rs"]
mod tests;
