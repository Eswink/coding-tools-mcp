//! Independent client/server codecs must agree without sharing authority objects.
use coding_tools_cloud_agent as client;
use coding_tools_cloud_gateway as server;
use serde_json::{json, Value};
use uuid::Uuid;
fn request() -> Value {
    let args = json!({"path":"fixture","nested":{"b":2,"a":1}});
    json!({"binding":{
        "request_id":Uuid::new_v4(),"peer":{"connector":Uuid::new_v4(),"device":Uuid::new_v4(),
        "device_epoch":1,"gateway_boot":Uuid::new_v4(),"channel_session":Uuid::new_v4(),"channel_generation":1},
        "grant_id":Uuid::new_v4(),"grant_revision":1,"authority_epoch":1,
        "conversation":"BwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwcHBwc",
        "scope":"files.read","tool":"read_file",
        "arguments_hash":server::admission::canonical_digest(&args,4096).unwrap(),"deadline":120},
        "arguments":args})
}
#[test]
fn client_server_execution_binding_roundtrip_is_byte_equivalent() {
    let input = request();
    let a: client::execution::ExecutionRequest = serde_json::from_value(input.clone()).unwrap();
    let b: server::execution::ExecutionRequest = serde_json::from_value(input).unwrap();
    assert_eq!(
        serde_json::to_vec(&a).unwrap(),
        serde_json::to_vec(&b).unwrap()
    );
    a.validate_at(&a.binding.peer, 100).unwrap();
    b.validate_at(&b.binding.peer, 100).unwrap();
    let result = json!({"ok":true,"data":{"z":1,"a":[true,null]}});
    let ra = client::execution::ExecutionReply {
        binding: a.binding.clone(),
        result: result.clone(),
    };
    let rb = server::execution::ExecutionReply {
        binding: b.binding.clone(),
        result,
    };
    assert_eq!(
        ra.validate_for(&a.binding, 100).unwrap(),
        rb.validate_for(&b.binding, 100).unwrap()
    );
}
#[test]
fn client_server_reject_the_same_stale_forged_and_oversize_requests() {
    for mode in 0..9 {
        let mut value = request();
        match mode {
            0 => value["binding"]["deadline"] = json!(100),
            1 => value["binding"]["peer"]["channel_generation"] = json!(0),
            2 => value["binding"]["scope"] = json!("host.root"),
            3 => value["binding"]["conversation"] = json!("a".repeat(43)),
            4 => value["arguments"]["path"] = json!("changed"),
            5 => value["binding"]["grant_id"] = json!(Uuid::nil()),
            6 => value["arguments"] = json!({"huge":"x".repeat(4096)}),
            7 => value["binding"]["grant_revision"] = json!(0),
            _ => value["binding"]["tool"] = json!("bad\nname"),
        }
        let a: client::execution::ExecutionRequest = serde_json::from_value(value.clone()).unwrap();
        let b: server::execution::ExecutionRequest = serde_json::from_value(value).unwrap();
        assert!(a.validate_at(&a.binding.peer, 100).is_err(), "{mode}");
        assert!(b.validate_at(&b.binding.peer, 100).is_err(), "{mode}");
    }
}
#[test]
fn client_server_scopes_domains_and_frame_bounds_match() {
    assert_eq!(client::grant::LOCAL_SCOPES, server::grant::LOCAL_SCOPES);
    assert_eq!(client::channel::SUBPROTOCOL, server::channel::SUBPROTOCOL);
    assert_eq!(client::channel::MAX_MESSAGE, server::channel::MAX_MESSAGE);
    assert_eq!(client::channel::AUTH_SECONDS, server::channel::AUTH_SECONDS);
    assert_eq!(
        client::channel::connect_message(b"fixture").unwrap(),
        server::channel::connect_message(b"fixture").unwrap()
    );
    assert_eq!(
        client::projection::projection_message(b"fixture").unwrap(),
        server::projection::projection_message(b"fixture").unwrap()
    );
    assert_eq!(
        client::execution::MAX_EXECUTION_ARGUMENTS,
        server::execution::MAX_EXECUTION_ARGUMENTS
    );
    assert_eq!(
        client::execution::MAX_EXECUTION_RESULT,
        server::execution::MAX_EXECUTION_RESULT
    );
}
#[test]
fn client_server_strict_codecs_reject_added_authority_fields() {
    let mut value = request();
    value["authorized"] = json!(true);
    assert!(serde_json::from_value::<client::execution::ExecutionRequest>(value.clone()).is_err());
    assert!(serde_json::from_value::<server::execution::ExecutionRequest>(value).is_err());
    for value in [
        json!({"type":"heartbeat","seq":1}),
        json!({"type":"execution_ready","seq":2,"version":1}),
    ] {
        let a: client::channel::ControlMessage = serde_json::from_value(value.clone()).unwrap();
        let b: server::channel::ControlMessage = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(
            serde_json::to_value(a).unwrap(),
            serde_json::to_value(b).unwrap()
        );
        let mut bad = value;
        bad["grant"] = json!("forged");
        assert!(serde_json::from_value::<client::channel::ControlMessage>(bad.clone()).is_err());
        assert!(serde_json::from_value::<server::channel::ControlMessage>(bad).is_err());
    }
}
