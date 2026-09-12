use tauri::State;

use crate::app_state::AppState;
use crate::auth::PublicOrigin;
use crate::runtime::ServiceKind;
use crate::error::{AppError, AppResult};
use crate::platform::platform;
use crate::tunnel::{
    frp_snippet, supervisor, sync_managed_runtime_routes, TunnelServiceKind, TunnelStatus,
};
use crate::workspace::resources::{validate_service_start, WorkspaceService};

fn profile_by_id(state: &AppState, id: &str) -> AppResult<crate::workspace::WorkspaceProfile> {
    state.with_workspaces(|store| {
        store
            .get(id)
            .cloned()
            .ok_or_else(|| AppError::Message(format!("workspace not found: {id}")))
    })
}

fn validate_tunnel_start_resources(
    state: &AppState,
    id: &str,
    kind: TunnelServiceKind,
) -> AppResult<()> {
    let service = match kind {
        TunnelServiceKind::Mcp => WorkspaceService::Mcp,
        TunnelServiceKind::Actions => WorkspaceService::Actions,
    };
    state.with_workspaces(|store| validate_service_start(store.list(), id, service))
}

fn runtime_origin(state: &AppState, id: &str, kind: TunnelServiceKind) -> AppResult<Option<PublicOrigin>> {
    let service = match kind { TunnelServiceKind::Mcp => ServiceKind::Mcp, TunnelServiceKind::Actions => ServiceKind::Actions };
    state.with_runtime(|runtime| Ok(runtime.public_origin_handle(id, service)))
}

fn persist_public_url(origin: Option<&PublicOrigin>, status: &TunnelStatus) -> AppResult<()> {
    if let Some(origin) = origin {
        if status.state == "running" { origin.publish(&status.public_url)?; }
        else { origin.clear(); }
    }
    Ok(())
}

async fn sync_tunnel_routes_from_runtime(state: &AppState) -> AppResult<()> {
    let active_keys = state.with_runtime(|runtime| Ok(runtime.active_tunnel_service_keys()))?;
    sync_managed_runtime_routes(active_keys).await
}

fn restore_tunnel_config(
    state: &AppState,
    id: &str,
    kind: TunnelServiceKind,
    failed: &crate::workspace::WorkspaceProfile,
    restored: &crate::workspace::WorkspaceProfile,
) -> AppResult<()> {
    state.with_workspaces(|store| {
        let Some(mut current) = store.get(id).cloned() else {
            return Ok(());
        };
        let unchanged_since_failure = match kind {
            TunnelServiceKind::Mcp => mcp_tunnel_matches(&current, failed),
            TunnelServiceKind::Actions => actions_tunnel_matches(&current, failed),
        };
        if !unchanged_since_failure {
            return Err(AppError::Message(
                "检测到更新的隧道配置，已拒绝用旧请求覆盖。".into(),
            ));
        }
        match kind {
            TunnelServiceKind::Mcp => current.tunnel = restored.tunnel.clone(),
            TunnelServiceKind::Actions => {
                current.actions.public_url = restored.actions.public_url.clone();
                current.actions.tunnel_type = restored.actions.tunnel_type.clone();
                current.actions.frp = restored.actions.frp.clone();
                current.actions.frp_server = restored.actions.frp_server.clone();
                current.actions.frp_subdomain = restored.actions.frp_subdomain.clone();
                current.actions.frp_profile_id = restored.actions.frp_profile_id.clone();
                current.actions.frp_server_port = restored.actions.frp_server_port;
                current.actions.cloudflare_mode = restored.actions.cloudflare_mode.clone();
                current.actions.cloudflare_token = restored.actions.cloudflare_token.clone();
                current.actions.cloudflare_http2 = restored.actions.cloudflare_http2;
                current.actions.use_proxy = restored.actions.use_proxy;
            }
        }
        store.update(current)
    })
}

fn mcp_tunnel_matches(
    left: &crate::workspace::WorkspaceProfile,
    right: &crate::workspace::WorkspaceProfile,
) -> bool {
    left.tunnel.tunnel_type == right.tunnel.tunnel_type
        && left.tunnel.public_url == right.tunnel.public_url
        && left.tunnel.frp == right.tunnel.frp
        && left.tunnel.frp_server == right.tunnel.frp_server
        && left.tunnel.frp_subdomain == right.tunnel.frp_subdomain
        && left.tunnel.frp_profile_id == right.tunnel.frp_profile_id
        && left.tunnel.frp_server_port == right.tunnel.frp_server_port
        && left.tunnel.cloudflare_mode == right.tunnel.cloudflare_mode
        && left.tunnel.cloudflare_http2 == right.tunnel.cloudflare_http2
        && left.tunnel.use_proxy == right.tunnel.use_proxy
}

fn actions_tunnel_matches(
    left: &crate::workspace::WorkspaceProfile,
    right: &crate::workspace::WorkspaceProfile,
) -> bool {
    left.actions.public_url == right.actions.public_url
        && left.actions.tunnel_type == right.actions.tunnel_type
        && left.actions.frp == right.actions.frp
        && left.actions.frp_server == right.actions.frp_server
        && left.actions.frp_subdomain == right.actions.frp_subdomain
        && left.actions.frp_profile_id == right.actions.frp_profile_id
        && left.actions.frp_server_port == right.actions.frp_server_port
        && left.actions.cloudflare_mode == right.actions.cloudflare_mode
        && left.actions.cloudflare_token == right.actions.cloudflare_token
        && left.actions.cloudflare_http2 == right.actions.cloudflare_http2
        && left.actions.use_proxy == right.actions.use_proxy
}

fn tunnel_type_for(profile: &crate::workspace::WorkspaceProfile, kind: TunnelServiceKind) -> &str {
    match kind {
        TunnelServiceKind::Mcp => profile.tunnel.tunnel_type.as_str(),
        TunnelServiceKind::Actions => profile.actions.tunnel_type.as_str(),
    }
}

#[tauri::command]
pub fn get_frp_snippet(
    state: State<'_, AppState>,
    id: String,
    service: String,
) -> AppResult<String> {
    let profile = profile_by_id(&state, &id)?;
    let kind = TunnelServiceKind::parse(&service)?;
    Ok(frp_snippet(&profile, kind))
}

#[tauri::command]
pub async fn restart_tunnel(
    state: State<'_, AppState>,
    id: String,
    service: String,
) -> AppResult<TunnelStatus> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let profile = profile_by_id(&state, &id)?;
    let kind = TunnelServiceKind::parse(&service)?;
    let origin = runtime_origin(&state, &id, kind)?;
    validate_tunnel_start_resources(&state, &id, kind)?;
    sync_tunnel_routes_from_runtime(&state).await?;
    let settings = state.with_settings(|store| Ok(store.settings()))?;

    let result = {
        let mut guard = supervisor().lock().await;
        let was_running = guard.status(&profile, kind, &settings).state == "running";
        let tunnel_type = tunnel_type_for(&profile, kind);
        let result = if was_running && tunnel_type == "frp" && guard.route_profile(&id, kind).is_some() {
            // Start validates the candidate before replacing the existing FRP
            // routes. Stopping first destroys the state needed for rollback.
            guard.start(&profile, kind, &settings).await
                .map_err(|error| (error, guard.route_profile(&id, kind)))
        } else if was_running {
            match guard.stop(&profile, kind, &settings).await {
                Ok(()) => guard
                    .start(&profile, kind, &settings)
                    .await
                    .map_err(|error| (error, None)),
                Err(error) => Err((error, None)),
            }
        } else {
            Ok(guard.status(&profile, kind, &settings))
        };
        // A failed replacement may either restore the previous route or leave
        // no connector. Publish the actual visible state, not the failed candidate.
        let visible = match &result {
            Ok(status) => status.clone(),
            Err(_) => guard.status(&profile, kind, &settings),
        };
        persist_public_url(origin.as_ref(), &visible)?;
        result

    };

    let status = match result {
        Ok(status) => status,
        Err((error, restored)) => {
            if let Some(restored) = restored {
                if let Err(rollback_error) =
                    restore_tunnel_config(&state, &id, kind, &profile, &restored)
                {
                    return Err(AppError::Message(format!(
                        "FRP 线路已恢复，但配置回滚失败：{error}; rollback: {rollback_error}"
                    )));
                }
            }
            return Err(error);
        }
    };

    Ok(status)
}

#[tauri::command]
pub async fn start_tunnel(
    state: State<'_, AppState>,
    id: String,
    service: String,
) -> AppResult<TunnelStatus> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let profile = profile_by_id(&state, &id)?;
    let kind = TunnelServiceKind::parse(&service)?;
    let origin = runtime_origin(&state, &id, kind)?;
    validate_tunnel_start_resources(&state, &id, kind)?;
    sync_tunnel_routes_from_runtime(&state).await?;
    let settings = state.with_settings(|store| Ok(store.settings()))?;

    let status = {
        let mut guard = supervisor().lock().await;
        let status = guard.start(&profile, kind, &settings).await?;
        persist_public_url(origin.as_ref(), &status)?;
        status
    };

    Ok(status)
}

#[tauri::command]
pub async fn stop_tunnel(
    state: State<'_, AppState>,
    id: String,
    service: String,
) -> AppResult<TunnelStatus> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let profile = profile_by_id(&state, &id)?;
    let kind = TunnelServiceKind::parse(&service)?;
    let origin = runtime_origin(&state, &id, kind)?;
    let settings = state.with_settings(|store| Ok(store.settings()))?;
    let mut guard = supervisor().lock().await;
    guard.stop(&profile, kind, &settings).await?;
    if let Some(origin) = origin { origin.clear(); }
    Ok(guard.status(&profile, kind, &settings))
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TunnelTestResult {
    pub success: bool,
    pub public_url: String,
    pub kept_running: bool,
    pub message: String,
}

fn local_service_listening(
    profile: &crate::workspace::WorkspaceProfile,
    kind: TunnelServiceKind,
) -> AppResult<bool> {
    let port = match kind {
        TunnelServiceKind::Mcp => profile.runtime.local_port,
        TunnelServiceKind::Actions => profile.actions.local_port,
    };
    Ok(platform().find_pid_listening_on_port(port)?.is_some())
}

/// Probe tunnel connectivity without leaving it running unless the local service is already up.
#[tauri::command]
pub async fn test_tunnel(
    state: State<'_, AppState>,
    id: String,
    service: String,
) -> AppResult<TunnelTestResult> {
    let _gate = super::runtime::RESTART_GATE.lock().await;
    let profile = profile_by_id(&state, &id)?;
    let kind = TunnelServiceKind::parse(&service)?;
    let origin = runtime_origin(&state, &id, kind)?;
    validate_tunnel_start_resources(&state, &id, kind)?;
    sync_tunnel_routes_from_runtime(&state).await?;
    let settings = state.with_settings(|store| Ok(store.settings()))?;
    let runtime_running = local_service_listening(&profile, kind)?;

    let was_tunnel_running = {
        let guard = supervisor().lock().await;
        guard.status(&profile, kind, &settings).state == "running"
    };

    let result = {
        let mut guard = supervisor().lock().await;
        let result = if was_tunnel_running && tunnel_type_for(&profile, kind) == "frp"
            && guard.route_profile(&id, kind).is_some() {
            guard
                .start(&profile, kind, &settings)
                .await
                .map_err(|error| (error, guard.route_profile(&id, kind)))
        } else {
            let stop_result = if was_tunnel_running {
                guard.stop(&profile, kind, &settings).await
            } else {
                Ok(())
            };
            match stop_result {
                Ok(()) => guard
                    .start(&profile, kind, &settings)
                    .await
                    .map_err(|error| (error, None)),
                Err(error) => Err((error, None)),
            }
        };
        // A failed replacement may either restore the previous route or leave
        // no connector. Publish the actual visible state, not the failed candidate.
        let visible = match &result {
            Ok(status) => status.clone(),
            Err(_) => guard.status(&profile, kind, &settings),
        };
        persist_public_url(origin.as_ref(), &visible)?;
        result

    };

    let status = match result {
        Ok(status) => status,
        Err((error, restored)) => {
            if let Some(restored) = restored {
                if let Err(rollback_error) =
                    restore_tunnel_config(&state, &id, kind, &profile, &restored)
                {
                    return Err(AppError::Message(format!(
                        "FRP 测试失败且配置回滚失败：{error}; rollback: {rollback_error}"
                    )));
                }
            }
            return Err(error);
        }
    };

    let public_url = status.public_url.clone();
    let keep_tunnel = runtime_running;

    if keep_tunnel {
        return Ok(TunnelTestResult {
            success: !public_url.is_empty() || status.state == "running",
            public_url,
            kept_running: true,
            message: if runtime_running {
                "隧道连接已确认并保持运行；DNS、源站与 OAuth 请继续执行健康检查。".into()
            } else {
                "隧道连接已恢复；尚未验证公网源站与 OAuth。".into()
            },
        });
    }

    {
        let mut guard = supervisor().lock().await;
        guard.stop(&profile, kind, &settings).await?;
        if let Some(origin) = origin.as_ref() { origin.clear(); }
    }

    let success = !public_url.is_empty();
    let message = if public_url.is_empty() {
        "隧道进程已退出，未获取到公网地址。".into()
    } else {
        "隧道连接已确认。本地服务未运行，测试连接已自动断开；未验证公网源站与 OAuth。".into()
    };

    Ok(TunnelTestResult {
        success,
        public_url,
        kept_running: false,
        message,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn visible(state: &str, public_url: &str) -> TunnelStatus {
        TunnelStatus { state: state.into(), public_url: public_url.into(), tunnel_pid: None }
    }

    #[test]
    fn failed_replacement_with_no_connector_clears_the_previous_origin() {
        let origin = PublicOrigin::managed("https://old.trycloudflare.com").unwrap();
        persist_public_url(Some(&origin), &visible("stopped", "https://old.trycloudflare.com")).unwrap();
        assert!(origin.snapshot().is_empty());
    }

    #[test]
    fn successful_rollback_keeps_the_restored_route_identity() {
        let origin = PublicOrigin::managed("https://old.example.com").unwrap();
        persist_public_url(Some(&origin), &visible("running", "https://old.example.com")).unwrap();
        assert_eq!(origin.snapshot(), "https://old.example.com");
    }

    #[test]
    fn invalid_running_origin_does_not_overwrite_current_identity() {
        let origin = PublicOrigin::managed("https://fixed.example.com").unwrap();
        assert!(persist_public_url(Some(&origin), &visible("running", "https://wrong.example.com/mcp")).is_err());
        assert_eq!(origin.snapshot(), "https://fixed.example.com");
    }

    #[test]
    fn connection_probe_without_a_listener_does_not_create_an_identity() {
        assert!(persist_public_url(None, &visible("running", "https://probe.example.com")).is_ok());
    }
}
