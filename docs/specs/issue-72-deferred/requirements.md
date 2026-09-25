# Requirements: issue-72-deferred

## Scope

### In scope
- A read-only registry discovery result for tools whose `ToolExposure` is exactly `Deferred`.
- Deterministic name ordering and a repository-owned upper bound on returned entries and encoded metadata.
- Focused tests for Direct/Deferred/Hidden separation, truncation/bounds, stable ordering, and proof that discovery never calls an executor.
- Windows 2025 and Ubuntu 24.04 validation.

### Out of scope
- Automatic execution or promotion of deferred tools.
- New LocalAdmission authority, capability expansion, policy bypass, cloud publication, UI, sandbox, worktree, snapshot, Hooks, PTY, or packaging changes.

## Functional requirements

| FR | Requirement | Owner |
|---|---|---|
| FR-1 | The registry SHALL discover only `ToolExposure::Deferred` entries in deterministic ToolName order; Direct and Hidden entries SHALL NOT appear. | deferred-catalog-contract |
| FR-2 | The discovery result SHALL be bounded by repository constants for entry count and encoded metadata size and SHALL report whether additional deferred entries were omitted without exposing executor internals or host paths. | deferred-catalog-contract |
| FR-3 | Reading discovery metadata SHALL NOT call any `ToolExecutor::execute`, create/reuse `VerifiedInvocation`, mutate registry entries, widen capabilities, or require LocalAdmission; tests SHALL prove these invariants on supported runners. | discovery-safety-evaluation |

## Non-functional requirements
- Existing ToolSpec validation limits remain authoritative for names, descriptions and schemas.
- Debug/output must remain non-secret and host-path-free.
- New Rust source files, if any, use English filenames and stay below repository source-length limits.
- Published changes require staged GitNexus detect evidence and no force push.
