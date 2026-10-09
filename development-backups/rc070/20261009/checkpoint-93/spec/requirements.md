# Native birth and executable-source contract — SPEC ONLY

## 功能概述

Define the smallest conditional native mechanism that removes user child callbacks before startup-family attribution. Only read-only source research and three specifications are delivered. No native module, collector, compile, process control or product edit is authorized.

## 需求列表

### FR-1 — Native-only birth and atomic real ownership
WHEN the proposed birth primitive is called, it SHALL create the actual root and pidfd through clone3(CLONE_PIDFD) with SIGCHLD, without CLONE_VM/FILES/THREAD/PARENT/namespace flags or fork/atfork/Python preexec callbacks. Native-owned escrow and its non-droppable native registry link SHALL be preallocated before clone3. Actual created child/pidfd/private pipes SHALL be recorded using that existing storage before returning to Python or unblocking caller cancellation; no post-creation malloc or Python Capsule success may be required to retain ownership. No external numeric PID, Popen constructor, JSON or test boolean creates owner authority. The native child branch SHALL execute only reviewed direct syscalls and must never return to Python.

### FR-2 — Source-bound pre-exec and collector initialization
The child SHALL inherit a native-established blocked-signal mask, establish/verify subreaper, and execute a sealed fixed native root image through descriptor-based execveat. Unknown exec, signal-handler, image/build/ABI or descriptor binding SHALL refuse sole-child closure. The root image SHALL have its entire entry path audited, including no uncontrolled CRT/init/loader/instrumentation calls, and SHALL create no child before actual valid LAUNCH. Static build flags or installed Linux headers alone are not runtime proof. No actual syscall support is assumed from headers.

### FR-3 — Fixed lifecycle limits and separate closure outcome
The .2 READY deadline SHALL include birth, BOOTREADY, Python startup and actual original worker READY, without restart. Stop2/finish2/reader5/outer2700/7/2/2/2MiB remain unchanged. Before-first-LAUNCH-write differs from before-original-request/G; partial attempt state is sticky before a syscall. Native root family ECHILD, actual owned IO EOF/drain/once-close and same created terminal are necessary; stderrDEVNULL has no observable EOF. A safe startup abort SHALL never become command success or original fake DONE. Uncertainty, primary and every cancellation object SHALL remain preserved. Independent finite design review is required before separate implementation/control authorization; no current original-method or whole488 launch permission.

## 非功能需求

No duplicate FD-number close after UNKNOWN; immediate native escrow precedes checks and Python object exposure. A native-birth failure/cancellation must retain the true owned record rather than losing it in Python return/unwind. Privileged external injection is outside this limited design and must be identified rather than silently assumed handled.

## 依赖关系

New source-bound native birth module, image sealer, no-CRT root collector, real build/disassembly/link-map identity, kernel ABI/support and future owned-process/IO/cancel controls. All are absent or unproven now. Publisher issuer/same-client/server-held-tag service remains independently MISSING.
