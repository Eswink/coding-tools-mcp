use super::*;
use crate::tools::{
    listener_context::{ListenerContextLease, ListenerLeaseError},
    ToolContext,
};

fn fixture() -> (
    tempfile::TempDir,
    tempfile::TempDir,
    RuntimeSupervisor,
    String,
    ListenerContextLease,
) {
    let root = tempfile::tempdir().unwrap();
    let history = tempfile::tempdir().unwrap();
    let context =
        Arc::new(ToolContext::for_test(root.path().into(), history.path().into()).unwrap());
    let lease = ListenerContextLease::new(context.clone());
    let id = uuid::Uuid::new_v4().to_string();
    let mut supervisor = RuntimeSupervisor::default();
    supervisor.entries.insert(
        (id.clone(), ServiceKind::Mcp),
        RuntimeEntry {
            public_origin: PublicOrigin::managed("").unwrap(),
            phase: RuntimePhase::Running,
            shutdown: None,
            handle: None,
            error_message: None,
            started_at: Some(std::time::Instant::now()),
            missing_port_checks: 0,
            generation: uuid::Uuid::new_v4().to_string(),
            execution_gate: Some(context.execution_gate()),
            context_lease: Some(lease.clone()),
        },
    );
    (root, history, supervisor, id, lease)
}

#[test]
fn accessor_returns_exact_live_listener_lease() {
    let (_root, _history, supervisor, id, lease) = fixture();
    let observed = supervisor.mcp_context_lease(&id).unwrap();
    assert_eq!(observed.generation(), lease.generation());
    let expected = lease.with_live(Arc::clone).unwrap();
    observed
        .with_live(|context| assert!(Arc::ptr_eq(context, &expected)))
        .unwrap();
    assert!(supervisor.is_running(&id, ServiceKind::Mcp));
    assert!(supervisor.mcp_context_lease("missing").is_none());
}

#[test]
fn begin_stop_seals_context_before_network_task_is_awaited() {
    let (_root, _history, mut supervisor, id, lease) = fixture();
    let (shutdown, mut receiver) = tokio::sync::oneshot::channel();
    supervisor
        .entries
        .get_mut(&(id.clone(), ServiceKind::Mcp))
        .unwrap()
        .shutdown = Some(shutdown);
    assert!(supervisor.begin_stop(&id, ServiceKind::Mcp).is_none());
    assert_eq!(receiver.try_recv(), Ok(()));
    assert_eq!(lease.with_live(|_| ()), Err(ListenerLeaseError::Closed));
    assert!(supervisor.mcp_context_lease(&id).is_none());
    assert!(!supervisor.is_running(&id, ServiceKind::Mcp));
    assert!(supervisor
        .entries
        .contains_key(&(id.clone(), ServiceKind::Mcp)));
}

#[test]
fn finish_stop_invalidates_any_retained_context_lease() {
    let (_root, _history, mut supervisor, id, lease) = fixture();
    supervisor.finish_stop(&id, ServiceKind::Mcp);
    assert!(!lease.is_live());
    assert!(supervisor.mcp_context_lease(&id).is_none());
    assert!(!supervisor.entries.contains_key(&(id, ServiceKind::Mcp)));
}

#[test]
fn nonrunning_or_failed_listener_never_produces_a_cloud_context() {
    let (_root, _history, mut supervisor, id, lease) = fixture();
    for phase in [
        RuntimePhase::Starting,
        RuntimePhase::Stopping,
        RuntimePhase::Error,
        RuntimePhase::Stopped,
    ] {
        supervisor
            .entries
            .get_mut(&(id.clone(), ServiceKind::Mcp))
            .unwrap()
            .phase = phase;
        assert!(supervisor.mcp_context_lease(&id).is_none());
    }
    supervisor
        .entries
        .get_mut(&(id.clone(), ServiceKind::Mcp))
        .unwrap()
        .phase = RuntimePhase::Running;
    lease.close();
    assert!(supervisor.mcp_context_lease(&id).is_none());
    assert!(!supervisor.is_running(&id, ServiceKind::Mcp));
}

#[test]
fn actions_only_workspace_does_not_supply_an_mcp_context() {
    let (_root, _history, mut supervisor, id, _lease) = fixture();
    let mut entry = supervisor
        .entries
        .remove(&(id.clone(), ServiceKind::Mcp))
        .unwrap();
    entry.context_lease = None;
    entry.execution_gate = None;
    supervisor
        .entries
        .insert((id.clone(), ServiceKind::Actions), entry);
    assert!(supervisor.is_running(&id, ServiceKind::Actions));
    assert!(supervisor.mcp_context_lease(&id).is_none());
}
