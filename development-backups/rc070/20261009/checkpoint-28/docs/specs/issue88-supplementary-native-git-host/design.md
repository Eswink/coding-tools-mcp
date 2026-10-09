# 设计文档：issue88-supplementary-native-git-host

## 概述

FR-1/2 proposes a genuine supplementary Git, not a runtime-path placeholder. FR-3 preserves all original qualification. FR-4 separates research from a future explicitly authorized host exception.

## 技术方案

### 架构设计

Exact named ephemeral push job → unchanged /usr/bin/git fullflags preflight → separately approved source-authentication/owned build/exclusive supplementary install → private setup receipt and unchanged-system checks → original source restore/precondition85→strictseal→300 → existing safe-artifact policy. Setup failure executes zero SUT. Original180minute envelope stays.

### 技术选型

Official kernel.org source2.55.0 and detached developer tar signature; preexisting GNU make/compiler/GnuPG. Proposed native build/install path contract: build with prefix=/usr/local/ctm-native-git/2.55.0 and bindir=/usr/local/bin consistently; stage via DESTDIR in fresh owned temp, never run make install as root. All helper/resource payload must be beneath the fresh versioned prefix; shared bin permits only actual git native executable. Staged git-shell/cvsserver or other bin outputs cannot be copied to preexisting shared locations. Exact generated path configuration, Linux RUNTIME_PREFIX behavior and prospective staged manifest must be audited before execution; alternative installation layout requires spec revision, not silent fallback.

## 文件结构

No current carrier/SUT changes. Proposed future management delta: separate host helper + scoped specs/controls; workflow setup step; existing rc_native_probe.py management metadata that currently claims unconditional no_install_or_binary_replacement/no_compiler_install_or_privilege. PureSUT, original6259B runner, owner RUNTIME and strict seal reader immutable. This is not a workflow-only exception.

## 设计决策

### 决策1：Primary source identity (FR-1)

Actual downloaded source8.18MB matches official checksum row. Research GPG crypto verification exit0 gives exact developer/subkey VALIDSIG; public key obtained from Ubuntu public keyserver and primary fingerprint matches official kernel.org junio analysis. Local GnuPG TRUST_UNDEFINED is retained, not magically trusted; before execution review pins exact public-key payload and signer association. Kernel.org documentation warns autosigner checksums do not replace developer signature. WKD lookup refused and first minimal key lacked usable subkey; failures retained privately.

### 决策2：Exclusive install with real payload (FR-2)

Build unprivileged in owned temp and stage all bytes. A small installer, if root write is required, uses held parent FDs plus exclusive/no-follow creation and no writes outside pre-reviewed manifest. Prefer existing writable ownership when proven, never chmod/chown system directories. Existing target or prefix fails. Re-read each actual destination size/hash/mode/identity; native ELF is the actual freshly built Git, not copied /usr/bin/git/wrapper/symlink. Non-root build dependency absence fails; no apt or extra build flags to hide missing capabilities. Compiler and runtime identities before/after; original tools remain unchanged.

### 决策3：Truthful phase markers (FR-3)

Original management no-install fields would be misleading if simply prepending setup to workflow. New management schema must state host_setupperformed/authorizedscope/setupreceiptSHA and probe_phase_no_install_or_privilege. It must not change original raw runner receipts or amend failed historical files. Updating this schema requires fresh actual symbol impact and controls. Original same-client issuer/tag/publication authorization remains separate and unavailable.

### 决策4：Concrete reviewed exception (FR-4)

Original requirements explicitly exclude compiler/install/privilege and source documentation repeats it. New setup cannot execute within old scope. Root first reviews exact source, writes, native trust, negative controls and one-time exception. No current host install/sudo/host mutation is authorized by this spec. Root explicitly permits genuine build and staging inside owned workspace for source review; existing user real-compatible-CI scope may cover disposable setup without repeated confirmation if no new external permission is required. Future real CI gives new evidence only; preflight20static controls/current signature verification cannot approve85/300.

## 测试策略

New ordinary owned-directory installer tests: absent→exclusive regular file, existing/symlink/hardlink/parent swap rejected, bad archive/hash/signature/key fingerprint rejected before execution, bounded cancellation/error closure, source/compiler/output/installed byte changes rejected, destinations outside full manifest rejected. Controls extract/test actual implementation after fresh impact. Then real ephemeral CI setup/source/runtime lease and complete original85 raw files/seal/native closure; no300 on any non-success. No borrowed original local failure receipts or unrelated samehead PR workflow SUCCESS.

## 风险评估

Manual HIGH: privileged install/executable provenance, future management metadata semantics and distro dependency/prefix/helper behavior. Current graph impact UNKNOWN until actual symbols exist. Ubuntu image README shows gcc/make/libssl-dev but does not prove all original Git default build dependencies or runtime compatibility on targetrun. Existing user/production host never touched. Installation artifacts are not RC product assets. Proposed600s setup might fail naturally; no timer expansion.

## 检查清单

- [x] FR-1 source; FR-2 bounded actual install; FR-3 unchanged original qualification; FR-4 authorization/newcontrols.
- [ ] Exact future source/staged manifest/installer and independent review before running.
