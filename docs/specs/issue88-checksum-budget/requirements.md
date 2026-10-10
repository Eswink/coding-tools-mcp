# Requirements: cooperative checksum budget
## 功能概述
Carry the existing publisher activation controls through owned FINAL checksum validation.
## 历史经验与坑
PR136 shares the original deadline across both downloads. Hashing can still continue after cancellation; preserve established content errors and sticky retirement failures.
## 术语定义
Budget means the original absolute deadline and identical bound check_active callback. A checkpoint is cooperative and cannot interrupt a synchronous operating-system call.
## 范围边界
Three existing runtime modules, one runtime test module and finite historical admission. Live authentication remains blocked before staging while required gates are missing.
## 需求列表
### FR-1: Check the existing budget throughout checksum work (Must)
As the publisher owner, I need cancellation and expiry observed during checksum work.
WHEN FINAL checksum validation starts THEN the system SHALL forward the same original deadline and callback to inventory rows and each existing 64 KiB hash chunk without renewal.
WHEN a read, EOF or successful close finishes late THEN the system SHALL reject before returning a digest or starting the next validation phase.
WHEN callers omit controls THEN the system SHALL retain old call shapes, checksum results and no clock reads.
### FR-2: Preserve rejection and ownership semantics (Must)
As the owner, I need fixed errors and reliable retirement.
IF controls are invalid or callbacks fail THEN the system SHALL fail closed with bounded existing codes and no raw callback context.
WHEN parsing, checksum, file I/O or close has already failed THEN the system SHALL preserve that failure rather than poll from a finally block.
WHEN checksum cancellation or expiry unwinds staging THEN the system SHALL retain original ownership, one-shot retirement and sticky cleanup uncertainty; no transition or mutation occurs.
### FR-3: Admit only exact finite source (Must)
As the maintainer, I need historical assertions and source identities preserved.
WHEN selecting D[M], I[M,D] or J[R,I] THEN the system SHALL enforce exact ordered parents, full trees, seven whole-byte inverses and the four pinned R documents.
IF selected current or historical content is invalid THEN the system SHALL terminate without fallback or caching mutable candidate results.
### FR-4: Verify real checksum and worker behavior (Must)
As the maintainer, I need actual file/chunk and child-process outcomes.
WHEN testing this increment THEN the system SHALL preserve all1352 old IDs, strict303 and consumer452 and add exactly12 runtime plus12 composition cases.
WHEN publisher engineering CI runs THEN the system SHALL execute192 unique cases on Ubuntu22/24 with exact source and outcome receipts.
## 非功能需求
NFR-1: Exactly13 paths,7 replacements,6 additions,1776 entries; actual additions+deletions≤1800 and tasks caps apply.
NFR-2: Preserve PrivateRoot retention, original receipt bytes, default hashes/copies, fixed hosts/IPC and existing retirement deadlines.
NFR-3: No deletion, supervisor/Git wrapper, authority change, native/security admission or full parser/Git timeout claim.
## 依赖关系
Reuse ConsumerError, existing checksum/hash functions, publisher fixture and real TLS download workers; no new dependency.
## 检查清单
FR-1–FR-4 require implementation, exact independent review, source-specific tests and actual CI before engineering closure.
