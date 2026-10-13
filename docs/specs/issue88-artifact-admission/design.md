# Design: owned artifact admission after read-only preparation

## 对应需求
FR-1 through FR-7 apply to one bounded increment based on D750b11b20651b3f8bfadba69c19cb7eaf0c11e1e. This worktree is a review draft, not a sealed or admitted candidate.

## 概述
The existing all-gate requirement runs before artifact staging and prevents the artifact verifier from obtaining bytes. Separate read-only preparation from full admission, and add one private owner that can authenticate only the concrete evidence it actually verifies.

## 技术方案
Keep authenticate_packaging and its two-gate blocked report unchanged. A fixed preparation wrapper validates that exact report and permits only local staging, never a core intent or HTTP mutation. PublisherSession then creates a private artifact owner with its concrete GitHub, Selection and owned stage. The stage receives a fixed API adapter whose GET delegates to GitHub.get rather than a replaceable instance method; its token is only reused by the existing bounded artifact worker. (FR-1, FR-2, FR-5)

The owner calls the unchanged stage entry, including _verify_bundle_bytes and _provenance. Read the exact retained provenance handle with bounded reads and strict JSON parsing, then check the digest/asset bindings and original plan. Hash fixed canonical evidence envelopes containing the frozen source, selected FINAL/consumer artifacts, six assets and validated provenance. Bind exactly bundle_bytes, raw_cloud_audit and raw_noncloud_audits; the latter two reuse the raw audit/applicability/source checks already transitively authenticated by the exact API ZIP. Do not claim broad #84 malformed-input regressions, #85 TLS/WSS acceptance or independently repeated installer execution. (FR-2, FR-3, FR-6)

The private registry binds this owner to the concrete GitHub instance. Full _authenticate first checks the original owner's controls, runs fresh authenticate_packaging and then asks that same owner to revalidate stage metadata, retained identities/inventory/hash and evidence digests. No public report importer, status/authority argument or caller transport is added. A report is inert and immutable; a forged report is never consumed by a production gate. (FR-3 through FR-5)

Move the existing all-gate and remote-constraint checks after staging in activation, retaining both immediately before the core starts. Every direct mutation still performs complete _authenticate, unchanged _remote_constraint and _authorize before before_write or sendall. Unknown snapshot/Windows/review/visibility rows keep activation blocked and clean up all local owners. (FR-4, FR-6)

## 预算、生命周期与测试
Carry one activation/operation deadline and cancellation callback through the new metadata, adapter, retained-handle hashing and final return paths. Enter fixes the original lifetime callback; each later caller callback can only add checks. A direct owner keeps its first deadline. For an exact bound PublisherSession._check_active method whose session has the same owner/API/Selection, read only that session's internally renewed operation deadline; reject a paused scope and cap it by any shorter caller deadline. No caller argument renews authority and no per-read reset occurs. Consume provenance via retained handles with 64KiB chunks and the existing JSON_LIMIT, hash the same bytes, and rewind without reopening paths. Closing/disposing withdraws the owner before stage/connection retirement. Existing cooperative DNS/kernel limits and no concurrent same-UID writer assumption remain explicit. Some existing installer/noncloud/GLib/raw parsing paths do not yet carry a complete shared budget; this partial evidence must not claim final liveness admission for those paths. (FR-4)

New verified TLS cases exercise real metadata/staging success with global block, exact three digests, caller/foreign/closed owner rejection, original plan/provenance drift, archive corruption, raw active RustSec/nonnumeric npm/GLib evidence rejection, stage revalidation drift and cancellation/expiry during final owned reads. Existing metadata and mutation regression IDs remain, with explicit entry/policy assertion updates rather than weakened assertions. Stage API source, held PR98/snapshot source, eligibility evaluator, core and consumers remain unchanged. (FR-5 through FR-7)

## 文件结构
New scripts/rc_publication_artifact_admission.py and scripts/rc_publication_artifact_admission_cases.py, and this specification directory. Existing changes are restricted to executor preparation/retirement, GitHub admission, fixed policy verifier descriptions and explicitly affected test fixture/assertion symbols. No finite profile is resealed in this draft.
