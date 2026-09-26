# ISSUE-022A — Shared Tool Runtime Foundation

Status: **ENGINEERING_VERIFIED / ADDITIVE_ONLY / NO_REAL_SIDE_EFFECTS / HOST_DEFERRED**

Published implementation: `935672250491afccfbfa47e7459ce227060db707`.

## Boundary

This increment adds an independent `services/local-agent` Rust crate and does not move or rewrite existing desktop tools.

It defines:

- bounded `ToolName`, `ToolSpec`, `ToolCall`, `ToolOutput`, and structured `ToolError`;
- deterministic `ToolRegistry` ordering and Direct / Deferred / Hidden exposure classes;
- explicit capability requirements and per-tool parallel-call declaration, defaulting to false;
- strict argument parsing and input/output byte budgets;
- opaque, non-serializable local admission state;
- registry-minted `VerifiedInvocation` required by every `ToolExecutor::execute` call.

The last rule prevents safe external callers from invoking a tool executor directly with cloud/model input while bypassing the registry's local-admission checks.

No shell, filesystem, Git, patch, PTY, sandbox, approval UI, cloud dispatch, or Tauri integration is introduced here.

## Verification

- Pre-publication exact-source CI: run `35726442664`, Windows 2025 and Ubuntu 24.04 PASS.
- Permanent feature CI: run `35726846341`, Windows 2025 and Ubuntu 24.04 PASS.
- Both platforms ran rustfmt check, Clippy with `-D warnings`, locked Cargo tests/checks.
- Unit tests: 9 PASS on each platform.
- Verified source blob receipt was imported without moving refs before publication.
- Initial failures are retained: unused imports, Rust 1.98 manual no-op waker lint, and a shallow-clone comparison failure. Lints were fixed and checkout depth corrected; no warnings or assertions were disabled.

## Acceptance

- [x] Additive crate only; existing desktop symbols are unchanged.
- [x] Name/schema/input/output limits and duplicate registration fail deterministically.
- [x] Registry ordering and exposure are stable on Windows/Linux.
- [x] ToolExecutor requires a registry-minted VerifiedInvocation.
- [x] Local admission is opaque/non-serializable; cloud tokens cannot substitute for it.
- [x] Strict parsing, redacted debug output, UTF-8-safe truncation and output bounds are tested.
- [x] Direct/Deferred/Hidden and parallel-call declarations are tested.
- [x] Windows 2025 and Ubuntu 24.04 native CI pass.
- [x] Rollback is additive: remove `services/local-agent` and its CI workflow; no durable authority data changes.
- [ ] Physical workstation/VPS/real ChatGPT acceptance remains deferred and is not PASS.

Downstream execution, PTY, policy, sandboxing, guidance and discovery remain separate delivery tasks.
