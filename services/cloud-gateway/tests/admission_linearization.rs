//! Actual PostgreSQL lock-wait and retry boundaries, not a mocked clock/store.
#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod projection_support;
use coding_tools_cloud_gateway::{admission::*, IdentityError};
use serde_json::{json, Value};
use std::time::Duration;
use uuid::Uuid;

fn input<'a>(
    h: &'a projection_support::Harness,
    id: Uuid,
    args: &'a Value,
    deadline: i64,
) -> AdmissionRequest<'a> {
    AdmissionRequest {
        request_id: id,
        conversation: &h.a,
        scope: "files.read",
        tool_name: "read_file",
        arguments: args,
        class: RequestClass::ReadOnly,
        deadline,
    }
}
async fn near_deadline(h: &projection_support::Harness) -> i64 {
    // Start early in a real database second: the lock is held across expiry
    // without getting close to the production two-second lock timeout.
    loop {
        let ms: i64 =
            sqlx::query_scalar("SELECT floor(extract(epoch FROM clock_timestamp())*1000)::bigint")
                .fetch_one(&h.f.pool)
                .await
                .unwrap();
        if ms.rem_euclid(1000) < 250 {
            return ms / 1000 + 1;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}
async fn past_deadline(h: &projection_support::Harness, deadline: i64) {
    while projection_support::clock(&h.f).await < deadline {
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
}

async fn hold_until_expired<F>(
    h: &projection_support::Harness,
    holder: i32,
    deadline: i64,
    pending: &mut F,
) where
    F: std::future::Future<Output = Result<AdmissionReceipt, IdentityError>> + Unpin,
{
    // A sleeping/unpolled future is not evidence of a database lock wait.
    // Drive the real request while observing its blocker, then across expiry.
    let blocked = async {
        loop {
            let waiting: bool = sqlx::query_scalar(
                "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE $1 = ANY(pg_blocking_pids(pid)))",
            )
            .bind(holder)
            .fetch_one(&h.f.pool)
            .await
            .unwrap();
            if waiting {
                break;
            }
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    };
    tokio::select! {
        result = &mut *pending => panic!("PROBE_SETUP: request completed before observed channel lock: {result:?}"),
        result = tokio::time::timeout(Duration::from_secs(1), blocked) => result.expect("PROBE_SETUP: no actual channel blocker observed"),
    }
    tokio::select! {
        result = &mut *pending => panic!("PROBE_SETUP: request completed while channel lock still held: {result:?}"),
        _ = past_deadline(h, deadline) => {},
    }
}

#[tokio::test]
async fn admission_rechecks_deadline_after_channel_lock_wait() {
    let (h, c) = channel_support::setup().await;
    let s = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &s, 1, 1).await;
    let store = AdmissionStore::new(h.f.store.clone());
    let mut held = h.f.pool.begin().await.unwrap();
    let holder: i32 = sqlx::query_scalar("SELECT pg_backend_pid()")
        .fetch_one(&mut *held)
        .await
        .unwrap();
    sqlx::query("SELECT connector FROM ctm_agent_channel FOR UPDATE")
        .fetch_all(&mut *held)
        .await
        .unwrap();
    let deadline = near_deadline(&h).await;
    let args = json!({"path":"fixture.txt"});
    let mut pending = Box::pin(store.admit(input(&h, Uuid::new_v4(), &args, deadline)));
    hold_until_expired(&h, holder, deadline, &mut pending).await;
    held.commit().await.unwrap();
    let result = pending.await.unwrap();
    assert_eq!(
        result.decision,
        AdmissionDecision::Denied(AdmissionDeny::Deadline),
        "ADMITTED_AFTER_LOCKED_DEADLINE"
    );
}

#[tokio::test]
async fn legacy_begin_rechecks_deadline_after_channel_lock_wait() {
    let (h, c) = channel_support::setup().await;
    let s = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &s, 1, 1).await;
    let store = AdmissionStore::new(h.f.store.clone());
    let deadline = near_deadline(&h).await;
    let args = json!({"path":"fixture.txt"});
    let id = Uuid::new_v4();
    assert_eq!(
        store
            .admit(input(&h, id, &args, deadline))
            .await
            .unwrap()
            .decision,
        AdmissionDecision::Admitted
    );
    let mut held = h.f.pool.begin().await.unwrap();
    let holder: i32 = sqlx::query_scalar("SELECT pg_backend_pid()")
        .fetch_one(&mut *held)
        .await
        .unwrap();
    sqlx::query("SELECT connector FROM ctm_agent_channel FOR UPDATE")
        .fetch_all(&mut *held)
        .await
        .unwrap();
    let mut pending = Box::pin(store.begin_execution(id));
    hold_until_expired(&h, holder, deadline, &mut pending).await;
    held.commit().await.unwrap();
    assert_eq!(
        pending.await.unwrap().decision,
        AdmissionDecision::Denied(AdmissionDeny::Deadline),
        "BEGAN_AFTER_LOCKED_DEADLINE"
    );
}

#[tokio::test]
async fn expired_exact_retry_reconciles_instead_of_becoming_a_fresh_request() {
    let (h, c) = channel_support::setup().await;
    let s = channel_support::attach(&h, &c).await;
    channel_support::project(&h, &c, &s, 1, 1).await;
    let store = AdmissionStore::new(h.f.store.clone());
    let deadline = near_deadline(&h).await;
    let id = Uuid::new_v4();
    let args = json!({"path":"fixture.txt"});
    store.admit(input(&h, id, &args, deadline)).await.unwrap();
    store.begin_execution(id).await.unwrap();
    store.complete(id, [7; 32], true).await.unwrap();
    past_deadline(&h, deadline).await;
    let result = store.admit(input(&h, id, &args, deadline)).await;
    assert!(
        result.is_ok(),
        "EXPIRED_RETRY_LOST_DURABLE_RECONCILIATION: {result:?}"
    );
    assert_eq!(result.unwrap().state, RequestState::Completed);
    assert_eq!(
        store
            .admit(input(&h, id, &json!({"path":"different"}), deadline))
            .await
            .unwrap_err(),
        IdentityError::Conflict
    );
}
