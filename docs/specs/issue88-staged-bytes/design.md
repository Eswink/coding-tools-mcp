# Design: cooperative publisher staged-byte budget
## 概述
Provisional D2=564a68d42463b3e3b526d875970dd631da2e3eec, tree57903a2751483c8b6e1aaa3879dce8173e77d647, sole parent e90e15fa8b6d527006b6c62a75eb2fcab6629f0f.
Actual F=f9d414b0c85348da79fee80c3b04bf5a06daf1d7 is bound with ordered parents[e90e15fa8b6d527006b6c62a75eb2fcab6629f0f,D2] and the complete identical1783-entry tree. Raw actual object and all baseline bytes are verified in ACTUAL-F-BINDING.json.
## 技术方案
### FR-1: Caller-owned invocation controls
Only _receipts, StagedAssets.__enter__/revalidate, PrivateRoot.copy and PublisherSession._execute change.
Add optional keyword-only deadline/check_active to receipts/copy/revalidate. Empty kwargs preserve omitted controls.
Activation forwards its existing pair through receipt archive helpers, four copies, both output hash groups and initial revalidation.
Later ObserveFence/ObserveDraft/VerifyPublished captures the current bound callback once and supplies it with that operation's deadline to authentication and revalidation.
Bare legacy revalidate() keeps its old unbudgeted default. Never reuse the retained activation deadline for a later operation or renew time inside a byte loop.
_receipts reuses _directory_guard/_local_records/_deflate_integrity and keeps the existing JSON_LIMIT+1 member read, exact receipt bytes and original parser/close order.
PrivateRoot.copy keeps nofollow source/exclusive target ownership, CHUNK reads, FILE_LIMIT, registration, flush/fsync and close order; add checks around successful read/write/EOF/close boundaries.
Output writes remain existing bounded writes; hash_file receives the identical original pair in both groups.
Revalidation hashes retained descriptors directly, checks around observation/inventory/handle work and CHUNK read/EOF/rewind, and rewinds successful handles to zero.
### FR-2: Error order and cleanup
Newly acquired resources enter existing ownership scopes before callbacks. Validate established size/digest/content facts before the operation's post-success check.
No callback runs in failed unwind/finally. Existing read/write/close diagnostics take precedence; retained close methods and six-root ExitStack stay unchanged.
Only the try/except around executor revalidate converts actual ConsumerError codes transport_deadline_exceeded/transport_cancelled to WireFailure timeout/cancel, effect none.
Require a real string before map lookup. Other errors continue through existing adapter_error handling; do not change _failure, core enums or transition authority.
Existing activation blocked_no_effect, later partial_draft/published_unverified and sticky disposal uncertainty remain; repeated close never retries retired owners.
### FR-3: Exact source and history
Use actual F as the new profile M after binding; D[F], I[F,D] and J[R,I] with four exact R documents are the entire grammar.
All15paths must be exact100644 blobs and all outside-CAPS entries equal F. Eight replacements reverse to full F mode/blob/SHA256/size/line identities.
Finite prior pins cover stage1, IO1, executor2, checksumcases1 and workflow6; no ancestry exemptions or inferred variants.
The old archive profile gains only four selector/two normalizer lines; selected-source failures cannot delegate.
Seven old archive-case operands plus import, two checksum-case operands and two parser-spy keyword-forwarding lines preserve IDs/assertions; complete-byte inverses and declared AST removal prove preservation.
Pin all scoped sources except the new profile itself; independent whole-tree review binds that profile. No production cache.
An isolated lower archive-fragment diagnostic uses authenticated complete baseline bytes, one test-only outer identity delegate and exact call assertion, followed by independent unpatched outer rejection.
### FR-4: Real IO and source evidence
Eighteen cases cover default bytes/no clock, invalid controls, callbacks, receipts, copy/hash/revalidation boundaries, errors/nofollow, real workers and retirement.
Valid original-provenance JSON whitespace supplies genuine multi-CHUNK retained bytes. Do not stub parser/hash/copy success or inherit an old TestCase.
Reuse current fixture helpers and Trace/Observed/Budget; retain trace_calls rather than the forbidden installed attribute name.
Per-operation cases expire activation after pause then succeed under the next pair, and verify cancellation/timeout before/after modeled mutations plus sticky disposal failures.
Twelve composition cases cover anchors/topology/path/mode/pins/budgets/inverses/historical failures/cache/IDs/workflow/outcomes.
Preserve old1403, strict303 and consumer452; new30 totals D1433, I/J1094, publisher249. Planning counts are not executed proof.
Frozen new30 digestd574f4b98732882ad85e3e69a7e1b53ab65b8a3d6ea53e38170aa77a3d5a9825.
## 数据模型与 API
No new stored model or authority flag. Controls remain optional int/finite-float deadline and callable callback validated by existing _check_budget.
Exact receipt/provenance, AssetPlanView, six handles, fixed hosts and metadata identity models stay unchanged.
## 文件结构
The15exact paths/caps appear in tasks. Current sizing is125delta for8existing paths and496case lines plus60support lines for the unexecuted complete runtime sketch.
## 风险与边界
Git/source subprocesses and metadata/API calls remain synchronous. Checks around successful returns do not make them interruptible or hard bounded.
PrivateRoot.files remains a recursive inventory walk; hostile directory churn can delay it. This increment checks around success without changing its recursion, metadata limits or ownership.
Receipt readback, JSON decode/encode, original-plan memory hash, schema/contracts, sorting/allocation and ZipExtFile/zlib internals remain synchronous.
OS open/stat/seek/read/write/flush/fsync/close and callbacks cannot be interrupted mid-call; reject late success only at supported checkpoints. Cleanup retains its existing separate retirement behavior.
PR98/snapshot, Windows, main/tag/release changes, credentials/security, live activation and full native/bundle acceptance remain outside scope.
Standing engineering nonforce branch/PR/read-only-CI authority persists subject to exact-source gates. No ownership removal/deletion or Git/supervisor framework.
## 检查清单
Fresh archive-normalizer impact is CRITICAL9direct/39affected/9flows. Root/independent acceptance and check_spec precede runtime edits. Actual F precedes final admission/publication; source-specific tests/review/detect_changes precede engineering integration.
