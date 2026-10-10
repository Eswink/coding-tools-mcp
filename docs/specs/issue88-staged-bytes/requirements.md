# Requirements: cooperative publisher staged-byte budget
## 功能概述
Carry caller-owned controls through receipts, payload copies/output hashes and retained-handle revalidation as one finite capability.
## 历史经验与坑
The stage retains activation controls; later session operations intentionally have different deadlines. Reusing the old deadline after a pause is invalid. Preserve trace_calls and the no-execution scanner.
## 术语定义
Budget means the original deadline/callback for the current invocation. Cooperative checks reject late success without interrupting synchronous work.
## 范围边界
Five runtime symbols in stage/IO/executor, finite admission and necessary tests. No new framework, deletion or authority.
## 需求列表
### FR-1: Share controls through staged byte work (Must)
As the publisher owner, I need receipts and staged bytes to observe my current budget.
WHEN activation stages receipts, payloads, hashes and retained handles THEN the system SHALL forward the same activation pair without renewal.
WHEN later fence operations revalidate THEN the system SHALL pass that operation's current pair without changing retained owners or the stored activation pair.
WHEN controls are omitted THEN the system SHALL preserve legacy call shapes, original bytes/results and no clock reads.
### FR-2: Preserve ownership and diagnostics (Must)
As the owner, I need failures to preserve resource retirement and public effects.
WHEN streams are acquired THEN the system SHALL enter their close scopes before new callbacks.
WHEN an operation establishes invalid bytes or IO/close failure THEN the system SHALL preserve that error before post-success checks, with no polling from failed unwind.
WHEN executor revalidation raises ConsumerError timeout/cancel THEN the system SHALL map only those codes to existing WireFailure timeout/cancel with effect none; unrelated errors SHALL retain adapter_error handling.
WHEN cleanup fails after current or prior effects THEN the system SHALL retain existing outcome semantics, sticky uncertainty and one-shot retirement.
### FR-3: Admit only exact finite compositions (Must)
As the maintainer, I need the actual integrated baseline and all historical contracts preserved.
WHEN final admission or publication begins THEN the system SHALL bind actual merged PR139 F and verify its entire tree equals reviewed provisional D2.
WHEN selecting D[F], I[F,D] or J[R,I] THEN the system SHALL enforce exact ordered parents/trees, eight full-byte inverses, eleven historical identities and four pinned R documents.
IF selected or historical content fails THEN the system SHALL terminate without fallback or mutable candidate caching.
### FR-4: Verify real IO and unchanged inventories (Must)
As the maintainer, I need source-bound observed outcomes.
WHEN validating THEN the system SHALL retain all old1403/strict303/consumer452 IDs and complete historical bodies, adding eighteen real-IO plus twelve composition cases.
WHEN engineering CI runs THEN the system SHALL execute249 unique cases on Ubuntu22/24 with source/ID/outcome receipts before integration.
## 非功能需求
NFR-1: Preserve exact original receipt/provenance bytes, six roots/handles, nofollow modes, CHUNK/JSON/FILE limits and existing close order.
NFR-2: Exactly15paths/8replacements/7additions; expected1790entries; allfiles≤500; sumdelta caps1753, aggregate1800.
NFR-3: Git, metadata, recursive inventory, JSON, stdlib/native and OS/close work remain synchronous; no hard parser/global bundle/native/security claim.
## 依赖关系
Reuse existing archive/_check_budget/hash_file/PrivateRoot, unchanged fixtures, Trace/Observed/Budget and original tests.
## 检查清单
FR-1–FR-4 require exact root/independent review, fresh impact/spec gates, actual-F binding and source-specific real tests. PR98/snapshot and live publication remain held.
