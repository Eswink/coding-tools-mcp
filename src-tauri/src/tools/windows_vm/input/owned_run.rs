//! Concrete native input preflight, with no CI synthetic/VM/output shortcut.
#[cfg(test)]
pub(crate) mod hcs;
pub(crate) use super::transfer::{leaf as valid_leaf, RunBinding};
use super::{
    lease::InputLease, retained::Retained, transfer::InputTransfer, WindowsInputAuthority,
};
use crate::tools::{
    cloud_host::windows_workspace::WorkspaceRunGrant, root_work::RootWorkGuard, ToolContext,
};
use coding_tools_cloud_agent::work::{WorkGuard, WorkScope};
use std::{sync::Arc, time::Instant};
use tokio::sync::watch;
#[derive(Clone, Copy)]
pub(crate) enum Fault {
    None,
    #[cfg(test)]
    CloseUnknown,
    #[cfg(test)]
    PanicOwned,
}
/// This is a diagnostic, not an executable owner, retirement seal or bytes.
#[derive(Clone, Debug)]
pub(crate) struct PreflightReport {
    pub(crate) operation: uuid::Uuid,
    pub(crate) error: &'static str,
    pub(crate) input_checked: bool,
    pub(crate) source_handles_closed: bool,
    pub(crate) vm_started: bool,
    pub(crate) output_attempted: bool,
    pub(crate) production_qualified: bool,
}
struct OwnedWorkspaceInput {
    grant: WorkspaceRunGrant,
    context: Arc<ToolContext>,
    authority: Arc<WindowsInputAuthority>,
    lease: InputLease,
    transfer: Option<InputTransfer>,
    cloud: Option<WorkGuard>,
    root: Option<RootWorkGuard>,
}
impl OwnedWorkspaceInput {
    fn begin(&mut self) -> Result<(), &'static str> {
        self.cloud
            .as_mut()
            .ok_or("WINDOWS_WORKSPACE_CLOUD_SCOPE_REQUIRED")?
            .begin()
            .map_err(|_| "WINDOWS_INPUT_CLOUD_STOPPING")?;
        self.root
            .as_mut()
            .ok_or("WINDOWS_WORKSPACE_ROOT_SCOPE_REQUIRED")?
            .begin()
            .map_err(|_| "WINDOWS_INPUT_ROOT_STOPPING")
    }
    fn complete_guards(&mut self) {
        if let Some(cloud) = self.cloud.take() {
            cloud.complete();
        }
        if let Some(root) = self.root.take() {
            root.complete();
        }
    }
}
static RECOVERY: std::sync::OnceLock<
    std::sync::Mutex<std::collections::HashMap<uuid::Uuid, Box<OwnedWorkspaceInput>>>,
> = std::sync::OnceLock::new();
fn retain_unknown(mut owned: Box<OwnedWorkspaceInput>) {
    // Dropping running guards seals the existing durable root/cloud fences.
    // Keep the *actual* grant, permit, context, root authority, handles and both
    // original/detached immutable byte owners, even on map failure or unwind.
    drop(owned.cloud.take());
    drop(owned.root.take());
    let store = RECOVERY.get_or_init(Default::default);
    let Ok(mut entries) = store.lock() else {
        let _ = Box::leak(owned);
        return;
    };
    if entries.len() >= 256 || entries.contains_key(&owned.grant.operation()) {
        let _ = Box::leak(owned);
        return;
    }
    entries.insert(owned.grant.operation(), owned);
}
pub(crate) fn preflight(
    context: Arc<ToolContext>,
    authority: Arc<WindowsInputAuthority>,
    grant: WorkspaceRunGrant,
    work: WorkScope,
    deadline: Instant,
    cancellation: Option<watch::Receiver<bool>>,
    fault: Fault,
) -> Result<PreflightReport, &'static str> {
    if !grant.binding().valid()
        || grant.binding().source != super::native_source()?
        || Instant::now() >= deadline
    {
        return Err("WINDOWS_WORKSPACE_GRANT_REJECTED");
    }
    let root = context
        .root_work
        .as_ref()
        .map_err(|_| "WINDOWS_INPUT_ROOT_UNAVAILABLE")?
        .register()
        .map_err(|_| "WINDOWS_INPUT_ROOT_STOPPING")?;
    let cloud = work.fork().map_err(|_| "WINDOWS_INPUT_CLOUD_STOPPING")?;
    let operation = grant.operation();
    let mut owned = Retained::new(
        OwnedWorkspaceInput {
            grant,
            context,
            authority,
            lease: InputLease::new(),
            transfer: None,
            cloud: Some(cloud),
            root: Some(root),
        },
        retain_unknown,
    );
    let cancelled = || cancellation.as_ref().is_some_and(|r| *r.borrow());
    let result = (|| {
        owned.get_mut().begin()?;
        if cancelled() || Instant::now() >= deadline {
            return Err("WINDOWS_INPUT_CANCELLED");
        }
        let assets = owned.get_mut();
        let binding = assets.grant.binding().clone();
        assets.lease.prepare(
            &assets.authority,
            assets.grant.host(),
            &binding.profile,
            &binding.input_relative,
            deadline,
            &cancelled,
        )?;
        let transfer = assets
            .lease
            .transfer(binding.clone(), deadline, &cancelled)?;
        if !transfer.matches(&binding) {
            return Err("WINDOWS_WORKSPACE_TRANSFER_REJECTED");
        }
        assets.transfer = Some(transfer);
        if cancelled() || Instant::now() >= deadline {
            return Err("WINDOWS_INPUT_CANCELLED");
        }
        #[cfg(test)]
        if matches!(fault, Fault::PanicOwned) {
            panic!("controlled concrete workspace owner panic");
        }
        Ok(())
    })();
    let input_checked = result.is_ok();
    #[cfg(test)]
    if matches!(fault, Fault::CloseUnknown) {
        owned.get_mut().lease.simulate_close_unknown();
    }
    #[cfg(not(test))]
    let _ = fault;
    let closed = owned.get_mut().lease.retire();
    let error = if !closed {
        "WINDOWS_INPUT_CLOSE_UNKNOWN"
    } else if cancelled() || Instant::now() >= deadline {
        "WINDOWS_INPUT_CANCELLED"
    } else {
        result.err().unwrap_or("WINDOWS_WORKSPACE_VM_UNAVAILABLE")
    };
    if closed {
        if let Some(transfer) = owned.get_mut().transfer.as_mut() {
            transfer.clear_after_checked_close();
        }
        owned.get_mut().complete_guards();
        owned.retire_known();
    } else {
        drop(owned);
    }
    Ok(PreflightReport {
        operation,
        error,
        input_checked,
        source_handles_closed: closed,
        vm_started: false,
        output_attempted: false,
        production_qualified: false,
    })
}
#[cfg(test)]
pub(crate) fn recovery_probe(operation: uuid::Uuid) -> Option<(bool, usize, bool, bool)> {
    let entries = RECOVERY.get()?.lock().ok()?;
    let owned = entries.get(&operation)?;
    let (held, uncertain, immutable) = owned.lease.recovery_evidence();
    Some((
        owned.context.execution_gate.snapshot().in_flight > 0,
        held,
        uncertain,
        immutable
            && owned
                .transfer
                .as_ref()
                .is_some_and(|t| t.matches(owned.grant.binding())),
    ))
}
#[cfg(test)]
pub(crate) fn recovery_for_context(context: &Arc<ToolContext>) -> Option<uuid::Uuid> {
    let entries = RECOVERY.get()?.lock().ok()?;
    entries
        .iter()
        .find_map(|(operation, owned)| Arc::ptr_eq(context, &owned.context).then_some(*operation))
}
