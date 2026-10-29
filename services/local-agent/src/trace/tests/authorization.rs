use super::*;

#[test]
fn foreign_scope_generation_expiry_cannot_append_or_observe() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let owner = admission();
    let call = call();
    let trace = journal(&owner, 8, 2);
    for (conversation, workspace, generation, expiry) in [
        ("foreign", CANARY, 7, 2_000),
        (CANARY, "foreign", 7, 2_000),
        (CANARY, CANARY, 8, 2_000),
        (CANARY, CANARY, 7, NOW - 1),
    ] {
        let a = LocalAdmission::fixture(
            conversation,
            workspace,
            [Capability::ProcessExec],
            generation,
            expiry,
        );
        assert_eq!(
            trace.snapshot(&a, NOW).unwrap_err(),
            TraceError::Unauthorized
        );
        assert_eq!(
            ready(trace.invoke(&registry, &call, &a, NOW))
                .unwrap_err()
                .kind,
            ToolErrorKind::Unauthorized
        );
    }
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(trace.snapshot(&owner, NOW).unwrap().events().is_empty());
}

#[test]
fn swapped_call_context_is_denied_before_trace_allocation() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let trace = journal(&a, 8, 2);
    for workspace in [true, false] {
        let mut call = call();
        if workspace {
            call.workspace_id = "foreign".into();
        } else {
            call.conversation_id = "foreign".into();
        }
        assert_eq!(
            ready(trace.invoke(&registry, &call, &a, NOW))
                .unwrap_err()
                .kind,
            ToolErrorKind::Unauthorized
        );
    }
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(trace.snapshot(&a, NOW).unwrap().events().is_empty());
}

#[test]
fn underlying_registry_capability_and_not_found_errors_are_not_bypassed() {
    let (registry, calls) = registry(Behavior::Ok, true);
    let a = LocalAdmission::fixture(CANARY, CANARY, [], 7, 2_000);
    let trace = journal(&a, 8, 2);
    let mut call = call();
    assert_eq!(
        ready(trace.invoke(&registry, &call, &a, NOW))
            .unwrap_err()
            .kind,
        ToolErrorKind::CapabilityDenied
    );
    call.tool_name = ToolName::parse("unknown").unwrap();
    assert_eq!(
        ready(trace.invoke(&registry, &call, &a, NOW))
            .unwrap_err()
            .kind,
        ToolErrorKind::NotFound
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(
        snapshot.events()[1].phase,
        TracePhase::ReturnedError {
            kind: TraceToolError::CapabilityDenied
        }
    );
    assert_eq!(
        snapshot.events()[3].phase,
        TracePhase::ReturnedError {
            kind: TraceToolError::NotFound
        }
    );
    assert!(snapshot.recovery_view().reconciliation_required);
}

#[test]
fn limits_are_bounded_and_invalid_local_identity_is_rejected() {
    let a = admission();
    for (events, active) in [(0, 1), (4097, 1), (1, 0), (1, 65), (usize::MAX, usize::MAX)] {
        assert_eq!(
            TraceJournal::new(&a, events, active, NOW).unwrap_err(),
            TraceError::InvalidLimits
        );
    }
    assert_eq!(
        TraceJournal::new(&a, 1, 1, 2_001).unwrap_err(),
        TraceError::Unauthorized
    );
    for id in ["".into(), "x".repeat(257), "bad\nvalue".into()] {
        let bad = LocalAdmission::fixture(&id, CANARY, [], 7, 2_000);
        assert_eq!(
            TraceJournal::new(&bad, 1, 1, NOW).unwrap_err(),
            TraceError::Unauthorized
        );
    }
    assert!(TraceJournal::new(&a, 4096, 64, NOW).is_ok());
}
