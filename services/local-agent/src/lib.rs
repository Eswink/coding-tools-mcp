mod executor;
mod model;
mod policy;
mod process;
mod process_tree;
mod registry;
mod trace;

pub use executor::{ToolExecutor, ToolFuture};
pub use model::{
    parse_arguments, Capability, LocalAdmission, ToolCall, ToolError, ToolErrorKind, ToolExposure,
    ToolName, ToolOutput, ToolSpec,
};
pub use policy::{
    Command, CommandFingerprint, ExecDecision, ExecPolicy, ExecutionAuthorization, HostExecutable,
    PolicyError, PolicyErrorKind, PolicyEvaluation, PrefixRule, PrefixRuleMatch, ScopedApproval,
    TokenPattern,
};
pub use process::{
    ExecError, ExecErrorKind, ExecOutcome, ExecSpec, ExecTermination, ProcessManager,
    ProcessSession,
};
pub use registry::{ToolRegistry, VerifiedInvocation};
pub use trace::{
    RecoveryItem, RecoveryState, RecoveryView, TraceError, TraceEvent, TraceJournal, TracePhase,
    TraceSnapshot, TraceToolError,
};
