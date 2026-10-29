# Requirements: publisher staging download budget
## 功能概述
Connect the existing PublisherSession activation budget to both owned staging downloads.
## 历史经验与坑
PR135 added downloader controls; separate calls still default to fresh budgets. Preserve cleanup uncertainty and existing cancellation assertions.
## 术语定义
Activation budget means the original session absolute deadline and bound check_active callback. Cleanup retains its independent real deadline.
## 范围边界
Only three runtime modules, finite source admission and necessary tests. Authentication remains before staging and live writes remain blocked.
## 需求列表
### FR-1: Share the existing activation controls (Must)
As the publisher owner, I need both receipt and FINAL downloads to consume one budget.
WHEN staging starts THEN the system SHALL pass the original session deadline and callback through StagedAssets to both existing downloads without renewal.
WHEN legacy callers omit both controls THEN the system SHALL preserve existing default download behavior.
WHEN cancellation or expiry occurs between downloads THEN the system SHALL prevent the second worker launch.
### FR-2: Preserve cleanup and public failure semantics (Must)
As the owner, I need reliable retirement and persistent cleanup failure.
WHEN a download cancels or expires AND cleanup succeeds THEN the system SHALL preserve existing cancelled or timeout public codes with effect none.
WHEN transport cleanup is uncertain or stage/API disposal fails THEN the system SHALL retain sticky cleanup failure and report adapter_error with effect none.
WHEN an activation fails THEN the system SHALL retain blocked_no_effect, no transition and no remote mutation.
WHEN close repeats THEN the system SHALL never retry a possibly closed descriptor or erase previous cleanup failure.
### FR-3: Admit only finite exact source compositions (Must)
As the maintainer, I need historical source contracts and assertions preserved.
WHEN validating D[M], I[M,D] or J[R,I] THEN the system SHALL enforce exact parents, full trees, seven whole-byte inverses and the four pinned R documents.
IF selected current or historical content is invalid THEN the system SHALL terminate without fallback or mutable candidate caching.
### FR-4: Run real worker and regression evidence (Must)
As the maintainer, I need current source-bound outcomes.
WHEN validating this change THEN the system SHALL retain all old1328, strict303 and consumer452 IDs and add exactly12 runtime plus12 composition cases.
WHEN publisher engineering CI runs THEN the system SHALL execute all168 unique cases on Ubuntu22/24 with complete source and outcome receipts.
## 非功能需求
NFR-1: Preserve original receipt bytes, six owned roots/asset handles, fixed hosts/IPC, downloader implementation and independent retirement deadline.
NFR-2: No scratch deletion, global parser/copy/hash bound, native/security acceptance, public authority seam or activation change.
NFR-3: Exactly13 paths,7 replacements,6 additions,1770 entries; aggregate additions+deletions≤1800 and per-file caps in tasks.
## 依赖关系
Reuse PublisherSession, StagedAssets, PrivateRoot, the existing downloader and publisher TLS/child fixtures. No dependencies added.
## 检查清单
FR-1–FR-4 need implementation, source-specific tests, exact independent review and real CI before engineering closure.
