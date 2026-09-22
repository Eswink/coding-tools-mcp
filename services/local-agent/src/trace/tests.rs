use super::*;
use crate::{Capability, ToolExecutor, ToolName, ToolOutput, ToolSpec, VerifiedInvocation};
use serde_json::json;
use std::future::{pending, Future};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::task::{Context, Poll, Waker};

const CANARY: &str = "trace-secret-canary";
const TOOL: &str = "secret_canary_tool";
const NOW: u64 = 1_000;

#[derive(Clone, Copy)]
enum Behavior {
    Ok,
    Error,
    Pending,
    Panic,
}
struct Fixture {
    calls: Arc<AtomicUsize>,
    behavior: Behavior,
    capability: bool,
}
impl ToolExecutor for Fixture {
    fn tool_name(&self) -> ToolName {
        ToolName::parse(TOOL).unwrap()
    }
    fn spec(&self) -> ToolSpec {
        let spec = ToolSpec::new(self.tool_name(), "fixture", json!({"type":"object"})).unwrap();
        if self.capability {
            spec.require(Capability::ProcessExec)
        } else {
            spec
        }
    }
    fn execute<'a>(&'a self, call: &'a ToolCall, _: VerifiedInvocation<'a>) -> ToolFuture<'a> {
        Box::pin(async move {
            self.calls.fetch_add(1, Ordering::SeqCst);
            assert_eq!(call.arguments["secret"], CANARY);
            match self.behavior {
                Behavior::Ok => Ok(ToolOutput::json(json!({"secret":CANARY}))),
                Behavior::Error => Err(ToolError::new(ToolErrorKind::Execution, CANARY)),
                Behavior::Pending => pending().await,
                Behavior::Panic => panic!("fixed fixture panic"),
            }
        })
    }
}
fn registry(behavior: Behavior, capability: bool) -> (ToolRegistry, Arc<AtomicUsize>) {
    let calls = Arc::new(AtomicUsize::new(0));
    let mut registry = ToolRegistry::new();
    registry
        .register(Arc::new(Fixture {
            calls: calls.clone(),
            behavior,
            capability,
        }))
        .unwrap();
    (registry, calls)
}
fn admission() -> LocalAdmission {
    LocalAdmission::fixture(CANARY, CANARY, [Capability::ProcessExec], 7, 2_000)
}
fn call() -> ToolCall {
    ToolCall::new(
        CANARY,
        CANARY,
        CANARY,
        ToolName::parse(TOOL).unwrap(),
        json!({"secret":CANARY}),
    )
    .unwrap()
}
fn ready<F: Future>(future: F) -> F::Output {
    let mut future = Box::pin(future);
    match future
        .as_mut()
        .poll(&mut Context::from_waker(Waker::noop()))
    {
        Poll::Ready(result) => result,
        Poll::Pending => panic!("fixture unexpectedly pending"),
    }
}
fn assert_pending(future: &mut ToolFuture<'_>) {
    assert!(future
        .as_mut()
        .poll(&mut Context::from_waker(Waker::noop()))
        .is_pending());
}
fn journal(admission: &LocalAdmission, events: usize, active: usize) -> TraceJournal {
    TraceJournal::new(admission, events, active, NOW).unwrap()
}
fn assert_redacted(trace: &TraceJournal, snapshot: &TraceSnapshot) {
    for text in [
        format!("{trace:?}"),
        format!("{snapshot:?}"),
        serde_json::to_string(snapshot).unwrap(),
        format!("{:?}", snapshot.recovery_view()),
        serde_json::to_string(&snapshot.recovery_view()).unwrap(),
    ] {
        assert!(!text.contains(CANARY));
        assert!(!text.contains(TOOL));
        assert!(!text.contains("arguments"));
        assert!(!text.contains("request_id"));
        assert!(!text.contains("conversation"));
        assert!(!text.contains("workspace"));
    }
}

mod authorization;
mod fault_boundary;
mod lifecycle;
mod retention;
