//! Failure-first safety prerequisites for production dispatch (#81).
#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;

use coding_tools_cloud_gateway::{
    admission::{AdmissionDecision, AdmissionDeny, AdmissionRequest, AdmissionStore, RequestClass, RequestState},
    IdentityError,
};
use serde_json::json;
use std::time::Duration;
use uuid::Uuid;

async fn admitted() -> (projection_support::Harness, AdmissionStore, Uuid) {
    let (h, c) = channel_support::setup().await;
    let session = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &session, 1, 1).await;
    let store = AdmissionStore::new(h.f.store.clone());
    let id = Uuid::new_v4();
    let args = json!({"path": "fixture-only.txt"});
    store.admit(AdmissionRequest {
        request_id: id, conversation: &h.a, scope: "files.read", tool_name: "read_file",
        arguments: &args, class: RequestClass::ReadOnly,
        deadline: projection_support::clock(&h.f).await + 120,
    }).await.unwrap();
    (h, store, id)
}

async fn foreign(h: &projection_support::Harness, id: Uuid) {
    sqlx::query("UPDATE ctm_request_ledger SET connector=$2 WHERE request_id=$1")
        .bind(id).bind(Uuid::new_v4()).execute(&h.f.pool).await.unwrap();
}

async fn state(h: &projection_support::Harness, id: Uuid) -> String {
    sqlx::query_scalar("SELECT state FROM ctm_request_ledger WHERE request_id=$1")
        .bind(id).fetch_one(&h.f.pool).await.unwrap()
}

#[tokio::test]
async fn foreign_connector_cannot_cancel_a_request() {
    let (h, store, id) = admitted().await;
    foreign(&h, id).await;
    assert_eq!(store.cancel(id).await.unwrap_err(), IdentityError::InvalidRequest,
        "DISPATCH_GAP_FOREIGN_CANCEL");
    assert_eq!(state(&h, id).await, "admitted");
}

#[tokio::test]
async fn foreign_connector_cannot_complete_a_request() {
    let (h, store, id) = admitted().await;
    store.begin_execution(id).await.unwrap();
    foreign(&h, id).await;
    assert_eq!(store.complete(id, [3; 32], true).await.unwrap_err(), IdentityError::InvalidRequest,
        "DISPATCH_GAP_FOREIGN_COMPLETE");
    assert_eq!(state(&h, id).await, "running");
}

#[tokio::test]
async fn foreign_expired_request_cannot_be_mutated_by_begin() {
    let (h, store, id) = admitted().await;
    foreign(&h, id).await;
    sqlx::query("UPDATE ctm_request_ledger SET deadline=0 WHERE request_id=$1")
        .bind(id).execute(&h.f.pool).await.unwrap();
    assert_eq!(store.begin_execution(id).await.unwrap_err(), IdentityError::InvalidRequest,
        "DISPATCH_GAP_FOREIGN_BEGIN");
    assert_eq!(state(&h, id).await, "admitted");
}

#[tokio::test]
async fn foreign_connector_cannot_mark_unknown() {
    let (h, store, id) = admitted().await;
    foreign(&h, id).await;
    assert_eq!(store.mark_outcome_unknown(id).await.unwrap_err(), IdentityError::InvalidRequest,
        "DISPATCH_GAP_FOREIGN_UNKNOWN");
    assert_eq!(state(&h, id).await, "admitted");
}

#[tokio::test]
async fn deadline_expiring_behind_channel_lock_cannot_start() {
    let (h, store, id) = admitted().await;
    let deadline = projection_support::clock(&h.f).await + 1;
    sqlx::query("UPDATE ctm_request_ledger SET deadline=$2 WHERE request_id=$1")
        .bind(id).bind(deadline).execute(&h.f.pool).await.unwrap();
    let mut blocker = h.f.pool.begin().await.unwrap();
    sqlx::query("SELECT connector FROM ctm_agent_channel FOR UPDATE")
        .execute(&mut *blocker).await.unwrap();
    let worker = tokio::spawn(async move { store.begin_execution(id).await });
    // Observe an actual database lock waiter; elapsed sleep alone is not setup proof.
    tokio::time::timeout(Duration::from_millis(600), async {
        loop {
            let count: i64 = sqlx::query_scalar(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE 'SELECT * FROM ctm_agent_channel%'")
                .fetch_one(&h.f.pool).await.unwrap();
            if count > 0 { break; }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    }).await.expect("PROBE_SETUP: no actual channel lock waiter");
    while projection_support::clock(&h.f).await < deadline {
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    blocker.commit().await.unwrap();
    let result = tokio::time::timeout(Duration::from_secs(4), worker)
        .await.unwrap().unwrap().unwrap();
    assert_eq!(result.state, RequestState::NotAdmitted, "DISPATCH_GAP_POST_LOCK_DEADLINE");
    assert_eq!(result.decision, AdmissionDecision::Denied(AdmissionDeny::Deadline));
}
