use super::protocol::{self, RpcMessage, WireError};
use crate::{
    admission::{
        AdmissionDecision, AdmissionDeny, AdmissionRequest, AdmissionStore, RequestClass,
        RequestState,
    },
    channel::ChannelController,
    observability::{
        AuthObservation, GatewayObservability, IngressRejection, McpObservation,
    },
    projection::ProjectionDecision,
    IdentityError, IdentityStore, OAuthPrincipal,
};
use axum::{
    body::Bytes,
    extract::{DefaultBodyLimit, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde_json::{json, Value};
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

const MAX_BODY: usize = 65_536;
const TOOL_SCOPE: &str = "files.read";

#[derive(Clone)]
pub struct McpState {
    store: IdentityStore,
    control: ChannelController,
    admission: AdmissionStore,
    observability: GatewayObservability,
}
impl McpState {
    pub fn new(store: IdentityStore, control: ChannelController) -> Self {
        Self::with_observability(store, control, GatewayObservability::default())
    }

    pub fn with_observability(
        store: IdentityStore,
        control: ChannelController,
        observability: GatewayObservability,
    ) -> Self {
        Self {
            admission: AdmissionStore::new(store.clone()),
            store,
            control,
            observability,
        }
    }
}

pub fn routes(store: IdentityStore, control: ChannelController) -> Router {
    routes_with_observability(store, control, GatewayObservability::default())
}

pub fn routes_with_observability(
    store: IdentityStore,
    control: ChannelController,
    observability: GatewayObservability,
) -> Router {
    let path = store.identity().resource_path();
    Router::new()
        .route(&path, post(mcp_post))
        .with_state(McpState::with_observability(store, control, observability))
        .layer(DefaultBodyLimit::max(MAX_BODY))
}

fn safe_json(status: StatusCode, value: Value) -> Response {
    let mut r = (status, Json(value)).into_response();
    r.headers_mut()
        .insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    r.headers_mut()
        .insert(header::PRAGMA, HeaderValue::from_static("no-cache"));
    r.headers_mut().insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    r.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    r
}

fn wire_error(error: WireError, id: Option<&Value>) -> Response {
    let status = StatusCode::from_u16(error.status).unwrap_or(StatusCode::BAD_REQUEST);
    safe_json(status, protocol::error_envelope(&error, id))
}

fn singleton(headers: &HeaderMap, name: &str) -> bool {
    headers.get_all(name).iter().count() <= 1
}

fn accepts_both(raw: &str) -> bool {
    ["application/json", "text/event-stream"]
        .iter()
        .all(|wanted| {
            raw.split(',').any(|part| {
                let mut pieces = part.trim().split(';');
                if !pieces
                    .next()
                    .is_some_and(|m| m.trim().eq_ignore_ascii_case(wanted))
                {
                    return false;
                }
                let mut q = 1.0f32;
                for p in pieces.map(str::trim) {
                    if let Some(v) = p.strip_prefix("q=") {
                        let Ok(parsed) = v.parse::<f32>() else {
                            return false;
                        };
                        if !(0.0..=1.0).contains(&parsed) {
                            return false;
                        }
                        q = parsed;
                    }
                }
                q > 0.0
            })
        })
}

#[derive(Clone, Copy)]
struct BoundaryFailure {
    status: StatusCode,
    code: i64,
    message: &'static str,
    observation: IngressRejection,
}

fn boundary_headers(state: &McpState, headers: &HeaderMap) -> Result<(), BoundaryFailure> {
    for h in [
        "host",
        "origin",
        "authorization",
        "content-type",
        "content-length",
        "transfer-encoding",
        "content-encoding",
        "accept",
        "mcp-protocol-version",
        "mcp-method",
        "mcp-name",
    ] {
        if !singleton(headers, h) {
            let status = if matches!(h, "host" | "origin" | "authorization") {
                StatusCode::FORBIDDEN
            } else {
                StatusCode::BAD_REQUEST
            };
            return Err(BoundaryFailure {
                status,
                code: -32020,
                message: "Duplicate header",
                observation: if matches!(h, "host" | "origin") {
                    IngressRejection::HostOrOrigin
                } else {
                    IngressRejection::Headers
                },
            });
        }
    }
    if headers.get(header::HOST).and_then(|v| v.to_str().ok())
        != Some(state.store.identity().authority())
        || headers.get(header::ORIGIN).is_some_and(|v| {
            !v.to_str()
                .is_ok_and(|s| state.store.identity().allow_origin(s))
        })
    {
        return Err(BoundaryFailure {
            status: StatusCode::FORBIDDEN,
            code: -32600,
            message: "Request rejected",
            observation: IngressRejection::HostOrOrigin,
        });
    }
    if headers.contains_key(header::CONTENT_LENGTH)
        && headers.contains_key(header::TRANSFER_ENCODING)
    {
        return Err(BoundaryFailure {
            status: StatusCode::FORBIDDEN,
            code: -32600,
            message: "Request rejected",
            observation: IngressRejection::Headers,
        });
    }
    let content = headers
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if !content
        .split(';')
        .next()
        .is_some_and(|v| v.trim().eq_ignore_ascii_case("application/json"))
        || headers
            .get(header::CONTENT_ENCODING)
            .is_some_and(|v| v.to_str().ok() != Some("identity"))
    {
        return Err(BoundaryFailure {
            status: StatusCode::UNSUPPORTED_MEDIA_TYPE,
            code: -32600,
            message: "Unsupported content type or encoding",
            observation: IngressRejection::Media,
        });
    }
    let accept = headers
        .get(header::ACCEPT)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("");
    if !accepts_both(accept) {
        return Err(BoundaryFailure {
            status: StatusCode::NOT_ACCEPTABLE,
            code: -32600,
            message: "Unsupported response media types",
            observation: IngressRejection::Media,
        });
    }
    Ok(())
}

#[derive(Clone, Copy)]
enum AuthFailure {
    Invalid,
    Unavailable,
}

async fn authenticate(
    state: &McpState,
    headers: &HeaderMap,
) -> Result<OAuthPrincipal, AuthFailure> {
    let token = headers
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    let Some(token) = token.filter(|v| !v.is_empty() && !v.chars().any(char::is_whitespace)) else {
        return Err(AuthFailure::Invalid);
    };
    state
        .store
        .authenticate_access(token)
        .await
        .map_err(|e| match e {
            IdentityError::InvalidToken | IdentityError::InvalidGrant => AuthFailure::Invalid,
            _ => AuthFailure::Unavailable,
        })
}

fn oauth_challenge(state: &McpState) -> Response {
    let metadata = format!(
        "{}{}",
        state.store.identity().origin(),
        state.store.identity().resource_metadata_path()
    );
    let mut r = safe_json(StatusCode::UNAUTHORIZED, json!({"error":"invalid_token"}));
    let challenge = format!("Bearer resource_metadata=\"{}\", scope=\"mcp\"", metadata);
    if let Ok(v) = HeaderValue::from_str(&challenge) {
        r.headers_mut().insert(header::WWW_AUTHENTICATE, v);
    }
    r
}

fn host_session(message: &RpcMessage) -> Option<&str> {
    message
        .params
        .get("_meta")
        .and_then(Value::as_object)
        .and_then(|m| m.get("openai/session"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|s| !s.is_empty() && s.len() <= 1024 && !s.chars().any(char::is_control))
}

fn denial(code: &str, category: &str, message: &str) -> Value {
    json!({"ok":false,"error":{"code":code,"category":category,"retryable":false,"message":message},"requires_local_action":false})
}
fn permission(code: &str) -> Value {
    let message=match code {
        "CHAT_CONTEXT_REQUIRED"=>"Conversation context is required.",
        "CHAT_SCOPE_REQUIRED"=>"This conversation lacks the required local scope.",
        "CHAT_RECOVERY_REQUIRED"=>"Local workspace authorization requires recovery. Do not retry or request OAuth.",
        "CHAT_AUTHORIZATION_UNAVAILABLE"=>"New cloud-side authorization cannot be created. Use the local approval path when available.",
        _=>"This conversation is not locally approved.",
    };
    denial(code, "permission", message)
}
fn availability(code: &str) -> Value {
    let message=match code {
        "WORKSPACE_OFFLINE"=>"Workspace execution is offline. Do not retry or request OAuth.",
        "EXECUTION_OUTCOME_UNKNOWN"=>"Execution outcome is unknown. Do not resubmit; reconcile the original request.",
        "EXECUTION_BACKPRESSURE"=>"Execution admission is currently full. Do not automatically retry.",
        "REQUEST_EXPIRED"=>"The request deadline expired before local execution.",
        _=>"Local execution dispatch is not connected in this gateway increment. Do not replay the request.",
    };
    denial(code, "availability", message)
}

fn validate_empty_args(message: &RpcMessage) -> Result<Value, Value> {
    match message.params.get("arguments") {
        None => Ok(json!({})),
        Some(Value::Object(m)) if m.is_empty() => Ok(json!({})),
        _ => Err(denial(
            "INVALID_ARGUMENTS",
            "permission",
            "Invalid tool arguments.",
        )),
    }
}
fn validate_authorize_args(message: &RpcMessage) -> Result<(), Value> {
    match message.params.get("arguments") {
        None => Ok(()),
        Some(Value::Object(m)) if m.is_empty() => Ok(()),
        Some(Value::Object(m))
            if m.len() == 1
                && m.get("scopes")
                    .and_then(Value::as_array)
                    .is_some_and(|a| a.len() == 1 && a[0].as_str() == Some(TOOL_SCOPE)) =>
        {
            Ok(())
        }
        _ => Err(denial(
            "INVALID_ARGUMENTS",
            "permission",
            "Invalid tool arguments.",
        )),
    }
}

fn request_uuid(
    state: &McpState,
    binding: &crate::projection::ConversationBinding,
    id: &Value,
) -> Result<Uuid, IdentityError> {
    let bytes = serde_json::to_vec(&(state.store.identity().connector(), binding.as_str(), id))
        .map_err(|_| IdentityError::InvalidRequest)?;
    let digest = state.store.key.digest("mcp-request-id-v1", &bytes);
    let mut raw = [0u8; 16];
    raw.copy_from_slice(&digest[..16]);
    raw[6] = (raw[6] & 0x0f) | 0x50;
    raw[8] = (raw[8] & 0x3f) | 0x80;
    let id = Uuid::from_bytes(raw);
    if id.is_nil() {
        Err(IdentityError::InvalidRequest)
    } else {
        Ok(id)
    }
}
fn unix_now() -> Result<i64, IdentityError> {
    i64::try_from(
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| IdentityError::InvalidRequest)?
            .as_secs(),
    )
    .map_err(|_| IdentityError::InvalidRequest)
}

fn map_projection(d: ProjectionDecision, for_request: bool) -> Value {
    match d {
        ProjectionDecision::Eligible | ProjectionDecision::WorkspaceOffline if for_request => {
            json!({"ok":true,"authorization":{"status":"active"}})
        }
        ProjectionDecision::Eligible | ProjectionDecision::WorkspaceOffline => {
            json!({"ok":true,"authorization":{"status":"active"}})
        }
        ProjectionDecision::RecoveryRequired => permission("CHAT_RECOVERY_REQUIRED"),
        ProjectionDecision::ScopeDenied => permission("CHAT_SCOPE_REQUIRED"),
        ProjectionDecision::AuthorizationUnavailable if for_request => {
            permission("CHAT_AUTHORIZATION_UNAVAILABLE")
        }
        ProjectionDecision::AuthorizationUnavailable => permission("CHAT_AUTHORIZATION_REQUIRED"),
    }
}

async fn business_call(
    state: &McpState,
    principal: &OAuthPrincipal,
    message: &RpcMessage,
) -> Value {
    let Some(name) = message.params.get("name").and_then(Value::as_str) else {
        return permission("INVALID_ARGUMENTS");
    };
    if ![
        "auth_status",
        "request_chat_authorization",
        "workspace_probe",
    ]
    .contains(&name)
    {
        return permission("INVALID_ARGUMENTS");
    }
    let Some(session) = host_session(message) else {
        return permission("CHAT_CONTEXT_REQUIRED");
    };
    let binding = match state.control.conversation_binding(principal, session) {
        Ok(v) => v,
        Err(_) => return permission("CHAT_CONTEXT_REQUIRED"),
    };
    match name {
        "auth_status" => {
            if validate_empty_args(message).is_err() {
                return permission("INVALID_ARGUMENTS");
            }
            match state.control.assess(&binding, TOOL_SCOPE).await {
                Ok(ProjectionDecision::RecoveryRequired)
                    if state.control.is_online().await.ok() == Some(false) =>
                {
                    json!({"ok":true,"authorization":{"status":"active"},"execution":"offline"})
                }
                Ok(d) => map_projection(d, false),
                Err(_) => availability("WORKSPACE_OFFLINE"),
            }
        }
        "request_chat_authorization" => {
            if let Err(v) = validate_authorize_args(message) {
                return v;
            }
            match state.control.assess(&binding, TOOL_SCOPE).await {
                Ok(ProjectionDecision::RecoveryRequired)
                    if state.control.is_online().await.ok() == Some(false) =>
                {
                    json!({"ok":true,"authorization":{"status":"active"},"execution":"offline"})
                }
                Ok(d) => map_projection(d, true),
                Err(_) => permission("CHAT_AUTHORIZATION_UNAVAILABLE"),
            }
        }
        "workspace_probe" => {
            let args = match validate_empty_args(message) {
                Ok(v) => v,
                Err(v) => return v,
            };
            match state.control.assess(&binding, TOOL_SCOPE).await {
                Ok(ProjectionDecision::AuthorizationUnavailable) => {
                    return permission("CHAT_AUTHORIZATION_REQUIRED")
                }
                Ok(ProjectionDecision::ScopeDenied) => return permission("CHAT_SCOPE_REQUIRED"),
                Ok(ProjectionDecision::RecoveryRequired) => {
                    if state.control.is_online().await.ok() == Some(false) {
                        return availability("WORKSPACE_OFFLINE");
                    }
                    return permission("CHAT_RECOVERY_REQUIRED");
                }
                Ok(ProjectionDecision::WorkspaceOffline) => {
                    return availability("WORKSPACE_OFFLINE")
                }
                Err(_) => return availability("WORKSPACE_OFFLINE"),
                Ok(ProjectionDecision::Eligible) => {}
            }
            let Some(external_id) = message.id.as_ref() else {
                return permission("INVALID_ARGUMENTS");
            };
            let request_id = match request_uuid(state, &binding, external_id) {
                Ok(v) => v,
                Err(_) => return permission("INVALID_ARGUMENTS"),
            };
            let deadline = match unix_now()
                .and_then(|n| n.checked_add(30).ok_or(IdentityError::InvalidRequest))
            {
                Ok(v) => v,
                Err(_) => return availability("REQUEST_EXPIRED"),
            };
            let receipt = match state
                .admission
                .admit(AdmissionRequest {
                    request_id,
                    conversation: &binding,
                    scope: TOOL_SCOPE,
                    tool_name: name,
                    arguments: &args,
                    class: RequestClass::ReadOnly,
                    deadline,
                })
                .await
            {
                Ok(r) => r,
                Err(IdentityError::Conflict) => return permission("REQUEST_ID_CONFLICT"),
                Err(_) => return availability("EXECUTION_NOT_CONNECTED"),
            };
            match receipt.decision {
                AdmissionDecision::Denied(AdmissionDeny::Authorization) => {
                    permission("CHAT_AUTHORIZATION_REQUIRED")
                }
                AdmissionDecision::Denied(AdmissionDeny::Scope) => {
                    permission("CHAT_SCOPE_REQUIRED")
                }
                AdmissionDecision::Denied(AdmissionDeny::Recovery) => {
                    permission("CHAT_RECOVERY_REQUIRED")
                }
                AdmissionDecision::Denied(AdmissionDeny::Offline) => {
                    availability("WORKSPACE_OFFLINE")
                }
                AdmissionDecision::Denied(AdmissionDeny::Backpressure) => {
                    availability("EXECUTION_BACKPRESSURE")
                }
                AdmissionDecision::Denied(AdmissionDeny::Deadline) => {
                    availability("REQUEST_EXPIRED")
                }
                AdmissionDecision::ReconcileRequired => availability("EXECUTION_OUTCOME_UNKNOWN"),
                AdmissionDecision::Admitted => {
                    let _ = state.admission.cancel(request_id).await;
                    availability("EXECUTION_NOT_CONNECTED")
                }
                AdmissionDecision::Existing => match receipt.state {
                    RequestState::Running | RequestState::OutcomeUnknown => {
                        availability("EXECUTION_OUTCOME_UNKNOWN")
                    }
                    _ => availability("EXECUTION_NOT_CONNECTED"),
                },
            }
        }
        _ => permission("INVALID_ARGUMENTS"),
    }
}

fn record_business_outcome(observability: &GatewayObservability, data: &Value) {
    let outcome = match data
        .get("error")
        .and_then(Value::as_object)
        .and_then(|error| error.get("category"))
        .and_then(Value::as_str)
    {
        Some("permission") => McpObservation::Permission,
        Some("availability") => McpObservation::Availability,
        Some(_) => McpObservation::ProtocolError,
        None => McpObservation::Success,
    };
    observability.record_mcp(outcome);
}

async fn mcp_post(State(state): State<McpState>, headers: HeaderMap, body: Bytes) -> Response {
    if let Err(e) = boundary_headers(&state, &headers) {
        state
            .observability
            .record_ingress_rejected(e.observation);
        return safe_json(
            e.status,
            json!({"jsonrpc":"2.0","error":{"code":e.code,"message":e.message}}),
        );
    }
    let principal = match authenticate(&state, &headers).await {
        Ok(p) => p,
        Err(AuthFailure::Invalid) => {
            state.observability.record_auth(AuthObservation::Invalid);
            return oauth_challenge(&state);
        }
        Err(AuthFailure::Unavailable) => {
            state
                .observability
                .record_auth(AuthObservation::Unavailable);
            return safe_json(
                StatusCode::SERVICE_UNAVAILABLE,
                json!({"error":"temporarily_unavailable"}),
            )
        }
    };
    let message = match protocol::parse_message(&body) {
        Ok(v) => v,
        Err(e) => {
            state.observability.record_mcp(McpObservation::ProtocolError);
            return wire_error(e, None);
        }
    };
    let version = match protocol::validate_version(&message, &headers) {
        Ok(v) => v,
        Err(e) => {
            state.observability.record_mcp(McpObservation::ProtocolError);
            return wire_error(e, message.id.as_ref());
        }
    };
    match protocol::protocol_result(&message, &version) {
        Ok(Some(value)) => {
            state.observability.record_mcp(McpObservation::Success);
            safe_json(StatusCode::OK, value)
        },
        Ok(None) if message.method == "tools/call" => {
            let data = business_call(&state, &principal, &message).await;
            record_business_outcome(&state.observability, &data);
            safe_json(
                StatusCode::OK,
                json!({"jsonrpc":"2.0","id":message.id,"result":protocol::tool_result(&version,data)}),
            )
        }
        Ok(None) => {
            state.observability.record_mcp(McpObservation::Success);
            safe_json(StatusCode::ACCEPTED, json!({}))
        }
        Err(e) => {
            state.observability.record_mcp(McpObservation::ProtocolError);
            wire_error(e, message.id.as_ref())
        },
    }
}
