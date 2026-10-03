# 需求文档：windows-applocker-script-observation

## 功能概述

Prepare one independent, read-only AppLocker record observation for the existing explicit-relative batch case on published 859c7bddc1018c587afa18d3ad84a15825e375ff (tree 4234f86632c1df2c7239c1678cb5d41918613820). The verified run37102342565/artifact11266328728 retains exit1 with empty streams for that case; cwd and TYPE were accepted independently. The experiment can identify a matching recorded AppLocker decision, not cmd's general failure stage or root cause. This specification does not authorize implementation or a new Windows run before root's exact pre-edit review.

## 历史经验与坑（来自记忆库）

Prior diagnostics distinguish raw observations from complete-run acceptance. The markerless nine-byte payload proves no entry stage. Separate profiles/PIDs/roots are comparable constructions, not the same objects. Existing direct LPAC query failures, surrogate AccessCheck evidence, original aggregate failures and NetworkDenialProven=false remain authoritative. Snapshot #86, the cancelled procfs write and unknown prior refusals remain untouched. No memory retrieval was available; published source and verified artifact evidence are the basis.

## 术语定义

- Invocation bracket: UTC and monotonic samples around the entire unchanged run-pilot.ps1 invocation; not a target-lifetime window
- Raw record match: one existing record selected by a single service-side query and rechecked for exact fixed fields, with all record/reader resources closed
- Reviewed correlation: raw match bound to independently authenticated artifact/source and complete existing journal protocol
- Inconclusive: unavailable, unsupported, absent, ambiguous, malformed, incomplete, or failed observation; never policy absence or permission success

## 范围边界

In scope: one local existing AppLocker MSI/Script channel, provider Microsoft-Windows-AppLocker, IDs8005/8006/8007, SCRIPT policy, existing slot10 target PID and exact generated direct.cmd path, fixed invocation UTC bracket, bounded sanitized ID/time output. Prepare six new sibling test-only code files, two existing documentation/workflow changes and three specifications (eleven paths).

Out of scope: new cmd variants/cases, host-wide logs, channel enumeration, provider enumeration, subscriptions, audit/tracing enablement, registry/policy/security changes, elevation, permissions/capabilities/ACL changes, new native APIs, process reopening, filesystem access to the deleted target root, network, fallback or relaxed queries, arbitrary command/channel/path input, production/snapshot changes, transport/procfs work, remote publication before reviewed candidate.

## 需求列表

### FR-1: Preserve existing execution and collect an outer time bracket

**优先级:** Must
**用户故事:** As a diagnostic reviewer I need the exact existing eleven cases and original failures preserved while the observer runs independently.

#### 验收标准（EARS）

1. WHEN observation is enabled in this diagnostic lane THEN the workflow SHALL execute its existing literal pilot invocation exactly once with unchanged arguments, condition and original exception/nonzero result.
2. WHEN the pilot completes or throws THEN the wrapper SHALL sample end UTC/monotonic time before observation work and SHALL preserve LASTEXITCODE value and absent/present state.
3. IF observer setup, sampling, parsing, query, disposal or writing fails THEN it SHALL NOT replace the pilot exception or turn its failure into success.
4. WHILE implementation proceeds THE existing C#/PowerShell pilot, all eleven commands, all old evaluators/audits/tests and journal final fallible sequence SHALL remain byte-identical.

### FR-2: Validate exact existing identity and a finite query before acquisition

**优先级:** Must
**用户故事:** As a reviewer I need the event service to receive all target restrictions before any record is delivered.

#### 验收标准（EARS）

1. WHEN preparing a query THEN strict bounded JSON parsing SHALL reject duplicate keys, nonfinite numbers, type confusion, unknown top-level keys and untrusted/missing identity; only fixed artifact member paths may be read.
2. WHEN identity validates THEN PID SHALL be a positive canonical integer no greater than Int32.MaxValue, and case/root/cwd/command/binary/payload identity SHALL agree across fixed process ownership, case and final-run receipts.
3. WHEN a bracket validates THEN its UTC timestamps SHALL have exactly seven fractional digits and Z, start<=end, elapsed milliseconds in0..900000, wall interval<=900000ms and wall/monotonic discrepancy<=2000ms.
4. WHEN constructing the sole query THEN channel, provider, finite IDs, both UTC endpoints, SCRIPT policy, target PID and exact path SHALL be conjoined in one selector with TolerateQueryErrors=false.
5. IF any input, escaping or supported-query requirement fails THEN no query SHALL occur; no alternate spelling, normalization, broadened selector or retry is permitted.

### FR-3: Observe existing records with bounded read and minimal output

**优先级:** Must
**用户故事:** As a reviewer I need only the matching recorded decision ID/time, without unrelated log data.

#### 验收标准（EARS）

1. WHEN querying THEN a direct local EventLogReader with BatchSize=1 set before reading SHALL read at most two records using a2000ms timeout per read, without message formatting or raw XML export.
2. IF exactly one revalidated record and then end-of-results are observed, and all disposals succeed THEN raw status MAY be raw_matched with one EventId/UTC pair.
3. IF zero or multiple records, denied/missing/disabled logging, unsupported schema/query, read/timeout/dispose error or an unexpected field appears THEN status SHALL be inconclusive with a finite reason and no decision.
4. WHEN persisting THEN bounded UTF8 no-BOM invocation JSON SHALL be created under the sibling evidence directory; the summary SHALL be written to observation-pending.json with CreateNew, fully flushed and closed, then renamed without overwrite in the same directory to observation.json as the final observer persistence action.
5. IF writing, flush, close or rename is uncertain THEN the pending evidence SHALL remain without cleanup, repair or retry, and reviewed correlation SHALL require final observation.json with no pending or extra sibling name. The pilot/journal is never mutated.

### FR-4: Derive reviewed correlation without changing accepted controls

**优先级:** Must
**用户故事:** As a reviewer I need a favorable observation to remain unusable after incomplete pilot finalization or mismatched artifact provenance.

#### 验收标准（EARS）

1. WHEN reviewing an artifact THEN the new pure evaluator SHALL first run the unchanged old evaluator over the whole independently authenticated member set and require its RunCompletionValidated=true before returning matched_record.
2. WHEN binding a raw summary THEN it SHALL strictly reparse the sibling schemas and recompute all fixed input and exact query digests; summary claims cannot supply source/run/artifact trust.
3. IF late root removal, selected-parent close, final evidence write, binding/resolve or case persistence fails THEN new reviewed status SHALL be inconclusive even if an authentic raw record match survives; old raw/accepted outputs remain unchanged.
4. IF the sibling summary contains unknown or accepted/security-success fields THEN the new evaluator SHALL reject it. Opaque sibling bytes SHALL never supply old evaluator prerequisite truth.

### FR-5: Prove scope, failure closure and interpretation limits

**优先级:** Must
**用户故事:** As a reviewer I need primary-source schema evidence, finite negative coverage and a fresh impact gate before implementation.

#### 验收标准（EARS）

1. WHEN presenting the packet THEN it SHALL include exact source/tree hashes, immutable-file proof, full fresh index validation, exact UID impacts, manual PowerShell/YAML caller analysis and all HIGH/CRITICAL warnings.
2. WHEN testing THEN all330 retained portable identities and seven managed entrypoints SHALL remain, while the new unified audit explicitly discovers and executes the new finite negative families; synthetic events SHALL never be represented as real log evidence.
3. WHEN interpreting a matching8007 THEN the result SHALL identify only the recorded AppLocker block under PID/path/time correlation;8006 is audit would-block,8005 permission only. No result proves script entry, exact process lifetime identity or universal failure cause.
4. IF the exact target-build schema/path representation is unsupported or no event matches THEN the result SHALL remain inconclusive without broader collection.

## 非功能需求

NFR-1: Local request ownership/case input members bounded at1MiB each, fixed pilot-result.json at2MiB (measured baseline1803796bytes), nine-byte payload at9bytes, invocation JSON4096bytes, prepared stdout request128KiB, raw summary16KiB, one query and two reads maximum. The fixed owned Python helper has10000ms timeout and bounded concurrent stdout/stderr capture; failed helper stop/close means no query. No acquisition loops/retries/subscriptions.

NFR-2: All new PowerShell is outside the exact broker-direct executable inventory. Pure Python has no filesystem/process/network operations. The fixed acquisition driver has no network, recursive scans, subprocesses or arbitrary inputs. No security-sensitive settings change.

NFR-3: Raw immutable-source auditing requires exact Git-blob checkout bytes; core.autocrlf=false is supplied only to the pinned checkout step through transient GIT_CONFIG_COUNT/KEY_0/VALUE_0 environment entries, with no persisted config or permission change. Windows PowerShell5.1 is the actual hosted contract; local Python/static checks cannot establish PowerShell or Windows execution. New files each remain at or below500lines with readable code. Scope expansion needs exact review.

## 依赖关系

Current11-case producer and artifact evaluator, already configured Python3.12 and PowerShell5.1, .NET Eventing.Reader API under the existing runner account, and existing enabled/accessible records. The observer does not make these available.

## 检查清单

- [x] Five FRs have EARS criteria and Must priority
- [x] Positive and missing/denied/late-failure outcomes distinguished
- [x] Existing security and diagnostic truth retained
- [x] Pre-edit review and actual hosted validation remain separate gates

## Published201 portability correction (FR-2, FR-5)

The original increment is published as20128605b3ecb39257e86c20f215412653cb8132/tree6ee934230cb9975f9b3a9787ec51937a510e6524. Its run37110825877 passed all330 retained portable tests, then the new32-method audit reported two open-metadata errors and one inventory-order failure. PowerShell, native execution and event acquisition were skipped. Artifact11268983773 contains only source/scope/manifest; it cannot establish an observation. This correction has exactly six paths: two modified Python files, one new test-only helper, and these three existing specifications. Root reviews its fresh impact packet before code edits.

FR-2 additional acceptance criteria:

6. WHEN comparing Windows path and descriptor metadata THEN shared device, inode, full mode, link count, size, mtime_ns and explicit birthtime_ns SHALL agree at initial-path/open-descriptor/final-descriptor/final-path observations; birthtime SHALL be a nonnegative integer excluding bool, and missing or malformed birthtime SHALL reject without fallback.
7. WHEN comparing Windows change signals THEN descriptor ctime_ns SHALL remain equal before/after reading, and path ctime_ns SHALL remain equal before/after reading. POSIX SHALL retain its existing cross-API ctime comparisons. All existing regular-file, ancestor/path identity, reparse, multilink, size, bounded-read and confirmed-close checks SHALL remain.
8. IF metadata differs or an operation is uncertain THEN the fixed driver SHALL continue to fail closed with no emitted request and no event query. The correction SHALL NOT claim a true pre-open Windows metadata ChangeTime, an atomic snapshot, or absence of every concurrent mutation.

FR-5 additional acceptance criteria:

5. WHEN hashing the44 immutable broker files THEN the audit SHALL explicitly order UTF8 filename bytes and retain the exact existing raw-byte digest1509f8ae681e529a732bc90d1c3e24e76ad8680ef1dd027751a6e174f10d2083; Windows casefold path ordering SHALL be covered as a regression, with no newline/content normalization.
6. WHEN testing timestamp comparisons THEN independent literal Windows/POSIX snapshots SHALL cover stable creation/change-time differences, every comparable field changed at each stage, ctime-only changes, and missing/malformed Windows birthtime. All32 existing test identities and every old assertion family SHALL remain, with actual expanded counts reported.
7. WHEN a synthetic real-file boundary read fails THEN test-only diagnostics MAY report at most ten already-returned metadata snapshots and fixed member/size/phase identifiers within16KiB. They SHALL issue no extra stat/read/reopen/retry, disclose no paths or file contents, and leave the failure intact. Runtime driver output and public schemas SHALL remain unchanged.
