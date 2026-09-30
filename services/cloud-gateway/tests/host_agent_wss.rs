//! Exact configured WSS + durable PostgreSQL + actual file read through LocalHost.
//! The callback here is an explicit test host, not a claim of native GUI approval.
mod host_agent_support;
use host_agent_support::Harness;
use std::{sync::atomic::Ordering, time::Duration};
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn authenticated_wss_routes_to_live_host_and_reads_actual_file_once() {
    let h = Harness::start().await;
    let out = h.call(1801, "host-session-A").await;
    assert_eq!(out["ok"], true, "LIVE_HOST_EXECUTION_FAILED: {out}");
    assert_eq!(out["content"], "actual-local-file-canary");
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 1);
    let again = h.call(1801, "host-session-A").await;
    assert_ne!(again["ok"], true);
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 1);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn foreign_conversation_never_reaches_live_host() {
    let h = Harness::start().await;
    let out = h.call(1802, "foreign").await;
    assert_ne!(out["ok"], true);
    assert!(!out.to_string().contains("actual-local-file-canary"));
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 0);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn live_host_heartbeat_and_projection_remain_active_during_execution() {
    let h = Harness::start().await;
    h.host.inner.delay.store(9000, Ordering::SeqCst);
    let out = h.call(1803, "host-session-A").await;
    assert_eq!(out["ok"], true, "LONG_RUNNING_HOST_EXECUTION_FAILED: {out}");
    let seq: i64 = sqlx::query_scalar("SELECT last_seq FROM ctm_agent_channel")
        .fetch_one(&h.pool)
        .await
        .unwrap();
    assert!(
        seq >= 9,
        "heartbeat/projection did not advance during the worker"
    );
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn paused_then_resumed_host_rejects_cached_cloud_authority_until_new_projection() {
    let h = Harness::start().await;
    h.host.inner.online.store(false, Ordering::SeqCst);
    h.host.inner.generation.fetch_add(1, Ordering::SeqCst);
    h.host.inner.online.store(true, Ordering::SeqCst);
    h.host.inner.generation.fetch_add(1, Ordering::SeqCst);
    let out = h.call(1804, "host-session-A").await;
    assert_eq!(out["error"]["code"], "LOCAL_AUTHORITY_CHANGED");
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 0);
    tokio::time::sleep(Duration::from_millis(4400)).await;
    assert_eq!(h.call(1805, "host-session-A").await["ok"], true);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn completed_request_never_reexecutes_after_host_restart() {
    let mut h = Harness::start().await;
    assert_eq!(h.call(1806, "host-session-A").await["ok"], true);
    h.stop_agent().await;
    h.restart().await;
    assert_ne!(h.call(1806, "host-session-A").await["ok"], true);
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 1);
    assert_eq!(h.call(1807, "host-session-A").await["ok"], true);
}
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn host_capacity_rejection_does_not_disconnect_four_inflight_winners() {
    let h = Harness::start().await;
    h.host.inner.delay.store(2500, Ordering::SeqCst);
    let winners = async {
        tokio::join!(
            h.call(1810, "host-session-A"),
            h.call(1811, "host-session-A"),
            h.call(1812, "host-session-A"),
            h.call(1813, "host-session-A")
        )
    };
    let surplus = async {
        let end = tokio::time::Instant::now() + Duration::from_secs(3);
        while h.host.inner.calls.load(Ordering::SeqCst) < 4 {
            assert!(tokio::time::Instant::now() < end);
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        h.call(1814, "host-session-A").await
    };
    let ((a, b, c, d), excess) = tokio::join!(winners, surplus);
    assert_eq!(
        excess["error"]["code"], "LOCAL_EXECUTION_CAPACITY",
        "CAPACITY_DISCONNECTED_VALID_WORK: {excess}"
    );
    for result in [a, b, c, d] {
        assert_eq!(result["ok"], true, "CAPACITY_CANCELLED_WINNER: {result}");
    }
    assert_eq!(h.host.inner.calls.load(Ordering::SeqCst), 4);
}

#[path = "host_agent_protocol_matrix/mod.rs"]
mod protocol_matrix;
