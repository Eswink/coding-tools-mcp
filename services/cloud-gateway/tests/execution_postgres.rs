//! Issue81 transport increment. Native desktop approval is a separate required gate.
#[allow(dead_code)]
mod channel_support;
#[allow(dead_code)]
mod common;
#[allow(dead_code)]
mod execution_wire_support;
#[allow(dead_code)]
mod projection_support;
use execution_wire_support::*;
use serde_json::json;
use std::time::Duration;

#[tokio::test]
async fn workspace_probe_reaches_the_authenticated_peer_and_reconciles_once() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    let ack = ready(&mut p, 3).await;
    let task = s.call(900, "host-session-A");
    let wire = read(&mut p).await;
    assert_eq!(wire["type"], "execution_request");
    let req = &wire["request"];
    assert_eq!(req["binding"]["peer"], ack["peer"]);
    assert_eq!(req["binding"]["tool"], "workspace_probe");
    assert_eq!(req["binding"]["scope"], "files.read");
    assert_eq!(req["arguments"], json!({}));
    write(&mut p,&json!({"type":"execution_reply","seq":4,"reply":{"binding":req["binding"],"result":{"ok":true,"probe":"actual-peer-roundtrip"}}})).await;
    assert_eq!(read(&mut p).await["type"], "execution_reply_ack");
    let result = task.await.unwrap();
    assert_eq!(
        result["ok"], true,
        "EXECUTION_BRIDGE_MISSING: routed result discarded"
    );
    assert_eq!(result["probe"], "actual-peer-roundtrip");
    let id = req["binding"]["request_id"].as_str().unwrap();
    let row:(String,Option<bool>,Option<Vec<u8>>)=sqlx::query_as("SELECT state,result_ok,result_hash FROM ctm_request_ledger WHERE request_id=$1::text::uuid").bind(id).fetch_one(&s.h.f.pool).await.unwrap();
    assert_eq!(row.0, "completed");
    assert_eq!(row.1, Some(true));
    assert_eq!(row.2.unwrap().len(), 32);
    let repeat = s.call(900, "host-session-A").await.unwrap();
    assert_ne!(
        repeat["ok"], true,
        "completed result is not persisted or replayed"
    );
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err(),
        "duplicate must not send a second command"
    );
}

#[tokio::test]
async fn execution_readiness_does_not_mint_a_local_grant() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    ready(&mut p, 1).await;
    let r = s.call(901, "host-session-A").await.unwrap();
    assert_eq!(r["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger")
        .fetch_one(&s.h.f.pool)
        .await
        .unwrap();
    assert_eq!(count, 0);
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err()
    );
}
#[tokio::test]
async fn recovery_only_peers_never_receive_an_execution_payload() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    let r = s.call(902, "host-session-A").await.unwrap();
    assert_eq!(r["error"]["code"], "EXECUTION_NOT_CONNECTED");
    let state: String = sqlx::query_scalar("SELECT state FROM ctm_request_ledger")
        .fetch_one(&s.h.f.pool)
        .await
        .unwrap();
    assert_eq!(state, "cancelled");
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err()
    );
}
#[tokio::test]
async fn foreign_conversation_is_denied_before_route_availability() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let r = s.call(903, "host-session-B").await.unwrap();
    assert_eq!(r["error"]["code"], "CHAT_AUTHORIZATION_REQUIRED");
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err()
    );
}
#[tokio::test]
async fn lost_reply_becomes_unknown_and_is_not_replayed_on_reconnect() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let task = s.call(904, "host-session-A");
    read(&mut p).await;
    p.close(None).await.unwrap();
    let r = task.await.unwrap();
    assert_eq!(r["error"]["code"], "EXECUTION_OUTCOME_UNKNOWN");
    let mut next = s.connect().await;
    s.project(&mut next, 1, 2).await;
    ready(&mut next, 3).await;
    let r = s.call(904, "host-session-A").await.unwrap();
    assert_eq!(r["error"]["code"], "EXECUTION_OUTCOME_UNKNOWN");
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut next))
            .await
            .is_err()
    );
}
#[tokio::test]
async fn mismatched_reply_authority_is_never_returned_or_committed() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let task = s.call(905, "host-session-A");
    let mut binding = read(&mut p).await["request"]["binding"].clone();
    binding["authority_epoch"] = json!(99);
    write(&mut p,&json!({"type":"execution_reply","seq":4,"reply":{"binding":binding,"result":{"ok":true,"leak":"must-not-be-returned"}}})).await;
    let r = task.await.unwrap();
    assert_eq!(r["error"]["code"], "EXECUTION_OUTCOME_UNKNOWN");
    assert!(!r.to_string().contains("must-not-be-returned"));
    let count: i64 =
        sqlx::query_scalar("SELECT count(*) FROM ctm_request_ledger WHERE state='completed'")
            .fetch_one(&s.h.f.pool)
            .await
            .unwrap();
    assert_eq!(count, 0);
}
#[tokio::test]
async fn heartbeat_is_processed_while_a_tool_reply_is_pending() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let task = s.call(906, "host-session-A");
    let wire = read(&mut p).await;
    write(&mut p, &json!({"type":"heartbeat","seq":4})).await;
    assert_eq!(read(&mut p).await["type"], "heartbeat_ack");
    write(&mut p,&json!({"type":"execution_reply","seq":5,"reply":{"binding":wire["request"]["binding"],"result":{"ok":true}}})).await;
    assert_eq!(read(&mut p).await["type"], "execution_reply_ack");
    assert_eq!(task.await.unwrap()["ok"], true);
}
#[tokio::test]
async fn newer_socket_fences_old_replies_without_losing_the_new_route() {
    let s = Harness::start().await;
    let mut old = s.connect().await;
    s.project(&mut old, 1, 1).await;
    ready(&mut old, 3).await;
    let first = s.call(907, "host-session-A");
    let wire = read(&mut old).await;
    let mut new = s.connect().await;
    s.project(&mut new, 1, 2).await;
    ready(&mut new, 3).await;
    write(&mut old,&json!({"type":"execution_reply","seq":4,"reply":{"binding":wire["request"]["binding"],"result":{"ok":true}}})).await;
    assert_eq!(
        first.await.unwrap()["error"]["code"],
        "EXECUTION_OUTCOME_UNKNOWN"
    );
    let second = s.call(908, "host-session-A");
    let wire = read(&mut new).await;
    write(&mut new,&json!({"type":"execution_reply","seq":4,"reply":{"binding":wire["request"]["binding"],"result":{"ok":true}}})).await;
    read(&mut new).await;
    assert_eq!(second.await.unwrap()["ok"], true);
}
#[tokio::test]
async fn post_dispatch_projection_revocation_blocks_result_disclosure() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let task = s.call(909, "host-session-A");
    let wire = read(&mut p).await;
    sqlx::query("UPDATE ctm_grant_projection SET reconciled=false")
        .execute(&s.h.f.pool)
        .await
        .unwrap();
    write(&mut p,&json!({"type":"execution_reply","seq":4,"reply":{"binding":wire["request"]["binding"],"result":{"ok":true,"secret":"revoked-output"}}})).await;
    read(&mut p).await;
    let r = task.await.unwrap();
    assert_eq!(r["error"]["code"], "EXECUTION_OUTCOME_UNKNOWN");
    assert!(!r.to_string().contains("revoked-output"));
}
#[tokio::test]
async fn gateway_restart_fences_running_rows_without_replaying_them() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let task = s.call(910, "host-session-A");
    read(&mut p).await;
    let _new =
        coding_tools_cloud_gateway::channel::ChannelController::activate(s.h.f.store.clone())
            .await
            .unwrap();
    let state: String = sqlx::query_scalar("SELECT state FROM ctm_request_ledger")
        .fetch_one(&s.h.f.pool)
        .await
        .unwrap();
    assert_eq!(state, "outcome_unknown");
    p.close(None).await.unwrap();
    assert_eq!(
        task.await.unwrap()["error"]["code"],
        "EXECUTION_OUTCOME_UNKNOWN"
    );
}

#[tokio::test]
async fn rejected_duplicate_claim_cannot_poison_the_winning_request() {
    use coding_tools_cloud_gateway::{admission::*, execution::*};
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let first = s.call(920, "host-session-A");
    let wire = read(&mut p).await;
    let request: ExecutionRequest = serde_json::from_value(wire["request"].clone()).unwrap();
    let duplicate =
        s.c.dispatch_admitted(AdmissionRequest {
            request_id: request.binding.request_id,
            conversation: &s.h.a,
            scope: &request.binding.scope,
            tool_name: &request.binding.tool,
            arguments: &request.arguments,
            class: RequestClass::ReadOnly,
            deadline: request.binding.deadline,
        })
        .await;
    assert_eq!(duplicate.unwrap_err(), DispatchError::Rejected);
    // Observe for a bounded period so an erroneously spawned Drop cleanup runs.
    let until = tokio::time::Instant::now() + Duration::from_millis(200);
    loop {
        let row: String =
            sqlx::query_scalar("SELECT state FROM ctm_request_ledger WHERE request_id=$1")
                .bind(request.binding.request_id)
                .fetch_one(&s.h.f.pool)
                .await
                .unwrap();
        assert_eq!(row, "running", "DUPLICATE_CLAIM_MUTATED_RUNNING_REQUEST");
        if tokio::time::Instant::now() >= until {
            break;
        }
        tokio::time::sleep(Duration::from_millis(5)).await;
    }
    write(
        &mut p,
        &json!({"type":"execution_reply","seq":4,"reply":{
            "binding":request.binding,"result":{"ok":true,"owner":"first"}
        }}),
    )
    .await;
    read(&mut p).await;
    assert_eq!(first.await.unwrap()["owner"], "first");
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err()
    );
}

#[tokio::test]
async fn completed_dispatch_tombstone_survives_terminal_cleanup() {
    use coding_tools_cloud_gateway::admission::AdmissionStore;
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let first = s.call(921, "host-session-A");
    let wire = read(&mut p).await;
    let id: uuid::Uuid =
        serde_json::from_value(wire["request"]["binding"]["request_id"].clone()).unwrap();
    write(
        &mut p,
        &json!({"type":"execution_reply","seq":4,"reply":{
            "binding":wire["request"]["binding"],"result":{"ok":true}
        }}),
    )
    .await;
    read(&mut p).await;
    assert_eq!(first.await.unwrap()["ok"], true);
    sqlx::query("UPDATE ctm_request_ledger SET updated_at=1 WHERE request_id=$1")
        .bind(id)
        .execute(&s.h.f.pool)
        .await
        .unwrap();
    let store = AdmissionStore::new(s.h.f.store.clone());
    assert_eq!(
        store.purge_terminal_before(2, 100).await.unwrap(),
        0,
        "DISPATCH_TOMBSTONE_REMOVED_ALLOWING_REPLAY"
    );
    let retry = s.call(921, "host-session-A").await.unwrap();
    assert_ne!(retry["ok"], true);
    assert!(
        tokio::time::timeout(Duration::from_millis(100), read(&mut p))
            .await
            .is_err()
    );
}

#[tokio::test]
async fn older_cleanup_and_marker_downgrade_cannot_erase_dispatch_identity() {
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let first = s.call(922, "host-session-A");
    let wire = read(&mut p).await;
    let id: uuid::Uuid =
        serde_json::from_value(wire["request"]["binding"]["request_id"].clone()).unwrap();
    write(
        &mut p,
        &json!({"type":"execution_reply","seq":4,"reply":{
            "binding":wire["request"]["binding"],"result":{"ok":true}
        }}),
    )
    .await;
    read(&mut p).await;
    assert_eq!(first.await.unwrap()["ok"], true);
    assert_eq!(
        sqlx::query("DELETE FROM ctm_request_ledger WHERE request_id=$1")
            .bind(id)
            .execute(&s.h.f.pool)
            .await
            .unwrap()
            .rows_affected(),
        0
    );
    assert!(sqlx::query(
        "UPDATE ctm_request_ledger SET dispatch_claimed=false WHERE request_id=$1"
    )
    .bind(id)
    .execute(&s.h.f.pool)
    .await
    .is_err());
    assert!(
        sqlx::query("UPDATE ctm_request_ledger SET deadline=deadline+1 WHERE request_id=$1")
            .bind(id)
            .execute(&s.h.f.pool)
            .await
            .is_err()
    );
    let state: String =
        sqlx::query_scalar("SELECT state FROM ctm_request_ledger WHERE request_id=$1")
            .bind(id)
            .fetch_one(&s.h.f.pool)
            .await
            .unwrap();
    assert_eq!(state, "completed");
}

/// Issue #173: the caller must never observe EXECUTION_OUTCOME_UNKNOWN while the
/// ledger still says `running`. The race window is forced deterministically: on
/// this current-thread runtime, the instant `dispatch_admitted` returns, the
/// runtime thread is blocked while an independent connection reads the ledger,
/// so a detached (spawned) cleanup task cannot run before the observation.
#[tokio::test]
async fn lost_reply_unknown_is_durable_before_dispatch_returns() {
    use coding_tools_cloud_gateway::{admission::*, execution::*};
    let s = Harness::start().await;
    let mut p = s.connect().await;
    s.project(&mut p, 1, 1).await;
    ready(&mut p, 3).await;
    let schema: String = sqlx::query_scalar("SELECT current_schema()")
        .fetch_one(&s.h.f.pool)
        .await
        .unwrap();
    let id = uuid::Uuid::new_v4();
    let args = json!({});
    let deadline = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
        + 30;
    let request = || AdmissionRequest {
        request_id: id,
        conversation: &s.h.a,
        scope: "files.read",
        tool_name: "workspace_probe",
        arguments: &args,
        class: RequestClass::ReadOnly,
        deadline,
    };
    let receipt = AdmissionStore::new(s.h.f.store.clone())
        .admit(request())
        .await
        .unwrap();
    assert_eq!(receipt.decision, AdmissionDecision::Admitted);
    let dispatch = s.c.dispatch_admitted(request());
    tokio::pin!(dispatch);
    let peer = async {
        let wire = read(&mut p).await;
        assert_eq!(wire["request"]["binding"]["request_id"], id.to_string());
        // The Agent received the command; its reply is lost with the socket.
        p.close(None).await.unwrap();
        std::future::pending::<()>().await
    };
    let result = tokio::select! {
        biased;
        r = &mut dispatch => r,
        _ = peer => unreachable!(),
    };
    assert_eq!(result.unwrap_err(), DispatchError::Unknown);
    // No await between the return above and this blocking observation.
    let observed = std::thread::spawn(move || {
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(async move {
                use sqlx::Connection;
                let dsn = std::env::var("TEST_DATABASE_URL").unwrap();
                let mut c = sqlx::PgConnection::connect(&dsn).await.unwrap();
                sqlx::query(&format!("SET search_path TO {schema}"))
                    .execute(&mut c)
                    .await
                    .unwrap();
                let state: String =
                    sqlx::query_scalar("SELECT state FROM ctm_request_ledger WHERE request_id=$1")
                        .bind(id)
                        .fetch_one(&mut c)
                        .await
                        .unwrap();
                state
            })
    })
    .join()
    .unwrap();
    assert_eq!(
        observed, "outcome_unknown",
        "UNKNOWN_RETURNED_BEFORE_LEDGER_FENCED: ledger must already record outcome_unknown"
    );
}
