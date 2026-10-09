# 设计文档：issue88-owned-native-git-build-v4

## 概述

Design only, finite core+GUI MSGFMT propagation correction. V3 command-line variable appears in recursive MAKEFLAGS and carries core --check into GUI. Upstream FILE-origin config permits core += --check while GUI consumes the same base with its original --tcl flags. No original source changes. gitk-git is outside the two-config propagation scope; upstream fallback remains discoverable, never described as all-component GNU identity.

## 对应需求

FR-1 covers upstream FILE-origin vectors and lexical safety; FR-2 covers two owned config IO/leases and primary identity; FR-3 covers finite controls, design/source/startup separation.

## 技术方案

1. Copy V3 helper/tests into a new independent V4 source root only after root design authorization. Reuse authenticated extraction, runtime/loader/msgfmt dependency leases and protected source snapshot/run-phase functions without AST changes. Validate routine returns the genuine base vector and leases rather than CLI MSGFMT assignment. Prepare routine changes only configuration preparation, its separate lease guard, and deletion of MSGFMT CLI argument from makeall/install argv.
2. New bounded owned config helper accepts only the already admitted finite genuine base vector. Initial concrete serialization candidate is one `MSGFMT = <shell quoted base>` line; it is not yet accepted as an encoder. Reject Make-sensitive dollar/#/backslash/newline and unsafe shell grammar; explicit finite allowed token alphabet admits original library path colons and correct shell quotes. Actual GNU make readback and exact argv recording must prove candidate form. If current genuine base cannot be safely serialized, STOP UNKNOWN without broad encoder or Makefile patch.
3. Require native pinned fresh root and GUI directories and both config targets absent. Owned O_EXCL/no-follow writes produce independent config manifest <=4096B/file, mode644, bytes/SHA/native identity and exactonce close observations. Final guard reads both files plus original4991. Any close/cancel/final observation error preserves original objects and UNKNOWN; independently attempt all cleanup. No IO success masks a saved error.
4. Ordinary controls run genuine GNU make on clearly reduced owned upstream-equivalent include/+= recursion models, recording origin/value/actual executable argv. Separately run the current original GUI self-test/translation command on unchanged original PO relocated byte-identically into one owned component location with truthful relocation/provenance; malformed core fixture verifies base+original --check rejection. Component controls are not full makeall. Design does not invoke them.
5. Full realbuild/install remains a separate root-only protocol. Startup packet must reread source/helper/config/original4991/runtime leases and actual controls. Preserve 480/60/30 phase deadlines/log2MiB/native close adapters. Build failure keeps install NOTRUN; no partial Git reused. Native launch/reaping/state evidence distinct from configuration proof.

## 真实性与保护边界

Original snapshot_original_git_source and run_owned_git_phase AST exact; config IO new and explicitly declared. Original4991 byte/native identity guard never includes newly generated files. Source-wide membership whitelist distinguishes expected compiler build artifacts from policy configuration extras; no claim of whole fresh tree byte equality after build. Existing V3 failed source cannot be modified. No same-client credential issuer/tag grant is created. MSGFMT tool provenance for gitk remains unknown until actual all evidence.

## 风险与控制

Fresh graph prepare HIGH7, validate HIGH12; unchanged protected snapshot CRITICAL17, runphase CRITICAL11. New config helper is UNKNOWN/manual CRITICAL. Make parsing is distinct from shell parsing; shlex.join cannot prove safe Make encoding. Native close uncertainty not retried. Parent-child variable propagation must be shown by real GNU make controls, not a static assertion. Both config files have separate exact-vector leases throughout; original dynamic Makefile GUI fallback cannot be bypassed to make a control succeed.

## 文件结构

- owned_git_prepare_v4.py: intended independent helper, NOTIMPLEMENTED.
- owned_git_prepare_v4_tests.py: intended finite controls, NOTIMPLEMENTED/NOTRUN.
- docs/specs/issue88-owned-native-git-build-v4/{requirements,design,tasks}.md: current design only.
- Future fresh owned extraction root/config.mak and git-gui/config.mak: generated two-extra files, NOTCREATED, separate runtime/source guard records.
