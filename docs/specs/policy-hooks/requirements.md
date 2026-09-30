# Requirements: policy-hooks

## 功能概述

Policy-governed Hooks under existing authority.

## Scope
In Scope: explicit native-approved bounded before_tool/after_tool hooks for exec_command and start_exec_task; exact command/script identity, common policy and mandatory sandbox, truthful lifecycle. After start_exec_task means submission result, not background completion.
Out of Scope: automatic repository hook discovery, network grants, credential changes or unsafe fallback. Windows success remains gated on its actual sandbox, not removed from release scope.

## 需求列表
### FR-1: Native ownership
WHEN Hooks are configured THEN the system SHALL accept only explicit native owner approval of an exact preview digest bound to the current live listener, registry identity and workspace; model/project text cannot install or approve hooks.

### FR-2: Immutable manifest
WHEN a hook is registered or invoked THEN the system SHALL validate bounded unique IDs, fixed event/tool, host executable, immutable argv/cwd and captured script hash; missing or modified artifacts are rejected, never silently refreshed.

### FR-3: No ambient discovery
WHEN a project contains Git hooks, instructions or scripts THEN the system SHALL not discover or execute them implicitly; only explicitly selected native-approved scripts may execute, and Git hooks stay disabled.

### FR-4: Policy and scope
WHEN an enabled hook runs THEN the system SHALL recheck current local execution authority and parent exec.run scope, native command policy and shared ExecPolicy; prompt, forbidden, missing approval or unknown rules block and hook output never grants authority.

### FR-5: Mandatory isolation
WHEN a hook child starts THEN the system SHALL use the existing mandatory platform sandbox and managed process tree; network remains denied and filesystem write is allowed only when locally approved within the parent workspace capability; unsupported platforms fail closed.

### FR-6: Bounded lifetime
WHEN hooks run THEN the system SHALL enforce eight registrations, deterministic ID ordering, one nonqueued invocation per registry, per-hook two-second timeout, bounded output and total budget, request deadline/cancel/revoke checks and actual descendant drain; no recursive trigger or automatic uncertain replay is allowed.

### FR-7: Truthful before and after
WHEN a mandatory before hook fails THEN the primary operation SHALL not start; WHEN an after hook fails THEN the result SHALL retain the actual primary outcome and state that side effects are not rolled back; raw hook output remains untrusted and is not returned as permission.

### FR-8: Production integration and evidence
WHEN release validation runs THEN the system SHALL exercise the real native dispatcher and native approval path with immutable script execution, denial, changed hashes, malformed bounds, deterministic order, before/after failure, cancellation, revocation and sandbox containment; Windows unavailable remains release-blocking rather than waived.

## 非功能需求
Maximum 8 hooks, 16 argv tokens, 8KiB manifest, 64KiB script, 16MiB executable hashing, 2s per hook, 4KiB output per stream, 16s overall hook budget. Registry approval is runtime-only and disabled on restart.

## 依赖关系
Existing native ChatAuthorizer/LocalAdmission, ExecPolicy, mandatory platform sandbox and native listener lifecycle. ISSUE-031 remains release required.
