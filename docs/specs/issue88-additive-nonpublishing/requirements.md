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
