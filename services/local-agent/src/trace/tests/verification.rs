use super::*;

#[test]
fn verification_is_redacted_ordered_and_never_authority() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let admission = admission();
    let trace = journal(&admission, 16, 4);
    let call = call();

    ready(trace.invoke(&registry, &call, &admission, NOW)).unwrap();
    ready(trace.invoke(&registry, &call, &admission, NOW)).unwrap();

    let evidence = trace.verification_evidence(&admission, NOW).unwrap();
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(evidence.records.len(), 2);
    assert_eq!(evidence.records[0].invocation, 1);
    assert_eq!(evidence.records[1].invocation, 3);
    assert!(evidence.records.iter().all(|record| {
        record.entry_retained && record.observation == RecoveryState::ReturnedOk
    }));
    assert_eq!(evidence.observed_events, 4);
    assert_eq!(evidence.dropped_events, 0);
    assert!(evidence.history_complete);
    assert!(evidence.local_only);
    assert!(!evidence.durable);
    assert!(!evidence.automatic_replay_allowed);
    assert!(!evidence.external_effects_verified);
    assert!(!evidence.reconciliation_required);

    let json = serde_json::to_string(&evidence).unwrap();
    for secret in [CANARY, TOOL, "arguments", "request_id", "conversation", "workspace"] {
        assert!(!json.contains(secret));
    }
}

#[test]
fn foreign_generation_and_expiry_cannot_observe_verification() {
    let admission = admission();
    let trace = journal(&admission, 8, 2);
    for foreign in [
        LocalAdmission::fixture("foreign", CANARY, [], 7, 2_000),
        LocalAdmission::fixture(CANARY, "foreign", [], 7, 2_000),
        LocalAdmission::fixture(CANARY, CANARY, [], 8, 2_000),
        LocalAdmission::fixture(CANARY, CANARY, [], 7, NOW - 1),
    ] {
        assert_eq!(
            trace.verification_evidence(&foreign, NOW).unwrap_err(),
            TraceError::Unauthorized
        );
    }
}

#[test]
fn cancelled_and_error_outcomes_never_become_verified_success() {
    let admission = admission();
    let call = call();

    let (pending_registry, pending_calls) = registry(Behavior::Pending, false);
    let pending_trace = journal(&admission, 8, 2);
    let mut future = pending_trace.invoke(&pending_registry, &call, &admission, NOW);
    assert_pending(&mut future);
    drop(future);
    let cancelled = pending_trace
        .verification_evidence(&admission, NOW)
        .unwrap();
    assert_eq!(pending_calls.load(Ordering::SeqCst), 1);
    assert_eq!(
        cancelled.records[0].observation,
        RecoveryState::OutcomeUnknown
    );
    assert!(cancelled.reconciliation_required);
    assert!(!cancelled.external_effects_verified);

    let (error_registry, error_calls) = registry(Behavior::Error, false);
    let error_trace = journal(&admission, 8, 2);
    ready(error_trace.invoke(&error_registry, &call, &admission, NOW)).unwrap_err();
    let failed = error_trace.verification_evidence(&admission, NOW).unwrap();
    assert_eq!(error_calls.load(Ordering::SeqCst), 1);
    assert_eq!(
        failed.records[0].observation,
        RecoveryState::ReturnedError {
            kind: TraceToolError::Execution
        }
    );
    assert!(failed.reconciliation_required);
    assert!(!failed.external_effects_verified);
}

#[test]
fn retention_gaps_remain_explicit_and_bounded() {
    let (registry, _) = registry(Behavior::Ok, false);
    let admission = admission();
    let call = call();
    let trace = journal(&admission, 1, 1);

    for _ in 0..4 {
        ready(trace.invoke(&registry, &call, &admission, NOW)).unwrap();
    }
    let evidence = trace.verification_evidence(&admission, NOW).unwrap();
    assert_eq!(evidence.observed_events, 1);
    assert_eq!(evidence.records.len(), 1);
    assert!(evidence.dropped_events > 0);
    assert!(!evidence.history_complete);
    assert!(!evidence.records[0].entry_retained);
    assert!(evidence.reconciliation_required);
    assert!(!evidence.automatic_replay_allowed);
}

#[test]
fn in_flight_is_evidence_of_uncertainty_not_completion() {
    let (registry, calls) = registry(Behavior::Pending, false);
    let admission = admission();
    let call = call();
    let trace = journal(&admission, 8, 2);
    let mut future = trace.invoke(&registry, &call, &admission, NOW);
    assert_pending(&mut future);

    let evidence = trace.verification_evidence(&admission, NOW).unwrap();
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(evidence.records[0].observation, RecoveryState::InFlight);
    assert!(evidence.reconciliation_required);
    assert!(!evidence.external_effects_verified);
    drop(future);
}
