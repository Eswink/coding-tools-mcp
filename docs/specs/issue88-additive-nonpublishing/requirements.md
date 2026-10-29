# Requirements: authenticated FINAL artifact consumer

Issue: https://github.com/Eswink/coding-tools-mcp/issues/88
Release status: [full-scope RC ledger](../../releases/next-rc-ledger.md).
Baseline: 1281915b38c2364c4476ca94aabae3043423ed5f.

## 功能概述

Provide a fail-closed nonpublishing consumer for authenticated first-attempt FINAL evidence.

## 需求列表

- FR-1 (MUST): When manually invoked, the consumer shall bind actual invocation, clean reviewed source, all six RC versions, lightweight tag and latest successful full integration/FINAL API job inventories to explicit inputs; FINAL attempt must be 1
- FR-2 (MUST): Before parsing bytes, the consumer shall authenticate artifact metadata, fixed-origin read-only transport, exact outer size and SHA256, with token-free bounded storage redirects and repeated freshness checks
- FR-3 (MUST): When reading any artifact, bounded standard ZIP/TAR parsers shall reject unsafe names, aliases, links, extensions, invalid framing, resource exhaustion and checksum mismatch, using fresh private nofollow roots outside source
- FR-4 (MUST): The consumer shall recompute data-only cloud, noncloud, package and installed-native contracts against an explicit trusted producer, preserving raw findings, warnings, source/audit bindings and unchanged producer rejection semantics
- FR-5 (MUST): On successful content and freshness validation, the consumer shall produce exactly four payloads, sanitized RC_PROVENANCE.json and SHA256SUMS_<version>.txt, plus a nonpublic asset plan; both approval flags shall always be false
- FR-6 (MUST): The workflows shall use contents/actions read only, immutable source checkout and pinned actions, no cache, no payload execution and no Release/tag writes; hermetic and unchanged producer regressions shall run

## 非功能需求

Additive Python modules, tests, two workflows and these specs only. Existing producer, stable release and tag gates remain byte-for-byte unchanged. Source files have at most 500 lines. Fixed limits follow design section 4. No credential creation, production deployment, signing claim, real-host acceptance claim. Synthetic fixtures are not runtime release proof. A real harmless read-only transport observation is needed before enabling an observed storage host; genuine FINAL DAG and owner version remain separate release gates.

## 依赖关系

Requires unchanged release_tag_gate, final_rc_evidence, release_dependency_contract, cloud_release_bundle, rc_version_gate, reviewed_source_gate, rc_native_gate, rc_packages and authenticated GitHub read API.

## Acceptance

Each FR has adversarial tests. Any validation or finalization error fails the job and prevents success-only upload; it never grants release or publication authority. After a terminal commit error, the consumer makes one identity- and content-checked withdrawal attempt against only its own success-plan file. Absence is asserted only when confirmed. If withdrawal cannot be confirmed, `uncertain_plan_outcome` records possible on-disk plan residue, preserves the original failure and forbids automatic replay. Arbitrary filesystem failure is not covered by an unconditional no-residue promise. Source and environment stay unchanged. Independent code review binds the exact staged tree. Hosted fixture CI confirms exact-source Python 3.12 runner behavior after publication of the reviewed engineering commit. Missing transport or genuine FINAL evidence is reported as blocked rather than fabricated.

## Finite deadline bugfix addendum (2026-10-04; Issue107)

Engineering dependency: exact unmerged PR89 `6b6ad879bfaeb3246de0a30d965da42c85b17873`, tree `29cbb9194a89e461210535512760487c99a996da`. Canonical `c3fcfb1f2617d56f8f395317a18d93884d551789` lacks this consumer. This addendum does not choose integration or change canonical source.

- FR-7 (MUST): With an admitted test transport, `download_artifact_zip` shall own one monotonic operation deadline established before worker launch, covering readiness, DNS/TLS, both response status/header phases, body, parent count/hash/file completion and normal worker terminal observation. Read-idle timeouts are supplementary; progress never resets the operation deadline
- FR-8 (MUST): Every normal/error/cancellation path shall dispose of the one owned worker using one separate cleanup deadline. Unknown close/terminate/kill/reap outcome is sticky terminal failure. Escalation to terminate/kill cannot produce successful download
- FR-9 (MUST): Success shall require exact parent-computed size and SHA256, completed private file, worker DONE after both HTTP resources close, valid protocol terminal order, clean IPC EOF and normal exit 0. Late completion, malformed IPC, worker death or cleanup uncertainty shall not reach revalidation, archive parsing or plan creation
- FR-10 (MUST): Preserve current fixed two-hop request policy, empty production host set, validation/error sanitization, private-root ownership, unchanged public consumer/download signatures and all source/run/attempt/approval fences. The empty host set shall reject before launch/network
- FR-11 (MUST): Existing policy regressions plus actual supervised-boundary tests shall distinguish cancellation at the operation deadline from eventual rejection. Scope is the current Ubuntu24/Python3.12 consumer lane, not Windows support; tests and documentation shall disclose synchronous process-launch/file-I/O and OS scheduling limits

Acceptance: all FR-7..11 tests in the finite test matrix must have expected named outcomes, nonzero inventory and zero unexpected skips. No assertion may replace the demonstrated deadline violation with an arbitrary exception. Healthy-system network/IPC waits are bounded; synchronous OS process creation, regular-file writes/fsync/close and scheduling cannot receive a universal wall-clock return guarantee. A late return from any such operation must fail closed. The host/FINAL/publication holds remain unchanged.

Finite lifecycle bug tracking: [Issue107](https://github.com/Eswink/coding-tools-mcp/issues/107); Issue88 remains the broader consumer/release scope.

## Exact-host source adoption addendum (2026-10-04)

This separately approved finite increment is based on integrated PR89 commit `6dba87ceb3551b08fd98d0a49e649c3d02026d02`, tree `2f6b775ff396468de49802eed12552b6d626d2fc`. The historical Issue107 baseline and default-empty statements above remain historical evidence. This addendum supersedes only FR-10's production-default-empty hold: both compiled `TRUSTED_STORAGE_HOSTS` declarations shall equal exactly `frozenset({'productionresultssa5.blob.core.windows.net'})`. FR-10's remaining two-hop, sanitization, ownership, signature and source/run/attempt/approval fences remain in force. An explicitly empty policy must still reject before worker launch/network and remains the rollback mechanism.

- FR-12 (MUST): Admit only the reviewed exact singleton in both parent and worker; no wildcard, suffix, subdomain, discovery, fallback, retry, new redirect, CLI/environment override or new host-admission input. Retain HTTPS, API-only Authorization, fresh token-free storage request, no userinfo/IP/non443/fragment/arbitrary host/second redirect, metadata-authoritative size/SHA256 and all FR-7..11 lifecycle guarantees
- FR-13 (MUST): Production edits shall be only the two existing declarations and adjacent comments. Inverse removal of those edits must reproduce both runtime base files byte-for-byte. Preserve all original 12 transport-test assertion ASTs and the entire supervisor test file; add a distinct unpatched compiled-default test class, exact-host acceptance and adversarial rejection coverage in the existing transport tests
- FR-14 (MUST): Historical authenticated proof at `95055529c52e6883cab504a4470086dbdbb14ae8`, run `36805761735`/attempt1, establishes one 912-byte harmless fixture transfer, not a FINAL bundle or current-worker live success. Actual default-supervisor/worker compatibility remains UNPROVEN until separately authorized and exercised. Source adoption, live validation, canonical integration and release approval are distinct decisions

Acceptance: exactly six existing paths (two transports, existing transport tests, these three specs); full 174-existing-plus-new consumer, 194 unchanged producer and 14 version tests, pinned official GLib fixture and zero skips; exact inventory/source/tree, syntax/line caps, staged graph and independent frozen-tree review. No optional diagnostic framing/header/token/cache hardening, helper/workflow, PR97/100 import, live proof or FINAL execution is included. Empty-policy rollback does not widen any gate. Both approval flags remain false; all other release/security/real-host holds remain unchanged.
