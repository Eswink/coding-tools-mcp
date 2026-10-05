# Issue111: private-directory consume-once ownership

## 功能概述
Correct deterministic ownership defects at exact M `5a270a2ef659fb28500c6541f280849d914d25b9`, tree `ddb51315a6dd9bbdcdf4d8fc5a06bdf4d9ba862f`.
Issue: https://github.com/Eswink/coding-tools-mcp/issues/111
This source correction does not establish physical close success or current-source live proof.

## 需求列表
- FR-1: After a child descriptor is validated, `_directory` and both `_parent` branches SHALL transfer ownership before closing the previous parent; every cleanup authority is consumed before its sole close attempt.
- FR-2: A newly created `_parent` child identity failure SHALL attempt child then parent cleanup independently, including compounded cleanup failures; no filesystem rollback or close retry is permitted.
- FR-3: `PrivateRoot.__init__` SHALL retain root and parent as separate local owners and publish `self.fd` only after identity and parent-close success. Failed construction attempts both still-owned descriptors once in defined order.
- FR-4: Constructor OSError acquisition/cleanup SHALL map to existing `unsafe_root_parent`; non-OSError and cancellation preserve normal Python cleanup precedence. Existing public reports remain sanitized and cleanup uncertainty stays false/sticky.
- FR-5: Exactly one pinned 12,953-byte C IO fixture SHALL support original24 historical test bodies without changing live harness/workflow or production(). All three buffers verify before materialization; per-test ROOT patch and owned cleanup restore failed setup.
- FR-6: Original J/M 22-path, two-extraction, 3,966-line adopter gates SHALL remain frozen and separate from the current 13-path, 2,200-diff-line ownership overlay. Current IO never enters NARROW.
- FR-7: Corrected topology SHALL accept only a nonempty≤16 single-parent chain to exact M, exact same-tree [M,P], or [R,validated non-release] plus four pinned documents. Same-valid-tree malformed topology rejects before tree checks; no recursive fallback.
- FR-8: Acceptance SHALL preserve all542 existing IDs and execute proposed54 additions only when genuinely discovered, with zero skips/duplicates/xfails/xpasses. Historical24 remains separately identified; full source/context/CI-equivalent and independent review gates precede publication.

- FR-9: PR112 fixture repair SHALL classify each enumerated metadata entry from one non-following lstat result, sharing mode/link-count observations; every lookup error remains terminal and prevents child launch. No ignored disappearance, retry or name exemption.
- FR-10: Every owned Git child from init SHALL receive fixed maintenance.auto=false and gc.auto=0 after accepted identity options; repository/global/system config, process environment and caller dictionaries remain unchanged.
- FR-11: Retain all596 IDs and add exactly three same-source regressions (proposed599/pretag147), including physical post-observation lock deletion in baseline and candidate with the same successful-launch expectation. Preserve IO/C/H/workflow bytes and frozen-M budgets.

## 非功能需求
Only runtime `_directory`, `PrivateRoot._parent`, and `PrivateRoot.__init__` may change. All other runtime text is preserved.
All thirteen paths have individual approved caps; IO≤400 lines/diff120; consumer tests≤490; helper≤120; fixture360; proof tests≤500/diff20; composition≤500/diff120; topology helper≤220; pretag tests≤380; workflow≤90/diff20; three specs≤100 each.
The linked PR112 repair permits exactly seven existing paths, P-relative delta≤330; fixture≤330 lines/diff50, pretag tests≤380/diff150, profile≤220/diff40, composition≤500/diff10, each spec≤100/diff20. Current fixture adds the thirteenth M-relative path, with aggregate2200 unchanged.
All changed paths are regular100644; aggregate M-relative added/deleted≤2200; no source above500 lines.
Synthetic descriptor tests are namespace-local and never send fake IDs to the OS; modeled before/after close outcomes are not real OS evidence.

## 依赖关系
Unchanged C=`93c2ad95304668ecc112da0cb073e46fe177e4f7`; H=`729f794a6807e36721b990874b8678b83be031b7`; J=`1694fe8c771e57c72c89ca096693b03404c24b84`.
R=`e2e011f7f2a3a1df838bbd588106205b999db610` remains the historical release overlay anchor.
Parent owns external publication. Main/release, Issue86/PR98, live FINAL/manifest, version and security gates remain open and unchanged.
