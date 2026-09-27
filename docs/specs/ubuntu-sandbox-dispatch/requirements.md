# 需求文档：ubuntu-sandbox-dispatch

## 功能概述

Complete mandatory Ubuntu host isolation without creating local authority from cloud/model data.

## 范围边界

In scope: native authority binding, retained workspace identity, Process/TTY spawn enforcement and automated integration acceptance.
Out of scope: physical workstation/VPS/ChatGPT tests, main merge, deployment, packaging, Hooks, worktrees and other workstreams.

## 需求列表

### FR-1: Preserve native local authority

WHEN a request lacks the approved conversation/workspace/scopes THEN the host SHALL deny it before any child process or sandbox policy can authorize it.

主子规格: authority.

### FR-2: Bind the approved workspace object

WHEN the workspace is admitted THEN the host SHALL bind its retained directory object to the execution domain; replacement paths and symlinks SHALL NOT change the approved object.

主子规格: authority.

### FR-3: Fence revocation and restart

WHEN revocation, expiry, pause or a new boot wins before dispatch commit THEN the host SHALL reject stale tickets; committed work SHALL retain the existing draining and no-replay contract.

主子规格: authority.

### FR-4: Make isolation mandatory

WHEN an approved Linux Process or TTY request reaches spawn THEN the host SHALL attach the required sandbox, or return SANDBOX_REQUIRED/SANDBOX_SETUP_FAILED before exec. Omitted policy SHALL NOT select legacy unsandboxed execution.

主子规格: enforcement.

### FR-5: Keep authority outside model arguments

WHEN model arguments try sandbox=false or disable_sandbox=true THEN the host SHALL reject the unsupported fields or enforce isolation independently. Working-directory, filesystem and network constraints SHALL NOT be relaxed by those values.

主子规格: enforcement.

### FR-6: Prove actual dispatch containment

WHEN synthetic authenticated requests traverse /mcp THEN automated tests SHALL prove workspace read/write and symlink containment, network denial and valid in-workspace execution through the real dispatcher, not only ProcessManager fixtures.

主子规格: verification.

### FR-7: Preserve lifecycle and evidence

WHEN implementation is a candidate for integration THEN automated checks SHALL cover cancellation, timeout, output caps, admission expiry, restart/no-replay, supported toolchains and unchanged Windows behavior, tied to exact commit/tree; missing tests SHALL remain unverified.

主子规格: verification.

## 非功能需求

All command I/O, test runtimes and shutdown waits are bounded. Tests use only fixture-owned
files and loopback sockets. Evidence must distinguish compiler/setup failures, exact red
assertions, ignored tests and zero matches. Sandbox setup is fail closed; no retry without
isolation. Kernel policy must not be installed on the parent application thread.

## 依赖关系

See spec-manifest.json. Existing local authority, execution policy and LinuxSandbox are
separate contracts; the current local-agent admission has no public constructor and must
not acquire a general deserializing constructor as an integration shortcut.
