use super::*;
pub(crate) struct RootExclusiveGuard {
    owner: Arc<RootWorkTracker>,
    chain: uuid::Uuid,
}
impl Drop for RootExclusiveGuard {
    fn drop(&mut self) {
        if let Ok(mut state) = self.owner.state.lock() {
            if state.exclusive == Some(self.chain) {
                state.exclusive = None;
            }
        }
    }
}
pub(crate) fn exclusive_context(ctx: &ToolContext) -> Result<RootExclusiveGuard, RootWorkError> {
    let scope = ctx.root_scope.as_ref().ok_or(RootWorkError)?;
    scope.owner.anchor.verify(&scope.owner.root)?;
    let registry = REGISTRY
        .get_or_init(Default::default)
        .lock()
        .map_err(|_| RootWorkError)?;
    persisted_conflict(
        &scope.owner.store.join("native-root-work-v1"),
        &scope.owner.root,
        &scope.owner.anchor,
        &registry,
    )?;
    for (root, owner) in registry.iter() {
        if let Some(owner) = owner.upgrade() {
            if !overlaps(root, &scope.owner.root)
                && !storage::physical_overlap(&owner.anchor, &scope.owner.anchor)
            {
                continue;
            }
            owner.anchor.verify(&owner.root)?;
            let state = owner.state.lock().map_err(|_| RootWorkError)?;
            let status = state.drain.status();
            if state.poisoned || status.unconfirmed || state.exclusive.is_some() {
                return Err(RootWorkError);
            }
            if Arc::ptr_eq(&owner, &scope.owner) {
                if state.document.phase != Phase::Busy
                    || state.chains.len() != 1
                    || !state.chains.contains_key(&scope.chain)
                {
                    return Err(RootWorkError);
                }
            } else if state.document.phase != Phase::Clean || status.outstanding != 0 {
                return Err(RootWorkError);
            }
        }
    }
    scope
        .owner
        .state
        .lock()
        .map_err(|_| RootWorkError)?
        .exclusive = Some(scope.chain);
    Ok(RootExclusiveGuard {
        owner: scope.owner.clone(),
        chain: scope.chain,
    })
}
