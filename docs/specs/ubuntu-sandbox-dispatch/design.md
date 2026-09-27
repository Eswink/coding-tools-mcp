# 设计文档：ubuntu-sandbox-dispatch

## 概述

The baseline desktop chain is `listener -> MCP tools/call -> tools::call_tool ->
exec::exec_command -> exec::run_command -> Command::spawn/process_tree::spawn`.
Async tasks re-enter the shared dispatcher. The independent local-agent
`ExecSpec/PtySpec::with_sandbox` methods are not wired into this chain.
The desktop TTY flag is not evidence of native PTY compatibility.

## 技术方案

1. Bind the canonical workspace AND its retained directory object in the native host,
   not in model JSON. Background snapshots must share the same immutable binding.
2. Preserve local admission and command-policy checks before spawning. A one-use native
   spawn ticket must capture conversation/workspace/scopes, expiry, generation and the
   required isolation domain. It must be revalidated at the existing commit boundary.
3. Linux child setup must consume a mandatory sandbox policy; missing or failed setup
   is `SANDBOX_REQUIRED` or `SANDBOX_SETUP_FAILED`, without fallback or retry.
4. Apply prepared restrictions after fork and before exec, without allocating or
   locking in `pre_exec`; do not restrict the parent runtime. Reuse reviewed library
   primitives instead of copying seccomp/Landlock implementations into the desktop.
5. Keep stdout/stderr limits, cancellation, timeout, session ownership and durable
   no-replay behavior. Do not claim the old TTY flag satisfies the native PTY contract.
6. Reject model-controlled isolation disable fields. Fixed host compatibility policy
   may grant explicit read/execute runtime paths but never arbitrary workspace escape.

The exact cross-crate adapter API and dependency changes are deliberately NOT introduced
in this test-only increment. A public `LocalAdmission::new(raw IDs)` would weaken the
capability boundary and is not an acceptable shortcut.

## 影响面与实施闸门

Pinned GitNexus 1.6.9 rebuilt the baseline: 11,649 nodes, 26,396 edges. FTS unavailable;
source inspection supplemented the graph. Results are not a security certification.

| Symbol | Direct | Total impacted | Risk |
|---|---:|---:|---|
| exec_command | 1 | 8 | HIGH |
| run_command | 2 | 8 | HIGH |
| call_tool | 5 | 8 | HIGH |
| ToolContext::from_workspace_with_harness_root | 2 | 58 | CRITICAL |
| ChatAuthorizer::commit_local_admission | 0 resolved | 0 resolved | LOW (coverage limited) |

Issue #73 bars same-turn production edits after HIGH/CRITICAL. None of these production
functions is edited. The next production increment must review these exact caller
sets and preserve admission/async task/shared context contracts before making changes.

## 文件结构

`tests/cloud-gateway/ubuntu_sandbox_dispatch.rs` is injected into an isolated checkout's
auth test module by `sandbox-dispatch/run_probe.py`; the runner restores the original
module in `finally`. The checked-in production tree is byte-for-byte unchanged.
The workflow records source identity, controls and red assertions separately. Its final
safety gate stays FAILED while mandatory acceptance is false, even when diagnostics work.

## 验证与回滚

Four controls: unapproved denial, approved in-workspace success, pause/revoke denial and
foreign-chat denial. Seven initial acceptance probes: omitted policy, outside read,
outside write, symlink, loopback network in safe mode, model disable fields and TTY flag.
They do not constitute cancellation/restart/no-replay/toolchain completeness.

Only temporary fixtures and IPv4 loopback are used. No real secrets or remote services.
A future fix runs the SAME assertions in acceptance mode; no marker deletion, weakening,
ignore annotations or zero-match green results. Revert only this test/spec commit to
remove diagnostics; never reset shared refs or delete durable authority state.

## 一手技术参考

- Linux kernel Landlock documentation: https://docs.kernel.org/userspace-api/landlock.html
- Rust CommandExt/pre_exec safety: https://doc.rust-lang.org/std/os/unix/process/trait.CommandExt.html

## 对应需求

Authority: FR-1, FR-2, FR-3. Enforcement: FR-4, FR-5. Acceptance: FR-6, FR-7.
