# Design: Windows sandbox gate

## 概述
At2c5d133, process_tree_windows.rs::spawn creates suspended children and binds JobObject before resume but does not restrict filesystem/network. pty_windows.rs::AttributeList::new contains only ConPTY attribute. dispatch Core uses LinuxSandbox; NativeToolHost on recovered22c8c5e refuses non-Linux exec.run. No Windows AppContainer implementation exists.

## 技术方案
FR-1: Add immutable platform requirement/report types with no authority-minting constructor and conservative readiness. A Windows candidate is never a production permit. Do not change existing launch methods in this increment.
FR-2/FR-3: Native test-only Win32 harness creates a unique temporary tree and AppContainer package, applies minimal per-package fixture ACLs, sets SECURITY_CAPABILITIES and ALL_APPLICATION_PACKAGES_POLICY optout in STARTUPINFOEX, creates suspended, assigns kill-on-close JobObject, resumes and waits boundedly. Child is a purpose-built Rust fixture with fixed operations, not a shell. No host-wide prep or network capability. Owned cleanup occurs after child termination.
FR-4: Parent-owned loopback listener and outside canary prove unsandboxed controls. Same child contract verifies workspace write/read, outside read/write denial, loopback TCP denial and AppContainer token. Each observation carries a fixed case label. Failure at startup is a blocker, not successful denial.
FR-5: Production authorization paths unchanged. The test API cannot be reached from public MCP. Explicit unsupported shell/PTY remains failclosed.
FR-6: CI captures exact source SHA, individual cases, build exits and source hashes; Windows fixture pass is a foundation only. Linux regression must remain green. Current full release status stays incomplete.

## Threat review and unfinished engineering
LPAC needs explicit executable/runtime file access. Arbitrary existing workspace grants need separate crash-safe ACL ownership/recovery and junction/hardlink/root identity handling; this harness does not solve those. Standard toolchain startup may need host-wide preparation, which this scope forbids. No weak fallback. Fail tests honestly if Rust fixture cannot start without unsafe grants.

## Verification and rollback
Run locked local-agent fmt/clippy/full tests on Linux; Windows native same-source build/test gate. Control must show real access first, sandbox must deny same operations. Reverting additive model/harness/CI leaves existing authorization and durable journals untouched. No external publication by this worker.

## 文件结构
services/local-agent/src/isolation.rs; services/local-agent/src/bin/windows_sandbox_fixture.rs; tests/windows-sandbox; .github/workflows/windows-sandbox-foundation.yml. Launcher and fixture are separate test-only components.
