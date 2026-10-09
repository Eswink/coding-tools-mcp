# Design

## 概述

This design covers FR-1 through FR-5 with read-only finite preparation. No production code changes.

## 技术方案

### 架构设计

Proposal only. Retain frozen six sources unchanged until root finite implementation decision. A future source-owned stage receives the actual prepared source and remaining typed parent helper/raw budgets, validates them as bounded accounting inputs (never capabilities), and owns a separate empty destination. All native Git runs use the existing exact argv/env/custom-index/binary-stdin owned Job/OVERLAPPED collector. No original API, production Go/Rust or nine protected specifications change. Exact event/vector and aggregate failure accounting must return to the parent before original Go methods.

## 数据模型

Proposed records: immutable original target19bb/path1953; prepared source targetd86ece/path1954; separate clone actual HEAD/customindex/tree/fullbytes; native pool/ref before/after raw and metadata identities; current native helper request vector with argv/index/input/output/exit/IO/Job/cleanup outcome; parent starting consumed requests/bytes, stage actual consumption including failure and reserved pending capacities, mandatory-after reservation, and remaining allowance. Path/JSON/counter values are observations, not grants. Actual native child starts are not inferred from request counts. UNKNOWN acquisition/close/completion has a strong owned frame and terminal denial.

## 核心算法

Current exact success-path static vectors, derived by direct reading of frozen functions:

| Stage | Request groups | Count |
| --- | --- | ---: |
| verify_management_native before | own HEAD1 + original verify_manager HEAD1/ls-tree7 + six/v12 ls-tree/show14 | 23 |
| original restore_source remote | two backup fetch2 + exact73 show73 + patchshow1 + clone/config/checkout/read-tree4 + hash/update146 + exact73 write-tree/tree_rows2 + applycheck/apply2 + final write-tree/checkout-index2 + original verifier HEAD/tree/tree_rows/untracked4 | 236 |
| overlay and augmented before | fetch/show/hash/update/checkout-index5 + HEAD/tree/tree_rows/untracked4 | 9 |
| existing after | augmented4 + management23 | 27 |
| current total | no early errors, original exact vectors only | 295 |
| proposed separate clone setup | clone/checkout/read-tree/checkout-index4; original prefix always core.autocrlf=false, so no new config call | 4 |
| full1953 original positive before | HEAD/write-tree/tree_rows/untracked | 4 |
| bad-byte original negative | HEAD/write-tree/tree_rows, then actual check_blob rejection before untracked | 3 |
| extra-source original negative | HEAD/write-tree/tree_rows/untracked, exact extra marker rejected | 4 |
| link + preexisting negative | strict new owned file/FD metadata fence and exists rejection before native calls | 0 |
| full1953 final original positive | HEAD/write-tree/tree_rows/untracked | 4 |
| source pool/refs before and after | each phase cat-file batch-all-objects/batch-check1 + for-each-ref1 | 4 |
| proposed total | current295 + new23 | 318 |

These numbers are static path budgets only. Each actual prefix may stop earlier. New remaining-budgets/newhelper controls and mandatory final-fence counts must be implemented precisely; any unexpected extra call blocks. Existing before/after snapshot file reads add no Git request but still consume actual deadlines and checked-close resources. Mutation byte restoration uses preserved actual checked file bytes with independent write/close handling; a failed restoration cannot re-admit the fixture. On Windows hardlink and reparse support are actual capabilities, never skip. Final positive cannot borrow a prior positive receipt.

A separate full original local-payload restore would add at least146 hash/update plus clone/config/checkout/read-tree/apply/verifier calls and exceed the candidate path; do not silently include it, rename clone materialization as that branch, or increase320. Possible later exact remote-payload staging+single original local branch design is outside this proposal and needs separate finite review.

## 安全与失败边界

Known actual module/input/source hashes do not create VM or publisher authority. Pool/ref raw inventories plus actual object-file hashes remain trusted-host snapshots, not atomic directory pins or proof of all transitive/runtime data. UNKNOWN resources stay held; no close retries, flag clearing or delete while uncertain. Primary cancellation and close/observer cancellation must preserve exact objects, independently attempt after-fences, and reject stage even if inner original receipt says pass. Native APIs and ordinary original Go methods are NOTRUN; original FR6 full local restore success and genuine native count enforcement remain explicitly outstanding. Triple activation DISABLED remains.

## 文件结构

Work-only source-owned-spec/docs/specs/windows-nt-native-source-owned-controls/{requirements,design,tasks}.md. Future scoped manager files remain unchanged until root decision; original protected files remain byteexact.
