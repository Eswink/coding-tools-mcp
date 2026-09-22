use super::*;
use crate::{
    parse_arguments, Capability, LocalAdmission, ToolCall, ToolExposure, ToolName,
    ToolOutput, ToolSpec,
};
use serde::Deserialize;
use serde_json::json;
use std::{
    future::Future,
    sync::Arc,
    task::{Context, Poll, Waker},
};

struct Fixture {
    runtime_name: ToolName,
    spec: ToolSpec,
    parallel: bool,
}

impl Fixture {
    fn new(name: &str, exposure: ToolExposure, capabilities: &[Capability]) -> Self {
        let name = ToolName::parse(name).unwrap();
        let mut spec = ToolSpec::new(
            name.clone(),
            "fixture",
            json!({"type":"object","properties":{"value":{"type":"string"}},"additionalProperties":false}),
        )
        .unwrap()
        .exposure(exposure);
        for capability in capabilities {
            spec = spec.require(*capability);
        }
        Self {
            runtime_name: name,
            spec,
            parallel: false,
        }
    }
}

impl ToolExecutor for Fixture {
    fn tool_name(&self) -> ToolName {
        self.runtime_name.clone()
    }

    fn spec(&self) -> ToolSpec {
        self.spec.clone()
    }

    fn supports_parallel_calls(&self) -> bool {
        self.parallel
    }

    fn execute<'a>(
        &'a self,
        call: &'a ToolCall,
        verified: VerifiedInvocation<'a>,
    ) -> ToolFuture<'a> {
        Box::pin(async move {
            assert_eq!(verified.generation(), 7);
            Ok(ToolOutput::json(json!({
                "request": call.request_id,
                "ok": true
            })))
        })
    }
}

fn ready<F: Future>(future: F) -> F::Output {
    let waker = Waker::noop();
    let mut context = Context::from_waker(waker);
    let mut future = Box::pin(future);
    match future.as_mut().poll(&mut context) {
        Poll::Ready(value) => value,
        Poll::Pending => panic!("fixture future unexpectedly pending"),
    }
}

fn call(name: &str) -> ToolCall {
    ToolCall::new(
        "request-1",
        "conversation-a",
        "workspace-a",
        ToolName::parse(name).unwrap(),
        json!({"value":"ok"}),
    )
    .unwrap()
}

fn admission(capabilities: &[Capability]) -> LocalAdmission {
    LocalAdmission::fixture(
        "conversation-a",
        "workspace-a",
        capabilities.iter().copied(),
        7,
        2_000,
    )
}

#[test]
fn names_and_ids_are_bounded() {
    for bad in ["", "Upper", "_bad", "bad-name", "a b"] {
        assert!(ToolName::parse(bad).is_err(), "{bad}");
    }
    assert!(ToolName::parse("read_file2").is_ok());
    assert!(ToolCall::new(
        "id",
        "conversation",
        "workspace",
        ToolName::parse("read_file").unwrap(),
        json!("not-an-object"),
    )
    .is_err());
}

#[test]
fn registry_is_sorted_and_exposure_is_separate() {
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture::new("z_hidden", ToolExposure::Hidden, &[])))
        .unwrap();
    registry
        .register(Arc::new(Fixture::new("b_deferred", ToolExposure::Deferred, &[])))
        .unwrap();
    registry
        .register(Arc::new(Fixture::new("a_direct", ToolExposure::Direct, &[])))
        .unwrap();

    assert_eq!(
        registry
            .all_specs()
            .into_iter()
            .map(|s| s.name.to_string())
            .collect::<Vec<_>>(),
        vec!["a_direct", "b_deferred", "z_hidden"]
    );
    assert_eq!(registry.direct_specs()[0].name.as_str(), "a_direct");
    assert_eq!(registry.deferred_specs()[0].name.as_str(), "b_deferred");
}

#[test]
fn duplicate_and_executor_mismatch_fail_closed() {
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture::new("alpha", ToolExposure::Direct, &[])))
        .unwrap();
    assert!(registry
        .register(Arc::new(Fixture::new("alpha", ToolExposure::Direct, &[])))
        .is_err());

    let mut mismatched = Fixture::new("one", ToolExposure::Direct, &[]);
    mismatched.runtime_name = ToolName::parse("two").unwrap();
    let mut other = ToolRegistry::new();
    assert!(other.register(Arc::new(mismatched)).is_err());
}

#[test]
fn local_admission_and_capabilities_are_mandatory() {
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture::new(
            "read_file",
            ToolExposure::Direct,
            &[Capability::WorkspaceRead],
        )))
        .unwrap();

    let denied = ready(registry.invoke(&call("read_file"), &admission(&[]), 1_000)).unwrap_err();
    assert_eq!(denied.kind, ToolErrorKind::CapabilityDenied);

    let expired = ready(registry.invoke(
        &call("read_file"),
        &admission(&[Capability::WorkspaceRead]),
        2_001,
    ))
    .unwrap_err();
    assert_eq!(expired.kind, ToolErrorKind::Unauthorized);

    let ok = ready(registry.invoke(
        &call("read_file"),
        &admission(&[Capability::WorkspaceRead]),
        1_000,
    ));
    assert!(ok.is_ok());
}

#[test]
fn conversation_and_workspace_cannot_be_swapped() {
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture::new("status", ToolExposure::Direct, &[])))
        .unwrap();
    let wrong = LocalAdmission::fixture("conversation-b", "workspace-a", [], 1, 2_000);
    assert_eq!(
        ready(registry.invoke(&call("status"), &wrong, 1_000))
            .unwrap_err()
            .kind,
        ToolErrorKind::Unauthorized
    );
}

#[derive(Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
struct StrictArgs {
    value: String,
}

#[test]
fn parser_honors_strict_struct_and_byte_limit() {
    let parsed: StrictArgs = parse_arguments(&json!({"value":"x"}), 64).unwrap();
    assert_eq!(parsed, StrictArgs { value: "x".into() });
    assert!(parse_arguments::<StrictArgs>(&json!({"value":"x","extra":true}), 128).is_err());
    assert!(parse_arguments::<StrictArgs>(&json!({"value":"x".repeat(200)}), 32).is_err());
}

#[test]
fn output_truncates_utf8_on_boundary_and_json_is_bounded_by_registry() {
    let out = ToolOutput::text("ééé".to_string(), 5).unwrap();
    match out {
        ToolOutput::Text {
            text,
            truncated,
            original_bytes,
        } => {
            assert_eq!(text, "éé");
            assert!(truncated);
            assert_eq!(original_bytes, 6);
        }
        _ => panic!("wrong output"),
    }

    let mut fixture = Fixture::new("tiny", ToolExposure::Direct, &[]);
    fixture.spec = fixture.spec.limits(1024, 1).unwrap();
    let mut registry = ToolRegistry::new();
    registry.register(Arc::new(fixture)).unwrap();
    assert_eq!(
        ready(registry.invoke(&call("tiny"), &admission(&[]), 1_000))
            .unwrap_err()
            .kind,
        ToolErrorKind::OutputTooLarge
    );
}

#[test]
fn debug_redacts_arguments_and_context() {
    let rendered = format!("{:?}", call("status"));
    assert!(!rendered.contains("workspace-a"));
    assert!(!rendered.contains("conversation-a"));
    assert!(rendered.contains("<redacted>"));
}

#[test]
fn parallel_default_is_false() {
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture::new("status", ToolExposure::Direct, &[])))
        .unwrap();
    assert_eq!(registry.supports_parallel_calls("status"), Some(false));
}
