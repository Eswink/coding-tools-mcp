use crate::registry::VerifiedInvocation;
use crate::{ToolCall, ToolError, ToolName, ToolOutput, ToolSpec};
use std::{future::Future, pin::Pin};

pub type ToolFuture<'a> =
    Pin<Box<dyn Future<Output = Result<ToolOutput, ToolError>> + Send + 'a>>;

/// Runtime contract for a single local tool.
///
/// Authorization and sandbox orchestration deliberately live outside executors.
/// A registry only calls this after a locally issued admission capability is
/// validated for the invocation. The unforgeable-by-safe-external-code
/// `VerifiedInvocation` marker prevents callers from bypassing the registry
/// and directly invoking an executor with cloud/model input alone.
pub trait ToolExecutor: Send + Sync {
    fn tool_name(&self) -> ToolName;
    fn spec(&self) -> ToolSpec;

    fn supports_parallel_calls(&self) -> bool {
        false
    }

    fn execute<'a>(
        &'a self,
        call: &'a ToolCall,
        verified: VerifiedInvocation<'a>,
    ) -> ToolFuture<'a>;
}
