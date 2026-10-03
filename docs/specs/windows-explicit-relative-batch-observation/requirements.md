# 需求文档：windows-explicit-relative-batch-observation

## 功能概述

Append one CI-only explicit-relative batch observation to the exact published `071d5590d689d3b30c0dba5fdd7697264ba04f21` baseline (tree `3915136fe50228184e9c92f5764d4762b7475964`). The sole new command tail is `/d /q /c .\direct.cmd`, using the existing nine ASCII/CRLF bytes `exit 23\r\n`. This is a pathname-qualification discriminator. It is not a root-cause finding, quoting fix, runtime-support declaration, or release admission.

## 历史经验与坑（来自记忆库）

The preceding finite Plan converged after actual run `37096520158`, artifact `11264512816`: externally committed cwd/read controls passed while original/minimal batch cases retained exit 1. Late fallible cleanup/persistence requires raw-only producer receipts and independent final-journal acceptance. A synthetic removal of only the final completed journal preserved genuine raw matches but rejected accepted fields. No formal memory service result is claimed.

## 术语定义

- Raw match: fixed command/payload/provenance and measured empty streams with queried exit 23 satisfy the narrow relative-case observation predicate
- Accepted observation: external interpretation after complete current-run artifact provenance, case/run journals and stage-specific persisted receipts validate
- Retained cases: the ten baseline cases in their existing exact order, including cwd/read at indices 8/9

## 范围边界

In scope: one appended `cmd-relative-batch-exit23` case, finite helper/schema/cardinality adaptations, shared managed/portable negatives, exact artifact acceptance, source audits, workflow wording and documentation.

Out of scope: marker batch, same-process read-then-run, `/s`, `/a`, `/u`, `call`, chaining, redirection additions, arbitrary command input, fallback, warm-up, code-page changes, native API additions, privileges/capabilities/ACL/permission changes, registry/ETW/network work, production/snapshot changes, merging or release admission. Known snapshot #86 refusal, unknown refused actions and the independently cancelled procfs write remain untouched. A prior unidentified flag is not reconstructed or treated as clearance.

## 需求列表

### FR-1: One fixed append-only discriminator

**优先级:** Must
**用户故事:** As the diagnostic reviewer, I need one explicit-relative comparison to isolate command-path qualification without varying the payload or old cases.

#### 验收标准（EARS）

1. WHEN the pilot coordinates cases THEN it SHALL preserve all ten baseline case positions and append exactly `cmd-relative-batch-exit23` at index 10.
2. WHEN the new case is prepared THEN it SHALL use the same current-run original cmd.exe bytes, fixed tail `/d /q /c .\direct.cmd`, explicit absolute application name/workspace cwd, existing environment template, and payload hex `657869742032330d0a` with SHA256 `cab50bf1c23956b80d898c7af8f1c1e853e5bba6b14b8a2fbe4981d382fb7e8a`.
3. IF a case has a new profile/PID/root THEN it SHALL independently pass the existing predicate; no identical-token or identical-directory claim follows from shared construction.
4. WHEN the new case runs THEN it SHALL use the existing three fresh private regular stdio handles, job/deadline/drain and cleanup sequence without additional authority.

### FR-2: Strict raw observation only

**优先级:** Must
**用户故事:** As the reviewer, I need genuine byte/exit facts that survive later persistence failure without becoming accepted producer verdicts.

#### 验收标准（EARS）

1. WHEN the subject has stopped, drained and closed THEN the existing four bounded raw reads SHALL bind source streams to their original identities, verify evidence copies, exact lengths/hashes, single-link regular files, and confirmed reads/closes.
2. WHEN command/cwd/binary/payload/capture/authority facts are valid, both streams are empty, wait is signaled and exit query is 23 THEN the case SHALL record `CmdRelativeBatchExit23Observed=true` and the run SHALL reduce `CmdRelativeBatchRawObservationMatched=true`.
3. IF output has a BOM, LF, additional/truncated bytes, uncertain read/close, wrong identity, reparse/multilink/oversize file, stale exit, timeout or unverified pre-resume facts THEN the raw match SHALL remain false or the raw receipt SHALL fail closed as specified.
4. WHILE cwd is non-ASCII THEN the new case SHALL remain eligible because expected output is empty; existing cwd unsupported-encoding behavior and independent TYPE behavior SHALL remain unchanged.

### FR-3: Stage-correct committed acceptance

**优先级:** Must
**用户故事:** As the artifact consumer, I need acceptance only after the complete final commit protocol validates.

#### 验收标准（EARS）

1. WHEN parsing the new-schema artifact THEN the pure evaluator SHALL require strict field/types, exact eleven-case ordering/counts, all prior matrix snapshots plus matrix-11, exact journal bindings and source-correct case/precondition/final receipt projections.
2. IF run-root removal, selected-parent close, final evidence write/close, journal bind/flush/close/verify/resolve or case.json persistence fails or is missing THEN accepted fields SHALL remain false even when genuine raw matches remain true.
3. WHEN complete committed evidence validates THEN only the external evaluator SHALL return `CmdRelativeBatchObservationPassed`; no producer accepted field or post-Resolve action SHALL be added.
4. IF a legitimate new-case exit/output mismatch occurs THEN it SHALL not erase valid prior cwd/TYPE raw matches or accepted observations after common completion validates; corrupt shared evidence SHALL block common completion.
5. WHILE legacy JSON is opaque THEN it SHALL provide no prerequisite or accepted-result truth; recursive forbidden accepted-key checks SHALL cover every parsed contributing receipt/wrapper.

### FR-4: Preserve security and original verdicts

**优先级:** Must
**用户故事:** As the reviewer, I need this diagnostic to leave authority and original failure truth intact.

#### 验收标准（EARS）

1. WHILE adapting finite observation helpers THEN original fixed commands, `VerifyPilotSignature`, `PilotMayResume`, token/handle/ACL/parent/recovery/cleanup primitives and final fallible journal sequence SHALL remain byte-identical.
2. WHEN eleven rows exist THEN prior cwd/read reducers SHALL retain their original slots and predicates, with only the explicit bounded cardinality adaptation; all six original aggregate reducers and both prior sentinel/batch reducers SHALL retain their semantics.
3. WHEN reporting authority THEN AppContainer/profile SID/zero capabilities/LowIL and fixed AccessCheck observations SHALL remain surrogate facts; `TokenVerified=false`, Win32 class46 error87/native `C0000003` and `NetworkDenialProven=false` SHALL not be relabeled.
4. WHEN reporting cleanup THEN evidence SHALL count the actual eleven case outcomes, up to twelve completed journals and selected-parent pins/guards for that run; scoped cleanup SHALL not become universal `CleanupConfirmed`.

### FR-5: Reused verification and truthful interpretation

**优先级:** Must
**用户故事:** As the maintainer, I need a small reviewable increment with real tests and clear diagnostic limits.

#### 验收标准（EARS）

1. WHEN implementation is proposed THEN fresh exact-source upstream impacts and any HIGH/CRITICAL warning SHALL precede edits, and root SHALL review the finite packet.
2. WHEN implemented THEN existing 330 portable methods and seven managed entrypoints SHALL remain covered; finite new negative parameter rows/method counts SHALL be explicit, without duplicated large harnesses or compressed code to evade caps.
3. WHEN published after review THEN actual PS5.1/managed/metadata/Rust/original diagnostic workflow checks and exact run/artifact hash/CRC/manifest/source verification SHALL be performed; local syntax checks SHALL not substitute for hosted execution.
4. IF explicit-relative exit 23 differs from retained bare-name exit 1 THEN the conclusion SHALL be path-qualification-sensitive behavior under comparable fresh cases only; IF both return 1 THEN lookup/open/batch initialization/execution remain unresolved.
5. WHILE Windows documentation predicts equivalent pathname resolution and the disabling environment variable is absent THEN this SHALL be stated; no established quoting defect, failure-before-entry, general inability to read, network denial or runtime-support inference is permitted.

## 非功能需求

- NFR-1: Preserve all published security helper spans and unchanged tracked blobs outside the reviewed test/spec scope; no source implementation during preparation
- NFR-2: Reuse the bounded 1 MiB capture limit and pure evaluator; no acquisition, OS, process or network operations in evaluator/test fixture modules
- NFR-3: Retain readable source and explicit UTF-8 audit reads; exact line-cap or split changes must be proposed before implementation

## 依赖关系

Published ten-case baseline, existing fixed minimal-byte capture core and raw/evaluator contracts; pinned Probe 4.0.1 and GitNexus 1.6.9; existing Windows diagnostic workflow. Documentation sources and attribution are in design.md.

## 检查清单

- [x] Five stable FRs have measurable EARS acceptance and explicit exclusions
- [x] Prior published evidence and late-failure lesson preserved
- [x] Preparation precedes root review and implementation
- [x] Old failures, authority limits and diagnostic interpretation remain explicit
