use super::*;

#[test]
fn trace_success_preserves_output_and_single_invocation_without_payloads() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    let result = ready(trace.invoke(&registry, &call, &a, NOW)).unwrap();
    assert!(matches!(result, ToolOutput::Json(value) if value["secret"] == CANARY));
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(snapshot.events().len(), 2);
    assert_eq!(snapshot.events()[0].phase, TracePhase::Entered);
    assert_eq!(snapshot.events()[1].phase, TracePhase::ReturnedOk);
    assert_eq!(
        snapshot.events()[0].invocation,
        snapshot.events()[1].invocation
    );
    let view = snapshot.recovery_view();
    assert!(view.history_complete);
    assert!(!view.reconciliation_required);
    assert!(!view.durable);
    assert!(!view.automatic_replay_allowed);
    assert!(view.local_only);
    assert_redacted(&trace, &snapshot);
}

#[test]
fn error_after_side_effect_preserves_error_but_never_means_not_executed() {
    let (registry, calls) = registry(Behavior::Error, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    let error = ready(trace.invoke(&registry, &call, &a, NOW)).unwrap_err();
    assert_eq!(error.kind, ToolErrorKind::Execution);
    assert_eq!(error.public_message(), CANARY);
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(
        snapshot.events()[1].phase,
        TracePhase::ReturnedError {
            kind: TraceToolError::Execution
        }
    );
    assert!(snapshot.recovery_view().reconciliation_required);
    assert_redacted(&trace, &snapshot);
}

#[test]
fn never_polled_future_neither_dispatches_nor_allocates_observation() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    drop(trace.invoke(&registry, &call, &a, NOW));
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(trace.snapshot(&a, NOW).unwrap().events().is_empty());
}

#[test]
fn cancellation_records_uncertainty_and_view_never_replays() {
    let (registry, calls) = registry(Behavior::Pending, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    let mut future = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut future);
    let active = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(active.active_invocations(), &[1]);
    assert_eq!(
        active.recovery_view().items[0].observation,
        RecoveryState::InFlight
    );
    assert!(active.recovery_view().reconciliation_required);
    drop(future);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert!(snapshot.active_invocations().is_empty());
    assert_eq!(snapshot.events()[1].phase, TracePhase::OutcomeUnknown);
    for _ in 0..4 {
        assert_eq!(
            snapshot.recovery_view().items[0].observation,
            RecoveryState::OutcomeUnknown
        );
        assert!(!snapshot.recovery_view().automatic_replay_allowed);
    }
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_redacted(&trace, &snapshot);
}

#[test]
fn unwinding_executor_leaves_unknown_not_success() {
    let (registry, calls) = registry(Behavior::Panic, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        ready(trace.invoke(&registry, &call, &a, NOW))
    }));
    assert!(result.is_err());
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(
        trace.snapshot(&a, NOW).unwrap().events()[1].phase,
        TracePhase::OutcomeUnknown
    );
}
