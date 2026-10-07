# Design: finite yoke derive repair

## Requirements mapping
FR-1/2 constrain Cargo resolution; FR-3/4 constrain admission; FR-5/6/7 constrain execution evidence; FR-8 preserves authority and held scope.

## 概述
Use targeted `cargo update -p yoke-derive@0.8.3 --precise 0.8.4` for each cloud manifest. Published yoke0.8.3 requires ^0.8.2. The replacement preserves dependencies/features and changes underscore construction to support the declared Rust1.82 minimum; this repository continues using1.98.1. Keep yoke0.8.3 and every other resolved package. Desktop derive0.8.2 and the local-agent lock are unchanged.
Official references: https://github.com/unicode-org/icu4x/commit/a59ab860d4bda548e94dfbf992d87fe1f761bc55 and https://github.com/unicode-org/icu4x/issues/8506 . No advisory suppression or raw-zero claim is introduced.

## 技术方案
F is b97c469b1bd7ffb9973a65e19b798d2573561d92, tree c017dc6e5f2fde6f9f135119500916cbe88efe1e, parents [fd7b303839aa648d33456f7aaeec6388bfb696c4, decfd70c746c5dd0d7d7c6ceace718c5a49487da]. R remains e2e011f7f2a3a1df838bbd588106205b999db610 and its existing pinned tree/documents.
Add four lines before the historical topology handler in linux_package.select. The new selector tries only D[F], I[F,D], J[R,I]. F itself misses this grammar, so fresh historical validation through publication.selected_profile(F) terminates through the unchanged old profile.
Content requires the full reviewed tree, nine paths and exact non-self pins. The new profile's self bytes are externally bound by exact staged-tree review. Recover complete F lock bytes by exact-once replacement of the full old/new yoke-derive blocks, and recover complete F dispatcher bytes by exact-once removal of only the four inserted lines. No historical pin/cap/inverse table changes.
Only topology mismatch returns None. Selected-content exceptions, including historical TopologyError, propagate. No arbitrary ancestry, correction chain, same-tree substitute, mutable-ref authority or production cache is allowed.

## 文件结构
All paths are mode100644. Three replacements plus six additions give1732 entries from F's1726. Whole-file/delta ceilings below are independent of the720 aggregate added+deleted-line ceiling; generated lockfiles are not source modules.
| Path | Whole/delta |
| --- | --- |
| services/cloud-agent/Cargo.lock | 1108/4 |
| services/cloud-gateway/Cargo.lock | 2266/4 |
| scripts/rc_pretag_linux_package_profile.py | 185/4 |
| scripts/rc_pretag_yoke_repair_profile.py | 220/220 |
| scripts/rc_pretag_yoke_repair_cases.py | 300/300 |
| docs/specs/issue85-yoke-derive-repair/requirements.md | 40/40 |
| docs/specs/issue85-yoke-derive-repair/design.md | 60/60 |
| docs/specs/issue85-yoke-derive-repair/tasks.md | 40/40 |
| .github/workflows/issue85-yoke-repair.yml | 100/100 |

## Validation and execution
Freeze ten YokeRepairCompositionTests names for identity, topology, lock delta, paths/pins, budgets, inverses, terminal failures, protected boundaries and exact inventories. Existing1174 IDs/assertions and strict303 remain byte-identical. The new cases filename stays outside historical discovery and executes explicitly.
One new push-only workflow uses ci/issue40-current-nginx-include-yoke-*, full-history exact-SHA checkout and D-only admission in all three rows. Ubuntu22/Windows2025 run the full standalone cloud-agent test command. Windows2025 gateway runs the existing lib/service_contracts/enrollment_contracts command. The Ubuntu agent row executes the new ten cases once. Keep locked metadata/inverse-tree, toolchain, source/lock hashes and logs; failure artifacts cannot grant success.
That same branch triggers unchanged issue40-current-nginx-include.yml: Linux gateway lib/seven portable targets, one audited actual four-binary build,45/57 HTTP/pending-WebSocket geometries and separate authenticated native11/TLS9. The45/57 alone are not authenticated lifecycle proof. Verify actual inventories and same source SHA.
Retain existing PR strict303/contracts755/consumer452. Run focused affected cases/review first; publish the immutable reviewed candidate and run native/hosted CI parallel with required D1184/I845/J845 coverage. Exact-I hosted303 may join local542 only with authenticated same-checkout/full-inventory evidence; J retains all845. No source-identical native/package reruns are added.

## Boundaries
No runtime, credential, security-setting, release/publish permission, package version, desktop/local lock, held source-assembly path or snapshot change. No final RC admission follows. Stop on unrelated Cargo resolution, scope overflow or real gate failure; retain failed evidence and use normal nonforce correction/integration procedures.
