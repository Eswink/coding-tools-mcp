use super::*;

struct PoisonOnReturn {
    trace: Arc<TraceJournal>,
    calls: Arc<AtomicUsize>,
    return_error: bool,
}

impl ToolExecutor for PoisonOnReturn {
    fn tool_name(&self) -> ToolName {
        ToolName::parse(TOOL).unwrap()
    }
    fn spec(&self) -> ToolSpec {
        ToolSpec::new(self.tool_name(), "fixture", json!({"type":"object"})).unwrap()
    }
    fn execute<'a>(&'a self, _: &'a ToolCall, _: VerifiedInvocation<'a>) -> ToolFuture<'a> {
        Box::pin(async move {
            // The callback must never be called while the trace lock is held.
            assert!(self.trace.state.try_lock().is_ok());
            self.calls.fetch_add(1, Ordering::SeqCst);
            let poisoned = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let _lock = self.trace.state.lock().unwrap();
                panic!("fixed post-execution diagnostic failure fixture");
            }));
            assert!(poisoned.is_err());
            if self.return_error {
                Err(ToolError::new(ToolErrorKind::Execution, CANARY))
            } else {
                Ok(ToolOutput::json(json!({"secret":CANARY})))
            }
        })
    }
}

#[test]
fn diagnostic_failure_after_execution_preserves_success_and_error_without_replay() {
    for return_error in [false, true] {
        let a = admission();
        let call = call();
        let trace = Arc::new(journal(&a, 8, 2));
        let calls = Arc::new(AtomicUsize::new(0));
        let mut registry = ToolRegistry::new();
        registry
            .register(Arc::new(PoisonOnReturn {
                trace: trace.clone(),
                calls: calls.clone(),
                return_error,
            }))
            .unwrap();
        let result = ready(trace.invoke(&registry, &call, &a, NOW));
        if return_error {
            let error = result.unwrap_err();
            assert_eq!(error.kind, ToolErrorKind::Execution);
            assert_eq!(error.public_message(), CANARY);
        } else {
            assert!(
                matches!(result.unwrap(), ToolOutput::Json(value) if value["secret"] == CANARY)
            );
        }
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(
            trace.snapshot(&a, NOW).unwrap_err(),
            TraceError::Unavailable
        );
        assert_eq!(
            ready(trace.invoke(&registry, &call, &a, NOW))
                .unwrap_err()
                .public_message(),
            "local trace unavailable"
        );
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert!(!format!("{trace:?}").contains(CANARY));
    }
}

#[test]
fn admission_expiry_matches_the_existing_registry_exact_boundary() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    ready(trace.invoke(&registry, &call, &a, 2_000)).unwrap();
    assert!(trace.snapshot(&a, 2_000).is_ok());
    assert_eq!(
        trace.snapshot(&a, 2_001).unwrap_err(),
        TraceError::Unauthorized
    );
    assert_eq!(
        ready(trace.invoke(&registry, &call, &a, 2_001))
            .unwrap_err()
            .kind,
        ToolErrorKind::Unauthorized
    );
    assert_eq!(calls.load(Ordering::SeqCst), 1);
}
