mod executor;
mod guidance;
mod model;
mod policy;
mod process;
mod process_tree;
mod pty;
mod pty_io;
mod registry;
#[cfg(target_os = "linux")]
mod sandbox;
mod skills;
mod trace;

pub use executor::{ToolExecutor, ToolFuture};
pub use guidance::{GuidanceEntry, GuidanceError, GuidanceLimits, GuidanceResolver, GuidanceSet};
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
pub use pty::{
    PtyError, PtyErrorKind, PtyManager, PtyOutcome, PtyOutputSnapshot, PtySession, PtySize,
    PtySpec, PtyTermination,
};
pub use registry::{
    DeferredToolCatalog, ToolRegistry, VerifiedInvocation, MAX_DEFERRED_DISCOVERY_BYTES,
    MAX_DEFERRED_DISCOVERY_TOOLS,
};
pub use skills::{LocalSkill, SkillCatalog, SkillCatalogLoader, SkillError, SkillLimits};
pub use trace::{
    RecoveryItem, RecoveryState, RecoveryView, TraceError, TraceEvent, TraceJournal, TracePhase,
    TraceSnapshot, TraceToolError, VerificationEvidence, VerificationRecord,
};

#[cfg(target_os = "linux")]
pub use sandbox::{LinuxSandbox, SandboxError, SandboxErrorKind};
