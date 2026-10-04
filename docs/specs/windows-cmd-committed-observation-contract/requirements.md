# 需求文档：windows-cmd-committed-observation-contract

## 功能概述

Prepare, then only after exact root pre-edit review implement, two finite additive Windows CI controls: parameterless `/d /q /c cd` and `/d /q /c type direct.cmd`. Their producer receipts describe raw observations; accepted control results are independently derived only from complete trusted committed artifact evidence. All eight published cases and original failure reductions stay intact.

Baseline: Eswink/coding-tools-mcp commit `e5b4d80668e4e925f1f71c152b4f94e452771aff`, tree `4849505cc8bd6501c2271f5442f046883839a4fb`. Durable source is `/workspace/shared/windows-cwd-read-controls/source`. This is freshly rebuilt preparation from published source, not recovered lost code. The sealed preparation packet contains no implementation. Root reviewed its exact hashes and HIGH warning at02:54 on2026-10-03 and approved bounded local implementation; a precise four-module pure Python split was separately approved at02:59. Commit/push/CI require fresh staged graph/gencommit/exact-tree review.

## 历史经验与坑（来自记忆库）

- Prior independently verified published run36809192104/job110200216989/artifact11138499711 measured the same cmd hash64afc6db3aad1289533662e2d79e27dd55c7dcdb8cd918b08e145ad82ad5acb4/version10.0.26100.7309 in three fresh cases. Builtin exit23 returned23; original570-byte batch and minimal9-byte batch returned1 with empty streams. This turn does not claim to have re-downloaded/reverified the missing extracted artifact
- Artifact historical size2391864/SHA25610e9b76c4566ce6a7ec033d0cf695e7e2029612aeed2d80e4b8055e8fdecae1c; prior reviewer verified ZIP CRC/all246 hashes. Comment5923607862 on #81 refers to3f6357d and is not an e5b4d806 count source
- Exact minimal bytes are ASCII `exit 23` plus CRLF, SHA256cab50bf1c23956b80d898c7af8f1c1e853e5bba6b14b8a2fbe4981d382fb7e8a. No entry marker exists, so do not claim failure before entry or infer an exact phase. The batch tail is unquoted literal direct.cmd; no quoting defect is established
- Old/tmp Plan/specs/packet/index/artifact files were lost. Supported explicit and latest resume found no retained Plan after coordinated Probe4.0.1 restoration. The new durable Plan was resumed and extended, not silently replaced. Old packet hash is unavailable; historical spec digests are not present-byte verification
- #86 snapshot hardening has a documented refusal and is untouched. Oct1 generic cybersecurity flag has no operation payload: it neither identifies a particular Windows refusal nor clears an unknown refused operation. No lost operation is reconstructed or retried

## 术语定义

- Comparable process: fresh coordinator-owned profile/private root/process and stdio objects, same runtime bytes/templates, independently passing the current predicate; not literally the same token/directory object
- Raw match: exact case-bound command/hash/cwd/provenance/observed authority, terminal queried exit0 and byte output contract; not later persistence or run acceptance
- Accepted control: external artifact evaluation of trusted exact-source/current-run evidence, completed nonce-bound lifecycle, complete persisted case/raw facts and recomputed match
- Completion: existing no-replace completed journal filename binds immutable preconditions. The body remains state=pending; phase labels alone are not completion

## 范围边界

In scope: two new fixed cases at slots8/9, finite setup/routing, existing strict raw capture reuse, independent raw schema/reducers,10-row accounting, injected managed negatives, source-union mutations and pure committed-artifact evaluator/fixtures in five local Python modules with one unified audit/test entry, existing diagnostic workflow wiring and README.

Out of scope: arbitrary command/filename input; /s, /a, /u, call, /b, redirection/chaining; codepage/registry/ETW changes; warm-up/fallback; new native APIs, privileges, capabilities or ACL grants; production/snapshot/real-host acceptance; packaging/release; producer-side accepted-result files or any post-Resolve action.

## 需求列表

### FR-1: Preserve immutable controls and all old verdicts
**优先级:** Must
**用户故事:** As a reviewer, I need an additive diagnostic without repaired historical failures or expanded authority.
#### 验收标准（EARS）
1. WHEN implementing THEN retain the first eight case identities/order/generators/commands and original-six/sentinel/batch reducers byte-identically.
2. WHILE preparing/executing/cleaning either new case THE existing actual-token, ordinary negative control, stdio3, profile/ACL, job/deadline, selected-parent/recovery and cleanup/journal helper code SHALL remain unchanged; the exact sensitive spans listed in design SHALL remain byte-identical.
3. WHEN reporting THEN observed AppContainer1/exact profile SID/zero capabilities/LowIL and query-only identification duplicate/four AccessCheck descriptors SHALL remain the named surrogate policy; TokenVerified=false, Win32class46 error87 and nativeC0000003 remain failures. NetworkDenialProven remains false.
4. IF new raw/accepted controls succeed THEN old native/nested/runtime failures SHALL remain independently measured and fail the workflow; no script-entry, mutation, runtime, network or production credit is added.

### FR-2: Append exactly two independent fresh cases
**优先级:** Must
**用户故事:** As a diagnostic reviewer, I need cwd reporting and relative TYPE output under unchanged launch conditions.
#### 验收标准（EARS）
1. WHEN the unchanged gates permit THEN append cmd-cwd and cmd-read-direct at slots8 and9, with Launcher.Kind=cmd and their own case identity, current profile/root/process and exact3 inherited stdio handles.
2. WHEN assigning/resuming either THEN its copied cmd bytes SHALL equal the same-run original cmd hash, using unchanged explicit lpApplicationName, absolute private-workspace lpCurrentDirectory, environment/grants and30-second deadline. Each target must independently satisfy the existing predicate; no earlier target's authority is reused.
3. WHEN preparing cmd-read-direct THEN generate the existing9-byte minimal fixture and use a new exact-case adapter into the unchanged minimal-capture core; actual source/copy/readback hashes/bytes/identities and closes SHALL be verified before profile/process creation.
4. IF cwd output mismatches or is non-ASCII/inconclusive but cleanup is certain THEN TYPE SHALL remain independently eligible under unchanged PilotMayAdvance. An integrity/ownership failure still blocks progression.

### FR-3: Record strict bounded raw output
**优先级:** Must
**用户故事:** As an evidence consumer, I need exact bytes and successful reads/closes rather than text-normalized success.
#### 验收标准（EARS）
1. WHEN target stop/job drain and original captures are confirmed THEN read each actual stdout/stderr object by original identity and its artifact copy through unchanged bounded no-follow raw-read primitives, compare raw arrays, require stable single-link ordinary metadata and all single-attempt closes before cleanup.
2. WHEN cwd matches THEN stdout SHALL equal exact ASCII recorded workspace plus one CRLF, stderr empty, successful exit query and exit0. Non-ASCII expectation SHALL be explicitly unsupported/inconclusive without /u,/a,codepage change or normalization.
3. WHEN TYPE matches THEN stdout SHALL equal nine bytes65,78,69,74,20,32,33,0d,0a, stderr empty and independently queried exit0; source fixture proof and command/hash/cwd/case identity remain mandatory. TYPE never requires cwd output success.
4. IF wrong/missing identity/command/hash/cwd, BOM/LF/extra/truncated bytes, missing/uncertain read/close, wrong object/reparse/multilink/oversize, missing observed-token policy proof, extra handle, timeout or stale exit occurs THEN raw match SHALL be false. Capture uncertainty SHALL retain recovery; contained mismatches may clean up.

### FR-4: Separate producer observations from accepted controls
**优先级:** Must
**用户故事:** As a reviewer, I need late failures to prevent accepted-control claims even when earlier raw bytes matched.
#### 验收标准（EARS）
1. WHEN any producer receipt is serialized THEN only case CmdCwdObserved/CmdReadObserved and run CmdCwdRawObservationMatched/CmdReadRawObservationMatched SHALL be added; neither new ObservationPassed field nor computed property is permitted.
2. WHEN external artifact acceptance is evaluated THEN CmdCwdObservationPassed/CmdReadObservationPassed SHALL be derived only from trusted exact-source/run identity, complete independently verified bytes, committed linked journals, underlying lifecycle/persistence facts and recomputed per-case matches.
3. IF case.json/matrix persistence, runroot/finalscan/pinclose, final evidence, preconditions bind/verify/read/close or resolve/rename fails or remains unproven THEN accepted fields SHALL remain false/not established. Clearing in-memory fields later is not a substitute for safe persisted schema.
4. WHILE validating snapshots THE evaluator SHALL respect source-stage differences, reject contradictory fixed facts and accepted-field injection, and never require state=completed in journal bodies or whole-JSON snapshot equality.
5. AFTER existing final C# Resolve THEN no new assignment, helper, computation, read/write, verification, cleanup or launch SHALL be added.

### FR-5: Keep scoped counts and interpretations truthful
**优先级:** Must
**用户故事:** As a reviewer, I need exact allocated-resource accounting and bounded conclusions.
#### 验收标准（EARS）
1. WHEN all10 cases allocate/finish THEN report10 case journals+1run journal; otherwise count actual allocations only and preserve exact existing no-allocation preparation outcomes. Accepted new controls themselves cannot be unallocated.
2. WHEN reporting selected-parent counts THEN use current actual pins/guards/closes. Historical6pins/34boundaries and predicted42 full-path guards are not measurements or universal CleanupConfirmed.
3. WHEN cwd/TYPE succeeds THEN interpret only its own fresh process/root. TYPE output is no proof of prior batch opening/parsing/execution. Negative output proves neither denial nor a precise failing phase.
4. WHEN run scope completes THEN listener/preparation/outer capture/upload remain separately accounted; original token direct-query failure and CleanupConfirmed=false are not upgraded.

### FR-6: Validate exact source, effective negatives and committed artifact
**优先级:** Must
**用户故事:** As a reviewer, I need a tested finite increment and auditable failure behavior before publication.
#### 验收标准（EARS）
1. BEFORE any code edit THEN exact-source fresh upstream impact and manual missing-edge analysis SHALL reach root, including HIGH/CRITICAL warnings and exact spec/packet hashes.
2. AFTER authorized implementation THEN all7 existing portable audits plus new audit and all6 existing managed test entries plus new entry SHALL pass; new tests SHALL use injected operations/pure synthetic artifact bytes, never real Windows fault injection.
3. BEFORE any authorized commit THEN check unchanged protected files/spans, exact source union and actual gitnexus_detect_changes; review real diff and relevant test results.
4. WHEN authorized exact-source Windows CI runs THEN retain the same build/native controls/20nested rows and one10-case pilot with independent old failure semantics; verify source/tree/run/job/attempt, ZIP CRC/all manifest entries and required raw/authority/lifecycle evidence before deriving acceptance.

## 非功能需求
- NFR-1: Existing1MiB metadata/stream bound and30-second target deadline; exactly2 new finite launches, no retries
- NFR-2: No new P/Invoke/import/privilege/capability/ACL/template rights, no initializer/alias/member collision; source tests enforce entire executable union
- NFR-3: PS5.1-compatible managed code/tests; individual edited/new files <=500 lines, no package/version changes
- NFR-4: Artifact evaluator is pure on trusted outer context plus bounded member bytes; no ZIP/network acquisition or host access, and synthetic success is not Windows evidence

## 依赖关系
Root exact pre-edit review; restored pinned Probe4.0.1/GitNexus1.6.9 offline tooling; exact published source; separately authorized future CI and trusted outer artifact verification. Public command contracts: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cd ; /type ; /cmd. Historical source: https://github.com/Eswink/coding-tools-mcp/commit/e5b4d80668e4e925f1f71c152b4f94e452771aff .

## 检查清单
- [x]6 stable Must FRs with testable EARS conditions
- [x] Fixed scope, missing-material history, denial boundaries and actual-review blocker explicit
- [x] Raw matches separated from committed accepted controls
- [x] No implementation/runtime success claimed by preparation

Root clarification03:28: opaque legacy JSON contributes no prerequisite or accepted-result truth. Its bytes remain hash-verified only; reject accepted-result fields recursively in every parsed contributing receipt/wrapper. Test opaque field injection cannot change verdicts and cannot substitute for missing required parsed proof.
