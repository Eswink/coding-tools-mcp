use super::*;
use base64::{engine::general_purpose::STANDARD, Engine};
use protocol::{Cleanup, Event, GuestResult, Kind, Quarantine};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const SOURCE: &str = "0123456789abcdef0123456789abcdef01234567";
const SESSION: &str = "12345678-1234-4234-8234-123456789abc";
const VM: &str = "23456789-1234-4234-8234-123456789abc";
const RUNTIME: &str = "34567890-1234-4234-8234-123456789abc";

fn guest() -> GuestResult {
    let input = format!("ctm-synthetic:{SESSION}");
    let output = input.to_uppercase();
    let cases = ["cmd", "windows-powershell", "node", "pwsh"]
        .map(|name| json!({"name":name,"stdout":"ok","stderr":"","exit_code":23,"passed":true}));
    serde_json::from_value(json!({
        "cases":cases,"input_sha256":format!("{:x}", Sha256::digest(input.as_bytes())),
        "output_sha256":format!("{:x}", Sha256::digest(output.as_bytes())),
        "data_base64":STANDARD.encode(output.as_bytes()),"child_alive":false
    }))
    .unwrap()
}
fn receipt() -> Cleanup {
    let g = guest();
    serde_json::from_value(json!({
        "terminate_ok":true,"whole_vm_exited":true,"exit_ok":true,"close_ok":true,
        "guest_io_joined":true,"quarantine":"written","input_sha256":g.input_sha256,
        "output_sha256":g.output_sha256,"owned_data_retained":true,"network_denial_proven":false,
        "workspace_integration":false,"production_admission":false,"errors":[]
    }))
    .unwrap()
}
fn event(kind: Kind, seq: u64) -> Event {
    let runtime = if matches!(kind, Kind::Prepared | Kind::Creating) {
        ""
    } else {
        RUNTIME
    };
    serde_json::from_value(json!({
        "version":1,"source":SOURCE,"session":SESSION,"seq":seq,"kind":kind,
        "vm_id":VM,"runtime_id":runtime,"guest":(kind == Kind::Guest).then(guest),
        "cleanup":(kind == Kind::Cleanup).then(receipt),"error":""
    }))
    .unwrap()
}
fn frame(raw: impl AsRef<[u8]>) -> Vec<u8> {
    let raw = raw.as_ref();
    let mut bytes = (raw.len() as u32).to_le_bytes().to_vec();
    bytes.extend_from_slice(raw);
    bytes
}
fn decode(value: &Value) -> Result<Event, String> {
    protocol::decode_frame(&frame(serde_json::to_vec(value).unwrap()), &mut 0)
}
fn active() -> Validator {
    let mut v = Validator::new(SOURCE.into(), SESSION.into());
    v.accept(&event(Kind::Prepared, 0)).unwrap();
    v.start_attempted();
    v.accept(&event(Kind::Creating, 1)).unwrap();
    v.accept(&event(Kind::Running, 2)).unwrap();
    v.accept(&event(Kind::Guest, 3)).unwrap();
    v
}
fn completed() -> Validator {
    let mut v = active();
    v.accept(&event(Kind::Cleanup, 4)).unwrap();
    v
}

#[test]
fn wire_roundtrip_requires_every_field_including_nulls() {
    let value = serde_json::to_value(event(Kind::Guest, 3)).unwrap();
    assert_eq!(decode(&value).unwrap().session, SESSION);
    for (kind, paths) in [
        (Kind::Guest, vec!["", "/guest", "/guest/cases/0"]),
        (Kind::Cleanup, vec!["", "/cleanup"]),
    ] {
        let original = serde_json::to_value(event(kind, 3)).unwrap();
        for path in paths {
            let names: Vec<_> = original
                .pointer(path)
                .unwrap()
                .as_object()
                .unwrap()
                .keys()
                .cloned()
                .collect();
            for name in names {
                let mut missing = original.clone();
                missing
                    .pointer_mut(path)
                    .unwrap()
                    .as_object_mut()
                    .unwrap()
                    .remove(&name);
                assert!(decode(&missing).is_err(), "accepted missing {path}/{name}");
            }
        }
    }
}

#[test]
fn duplicate_known_and_nested_fields_are_rejected() {
    let raw = serde_json::to_string(&event(Kind::Guest, 3)).unwrap();
    for (from, to) in [
        ("\"version\":1", "\"version\":1,\"version\":1"),
        (
            "\"child_alive\":false",
            "\"child_alive\":false,\"child_alive\":true",
        ),
        ("\"passed\":true", "\"passed\":true,\"passed\":false"),
    ] {
        assert!(protocol::decode_frame(&frame(raw.replacen(from, to, 1)), &mut 0).is_err());
    }
}

#[test]
fn unknown_fields_trailing_values_and_non_utf8_are_rejected() {
    let mut value = serde_json::to_value(event(Kind::Guest, 3)).unwrap();
    for path in ["", "/guest", "/guest/cases/0"] {
        let mut bad = value.clone();
        bad.pointer_mut(path)
            .unwrap()
            .as_object_mut()
            .unwrap()
            .insert("host_cleanup".into(), json!(true));
        assert!(decode(&bad).is_err());
    }
    value["kind"] = json!("invented");
    assert!(decode(&value).is_err());
    let raw = serde_json::to_string(&event(Kind::Prepared, 0)).unwrap();
    assert!(protocol::decode_frame(&frame(format!("{raw} {{}}")), &mut 0).is_err());
    assert!(protocol::decode_frame(&frame([0xff]), &mut 0).is_err());
}

#[test]
fn length_truncation_and_aggregate_bounds_fail_closed() {
    for raw in [vec![], vec![1], vec![0; 4], frame(vec![b' '; 65_537])] {
        assert!(protocol::decode_frame(&raw, &mut 0).is_err());
    }
    let bytes = frame(serde_json::to_vec(&event(Kind::Prepared, 0)).unwrap());
    assert!(protocol::decode_frame(&bytes[..bytes.len() - 1], &mut 0).is_err());
    let mut total = protocol::MAX_TOTAL - bytes.len();
    assert!(protocol::decode_frame(&bytes, &mut total).is_ok());
    assert_eq!(total, protocol::MAX_TOTAL);
    assert!(protocol::decode_frame(&bytes, &mut total).is_err());
    assert!(protocol::read_event(&mut std::io::Cursor::new([1, 0]), &mut 0).is_err());
}

#[test]
fn nesting_and_output_bounds_do_not_count_brackets_inside_strings() {
    let mut value = serde_json::to_value(event(Kind::Guest, 3)).unwrap();
    value["guest"]["cases"][0]["stdout"] = json!("[{{\\\"}}]".repeat(40));
    assert!(decode(&value).is_ok());
    value["guest"]["cases"][0]["stdout"] = json!("x".repeat(65_537));
    assert!(decode(&value).is_err());
    assert!(
        protocol::decode_frame(&frame("[[[[[[[[[0]]]]]]]]]"), &mut 0)
            .unwrap_err()
            .contains("nesting")
    );
}

#[test]
fn source_session_version_and_sequence_are_bound() {
    for (field, value) in [
        ("source", json!("0".repeat(40))),
        ("session", json!(VM)),
        ("session", json!(SESSION.to_uppercase())),
        ("version", json!(2)),
        ("seq", json!(1)),
    ] {
        let mut bad = serde_json::to_value(event(Kind::Prepared, 0)).unwrap();
        bad[field] = value;
        let mut v = Validator::new(SOURCE.into(), SESSION.into());
        assert!(
            v.accept(&decode(&bad).unwrap()).is_err(),
            "accepted {field}"
        );
        assert!(v.failed);
    }
    let mut v = active();
    assert!(
        v.accept(&event(Kind::Guest, 3)).is_err(),
        "replayed sequence"
    );
    for source in ["z".repeat(40), SOURCE.to_uppercase()] {
        let mut v = Validator::new(source.clone(), SESSION.into());
        let mut bad = event(Kind::Prepared, 0);
        bad.source = source;
        assert!(v.accept(&bad).is_err(), "matching malformed source");
    }
}

#[test]
fn vm_and_runtime_identities_are_immutable() {
    for field in ["vm_id", "runtime_id"] {
        let mut v = active();
        let mut bad = serde_json::to_value(event(Kind::Cleanup, 4)).unwrap();
        bad[field] = json!("45678901-1234-4234-8234-123456789abc");
        assert!(v.accept(&decode(&bad).unwrap()).is_err());
        assert!(!v.finish(true, true, false));
    }
    for id in ["", "not-a-uuid", "00000000-0000-0000-0000-000000000000"] {
        let mut bad = event(Kind::Prepared, 0);
        bad.vm_id = id.into();
        assert!(Validator::new(SOURCE.into(), SESSION.into())
            .accept(&bad)
            .is_err());
    }
}

#[test]
fn illegal_order_and_guest_cleanup_spoof_never_retire() {
    for kind in [Kind::Creating, Kind::Running, Kind::Guest, Kind::Cleanup] {
        let mut v = Validator::new(SOURCE.into(), SESSION.into());
        assert!(v.accept(&event(kind, 0)).is_err());
    }
    let mut v = active();
    let mut spoof = event(Kind::Guest, 4);
    spoof.cleanup = Some(receipt());
    assert!(v.accept(&spoof).is_err());
    assert!(!v.finish(true, true, false));
}

#[test]
fn completion_requires_joined_host_io_and_successful_helper_exit() {
    assert!(completed().finish(true, true, false));
    for (joined, helper) in [(false, true), (true, false), (false, false)] {
        let mut v = completed();
        assert!(!v.finish(joined, helper, false));
    }
}

#[test]
fn every_independent_cleanup_failure_prevents_retirement() {
    for field in [
        "terminate_ok",
        "whole_vm_exited",
        "exit_ok",
        "close_ok",
        "guest_io_joined",
        "owned_data_retained",
    ] {
        let mut v = active();
        let mut bad = serde_json::to_value(event(Kind::Cleanup, 4)).unwrap();
        bad["cleanup"][field] = json!(false);
        let _ = v.accept(&decode(&bad).unwrap());
        assert!(!v.finish(true, true, false), "accepted missing {field}");
    }
    for field in [
        "network_denial_proven",
        "workspace_integration",
        "production_admission",
    ] {
        let mut v = active();
        let mut bad = serde_json::to_value(event(Kind::Cleanup, 4)).unwrap();
        bad["cleanup"][field] = json!(true);
        let _ = v.accept(&decode(&bad).unwrap());
        assert!(
            !v.finish(true, true, false),
            "accepted qualification {field}"
        );
    }
}

#[test]
fn partial_start_and_helper_eof_cannot_become_not_started() {
    let mut v = Validator::new(SOURCE.into(), SESSION.into());
    v.accept(&event(Kind::Prepared, 0)).unwrap();
    v.start_attempted();
    let request = serde_json::from_value(json!({
        "version":1,"source":SOURCE,"session":SESSION,"seq":1,"op":"start","fixture":"runtimes"
    }))
    .unwrap();
    let mut limited = std::io::Cursor::new([0u8; 6]);
    assert!(protocol::write_request(&mut limited, &request, &mut 0).is_err());
    assert_eq!(limited.position(), 6, "Start was only partially written");
    assert!(v.started);
    assert_eq!(v.stage, State::CreatingMayExist);
    assert!(!v.finish(true, false, false));
    assert_ne!(v.stage, State::RegisteredNoEffects);
    assert!(
        !active().finish(true, true, false),
        "EOF without terminal receipt"
    );
    let mut no_vm = serde_json::to_value(receipt()).unwrap();
    for field in [
        "terminate_ok",
        "whole_vm_exited",
        "exit_ok",
        "close_ok",
        "guest_io_joined",
    ] {
        no_vm[field] = json!(false);
    }
    no_vm["quarantine"] = json!("not-started");
    no_vm["output_sha256"] = json!("");
    let no_vm: Cleanup = serde_json::from_value(no_vm).unwrap();
    assert!(no_vm.retirable(None, false, true));
    assert!(
        !no_vm.retirable(None, true, true),
        "partial Start cannot use no-effects receipt"
    );
}

#[test]
fn quarantine_disposition_and_hashes_bind_the_result() {
    assert!(
        !completed().finish(true, true, true),
        "normal output cannot become cancellation"
    );
    let mut v = active();
    let mut cancelled = event(Kind::Cleanup, 4);
    cancelled.cleanup.as_mut().unwrap().quarantine = Quarantine::Withheld;
    cancelled.cleanup.as_mut().unwrap().output_sha256.clear();
    v.accept(&cancelled).unwrap();
    assert!(v.finish(true, true, true));
    for field in ["input_sha256", "output_sha256"] {
        let mut v = active();
        let mut bad = serde_json::to_value(&cancelled).unwrap();
        bad["cleanup"][field] = json!("0".repeat(64));
        let _ = v.accept(&decode(&bad).unwrap());
        assert!(
            !v.finish(true, true, true),
            "cancelled receipt accepted {field}"
        );
    }
    for field in ["input_sha256", "output_sha256"] {
        let mut v = active();
        let mut bad = serde_json::to_value(event(Kind::Cleanup, 4)).unwrap();
        bad["cleanup"][field] = json!("0".repeat(64));
        let _ = v.accept(&decode(&bad).unwrap());
        assert!(!v.finish(true, true, false), "unbound {field}");
    }
    let mut bad = guest();
    bad.data_base64 = STANDARD.encode(b"guest-supplied receipt");
    assert!(!bad.valid_for(SESSION));
    assert!(!guest().valid_for(VM), "fixture must bind exact session");
}

#[test]
fn protocol_or_cleanup_error_is_sticky_after_later_good_receipt() {
    let mut v = active();
    let mut bad = event(Kind::Cleanup, 4);
    bad.error = "helper channel failed".into();
    bad.cleanup
        .as_mut()
        .unwrap()
        .errors
        .push("close failed".into());
    let _ = v.accept(&bad);
    let _ = v.accept(&event(Kind::Cleanup, 5));
    assert!(!v.finish(true, true, false));
}

#[test]
fn terminal_must_be_last_and_close_is_not_exit_proof() {
    let mut v = completed();
    assert!(v.accept(&event(Kind::Guest, 5)).is_err());
    assert!(!v.finish(true, true, false));
    let mut v = active();
    let mut bad = event(Kind::Cleanup, 4);
    bad.cleanup.as_mut().unwrap().whole_vm_exited = false;
    let _ = v.accept(&bad);
    assert!(!v.finish(true, true, false));
}

fn paired_guard() -> (
    ToolContext,
    coding_tools_cloud_agent::work::WorkDrain,
    Option<native_drain::NativeGuard>,
) {
    use std::sync::{Mutex, OnceLock};
    static ROOTS: OnceLock<Mutex<Vec<tempfile::TempDir>>> = OnceLock::new();
    let root = tempfile::tempdir().unwrap();
    let workspace = root.path().join("workspace");
    let harness = root.path().join("harness");
    std::fs::create_dir(&workspace).unwrap();
    std::fs::create_dir(&harness).unwrap();
    let mut ctx = ToolContext::for_test(workspace, harness).unwrap();
    let cloud = coding_tools_cloud_agent::work::WorkDrain::new();
    let mut parent_cloud = cloud.register().unwrap();
    let mut parent_root = ctx.root_work.as_ref().unwrap().register().unwrap();
    parent_cloud.begin().unwrap();
    parent_root.begin().unwrap();
    ctx.native_work = Some(parent_cloud.scope());
    ctx.root_scope = Some(parent_root.scope());
    let mut guard = native_drain::child(&ctx).unwrap();
    native_drain::begin(&mut guard).unwrap();
    parent_cloud.complete();
    parent_root.complete();
    cloud.seal();
    ROOTS
        .get_or_init(Default::default)
        .lock()
        .unwrap()
        .push(root);
    (ctx, cloud, guard)
}
fn pending_session() -> (
    WindowsVmSession,
    mpsc::Receiver<Message>,
    watch::Sender<Arc<Completion>>,
) {
    let (control, commands) = mpsc::channel();
    let pending = Validator::new(SOURCE.into(), SESSION.into()).snapshot(Outcome::Pending, vec![]);
    let (updates, rx) = watch::channel(Arc::new(pending));
    (
        WindowsVmSession {
            control,
            completion: CompletionObserver { rx },
        },
        commands,
        updates,
    )
}

#[tokio::test]
async fn losing_only_a_wait_future_keeps_control_and_paired_guards() {
    // Exercise the real observer/control types without starting a helper or VM.
    let (ctx, cloud, guard) = paired_guard();
    let (session, commands, _updates) = pending_session();
    let observer = session.observer();
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(20), observer.wait())
            .await
            .is_err()
    );
    assert!(matches!(
        commands.try_recv(),
        Err(mpsc::TryRecvError::Empty)
    ));
    assert_eq!(cloud.status().outstanding, 1);
    assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
    session.finish();
    assert!(matches!(
        commands.recv().unwrap(),
        Message::Control(Op::Finish)
    ));
    native_drain::complete(guard);
    cloud.wait().await;
    assert!(ctx.root_work.as_ref().unwrap().restore().is_ok());
    assert!(!cloud.status().unconfirmed);
}

#[test]
fn losing_controller_requests_cancel_but_uncertain_work_keeps_both_fences() {
    let (ctx, cloud, guard) = paired_guard();
    let (session, commands, _updates) = pending_session();
    drop(session);
    assert!(matches!(
        commands.recv().unwrap(),
        Message::Control(Op::Cancel)
    ));
    assert_eq!(cloud.status().outstanding, 1);
    assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
    drop(guard);
    assert!(cloud.status().unconfirmed);
    assert_eq!(ctx.root_work.as_ref().unwrap().native_state(), "recovery");
    assert!(ctx.root_work.as_ref().unwrap().restore().is_err());
}
