//! Issue81 transport increment. Native desktop approval is a separate required gate.
#[allow(dead_code)] mod common;
#[allow(dead_code)] mod projection_support;
#[allow(dead_code)] mod channel_support;
#[allow(dead_code)] mod execution_wire_support;
use execution_wire_support::*;
use serde_json::json;
use std::time::Duration;

#[tokio::test]
async fn workspace_probe_reaches_the_authenticated_peer_and_reconciles_once() {
    let s=Harness::start().await;
    let mut p=s.connect().await;
    s.project(&mut p,1,1).await;
    let ack=ready(&mut p,3).await;
    let task=s.call(900,"host-session-A");
    let wire=read(&mut p).await;
    assert_eq!(wire["type"],"execution_request");
    let req=&wire["request"];
    assert_eq!(req["binding"]["peer"],ack["peer"]);
    assert_eq!(req["binding"]["tool"],"workspace_probe");
    assert_eq!(req["binding"]["scope"],"files.read");
    assert_eq!(req["arguments"],json!({}));
    write(&mut p,&json!({"type":"execution_reply","seq":4,"reply":{"binding":req["binding"],"result":{"ok":true,"probe":"actual-peer-roundtrip"}}})).await;
    assert_eq!(read(&mut p).await["type"],"execution_reply_ack");
    let result=task.await.unwrap();
    assert_eq!(result["ok"],true,"EXECUTION_BRIDGE_MISSING: routed result discarded");
    assert_eq!(result["probe"],"actual-peer-roundtrip");
    let id=req["binding"]["request_id"].as_str().unwrap();
    let row:(String,Option<bool>,Option<Vec<u8>>)=sqlx::query_as("SELECT state,result_ok,result_hash FROM ctm_request_ledger WHERE request_id=$1::text::uuid").bind(id).fetch_one(&s.h.f.pool).await.unwrap();
    assert_eq!(row.0,"completed"); assert_eq!(row.1,Some(true)); assert_eq!(row.2.unwrap().len(),32);
    let repeat=s.call(900,"host-session-A").await.unwrap();
    assert_ne!(repeat["ok"],true,"completed result is not persisted or replayed");
    assert!(tokio::time::timeout(Duration::from_millis(100),read(&mut p)).await.is_err(),"duplicate must not send a second command");
}
