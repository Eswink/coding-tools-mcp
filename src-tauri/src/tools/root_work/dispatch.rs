use super::*;
fn registration(ctx: &ToolContext) -> Result<RootWorkGuard, RootWorkError> {
    match &ctx.root_scope {
        Some(scope) => scope.fork(),
        None => ctx
            .root_work
            .as_ref()
            .map_err(|_| RootWorkError)?
            .register(),
    }
}
pub(crate) fn dispatch(
    ctx: &ToolContext,
    run: impl FnOnce(&ToolContext) -> Value,
) -> Result<Value, RootWorkError> {
    #[cfg(feature = "native-state-timing")]
    let admission_timing = crate::data::native_timing::Span::new("root_admission");
    let mut guard = registration(ctx)?;
    guard.begin()?;
    #[cfg(feature = "native-state-timing")]
    drop(admission_timing);
    let mut scoped = ctx.background_snapshot();
    scoped.default_cwd = ctx.default_cwd.clone();
    scoped.root_scope = Some(guard.scope());
    if guard.owner.managed_reads() {
        scoped.workspace.confine_reads();
    }
    let _thread = crate::tools::native_drain::enter_context(&scoped);
    #[cfg(feature = "native-state-timing")]
    let body_timing = crate::data::native_timing::Span::new("dispatch_body");
    let result = run(&scoped);
    #[cfg(feature = "native-state-timing")]
    drop(body_timing);
    #[cfg(feature = "native-state-timing")]
    let _retirement_timing = crate::data::native_timing::Span::new("root_retirement");
    guard.complete();
    Ok(result)
}
/// Registration occurs synchronously before a worker can be queued or its waiter dropped.
pub(crate) fn blocking_context<T, F>(
    ctx: Arc<ToolContext>,
    run: F,
) -> impl std::future::Future<Output = Result<T, RootWorkError>>
where
    T: Send + 'static,
    F: FnOnce(Arc<ToolContext>) -> T + Send + 'static,
{
    let registered = registration(&ctx);
    async move {
        let mut guard = registered?;
        tokio::task::spawn_blocking(move || {
            guard.begin()?;
            let mut scoped = ctx.background_snapshot();
            scoped.default_cwd = ctx.default_cwd.clone();
            scoped.root_scope = Some(guard.scope());
            let scoped = Arc::new(scoped);
            let _thread = crate::tools::native_drain::enter_context(&scoped);
            let result = run(scoped);
            guard.complete();
            Ok(result)
        })
        .await
        .map_err(|_| RootWorkError)?
    }
}
