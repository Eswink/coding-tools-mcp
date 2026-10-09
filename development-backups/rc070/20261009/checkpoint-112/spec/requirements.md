# Gateway unused RSA removal — SOURCE_ONLY_NOT_WIRED candidate

## 功能概述

Root authorized a source-only two-manifest candidate on exact F13 13cd343/tree f2be after manual HIGH/UNKNOWN disclosure. It is not wired into product Cargo. The gateway Cargo.lock contains RSA0.9.10, RUSTSEC-2023-0071, and the actual original audit exits1 with one vulnerability. Its database specifies patched=[]; no available stable or RC RSA upgrade is established as fixed. Desktop/local-agent/cloud-agent audits exit0, with six desktop unmaintained warnings. None qualify final0.7. WHEN producing this proposal, the reviewer SHALL retain the actual negative audit and declare all new source/build/audit/install qualification NOTRUN; WHEN constructing the source-only candidate, the implementation SHALL restore all193 official package files before editing only two normalized Cargo manifests; WHEN Cargo execution is considered, it SHALL remain blocked pending a separately reviewed root launch.

## 需求列表

### FR-1 — Preserve original audit and identify the complete locked dependency

Retain all four raw reports, exact lock hashes, source/tool/database identities, and no ignore flags. Independently identify both gateway lock paths: gateway→sqlx→sqlx-mysql→rsa, and gateway→sqlx→sqlx-macros→sqlx-macros-core→sqlx-mysql→rsa. Already configured default-features=false with postgres/runtime/macros/migrate/uuid is not a new fix. Actual selected compiler units without RSA do not satisfy raw audit admission.

### FR-2 — Limit the dependency surface without changing PostgreSQL semantics

The authorized current scope is manifest-only, provenance-sealed SQLx0.8.6 and sqlx-macros-core0.8.6 vendor packages to remove unused MySQL optional dependency routes and their weak feature references. Preserve all packaged Rust source, PostgreSQL code, current enabled feature semantics, both original migrate! invocations, embedded migration bytes/checksums/order, transaction/admission/authentication source, and SQLx versions. Reconstruct original full packages from original crates whose SHA equals the lock checksum, then record an exact manifest patch and a complete vendor inventory. Do not hand-delete RSA/MySQL lock entries, fake a crate, replace cryptography, ignore the advisory, or edit original database migration bytes.

### FR-3 — Independent resolution and new source qualification remain mandatory

Normal future Cargo resolution must generate the new lock; it must actually eliminate all RSA paths. Dangling sqlx-macros feature references, registry dev dependency behavior, unexpected cfg warnings, other package references, target/build/dev graphs and final packaging are OPEN until real resolution/build verifies them. If a third manifest or Rust source is required, stop and expand the finite specification and fresh impact before editing. New full selected/conservative graph, all four fresh raw audits, exact four gateway binaries, PostgreSQL migration tests, corresponding final source/installed artifact identities and original RC gates remain required. Existing build/audit results are not reusable candidate receipts.

## 非功能需求

Source edit/build/audit/installation/issuer/release runs are all unauthorized in this SOURCE_ONLY_NOT_WIRED candidate. Current dependency graph coverage is not native or supply-chain authority. Vendor and Cargo feature boundaries remain manual HIGH/UNKNOWN unless actual fresh graph covers them; zero graph edges never mean zero impact.

## 依赖关系

Exact F13 lock/manifest/source; original four audits and official RustSec database commit7eebec69; cached original SQLx crates verified by lock SHA and full packaged file bytes; future root authorization, ordinary controls, new frozen source/independent startup and real final qualifications.

## Authorized feature compatibility boundary

FR-2: retain sqlx mysql=["sqlx-macros?/mysql"] and sqlx-macros-core mysql=[] compatibility declarations so the untouched third sqlx-macros manifest has a declared target. Remove both optional sqlx-mysql dependencies and all weak sqlx-mysql? references. These declarations do not implement MySQL. WHEN a candidate launch selects mysql or all-databases, the source admission control SHALL reject it before any Cargo execution. Ordinary controls must show current PostgreSQL reachable features/dependencies equal the original projected graph excluding inactive MySQL references. Generic SQLx/all-features/MySQL compatibility is unsupported. If PostgreSQL parity changes or a third manifest is required, STOP and report it before editing.
