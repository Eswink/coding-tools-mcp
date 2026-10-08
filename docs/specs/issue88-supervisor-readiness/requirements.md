# Supervisor readiness fixture requirements

## 功能概述

Baseline: actual F69e749736b95b5921b4f6352838f69860c7a0a4e, tree0b14817a668e8d5f25b23ab3bb088fbf65ca8849.

## 需求列表

#### FR-1: Reach and sustain each real network phase
The five existing local header/body/API-header/API-status/storage-status subcases SHALL observe a real request and successful partial-response write before measuring their network phase.
Require at least eight successful drip writes, a recorded drip span of at least0.35s and at least0.5s real elapsed phase time.
Keep the160 waits at0.025s, storage authorization absence, original test IDs and every existing assertion.

### FR-2: Keep bounded, monotonic fixture timing
The caller passes the owned logical deadline explicitly as0.5, including expiry before the first clock read; no production deadline is renewed.
Readiness has a separate0.9s real watchdog. Once expired, it cannot revive after late publication of any phase timestamp, including a timestamp captured before the bound.
Sample the phase before the current clock so concurrent publication cannot create negative elapsed time.
Missing or late readiness must fail phase acceptance rather than become a positive timeout result.

### FR-3: Preserve actual lifecycle and defaults
Use the existing actual child, pipe, socket and downloader paths. Retain the1.5s wall assertion, cleanup uncertainty, error code and cause/context checks, and observed reaping.
Keep separate real-clock startup deadline cases unchanged and rerun affected DownloadBudgetCases callers.
Production runtime, worker, launch implementation, timeout constants, hosts and permissions remain unchanged.

### FR-4: Admit only the reviewed finite source change
Exactly10 paths,5 replacements/5 additions,1795 entries and at most1000 changed lines; each source file stays within500 lines and its declared cap.
Require5 complete-byte inverses,16 finite historical identities, exact F raw/tree/ordered parents and D[F], I[F,D], J[R,I] with four R documents.
Preserve1433 original IDs, strict303 and consumer452; add exactly12 uniquely inventoried composition cases.
Only topology mismatch may delegate; selected-content/history failures are terminal. No actual-candidate caching.
Keep existing read-only workflow permissions/events and all live publication, native/global admission and held-source boundaries.

## 非功能需求
All timing, ownership, source and inventory bounds above SHALL remain enforced.

## 依赖关系
Reuse the existing downloader, real-child fixtures and finite staged-byte admission chain.
