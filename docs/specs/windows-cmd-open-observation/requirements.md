# 需求文档：windows-cmd-open-observation

## 功能概述

Add one bounded observation of the first exact batch-file open attempted by the original suspended cmd child in the existing diagnostic pilot. This is operation evidence, not a fix, full LPAC verification, runtime acceptance or policy attribution. Baseline: PR99 4d8fc29595cf4e832deb0e336bb9932f162673f2. The current failure is exit1/empty output even for a minimal9-byte exit23 batch; prior same-binary builtin/cwd/TYPE controls passed.

## 历史经验与坑（来自记忆库）

No memory-store result was supplied. Current-source facts govern: EXIT_PROCESS_DEBUG_EVENT must be continued before kernel shutdown completes; the old unconditional cleanup cannot safely handle a pending debug event. Source graph C# partial/PowerShell edges are incomplete, so manual lifecycle risk remains HIGH.

## 范围边界

- In Scope: one existing cmd-relative-batch-exit23 subject; native AMD64; one paired NtCreateFile/NtOpenFile operation; fixed sanitized receipt; fake-native and source/artifact adversarial tests; existing compile integration
- Out of Scope: extra processes/cases, read tracing, async completion, live detach, system logging, stronger access, privileges, settings, production verifier changes, publication, unreviewed Actions execution, automatic alternate diagnostic facilities

## 需求列表

### FR-1: Preserve the exact target and containment
**优先级:** Must
**用户故事:** As a maintainer I need evidence from the original child so that separate-process controls are not mistaken for its behavior.
#### 验收标准（EARS）
1. WHEN the existing authority predicate and job assignment pass THEN the observer SHALL bind the original PID, creation FILETIME and existing process/thread handles.
2. IF any existing predicate or ownership premise fails THEN it SHALL not attach or resume through the observer.
3. WHEN another pilot case runs THEN its existing launch/resume/wait behavior SHALL stay unchanged.

### FR-2: Observe one bounded native open without increasing access
**优先级:** Must
**用户故事:** As a maintainer I need the exact attempted access and returned status for one prepared-file open.
#### 验收标准（EARS）
1. WHEN a supported native AMD64 ntdll module is observed THEN the observer SHALL resolve remote exports and arm only the two fixed entry bytes before the original resume.
2. WHEN the first absolute exact prepared batch path matches THEN it SHALL remove both entry traps permanently and pair one same-thread return with saved RSP binding.
3. IF STATUS_PENDING, an unsupported form, denial or a bound is encountered THEN it SHALL remain incomplete and never obtain stronger access or invoke another facility.
4. WHEN a successful nonpending return is observed THEN only a SAME_ACCESS broker duplicate SHALL be used for existing-object identity metadata, and never target CloseHandle or DUPLICATE_CLOSE_SOURCE.

### FR-3: Own breakpoint and suspension transitions precisely
**优先级:** Must
**用户故事:** As a maintainer I need the debugger not to corrupt unrelated thread state.
#### 验收标准（EARS）
1. WHEN a nonmatched entry needs step-over THEN the observer SHALL acquire exactly one owned suspension per peer, execute only the fixed mov r10,rcx, verify RIP/R10, rearm and release precisely those increments.
2. IF an event, context, byte, handle or suspension result is ambiguous THEN it SHALL abort without stale context restoration or retrying an uncertain operation.

### FR-4: Fail closed through cleanup
**优先级:** Must
**用户故事:** As a maintainer I need unresolved debugger state to retain recovery instead of reaching legacy cleanup blindly.
#### 验收标准（EARS）
1. WHEN attach succeeds THEN legacy StopQualificationSubject SHALL be gated on successful EXIT continuation and original-handle signal plus identity/exit confirmation.
2. IF the observer fails THEN it SHALL attempt original-target termination at most once and drain bounded exact-target exit events.
3. IF terminal proof is absent THEN it SHALL retain original resources and journals and SHALL NOT call legacy cleanup, detach, delete or classify.

### FR-5: Keep evidence sanitized and diagnostically honest
**优先级:** Must
**用户故事:** As a maintainer I need useful operation facts without target paths, secrets or false success.
#### 验收标准（EARS）
1. WHEN writing new evidence THEN only the version-specific35 (v1),36 (v2) or37 (v3) numeric and6 enum keys in design.md SHALL be emitted.
2. IF a new exception occurs THEN a fixed code SHALL replace its message/stack/inner exception before escaping any new entry point.
3. IF exit/output changes or a complete matched operation is absent THEN a fatal pre-classifier gate SHALL prevent acceptance and journal resolution; debugger exit23 SHALL never count as success.
4. WHEN one open fails or succeeds THEN the report SHALL describe only that operation; no match SHALL remain inconclusive.

### FR-6: Preserve source/test boundaries and review
**优先级:** Must
**用户故事:** As a maintainer I need a reviewable diagnostic increment that does not relax the existing safety gates.
#### 验收标准（EARS）
1. WHEN integrating THEN both existing Add-Type sites SHALL append the exact sibling files and existing runtime invocation/triggers/permissions SHALL remain unchanged.
2. WHEN changing Runner THEN all legacy catches and the separate1869-byte classifier-to-persistence span SHALL remain byte-identical.
3. BEFORE publication or one Windows attempt THEN the exact candidate SHALL receive independent review, staged graph/source checks and applicable regression evidence.

## 非功能需求

- NFR-1: No security-sensitive setting/access expansion; exact22 native APIs only, no installations or external software
- NFR-2: Operational30s plus cleanup5s; bounded event/thread/module/read/write/receipt counts as design.md
- NFR-3: At most16 cumulative changed/new paths (13 original plus three pure test/schema helpers); new code files each at most500 readable lines; no compression to conceal unsafe complexity
- NFR-4: Existing access and supported-bootstrap feasibility remain unproven until the one reviewed Windows attempt; synthetic results do not imply native success

## 依赖关系

Existing Windows broker pilot, its source/object identity captures and recovery journals; existing GitHub diagnostic compile/runtime job; installed Python and existing local tooling. No new package dependency. The root-cause bugfix remains blocked separately until actual evidence supports a cause-directed fix.

## Reviewed v2 context-reason increment

### FR-7: Discriminate only the immediate context round-trip
**优先级:** Must
**用户故事:** As a maintainer I need a bounded reason for the already-performed immediate Set/Get verification so that native failure and strict comparison failure are distinguishable without relaxing the guard.
#### 验收标准（EARS）
1. WHEN the existing SetThreadContext is followed by its existing immediate GetThreadContext THEN the observer SHALL reset the new mask to -1 before Set and perform exactly the same native calls, with no retry or extra read/write.
2. IF Set fails THEN the existing Set error SHALL remain distinct; IF Get fails THEN context_get_failed SHALL preserve its immediate native error including zero and mask -1.
3. IF successful Get returns null THEN context_roundtrip_unavailable SHALL have mask -1, API none and native error0; IF nonnull comparison fails THEN context_roundtrip_mismatch SHALL have a nonzero21-bit mask, API none and native error0.
4. WHEN comparing existing contexts THEN mask0 SHALL be equivalent to the unchanged SameRequested predicate; either invalid ContextFlags SHALL set bit0 even when equally invalid.
5. WHEN projecting receipts THEN v1 SHALL retain its exact old schema and semantics, while v2 SHALL require exactly one additional context_mismatch_mask field, with range -1 or0..0x1fffff.
6. WHEN any first failure is recorded THEN subsequent cleanup SHALL not replace its reason, API, native error or mask. Existing abort, cleanup, continuation and equality acceptance SHALL remain unchanged.
7. BEFORE publication or native execution THEN the exact revision SHALL receive a new independent review; the ended v1 attempt SHALL not be rerun automatically.

### FR-8: Identify differing EFLAGS bits without exposing register values
**优先级:** Must
**用户故事:** As a maintainer I need only the differing flag-bit identities from the already-obtained contexts, so a future review can reason about the strict guard without guessing or relaxing it.
#### 验收标准（EARS）
1. WHEN the existing immediate Get succeeds with a nonnull context THEN Session SHALL compute unsigned32 requested EFLAGS XOR actual EFLAGS and widen it to a nonnegative long, using only those existing buffers.
2. WHEN an immediate round-trip starts THEN both diagnostics SHALL reset to -1 before Set; IF Get fails or returns null THEN both SHALL remain unavailable.
3. WHEN emitting a completed comparison THEN both diagnostic values SHALL be computed before either is emitted, and field-mask bit3 SHALL be set exactly when the XOR is nonzero.
4. WHEN deciding acceptance THEN the byte-identical SameRequested predicate SHALL remain the sole guard; TF ownership/repair, API calls, abort and cleanup SHALL remain unchanged.
5. WHEN projecting v3 THEN exactly37 numeric and6 enum keys SHALL be required; v1/v2 schemas and archived interpretations SHALL remain unchanged, with no new field accepted retroactively.
6. WHEN extracting pure receipt tests THEN actual prior test.id() identities, discovery counts, bodies and mutations SHALL be preserved without omissions or duplicates.
7. BEFORE publication or native execution THEN the exact candidate SHALL receive independent review and a separate decision; neither is authorized by source implementation approval.
