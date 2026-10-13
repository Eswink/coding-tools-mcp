# Requirements: owned artifact admission after read-only preparation

## 功能概述
Break the metadata/staging circular dependency without opening publication. Exact integration and FINAL metadata may start owned local staging; mutation still requires all current gates and the unchanged remote-tag and owner constraints.

## 需求列表
- FR-1: Read-only preparation SHALL require the concrete owning GitHub connection, identical frozen Selection and freshly authenticated integration/FINAL metadata under one caller-owned deadline; no caller report or PASS flag is accepted.
- FR-2: The session SHALL create and own the real StagedAssets and use the unchanged FINAL ZIP, four payload, five installed receipt, cloud exact-build, raw npm/RustSec and GLib validators. Metadata alone SHALL never pass artifact evidence.
- FR-3: After staging, the owner SHALL read its retained provenance handle, bind exact original plan/provenance/asset bytes and compare fixed canonical digests for bundle_bytes, raw_cloud_audit and raw_noncloud_audits to the frozen subject. Every other missing gate remains unknown.
- FR-4: Every full admission SHALL first check the original lifetime cancellation, freshly authenticate metadata and revalidate that same owned stage under its owned operation scope. Later caller controls may only strengthen cancellation or shorten a deadline. Only a fixed bound PublisherSession, with exact owner/API/Selection back references, may renew its internal operation deadline; a direct owner retains its first deadline. A foreign, closed or absent owner, changed metadata/bytes, deadline or cancellation SHALL fail before mutation.
- FR-5: Instance GET overrides, caller records, callback-produced authority, alternate stages or mutable reports SHALL not authenticate evidence. Internal stage reads SHALL call the concrete fixed GitHub.get implementation.
- FR-6: Snapshot blockers, Windows isolation, full audit/regression scope, final review, draft visibility, owner authorization and remote tag races SHALL remain blocked. Installed observations remain authenticated producer assertions; raw findings remain visible and approval/atomic/live flags remain false.
- FR-7: Tests SHALL use real verified loopback TLS and real consumer archive/byte validators, preserving original test IDs and separately identifying intentional entry/policy changes. No skipped or expected-failure outcome qualifies.

## 非功能需求
No new dependency, production environment operation, credential/protection change, version edit, publication, sealed profile or workflow change. New code carries existing deadline/check_active budgets and fixed byte limits; no timeout reset or generic verifier registry.

## 依赖关系
Reuse authenticate_packaging, StagedAssets, consumer._verify_bundle_bytes, the strict retained-file and JSON helpers, and the unchanged publication core. The concrete Stage API budget workstream is separate; this increment does not modify its source.

## 验收标准
Successful local staging authenticates exactly the two metadata and three artifact evidence rows; it still produces blocked_no_effect, no core transition and no mutation while unknown gates remain. Every negative artifact/API/owner/budget case reaches its intended validator and performs no remote write. Full finite source admission and actual hosted gates remain required before integration.
