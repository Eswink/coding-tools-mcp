# 需求文档：issue88-supplementary-native-git-host

## 功能概述

Research/spec only, NOT authorized installation. Exact Publisher e90 CI37913922195 attempt1 has real /usr/bin/git2.55 fullflags success but original required /usr/local/bin/git missing; SUT0,85NOTRUN,300NOTRUN. Prepare a separately reviewed genuine supplementary Git build/install on disposable GitHub Ubuntu24; pure b9cf1878, original runtime set, flags,Reader,runner and strict85→300 gate stay byte-identical.

## 历史经验与坑（来自记忆库）

Do not turn system Git copies, PATH shims, aliases, deleted flags or incomplete raw seals into compatibility proof. Preserve original failures and source-only status. Original carrier bans compiler/install/privilege and emits unconditional no-install markers; this proposal needs an explicit bounded exception and truthful phase-scoped management metadata before execution.

## 术语定义

Supplementary Git: actual upstream2.55 ELF executable built from verified official source, installed exclusively at original fixed /usr/local/bin/git, with its genuine helper/resource payload under a fresh versioned prefix. It is not an upstream-provided prebuilt Linux binary.
Setup phase: disposable job preparation ending before the original precondition/runtime-before snapshots. Probe phase: original unchanged85 and300 runner lifecycle, no installation or privilege.

## 范围边界

In Scope now: readonly primary source research, finite proposal, independent review. Future exception scope: preinstalled compiler builds genuine Git2.55 in owned temp, exclusive supplementary install in the ephemeral named CI job, necessary new host controls/receipts and truthful management metadata.
Out of Scope now: host installation, sudo/permission mutation, workflow/code mutation, remote push. Always Out: modifying /usr/bin/git or existing binaries; compiler/dependency install; PATH/alias/symlink shim; SUT/test/Reader relaxation; new grants/tag/Release; user/production hosts; foreign process inspection.

## 需求列表

### FR-1: Immutable official source and signing identity
**优先级:** Must
**用户故事:** 作为维护者，我要真实同源 supplementary native executable，而不是为路径制造证明。
#### 验收标准（EARS）
1. WHEN setup is separately authorized THEN source SHALL be official git2.55.0.tar.xz8177180B SHA457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357, reject mismatch before extraction/execution.
2. WHEN authenticity is checked THEN the system SHALL verify developer signature against uncompressed tar, VALIDSIG subkey E1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB and primary96E07AF25771955980DAD10020D04E5A713660A7, with independently pinned public key bytes and review of official kernel.org primary fingerprint; fail bad/expired/revoked/unknown signer. A checksum/autosigner match alone is insufficient.
3. WHEN extraction starts THEN all source entries SHALL be rooted beneath one fresh owned directory, reject absolute/traversal/escaping links and bounded archive totals, execute no hooks/scripts before source lease verification.

### FR-2: Bounded genuine build and exclusive install
**优先级:** Must
**用户故事:** 作为维护者，我要可审查的实际 build/install身份和精确写入范围。
#### 验收标准（EARS）
1. WHEN building THEN the system SHALL use only existing compiler/dependencies, fixed reviewed make vector and prefix semantics, no package manager/toolchain download/install; unavailable dependencies fail SUT0. Record source/compiler/build-vector/output hashes without exposing full environment.
2. WHEN publishing supplementary payload THEN the system SHALL require /usr/local/bin/git absent under pinned non-reparse parent, exclusively create a regular native ELF file of reviewed bytes/mode and its fresh versioned helper/resource namespace; no overwrite/symlink/hardlink/system-Git copy. Prospective full staged manifest and exact install algorithm must be reviewed first.
3. WHILE setup runs THEN /usr/bin/git and original preexisting runtime binaries SHALL retain exact bytes/mode/device/inode identity; PATH and original /usr/bin:/bin selection remain unchanged. Any mutation or unknown fails SUT0.

### FR-3: Phase boundary and original qualification
**优先级:** Must
**用户故事:** 作为维护者，我要区分新增主机准备与原测试资格。
#### 验收标准（EARS）
1. WHEN handoff to original probe occurs THEN management metadata SHALL truthfully name explicit setup exception and receipt, scope no-install/no-privilege claims to probe phase, never emit a misleading job-lifetime True; original runner/owner runtime/PREFIX/Reader remain unchanged.
2. WHEN testing THEN system SHALL execute both native executables' real version/fullflags and usable builtin plumbing, verify actual helper identity where invoked, then original precondition and all85 exact tests; only current complete original raw8file reread/seal/native closure gate may admit300.
3. IF setup or any qualification gate fails THEN original profiles SHALL retain FAIL/NOTRUN with zero simulated named success, no retries, synthetic grants or historical receipt substitution; original local83/2FAIL retained.

### FR-4: Independent controls, authorization and safe evidence
**优先级:** Must
**用户故事:** 作为维护者，我要在具体新范围获批后才执行精确变更。
#### 验收标准（EARS）
1. BEFORE any external supplementary installation is run THEN a bounded spec exception to original no-compile/install/privilege SHALL have independent root review; existing user genuine-compatible-CI authorization SHALL be considered before requesting any further approval, exact paths/writes/budgets shown; current research is not approval.
2. WHEN controls are executed THEN the system SHALL run fresh controls for signature/hash/path/overwrite/parent/byte/mode drift and truthful markers, fresh GitNexus impacts and detect/gencommit for actual edited symbols; old20preflight controls are not this host scope proof.
3. WHEN preserving evidence THEN public backup SHALL include only reviewed source/patch/safe manifests/status, private evidence remains private; no tokens,TLS,raw host/proc/env or Git object pools published.

## 非功能需求

- NFR-1: Keep original180-minute workflow and1800/7200 probe timers,TERM7/KILL2/family2 unchanged. Proposed setup total≤600s inside existing slack, no budget expansion/retry.
- NFR-2: Original no-install/privilege boundary remains effective until separately authorized concrete exception; privileged execution, if necessary, only fixed reviewed exclusive supplemental install in this ephemeral CI job, never build as root.
- NFR-3: All unknown real host build/dependency/helper/prefix results remain UNKNOWN, real installed usability and original85/300 still required. No claim current source/signature research passes RC.

## 依赖关系

Actual e90 artifact and raw failure preserved; official source/INSTALL/Makefile/signature; fresh staging/install audit and independent review; original pureb9cf/sourceguards/current runner leases; bounded approval before execution.

## 检查清单

- [x] Four bounded FRs; no install executed; original conflict explicit.
- [ ] Separate scope approval, prospective exact staging manifest and installer review.

## 原约束精确引用与有限提案例外

Original issue88-native-runtime-recovery-probe FR-2.1: “不得削弱参数、替换二进制、下载 compiler 或安装工具。” Original NFR-2: “无privilege/compiler/install，token不进入worker，不发布。”
Current scripts/rc_native_probe.py precondition emits `no_install_or_binary_replacement=True`; main CARRIER-IDENTITY emits `no_compiler_install_or_privilege=True` unconditionally. The future setup phase requires truthful `INSTALL=true` with actual separately reviewed setup receipt, while no-install/no-privilege may describe only the original probe phase after setup. Compiler remains preinstalled; no compiler/dependency installation. User already requests real compatible CI; root evaluates whether this disposable bounded setup is covered without repeated permission prompts. Concrete external credential/permission barriers must be reported with exact proposed action. No current remote privileged action is run.
