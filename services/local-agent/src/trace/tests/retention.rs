use super::*;

#[test]
fn concurrent_capacity_fails_before_another_executor_and_is_released_on_drop() {
    let (registry, calls) = registry(Behavior::Pending, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 1);
    let mut first = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut first);
    assert_eq!(
        ready(trace.invoke(&registry, &call, &a, NOW))
            .unwrap_err()
            .public_message(),
        "local trace capacity exhausted"
    );
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    drop(first);
    let mut next = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut next);
    drop(next);
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(trace.snapshot(&a, NOW).unwrap().events().len(), 4);
}

#[test]
fn ring_eviction_marks_gaps_without_hiding_active_work() {
    let (registry, _) = registry(Behavior::Pending, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 1, 2);
    let mut first = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut first);
    let mut second = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut second);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(snapshot.events().len(), 1);
    assert_eq!(snapshot.dropped_events(), 1);
    let view = snapshot.recovery_view();
    assert_eq!(view.items.len(), 2);
    assert!(!view.items[0].entry_retained);
    assert!(view
        .items
        .iter()
        .all(|item| item.observation == RecoveryState::InFlight));
    assert!(!view.history_complete);
    assert!(view.reconciliation_required);
    drop(first);
    drop(second);
    let view = trace.snapshot(&a, NOW).unwrap().recovery_view();
    assert_eq!(view.dropped_events, 3);
    assert!(view.reconciliation_required);
}

#[test]
fn evicted_start_of_returned_call_is_not_complete_history() {
    let (registry, _) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 1, 1);
    ready(trace.invoke(&registry, &call, &a, NOW)).unwrap();
    let view = trace.snapshot(&a, NOW).unwrap().recovery_view();
    assert_eq!(view.items[0].observation, RecoveryState::ReturnedOk);
    assert!(!view.items[0].entry_retained);
    assert!(!view.history_complete);
    assert!(view.reconciliation_required);
    assert!(!view.automatic_replay_allowed);
}

#[test]
fn terminal_sequence_is_reserved_before_dispatch_and_never_wraps() {
    let (registry, calls) = registry(Behavior::Pending, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 2);
    trace.state.lock().unwrap().next_sequence = u64::MAX - 2;
    let mut first = trace.invoke(&registry, &call, &a, NOW);
    assert_pending(&mut first);
    assert_eq!(
        ready(trace.invoke(&registry, &call, &a, NOW))
            .unwrap_err()
            .public_message(),
        "local trace sequence exhausted"
    );
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    drop(first);
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(snapshot.events()[1].sequence, u64::MAX - 1);
    assert_eq!(snapshot.next_sequence(), u64::MAX);
    assert!(snapshot.active_invocations().is_empty());
    assert_eq!(snapshot.events()[1].phase, TracePhase::OutcomeUnknown);
}

#[test]
fn poisoned_state_fails_closed_but_foreign_callers_cannot_observe_it() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 8, 1);
    let _ = std::panic::catch_unwind(|| {
        let _lock = trace.state.lock().unwrap();
        panic!("fixed poison fixture");
    });
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
    let foreign = LocalAdmission::fixture("foreign", CANARY, [], 7, 2_000);
    assert_eq!(
        trace.snapshot(&foreign, NOW).unwrap_err(),
        TraceError::Unauthorized
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(!format!("{trace:?}").contains(CANARY));
}

#[test]
fn simultaneous_callers_keep_unique_ordered_bounded_observations() {
    let (registry, calls) = registry(Behavior::Ok, false);
    let a = admission();
    let call = call();
    let trace = journal(&a, 64, 32);
    std::thread::scope(|scope| {
        for _ in 0..16 {
            scope.spawn(|| {
                ready(trace.invoke(&registry, &call, &a, NOW)).unwrap();
            });
        }
    });
    let snapshot = trace.snapshot(&a, NOW).unwrap();
    assert_eq!(calls.load(Ordering::SeqCst), 16);
    assert_eq!(snapshot.events().len(), 32);
    assert!(snapshot
        .events()
        .windows(2)
        .all(|pair| pair[0].sequence < pair[1].sequence));
    assert_eq!(snapshot.recovery_view().items.len(), 16);
    assert!(!snapshot.recovery_view().reconciliation_required);
    assert!(snapshot.active_invocations().is_empty());
}
