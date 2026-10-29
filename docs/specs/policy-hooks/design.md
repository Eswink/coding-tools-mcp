# Design: policy-hooks

## 概述

Native-owned registry and production dispatch.

## 技术方案
FR-1/FR-2/FR-3: ToolContext owns an Arc HookRegistry. Native approval owner uses current ListenerContextLease for prepare/preview then consumes an opaque PreparedHooks on exact native confirmation. Artifact revalidate runs outside the lease lock; install_prevalidated commits only state under the short lease callback, requires a fresh opaque marker and the original registry generation. No MCP approval/config tool exists. Captured script bytes are fed to the approved interpreter through stdin; execution never rereads attacker-replaced script bytes. Current source is also hash-checked before invocation. Host executable must be a regular installed ELF inode not owned/writable by the agent identity; fingerprint changes fail closed. An owned read-only FD pins that exact inode through process completion. Linux execution uses /proc/self/fd/N; the existing sandbox grants only the selected executable inode, not any /proc directory, and CLOSE_RANGE_CLOEXEC takes effect after exec resolves the FD path. Path swaps cannot substitute another executable. A bounded Unix-only host-owned ExecSpec argv0 override preserves the exact approved program-name semantics while executable selection remains the pinned FD; it is never a model/JSON field. Captured source and digest are shown only in the native review preview. Script source revalidation uses openat2 beneath a pinned workspace FD with no symlink/magiclink traversal.

FR-4/FR-5: Dispatcher invokes hooks only after conversation intercept and native parent policy. Every hook checks native policy, shared ExecPolicy and current native admission; a subprocess always carries the existing LinuxSandbox (read-only by default, no network). No weaker fallback is allowed. Windows without an implemented/proven adapter returns unsupported. Explicit native approval chooses exact fixed command/argv/cwd and optional workspace-write subset; it never expands parent scope or network. Dependencies remain untrusted sandboxed inputs, not authority.

FR-6: Immutable registry generations and one try-lock invocation serialize bounded events without queuing; disable or generation change cancels work. Context carries outer native request deadline/cancellation. Every child retains actual native drain accounting and native admission until observed termination; uncertainty quarantines. A dedicated admission RAII guard retains the opaque native permit on uncertain termination or panic; dropping/replacing a ToolContext is not a termination receipt and cannot release that native occupancy. Known-not-started and verified process/tree/output completion release normally. Cloud Hook uncertainty maps to ExecutionUnknown before journal completion, preserving the original durable claim. Cloud outer durable request journal continues to precede hooks, and no hook replay mechanism exists. Restart never auto-enables hooks. Thread-local recursion guard prevents nested hook dispatch.

FR-7: Before failure reports primary_started=false. After failure preserves primary_result, primary_started=true, no rollback and no retry; primary success is not fabricated. Only bounded hook IDs/stages/codes are returned, never raw output or grant claims. Synchronous parent timeout is reduced after before hooks to the remaining native deadline. Async submission must still be accepted before that deadline, while its independently approved execution budget and deduplication fingerprint remain unchanged.

FR-8: Hook registry/execution integrated in actual tools dispatcher; independent library tests are not production proof. Native commands and lease approval belong to the native lifecycle integration worker, and tests must exercise those APIs on the combined candidate. Existing Git hooks disabled behavior remains unchanged.

## 文件结构
src-tauri/src/tools/policy_hooks.rs and policy_hooks/*: registry, pinning, execution, tests.
src-tauri/src/tools/context.rs, dispatch.rs, cloud_host.rs/live.rs: owned registry, real dispatch and cancellation/deadline bridge.
Native commands/approval integration is coordinated separately, not duplicated here.

## Validation and rollback
Fail-first security tests precede positive claims. Rollback disables native registry; do not delete recovery or cloud journals. Full release scope and platform/package gates remain open until actual combined-tree evidence passes.

Async logical-job ordering: the existing conversation-scoped task store atomically persists cmd/canonical-cwd/frozen-budget fingerprint and request_id before any before/after hook. Only the reservation creator runs hooks and launches primary; concurrent or later outer requests return the same queued/terminal job. Before failure persists failed or interrupted state, with unknown process state retaining capacity. A crash between reserve and checkpoint restores the queued record as interrupted, never resurrects hooks or primary. Native authority is rechecked by the existing request interceptor and child admission; configuration cannot grant or replace it.
