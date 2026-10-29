# Round 9 — local authority bridge validation

Classification: IMPLEMENTATION_CANDIDATE / NO_TOOL_DISPATCH / HOST_DEFERRED.

## Intended source scope

- `src-tauri/src/auth/local_authority.rs` — new local-only epoch/snapshot/ticket/permit types.
- `src-tauri/src/auth/mod.rs` — scoped internal export.
- `src-tauri/src/auth/聊天授权v1.rs` — storage attachment, read-only snapshot and local ticket issue/commit.
- `src-tauri/src/auth/聊天授权回归v1.rs` — local authority, drain, scope, Pause/Resume and revoke regressions.
- `src-tauri/src/runtime/execution_gate.rs` — monotonic availability generation and generation-bound admission.
- `src-tauri/src/runtime/mod.rs` — internal gate type export.
- this specification and the dedicated CI workflow.

No `call_tool`, tool registry, tunnel, OAuth, desktop UI, Nginx, deployment or production configuration is in scope.

## Failure-first / review record

A formatting-only rustfmt expansion initially touched 31 authorization/runtime files. It was discarded before publication; only the six intended Rust source paths remain. Review also tightened `attach_storage` so the existing execution fence and new epoch store are checked and published together under their mutexes, avoiding an in-memory half-attached state. Test assertions use `.err()` for opaque non-Debug tickets/permits.

## Gates

Local: `git diff --check`; standalone new module formatting; exact baseline blob comparison against current feature head. Native compilation and behavior are authoritative only after dedicated Windows/Ubuntu CI because the isolated development container lacks the full desktop Cargo dependency cache.

Release and real-host gates remain unchanged and fail closed.
