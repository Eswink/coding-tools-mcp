use std::path::PathBuf;
use std::sync::Arc;

use axum::extract::{DefaultBodyLimit, Form, Query, Request, State};
use axum::http::{header::{CACHE_CONTROL, ORIGIN}, HeaderMap, StatusCode, Uri};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde_json::{json, Value};
use tokio::sync::oneshot;
use tower_http::cors::CorsLayer;

use crate::auth::{
    authorization_server_metadata, authorize_get, authorize_post,
    protected_resource_metadata, token_exchange, verify_bearer_header, verify_oauth_bearer_header,
    AuthorizeForm, AuthorizeParams, OAuthRuntime, PublicOrigin, TokenForm,
};
use crate::mcp::server::{handle_request, new_state, SharedState};
use crate::secret::SecretStore;
use crate::tools::Workspace;
use crate::tunnel::append_profile_log;
use crate::tools::policy::PolicySettings;
use crate::workspace::{AuthConfig, RuntimeConfig};

pub type ShutdownSender = oneshot::Sender<()>;

#[derive(Clone)]
struct ListenerState {
    mcp: SharedState,
    auth: AuthConfig,
    workspace_id: String,
    workspace_path: String,
    bind_port: u16,
    configured_public_url: PublicOrigin,
    bearer_token: Option<String>,
    oauth: Option<Arc<OAuthRuntime>>,
    oauth_client_secret: Option<String>,
}

#[cfg(test)]
#[allow(clippy::too_many_arguments)]
pub fn spawn_listener_with_origin(
    port: u16,
    workspace_path: PathBuf,
    workspace_id: String,
    auth: AuthConfig,
    public_base_url: PublicOrigin,
    oauth_client_secret: Option<String>,
    oauth_password: Option<String>,
    oauth_token_secret: Option<String>,
    runtime: RuntimeConfig,
) -> Result<(ShutdownSender, tauri::async_runtime::JoinHandle<()>), String> {
    spawn_listener_with_origin_and_execution_gate(
        port,
        workspace_path,
        workspace_id,
        auth,
        public_base_url,
        oauth_client_secret,
        oauth_password,
        oauth_token_secret,
        runtime,
    ).map(|(shutdown, handle, _execution_gate)| (shutdown, handle))
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_listener_with_origin_and_execution_gate(
    port: u16,
    workspace_path: PathBuf,
    workspace_id: String,
    auth: AuthConfig,
    public_base_url: PublicOrigin,
    oauth_client_secret: Option<String>,
    oauth_password: Option<String>,
    oauth_token_secret: Option<String>,
    runtime: RuntimeConfig,
) -> Result<(ShutdownSender, tauri::async_runtime::JoinHandle<()>, Arc<crate::runtime::WorkspaceExecutionGate>), String> {
    auth.session_policy.validate()?;
    crate::auth::chat::service().configure(&workspace_id, &auth.session_policy)?;
    let workspace_display = workspace_path.display().to_string();
    let workspace = Workspace::new(workspace_path).map_err(|e| e.message())?;
    let policy = PolicySettings::from_runtime(&runtime);
    let mut mcp = new_state(
        workspace,
        auth.clone(),
        policy,
        runtime.tool_profile.clone(),
        runtime.permission_mode.clone(),
    );
    Arc::get_mut(&mut mcp).expect("new listener context").enable_durable_tasks(&workspace_id, "mcp");
    let execution_gate = mcp.execution_gate();
    crate::auth::chat::service().attach_storage(&workspace_id,
        &crate::auth::oauth_refresh::storage_root(&workspace_id)?.join("execution"),mcp.harness.store_root())?;
    let bearer_token = if auth.bearer_enabled() {
        let key = "bearer_token";
        if auth.use_shared_secrets {
            SecretStore::get_shared(key).map_err(|e| e.to_string())?
        } else {
            SecretStore::get(&workspace_id, key).map_err(|e| e.to_string())?
        }
    } else {
        None
    };
    let configured_public_url = public_base_url;
    let oauth = if auth.oauth_enabled() {
        let password = oauth_password.unwrap_or_default();
        let token_secret = oauth_token_secret.unwrap_or_default();
        let oauth_base = configured_public_url.resolve(&HeaderMap::new(), port);
        Some(Arc::new(OAuthRuntime::new(
            oauth_base,
            auth.oauth_client_id.clone(),
            oauth_client_secret.clone(),
            password,
            token_secret,
        ).with_redirect_uri(auth.oauth_redirect_uri.clone()).with_mcp_resource()
            .with_refresh_store(auth.session_policy.clone(),crate::auth::oauth_refresh::storage_root(&workspace_id)?.join("refresh"))?))
    } else {
        None
    };
    let state = ListenerState {
        mcp,
        auth,
        workspace_id,
        workspace_path: workspace_display,
        bind_port: port,
        configured_public_url,
        bearer_token,
        oauth,
        oauth_client_secret,
    };
    // 在返回 Running 之前完成 bind，避免后台任务里的端口冲突被伪装成启动成功。
    let listener = bind_listener(port)?;
    let (shutdown_tx, shutdown_rx) = oneshot::channel();
    let profile_id = state.workspace_id.clone();
    let handle = tauri::async_runtime::spawn(async move {
        let result = serve(listener, port, state, shutdown_rx).await;
        if let Err(err) = &result {
            append_profile_log(
                &profile_id,
                "stderr.log",
                &format!("[mcp] listener stopped: {err}"),
            );
            eprintln!("mcp listener stopped: {err}");
        } else {
            append_profile_log(&profile_id, "stderr.log", "[mcp] listener stopped");
        }
    });
    Ok((shutdown_tx, handle, execution_gate))
}

async fn serve(
    listener: tokio::net::TcpListener,
    port: u16,
    state: ListenerState,
    shutdown: oneshot::Receiver<()>,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let profile_id = state.workspace_id.clone();
    let origin_guard_state = state.clone();
    let app = Router::new()
        .route("/mcp", get(mcp_discovery).post(mcp_post))
        .route(
            "/.well-known/oauth-authorization-server",
            get(oauth_authorization_server_metadata),
        )
        .route(
            "/.well-known/oauth-protected-resource",
            get(oauth_protected_resource_metadata),
        )
        // RFC 9728 path-specific discovery; root remains a compatibility alias.
        .route("/.well-known/oauth-protected-resource/mcp", get(oauth_protected_resource_metadata))
        .route("/oauth/authorize", get(oauth_authorize_get).post(oauth_authorize_post).layer(DefaultBodyLimit::max(8192)))
        .route("/oauth/token", post(oauth_token_post).layer(DefaultBodyLimit::max(8192)))
        .with_state(state)
        .layer(CorsLayer::permissive())
        // The listener is loopback-only but may be browser-reachable through a
        // managed tunnel. Keep non-browser clients compatible (no Origin) while
        // denying foreign browser Origins before MCP/OAuth handlers run.
        .layer(middleware::from_fn_with_state(origin_guard_state, validate_origin));

    append_profile_log(
        &profile_id,
        "stdout.log",
        &format!("[mcp] listening on http://127.0.0.1:{port}/mcp"),
    );
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = shutdown.await;
        })
        .await?;
    Ok(())
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct CanonicalOrigin {
    scheme: String,
    host: String,
    port: u16,
}

fn canonical_origin(value: &str) -> Option<CanonicalOrigin> {
    let value = value.trim();
    if value.is_empty() {
        return None;
    }
    let uri: Uri = value.parse().ok()?;
    let scheme = uri.scheme_str()?.to_ascii_lowercase();
    let default_port = match scheme.as_str() {
        "http" => 80,
        "https" => 443,
        _ => return None,
    };
    let authority = uri.authority()?;
    if authority.as_str().contains('@') {
        return None;
    }
    let host = uri.host()?.trim_matches(|ch| ch == '[' || ch == ']');
    if host.is_empty() {
        return None;
    }
    let port = uri.port_u16().unwrap_or(default_port);
    Some(CanonicalOrigin {
        scheme,
        host: host.to_ascii_lowercase(),
        port,
    })
}

fn origin_allowed(state: &ListenerState, headers: &HeaderMap) -> bool {
    let mut values = headers.get_all(ORIGIN).iter();
    let Some(value) = values.next() else {
        // Non-browser MCP clients normally omit Origin.
        return true;
    };
    if values.next().is_some() {
        return false;
    }
    let Ok(raw) = value.to_str() else {
        return false;
    };
    if raw.trim().is_empty() {
        return true;
    }
    let Some(origin) = canonical_origin(raw) else {
        return false;
    };
    if matches!(origin.host.as_str(), "localhost" | "127.0.0.1" | "::1") {
        // Local browser tooling frequently uses an ephemeral UI port.
        return true;
    }
    let current_public_origin = state.configured_public_url.snapshot();
    canonical_origin(&current_public_origin).is_some_and(|allowed| allowed == origin)
}

fn invalid_origin_response() -> Response {
    (
        StatusCode::FORBIDDEN,
        [(CACHE_CONTROL, "no-store")],
        Json(json!({
            "jsonrpc": "2.0",
            "id": null,
            "error": {
                "code": -32000,
                "message": "Invalid Origin"
            }
        })),
    )
        .into_response()
}

async fn validate_origin(
    State(state): State<ListenerState>,
    request: Request,
    next: Next,
) -> Response {
    if !origin_allowed(&state, request.headers()) {
        append_profile_log(
            &state.workspace_id,
            "mcp-requests.log",
            "[security] rejected request with invalid Origin",
        );
        return invalid_origin_response();
    }
    next.run(request).await
}

fn bind_listener(port: u16) -> Result<tokio::net::TcpListener, String> {
    let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    #[cfg(unix)]
    {
        let socket = tokio::net::TcpSocket::new_v4()
            .map_err(|err| format!("MCP 本地端口 {port} 套接字初始化失败: {err}"))?;
        socket
            .set_reuseaddr(true)
            .map_err(|err| format!("MCP 本地端口 {port} 设置快速重绑定失败: {err}"))?;
        socket
            .bind(addr)
            .map_err(|err| format!("MCP 本地端口 {port} 绑定失败: {err}"))?;
        socket
            .listen(1024)
            .map_err(|err| format!("MCP 本地监听器初始化失败: {err}"))
    }
    #[cfg(not(unix))]
    {
        let listener = std::net::TcpListener::bind(addr)
            .map_err(|err| format!("MCP 本地端口 {port} 绑定失败: {err}"))?;
        listener
            .set_nonblocking(true)
            .map_err(|err| format!("MCP 本地端口 {port} 设置非阻塞失败: {err}"))?;
        tokio::net::TcpListener::from_std(listener)
            .map_err(|err| format!("MCP 本地监听器初始化失败: {err}"))
    }
}

async fn mcp_discovery() -> Response {
    ([(CACHE_CONTROL, "no-store")], Json(mcp_discovery_payload())).into_response()
}

fn mcp_discovery_payload() -> Value {
    json!({
        "name": "coding-tools-mcp",
        "version": env!("CARGO_PKG_VERSION"),
        "protocolVersion": "2025-06-18"
    })
}

fn resolve_oauth_base(state: &ListenerState, headers: &HeaderMap) -> String {
    state.configured_public_url.resolve(headers, state.bind_port)
}

async fn mcp_post(
    State(state): State<ListenerState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = require_mcp_auth(&state, &headers) {
        return response;
    }
    let method = body
        .get("method")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let request_id = body.get("id").cloned().unwrap_or(Value::Null);
    let tool_name = body
        .get("params")
        .and_then(|params| params.get("name"))
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    append_profile_log(
        &state.workspace_id,
        "mcp-requests.log",
        &format!(
            "[rpc] request id={} method={} tool={}",
            request_id, method, tool_name
        ),
    );

    let mut request_ctx = state.mcp.background_snapshot();
    let mut remote = crate::auth::chat::RemoteRequest::unresolved(&state.workspace_id);
    if let Some(oauth) = state.oauth.as_ref() {
        let token = headers.get(axum::http::header::AUTHORIZATION).and_then(|h| h.to_str().ok())
            .and_then(|h| h.strip_prefix("Bearer ")).map(str::trim).unwrap_or("");
        if let Some(principal) = oauth.principal(token, &resolve_oauth_base(&state, &headers)) {
            remote = crate::auth::chat::RemoteRequest::verified(&state.workspace_id,
                &state.workspace_path, principal, &body["params"]["_meta"], &oauth.token_secret);
        }
    }
    request_ctx.remote_request = Some(remote);
    let mcp = Arc::new(request_ctx);
    let profile_id = state.workspace_id.clone();
    let result = tokio::task::spawn_blocking(move || handle_request(&mcp, &body)).await;
    match result {
        Ok(response) => {
            append_profile_log(
                &profile_id,
                "mcp-requests.log",
                &format!("[rpc] completed id={} method={} tool={}", request_id, method, tool_name),
            );
            if tool_name == "exec_command" || tool_name == "exec_health_check" {
                let structured = response
                    .get("result")
                    .and_then(|result| result.get("structuredContent"));
                let status = structured
                    .and_then(|value| value.get("status"))
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let termination_reason = structured
                    .and_then(|value| value.get("termination_reason"))
                    .and_then(Value::as_str)
                    .unwrap_or("");
                let exit_code = structured
                    .and_then(|value| value.get("exit_code"))
                    .map(Value::to_string)
                    .unwrap_or_default();
                let is_error = response
                    .get("result")
                    .and_then(|result| result.get("isError"))
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                append_profile_log(
                    &profile_id,
                    "mcp-requests.log",
                    &format!(
                        "[exec] id={} tool={} is_error={} status={} termination_reason={} exit_code={}",
                        request_id, tool_name, is_error, status, termination_reason, exit_code
                    ),
                );
            }
            Json(response).into_response()
        }
        Err(error) => {
            append_profile_log(
                &profile_id,
                "mcp-requests.log",
                &format!(
                    "[rpc] worker_failed id={} method={} tool={} error={error}",
                    request_id, method, tool_name
                ),
            );
            Json(json!({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Exec RPC worker failed",
                    "data": {
                        "stage": "rpc_worker",
                        "reason": "worker_failed",
                        "retryable": true,
                        "suggestion": "重试请求或重启 MCP 运行时"
                    }
                }
            }))
            .into_response()
        }
    }
}

fn require_mcp_auth(state: &ListenerState, headers: &HeaderMap) -> Option<Response> {
    if state.auth.bearer_enabled() {
        let expected = state.bearer_token.as_deref().unwrap_or("");
        return verify_bearer_header(headers, expected);
    }
    if state.auth.oauth_enabled() {
        if let Some(oauth) = state.oauth.as_ref() {
            let server_url = resolve_oauth_base(state, headers);
            return verify_oauth_bearer_header(headers, oauth, &server_url);
        }
    }
    None
}

async fn oauth_authorization_server_metadata(
    State(state): State<ListenerState>,
    headers: HeaderMap,
) -> Response {
    if !state.auth.oauth_enabled() {
        return oauth_not_configured();
    }
    let base = resolve_oauth_base(&state, &headers);
    let mut metadata=authorization_server_metadata(&base,state.oauth_client_secret.as_deref());
    if state.oauth.as_ref().is_some_and(|o|o.refresh_enabled()) {
        metadata["grant_types_supported"]=json!(["authorization_code","refresh_token"]);
        metadata["scopes_supported"]=json!(["mcp","offline_access"]);
    }
    ([(CACHE_CONTROL,"no-store")],Json(metadata)).into_response()
}

async fn oauth_protected_resource_metadata(
    State(state): State<ListenerState>,
    headers: HeaderMap,
) -> Response {
    if !state.auth.oauth_enabled() {
        return oauth_not_configured();
    }
    let issuer = resolve_oauth_base(&state, &headers);
    let resource = format!("{}/mcp", issuer.trim_end_matches('/'));
    ([(CACHE_CONTROL, "no-store")], Json(protected_resource_metadata(&resource, &issuer))).into_response()
}

async fn oauth_authorize_get(
    State(state): State<ListenerState>,
    Query(params): Query<AuthorizeParams>,
) -> Response {
    let Some(oauth) = state.oauth.as_ref() else {
        return oauth_not_configured();
    };
    authorize_get(
        oauth,
        params,
        None,
    )
}

async fn oauth_authorize_post(
    State(state): State<ListenerState>,
    headers: HeaderMap,
    Form(form): Form<AuthorizeForm>,
) -> Response {
    let Some(oauth) = state.oauth.as_ref() else {
        return oauth_not_configured();
    };
    authorize_post(oauth, form, &resolve_oauth_base(&state, &headers))
}

async fn oauth_token_post(
    State(state): State<ListenerState>,
    headers: HeaderMap,
    Form(form): Form<TokenForm>,
) -> Response {
    let Some(oauth) = state.oauth.as_ref() else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "error": "unsupported_grant_type" })),
        )
            .into_response();
    };
    let oauth=oauth.clone(); let base=resolve_oauth_base(&state,&headers);
    tokio::task::spawn_blocking(move||token_exchange(&oauth,&headers,form,&base)).await.unwrap_or_else(|_| {
        (StatusCode::SERVICE_UNAVAILABLE,[(CACHE_CONTROL,"no-store")],Json(json!({"error":"server_error"}))).into_response()
    })
}

fn oauth_not_configured() -> Response {
    (
        StatusCode::NOT_FOUND,
        [(CACHE_CONTROL, "no-store")],
        Json(json!({ "error": "OAuth not configured" })),
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use axum::http::header::CACHE_CONTROL;
    use axum::response::IntoResponse;

    use super::{bind_listener, mcp_discovery, mcp_discovery_payload};

    #[test]
    fn bind_listener_reports_port_conflict_synchronously() {
        let occupied = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("占用测试端口");
        let port = occupied.local_addr().expect("读取测试端口").port();

        assert!(bind_listener(port).is_err());
    }

    #[tokio::test]
    async fn discovery_reports_the_current_package_version() {
        let discovery = mcp_discovery_payload();

        assert_eq!(discovery["version"], env!("CARGO_PKG_VERSION"));
    }

    #[tokio::test]
    async fn discovery_prevents_stale_tool_catalog_caching() {
        let response = mcp_discovery().await.into_response();

        assert_eq!(response.headers()[CACHE_CONTROL], "no-store");
    }
}
