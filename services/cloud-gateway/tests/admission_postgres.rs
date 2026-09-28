#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use channel_support::{attach, project, setup};
use coding_tools_cloud_gateway::{
    admission::{
        AdmissionDecision, AdmissionDeny, AdmissionRequest, AdmissionStore, RequestClass,
        RequestState, MAX_IN_FLIGHT,
    },
    channel::{ChannelController, ControlMessage, SignedPayload},
    projection::{ExecutionState, ProjectionClaims, ProjectionPhase},
    IdentityError,
};
use serde_json::json;
use uuid::Uuid;

async fn deadline(h: &projection_support::Harness) -> i64 {
    projection_support::clock(&h.f).await + 120
}
fn request<'a>(
    h: &'a projection_support::Harness,
    id: Uuid,
    arguments: &'a serde_json::Value,
    deadline: i64,
) -> AdmissionRequest<'a> {
    AdmissionRequest {
        request_id: id,
        conversation: &h.a,
        scope: "files.read",
        tool_name: "read_file",
        arguments,
        class: RequestClass::ReadOnly,
        deadline,
    }
}
async fn active() -> (
    projection_support::Harness,
    ChannelController,
    coding_tools_cloud_gateway::channel::ChannelSession,
    AdmissionStore,
) {
    let (h, c) = setup().await;
    let s = attach(&h, &c).await;
    project(&h, &c, &s, 1, 1).await;
    let a = AdmissionStore::new(h.f.store.clone());
    (h, c, s, a)
}
async fn project_execution(
    h: &projection_support::Harness,
    c: &ChannelController,
    s: &coding_tools_cloud_gateway::channel::ChannelSession,
    challenge_seq: i64,
    revision: i64,
    execution: ExecutionState,
) {
    let response = c
        .control(
            s,
            ControlMessage::ProjectionChallenge { seq: challenge_seq },
        )
        .await
        .unwrap();
    let at = projection_support::clock(&h.f).await;
    let value = ProjectionClaims {
        version: 1,
        issuer: common::identity().issuer(),
        resource: common::identity().resource(),
        connector: common::identity().connector(),
        device: h.device.id,
        device_epoch: h.device.epoch,
        gateway_boot: serde_json::from_value(response["gateway_boot"].clone()).unwrap(),
        challenge: response["nonce"].as_str().unwrap().into(),
        revision,
        authority_epoch: 1,
        issued_at: at,
        valid_until: response["snapshot_valid_until"].as_i64().unwrap(),
        phase: ProjectionPhase::Active,
        execution,
        grant: Some(h.lease.clone()),
        drained_grant: None,
    };
    let (payload, sig) = h.signed(&value);
    c.control(
        s,
        ControlMessage::Projection {
            seq: challenge_seq + 1,
            proof: SignedPayload {
                payload: URL_SAFE_NO_PAD.encode(payload),
                signature: URL_SAFE_NO_PAD.encode(sig),
            },
        },
    )
    .await
    .unwrap();
}

#[tokio::test]
async fn eligible_request_is_admitted_without_payload_storage() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({"path":"secrets-do-not-store.txt","line":7});
    let result = store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    assert_eq!(result.state, RequestState::Admitted);
    assert_eq!(result.decision, AdmissionDecision::Admitted);
    let row: (i32, i32) = sqlx::query_as(
        "SELECT octet_length(arguments_hash),octet_length(conversation_hash) FROM ctm_request_ledger WHERE request_id=$1",
    )
    .bind(id)
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    assert_eq!(row, (32, 32));
    let columns: Vec<String> = sqlx::query_scalar(
        "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='ctm_request_ledger' ORDER BY column_name",
    )
    .fetch_all(&h.f.pool)
    .await
    .unwrap();
    assert!(!columns
        .iter()
        .any(|c| c.contains("payload") || c.contains("output") || c.contains("arguments_json")));
}

#[tokio::test]
async fn exact_duplicate_reconciles_and_changed_arguments_conflict() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let d = deadline(&h).await;
    let a = json!({"b":2,"a":1});
    store.admit(request(&h, id, &a, d)).await.unwrap();
    let reordered = json!({"a":1,"b":2});
    let duplicate = store.admit(request(&h, id, &reordered, d)).await.unwrap();
    assert_eq!(duplicate.state, RequestState::Admitted);
    assert_eq!(duplicate.decision, AdmissionDecision::Existing);
    let changed = json!({"a":1,"b":3});
    assert_eq!(
        store.admit(request(&h, id, &changed, d)).await.unwrap_err(),
        IdentityError::Conflict
    );
    let count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger WHERE request_id=$1")
            .bind(id)
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
    assert_eq!(count, 1);
}

#[tokio::test]
async fn foreign_conversation_is_non_disclosing_and_never_queued() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    let d = deadline(&h).await;
    let r = store
        .admit(AdmissionRequest {
            request_id: id,
            conversation: &h.b,
            scope: "files.read",
            tool_name: "read_file",
            arguments: &args,
            class: RequestClass::ReadOnly,
            deadline: d,
        })
        .await
        .unwrap();
    assert_eq!(r.state, RequestState::NotAdmitted);
    assert_eq!(
        r.decision,
        AdmissionDecision::Denied(AdmissionDeny::Authorization)
    );
    let active: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM ctm_request_ledger WHERE state IN ('admitted','running')",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    assert_eq!(active, 0);
}

#[tokio::test]
async fn offline_request_is_terminal_not_an_offline_queue() {
    let (h, c, s, store) = active().await;
    project_execution(&h, &c, &s, 3, 2, ExecutionState::Offline).await;
    let id = Uuid::new_v4();
    let args = json!({});
    let d = deadline(&h).await;
    let first = store.admit(request(&h, id, &args, d)).await.unwrap();
    assert_eq!(
        first.decision,
        AdmissionDecision::Denied(AdmissionDeny::Offline)
    );
    project_execution(&h, &c, &s, 5, 3, ExecutionState::Online).await;
    let duplicate = store.admit(request(&h, id, &args, d)).await.unwrap();
    assert_eq!(
        duplicate.decision,
        AdmissionDecision::Denied(AdmissionDeny::Offline)
    );
    let fresh = store
        .admit(request(&h, Uuid::new_v4(), &args, deadline(&h).await))
        .await
        .unwrap();
    assert_eq!(fresh.state, RequestState::Admitted);
}

#[tokio::test]
async fn execution_start_rechecks_pause_and_does_not_dispatch_stale_work() {
    let (h, c, s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    project_execution(&h, &c, &s, 3, 2, ExecutionState::Offline).await;
    let started = store.begin_execution(id).await.unwrap();
    assert_eq!(started.state, RequestState::NotAdmitted);
    assert_eq!(
        started.decision,
        AdmissionDecision::Denied(AdmissionDeny::Offline)
    );
}

#[tokio::test]
async fn reconnect_generation_fences_previously_admitted_request() {
    let (h, c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    let replacement = attach(&h, &c).await;
    project(&h, &c, &replacement, 1, 2).await;
    let result = store.begin_execution(id).await.unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted);
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Recovery)
    );
}

#[tokio::test]
async fn completed_request_is_idempotent_but_conflicting_completion_fails() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    assert_eq!(
        store.begin_execution(id).await.unwrap().state,
        RequestState::Running
    );
    let digest = [3u8; 32];
    assert_eq!(
        store.complete(id, digest, true).await.unwrap().state,
        RequestState::Completed
    );
    assert_eq!(
        store.complete(id, digest, true).await.unwrap().state,
        RequestState::Completed
    );
    assert_eq!(
        store.complete(id, [4u8; 32], true).await.unwrap_err(),
        IdentityError::Conflict
    );
}

#[tokio::test]
async fn lost_result_becomes_unknown_and_is_never_readmitted() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    let d = deadline(&h).await;
    store.admit(request(&h, id, &args, d)).await.unwrap();
    store.begin_execution(id).await.unwrap();
    let unknown = store.mark_outcome_unknown(id).await.unwrap();
    assert_eq!(unknown.state, RequestState::OutcomeUnknown);
    let duplicate = store.admit(request(&h, id, &args, d)).await.unwrap();
    assert_eq!(duplicate.decision, AdmissionDecision::ReconcileRequired);
    assert_eq!(duplicate.state, RequestState::OutcomeUnknown);
}

#[tokio::test]
async fn cancel_before_dispatch_is_known_but_cancel_after_start_is_unknown() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let a = Uuid::new_v4();
    store
        .admit(request(&h, a, &args, deadline(&h).await))
        .await
        .unwrap();
    assert_eq!(
        store.cancel(a).await.unwrap().state,
        RequestState::Cancelled
    );
    let b = Uuid::new_v4();
    store
        .admit(request(&h, b, &args, deadline(&h).await))
        .await
        .unwrap();
    store.begin_execution(b).await.unwrap();
    assert_eq!(
        store.cancel(b).await.unwrap().state,
        RequestState::OutcomeUnknown
    );
}

#[tokio::test]
async fn deadline_expiry_before_dispatch_is_not_unknown() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({});
    let d = deadline(&h).await;
    store.admit(request(&h, id, &args, d)).await.unwrap();
    sqlx::query("UPDATE ctm_request_ledger SET deadline=0 WHERE request_id=$1")
        .bind(id)
        .execute(&h.f.pool)
        .await
        .unwrap();
    let result = store.begin_execution(id).await.unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted);
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Deadline)
    );
}

#[tokio::test]
async fn concurrent_duplicate_submit_creates_one_row() {
    let (h, _c, _s, store) = active().await;
    let id = Uuid::new_v4();
    let args = json!({"path":"same"});
    let d = deadline(&h).await;
    let a = request(&h, id, &args, d);
    let b = request(&h, id, &args, d);
    let (x, y) = tokio::join!(store.admit(a), store.admit(b));
    let x = x.unwrap();
    let y = y.unwrap();
    assert_eq!(x.state, RequestState::Admitted);
    assert_eq!(y.state, RequestState::Admitted);
    assert!(matches!(
        x.decision,
        AdmissionDecision::Admitted | AdmissionDecision::Existing
    ));
    assert!(matches!(
        y.decision,
        AdmissionDecision::Admitted | AdmissionDecision::Existing
    ));
    let count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger WHERE request_id=$1")
            .bind(id)
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
    assert_eq!(count, 1);
}

#[tokio::test]
async fn bounded_backpressure_never_creates_more_active_work() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    for _ in 0..MAX_IN_FLIGHT {
        let r = store
            .admit(request(&h, Uuid::new_v4(), &args, deadline(&h).await))
            .await
            .unwrap();
        assert_eq!(r.state, RequestState::Admitted);
    }
    let overflow = store
        .admit(request(&h, Uuid::new_v4(), &args, deadline(&h).await))
        .await
        .unwrap();
    assert_eq!(
        overflow.decision,
        AdmissionDecision::Denied(AdmissionDeny::Backpressure)
    );
    let active: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM ctm_request_ledger WHERE state IN ('admitted','running')",
    )
    .fetch_one(&h.f.pool)
    .await
    .unwrap();
    assert_eq!(active, MAX_IN_FLIGHT);
}

#[tokio::test]
async fn old_boot_fence_marks_nonterminal_work_unknown_only() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let a = Uuid::new_v4();
    let b = Uuid::new_v4();
    store
        .admit(request(&h, a, &args, deadline(&h).await))
        .await
        .unwrap();
    store
        .admit(request(&h, b, &args, deadline(&h).await))
        .await
        .unwrap();
    store.begin_execution(b).await.unwrap();
    let current: Uuid = sqlx::query_scalar("SELECT gateway_boot FROM ctm_agent_channel")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    let fenced = store.fence_other_boots(Uuid::new_v4()).await.unwrap();
    assert_eq!(fenced, 2);
    assert_eq!(
        store.get(a).await.unwrap().unwrap().state,
        RequestState::OutcomeUnknown
    );
    assert_eq!(
        store.get(b).await.unwrap().unwrap().state,
        RequestState::OutcomeUnknown
    );
    assert_eq!(store.fence_other_boots(current).await.unwrap(), 0);
}

#[tokio::test]
async fn purge_deletes_only_known_terminal_rows() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let completed = Uuid::new_v4();
    store
        .admit(request(&h, completed, &args, deadline(&h).await))
        .await
        .unwrap();
    store.begin_execution(completed).await.unwrap();
    store.complete(completed, [8; 32], true).await.unwrap();
    let unknown = Uuid::new_v4();
    store
        .admit(request(&h, unknown, &args, deadline(&h).await))
        .await
        .unwrap();
    store.begin_execution(unknown).await.unwrap();
    store.mark_outcome_unknown(unknown).await.unwrap();
    sqlx::query("UPDATE ctm_request_ledger SET updated_at=1")
        .execute(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(store.purge_terminal_before(2, 100).await.unwrap(), 1);
    assert!(store.get(completed).await.unwrap().is_none());
    assert_eq!(
        store.get(unknown).await.unwrap().unwrap().state,
        RequestState::OutcomeUnknown
    );
}

#[tokio::test]
async fn invalid_tool_scope_and_deadline_fail_before_ledger_write() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let now = projection_support::clock(&h.f).await;
    for bad in [
        AdmissionRequest {
            request_id: Uuid::new_v4(),
            conversation: &h.a,
            scope: "unknown",
            tool_name: "read_file",
            arguments: &args,
            class: RequestClass::ReadOnly,
            deadline: now + 10,
        },
        AdmissionRequest {
            request_id: Uuid::new_v4(),
            conversation: &h.a,
            scope: "files.read",
            tool_name: "../../bad",
            arguments: &args,
            class: RequestClass::ReadOnly,
            deadline: now + 10,
        },
        AdmissionRequest {
            request_id: Uuid::new_v4(),
            conversation: &h.a,
            scope: "files.read",
            tool_name: "read_file",
            arguments: &args,
            class: RequestClass::ReadOnly,
            deadline: now,
        },
    ] {
        assert_eq!(
            store.admit(bad).await.unwrap_err(),
            IdentityError::InvalidRequest
        );
    }
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
}

#[tokio::test]
async fn valid_but_ungranted_scope_is_denied_without_availability_disclosure() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let result = store
        .admit(AdmissionRequest {
            request_id: Uuid::new_v4(),
            conversation: &h.a,
            scope: "task.read",
            tool_name: "task_context",
            arguments: &args,
            class: RequestClass::ReadOnly,
            deadline: deadline(&h).await,
        })
        .await
        .unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted);
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Scope)
    );
}

#[tokio::test]
async fn device_revocation_between_admit_and_dispatch_fails_closed() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let id = Uuid::new_v4();
    store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    h.f.store.revoke_device(h.device.id).await.unwrap();
    let result = store.begin_execution(id).await.unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted);
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Authorization)
    );
}

#[tokio::test]
async fn disconnected_channel_requires_reconciliation_before_dispatch() {
    let (h, c, s, store) = active().await;
    let args = json!({});
    let id = Uuid::new_v4();
    store
        .admit(request(&h, id, &args, deadline(&h).await))
        .await
        .unwrap();
    c.disconnect(&s).await.unwrap();
    let result = store.begin_execution(id).await.unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted);
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Recovery)
    );
}

#[tokio::test]
async fn excessive_future_deadline_is_rejected_without_a_row() {
    let (h, _c, _s, store) = active().await;
    let args = json!({});
    let now = projection_support::clock(&h.f).await;
    let bad = AdmissionRequest {
        request_id: Uuid::new_v4(),
        conversation: &h.a,
        scope: "files.read",
        tool_name: "read_file",
        arguments: &args,
        class: RequestClass::ReadOnly,
        deadline: now + 301,
    };
    assert_eq!(
        store.admit(bad).await.unwrap_err(),
        IdentityError::InvalidRequest
    );
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&h.f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
}
