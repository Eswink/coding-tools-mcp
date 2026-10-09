# 需求文档：issue88-owned-native-git-build-v4

## 功能概述

New finite V4 design only. Two fresh owned config.mak files carry the same genuine GNU msgfmt base argv without --check. Signed upstream core retains += --check; git-gui retains its original --tcl discovery and translation flags. Remove only MSGFMT CLI assignment. No helper implementation, ordinary execution, full build or install is authorized by this draft. Historical V3 full build FAIL/install NOTRUN and Publisher85 83success/2FAIL are preserved.

## 范围边界

Only new V4 validate/prepare logic plus necessary bounded owned config IO helper, tests and these three specs. Original signed Git2.55 source4991 entries and original snapshot_original_git_source/run_owned_git_phase function AST remain unchanged. No Makefile, PO, test, Reader, original runtime or original budgets edits; no NO_GETTEXT/NO_MSGFMT/TCLTK disable, shell wrapper, PATH shim, global LD settings, tool replacement, issuer grant or privilege. Two configs apply ONLY to core and git-gui. gitk-git has no config.mak include and its upstream discovery/fallback is unchanged; these two files do not establish GNU msgfmt provenance for gitk or all components. Actual full-build tools/results require later original raw evidence.

## 需求列表

### FR-1: Distinct upstream FILE-origin msgfmt vectors
**优先级:** Must
**用户故事:** 作为维护者，我要核心与 GUI 各自保留原参数，而不将核心检查选项传播给 GUI。
#### 验收标准（EARS）
1. WHEN validating prerequisites THEN V4 SHALL preserve genuine completed Debian GNU msgfmt receipt, loader/base argv, original dependencies and current leases from V3; retain official signed Git2.55 source pins and 4991 original-entry guard. A receipt never grants execution or publisher authority.
2. WHEN preparing two absent owned configs THEN V4 SHALL write precisely one MSGFMT assignment using the same admitted base argv without --check to root/config.mak and git-gui/config.mak, using FILE origin. Core Makefile1044 include and2282 += --check stay original; GUI102 include/141 default/142 actual --tcl self-test/158 original --statistics --tcl remain original. Remove MSGFMT CLI assignment in both genuine makeall and makeinstall vectors; no MSGFMT environment/export/MAKEFLAGS assignment. Prefix CLI and all other original make flags remain unchanged. If actual GNU GUI self-test fails or selects fallback, report failure or actual selection truthfully; do not override the self-test.
3. WHEN validating emitted Make text THEN V4 SHALL separately validate Make lexical safety and shell argv fidelity. Reject NUL/newlines/carriage return, dollar expansion, comment #, backslash continuation and unintended shell operators before write. Reject unknown serialization forms rather than claim shlex.join alone is a Make encoder. Genuine library-path colon separators and required shell quoting must not be rejected merely for containing colon or quotes. Use actual GNU make ordinary readback and exact argv recorder to verify FILE origin and exact admitted token vector; actual current genuine base tokens must be checked against the finite allowed-token grammar. No arbitrary user text input.

### FR-2: Exact new-owned config IO and original exception preservation
**优先级:** Must
**用户故事:** 作为维护者，我要独立封存新增配置，保持旧源码与真实关闭异常。
#### 验收标准（EARS）
1. BEFORE any write THEN V4 SHALL require fresh trusted owned extraction with both targets absent, native parents pinned, no target symlink/hardlink/existing file. Create each with O_EXCL/no-follow, bounded one line <=4096 bytes per file, explicit owned mode644, actual native once-close. Seal exactly two extra paths/mode/bytes/SHA/native identities separately from original4991. No manifest pretending original source includes generated configs. Re-read two config leases before/after each build/install phase and enforce no additional source-policy configuration extras.
2. WHEN writer/observer/close/cancel fails THEN V4 SHALL retain original primary and each original cancel/close exception object, attempt each independent owned resource close and final observation, and retain UNKNOWN for uncertain close. Cleanup success cannot erase prior failure. Close-before observer failures cannot skip actual close; no retry on FD number or status inferred from inode. Reuse reviewed resource adapters; snapshot_original_git_source and run_owned_git_phase AST remain exact. Old V1/V2/V3 failures and raw evidence remain immutable.
3. WHEN verifying source THEN V4 SHALL require all4991 original paths/modes/bytes/native identities before/after unchanged, together with separate two-extra identity/hash checks. Existing failed V3 checkout is never edited or reused as fresh preparation. Additional new config files are workspace effects, not installation or a policy exemption.

### FR-3: Finite controls, peer and sole-root phase authorization
**优先级:** Must
**用户故事:** 作为维护者，我要真实参数和失败边界证据之后再启动完整构建。
#### 验收标准（EARS）
1. BEFORE source implementation THEN fresh exact GitNexus prepare HIGH7/validate HIGH12 and protected snapshot CRITICAL17/runphase CRITICAL11 SHALL be disclosed, new helper UNKNOWN/manual CRITICAL not0; this finite3FR design requires independent peer and root authorization. Before commit require fresh detect_changes and gencommit. This design is not source implementation permission.
2. WHEN later authorized ordinary controls execute THEN controls SHALL verify actual GNU make parent and recursive child FILE-origin/core base+one original --check/GUI base with zero --check; current original GUI self-test and translation vector without edited PO; genuine malformed core PO rejected; lexical negative cases plus actual genuine colon/quoted base; absence of MSGFMT CLI/ENV/MAKEFLAGS contamination. Controls SHALL execute failure-first close/cancel/primary identity and both config partial-creation/final-observation failure cases. Ordinary reduced make fixtures and original translation component controls do not prove full Git all/install or native family qualification.
3. BEFORE later full build/install THEN exact new source/runtime/config/original4991 leases, real ordinary results, fresh seal and independent startup peer SHALL precede root unique launch. Preserve makeall480/install60/probe30/log2MiB/TERM2s and cleanup2+2s, original run-phase AST and authenticated archive/tool predicates. On build failure install NOTRUN; authentic full install effects reported only if actually executed and validated. No author SUT/fullbuild/install launch, retry or budget increase. Original85FAIL/300NOTRUN/issuer unavailable unchanged.

## 非功能需求

- NFR-1: Private trusted workspace, not hostile same-UID proof; original system Git/runtime untouched.
- NFR-2: Keep original budget, cancellation and hardreject semantics; generated files bounded8192B total, accounted as two source extras, no source archive budget expansion.
- NFR-3: Safe backup only source/spec/hash/modes/status; exclude actual binary/data/archive/signature keys, TLS/env/proc/host/raw logs/Git object pool.

## 依赖关系

Signed original Git2.55 source and genuine current Debian GNU msgfmt PASS prerequisites, current loader/dependency leases, actual upstream Makefile/coreGUI reads, fixed GitNexus graph, source-design peer followed by separate root source authorization. Authentic actual full-build/install gate remains pending.
