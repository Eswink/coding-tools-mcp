use super::*;

pub(super) async fn business_call(
    state: &McpState,
    principal: &OAuthPrincipal,
    message: &RpcMessage,
) -> Value {
    let Some(name) = message.params.get("name").and_then(Value::as_str) else {
        return permission("INVALID_ARGUMENTS");
    };
    let spec = coding_tools_cloud_agent::catalog::tool(name);
    if !matches!(name, "auth_status" | "request_chat_authorization") && spec.is_none() {
        return permission("INVALID_ARGUMENTS");
    }
    let Some(session) = host_session(message) else {
        return permission("CHAT_CONTEXT_REQUIRED");
    };
    let binding = match state.control.conversation_binding(principal, session) {
        Ok(v) => v,
        Err(_) => return permission("CHAT_CONTEXT_REQUIRED"),
    };
    if state.control.has_native_approval_route()
        && matches!(name, "auth_status" | "request_chat_authorization")
    {
        let args = if name == "auth_status" {
            match validate_empty_args(message) {
                Ok(a) => a,
                Err(e) => return e,
            }
        } else {
            if let Err(e) = validate_authorize_args(message) {
                return e;
            }
            message
                .params
                .get("arguments")
                .cloned()
                .unwrap_or_else(|| json!({}))
        };
        let method = if name == "auth_status" {
            crate::approval::ApprovalMethod::Status
        } else {
            crate::approval::ApprovalMethod::Request
        };
        return state
            .control
            .authorization_roundtrip(&binding, method, args)
            .await
            .unwrap_or_else(|_| permission("CHAT_AUTHORIZATION_UNAVAILABLE"));
    }
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
            let requested = message
                .params
                .get("arguments")
                .and_then(|a| a.get("scopes"))
                .and_then(Value::as_array)
                .map(|values| values.iter().filter_map(Value::as_str).collect::<Vec<_>>())
                .unwrap_or_else(|| vec![TOOL_SCOPE]);
            let mut recovery = false;
            for scope in requested {
                match state.control.assess(&binding, scope).await {
                    Ok(ProjectionDecision::Eligible | ProjectionDecision::WorkspaceOffline) => {}
                    Ok(ProjectionDecision::RecoveryRequired) => recovery = true,
                    Ok(d) => return map_projection(d, true),
                    Err(_) => return permission("CHAT_AUTHORIZATION_UNAVAILABLE"),
                }
            }
            if recovery {
                if state.control.is_online().await.ok() == Some(false) {
                    return json!({"ok":true,"authorization":{"status":"active"},"execution":"offline"});
                }
                return permission("CHAT_RECOVERY_REQUIRED");
            }
            json!({"ok":true,"authorization":{"status":"active"}})
        }

        _ => {
            let Some(spec) = spec else {
                return permission("INVALID_ARGUMENTS");
            };
            let args = match spec.arguments(message.params.get("arguments").unwrap_or(&json!({}))) {
                Ok(v) => v,
                Err(_) => return permission("INVALID_ARGUMENTS"),
            };
            let scope = spec.primary_scope(&args);
            let class = if spec.is_mutating(&args) {
                RequestClass::Mutating
            } else {
                RequestClass::ReadOnly
            };
            // Check EVERY required scope before availability and admission. The
            // native host independently repeats this against current authority.
            let mut offline = false;
            let mut recovery = false;
            for required in spec.scopes_for(&args) {
                match state.control.assess(&binding, required).await {
                    Ok(ProjectionDecision::AuthorizationUnavailable) => {
                        return permission("CHAT_AUTHORIZATION_REQUIRED")
                    }
                    Ok(ProjectionDecision::ScopeDenied) => {
                        return permission("CHAT_SCOPE_REQUIRED")
                    }
                    Ok(ProjectionDecision::RecoveryRequired) => recovery = true,
                    Ok(ProjectionDecision::WorkspaceOffline) => offline = true,
                    Err(_) => return permission("CHAT_AUTHORIZATION_UNAVAILABLE"),
                    Ok(ProjectionDecision::Eligible) => {}
                }
            }
            if recovery {
                if state.control.is_online().await.ok() == Some(false) {
                    return availability("WORKSPACE_OFFLINE");
                }
                return permission("CHAT_RECOVERY_REQUIRED");
            }
            if offline {
                return availability("WORKSPACE_OFFLINE");
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
            let requested = AdmissionRequest {
                request_id,
                conversation: &binding,
                scope,
                tool_name: name,
                arguments: &args,
                class,
                deadline,
            };
            let deadline = match state.admission.original_deadline(&requested).await {
                Ok(Some(original)) => original,
                Ok(None) => deadline,
                Err(IdentityError::Conflict) => return permission("REQUEST_ID_CONFLICT"),
                Err(_) => return availability("EXECUTION_OUTCOME_UNKNOWN"),
            };
            let receipt = match state
                .admission
                .admit(AdmissionRequest {
                    request_id,
                    conversation: &binding,
                    scope,
                    tool_name: name,
                    arguments: &args,
                    class,
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
                    match state
                        .control
                        .dispatch_admitted(AdmissionRequest {
                            request_id,
                            conversation: &binding,
                            scope,
                            tool_name: name,
                            arguments: &args,
                            class,
                            deadline,
                        })
                        .await
                    {
                        Ok(result) => result,
                        Err(error) => {
                            if matches!(
                                error,
                                crate::execution::DispatchError::NotConnected
                                    | crate::execution::DispatchError::Backpressure
                            ) {
                                let _ = state.admission.cancel(request_id).await;
                            }
                            availability(error.code())
                        }
                    }
                }
                AdmissionDecision::Existing => match receipt.state {
                    RequestState::Running | RequestState::OutcomeUnknown => {
                        availability("EXECUTION_OUTCOME_UNKNOWN")
                    }
                    _ => availability("EXECUTION_NOT_CONNECTED"),
                },
            }
        }
    }
}
