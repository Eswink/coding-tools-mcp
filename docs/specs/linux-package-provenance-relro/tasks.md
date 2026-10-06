# Tasks: Linux package provenance and scoped RELRO preservation

## 交付物清单
Exactly34 paths,19 additions,15 replacements,1724 final tracked entries and aggregate8500 added+deleted lines. Every source/test file stays≤500 lines. The exact file/mode/final/delta table in design.md is controlling. No fourth guard module, additional source path, loader override, expanded protected set, generic RPATH skip or extra product build is hidden in this budget.

## 任务列表

### T1: Freeze current source and prerequisites (FR-1..FR-8)
- [x] Independent clone verifies Mfd7b3038/treee4ab19e2, no alternates
- [x] Read AGENTS, Probe4.0.1, project context and historical graph
- [x] Fresh index-only graph:23628 nodes,52954 edges,285 flows; FTS unavailable and source checks supplement it
- [x] Record HIGH selector impact10 direct/68 symbols/3 flows and inverse9/29/4; root conditionally acknowledged the exact focused-review gate
- [ ] Complete focused frozen-packet security review, check_spec and estimate before implementation
Evidence: current publication_profile.selected_profile is the shared selector; current AppImage profile admits only its existing eleven-path delta. Existing compiler contract is479 lines, so engineering-specific code is split into directly used new modules rather than expanding it beyond500.
Files: three specification files,150/260/200 final-line caps. No implementation function is edited during this task.

## T2: Stage the exact backend and owned control state (FR-2, FR-3)
- [ ] Implement appimage_relro_tool.py≤370 lines with fixed original outer/inner pins, official OS parser, list-first descriptor-bound extraction and exact output caps
- [ ] Authenticate the four signed-origin host library inputs before compiling; create disjoint owned guard state
- [ ] Use the existing cargo_runner's post-copy hook as sole compiler-binding writer
Evidence: desktop_glib_build_evidence.py:117 cargo_runner captures real Cargo, validates events and copies desktop.elf/glib.rlib before returning. The fixed backend is the original1029016-byte patchelf0.8, not the runner's unrelated tool.
Tests: RelroToolTests12, including real bounded tool probes in the necessary native build. No acquired product payload runs in hermetic tests.

## T3: Preserve scoped bytes and original delegation (FR-2, FR-3, FR-5)
- [ ] Implement appimage_relro_guard.py≤440 and appimage_relro_contract.py≤480
- [ ] Authenticate exact argv, nine destinations, original identities, descriptors/owners and expected marker/RELRO
- [ ] Preserve only exact protected setters; delegate every legitimate unprotected operation/query with original output/status
- [ ] Enforce paired fsynced journal, sticky failure, owned-child cleanup, pending-call rejection and final-image byte/RELRO replay
Evidence: pinned linuxdeploy's setter loop can log failure yet return true; original0.8 parses first nonoption and writes filename_patchelf_tmp then renames. Final gate checks actual bytes and logs rather than trusting that return.
Tests: RelroGuardTests20 and RelroContractTests16. Test files≤480 each; tool tests≤360. Meaningful negatives cover target substitution, unknown protected mutation, wrong marker/hash, failed delegate, swallowed error, crash/pending operation, malformed journal and final-image mutation.

## T4: Reuse compiler collection in one package build (FR-1, FR-4, FR-5)
- [ ] Add linux_package_provenance.py≤450 and linux_package_provenance_contract.py≤460
- [ ] Keep old collect/build_environment/producer identity/link/probe/DEB algorithms intact; add narrow old-main/runner hooks and share one existing verification tail within old contract≤500
- [ ] Use one exact verbose Tauri call and one external target across tools, hook, compiler, copy, package preparation and checks
- [ ] Bind raw Tauri DEB separately from final RC DEB with payload equality, and bind protected APP bytes to same-run compiler output
- [ ] Extend existing AppImage verification to a bounded complete regular-ELF inventory; keep launcher/helper/GIO/graphics checks
- [ ] Seal the small provenance-inputs then envelope handoff without a digest cycle; use exact artifact IDs/attempts in installed jobs
Evidence: rc_packages.py:75 prepare hardcodes src-tauri/target/release/bundle; desktop_glib_build_contract.py:196 source_identity rejects untracked evidence; build evidence therefore moves to RUNNER_TEMP and prepare receives the authenticated target/triple path.
Files/caps: exact ten compiler/workflow/package paths in design.md. Existing compiler script mode100755 stays; all other existing modes stay exact.
Tests: CompilerIntegrationTests20, PackageBindingTests12, required affected existing compiler/source cases and preliminary5. Preserve the old preliminary test's Windows assertions while replacing only the Linux literal-command location check with fixed collector/argv verification.

Three inherited entry-test mocks are narrowed to Cargo metadata only (12-line delta); all15 IDs/assertions and real graphics lookups remain unchanged. A local owned graphics cache supplies the missing GLES member as data; native CI uses official libgles2.

## T5: Attach bounded actual-process observations (FR-6, FR-7)
- [ ] Add linux_runtime_provenance.py≤500 with owned attach/checkpoint/finish and data-only verification
- [ ] Add optional narrow lifecycle hooks to startup and Linux NativeSession, both native sessions and existing checkpoints
- [ ] Thread the option through the Linux adapter only; Windows and no-observer call semantics remain unchanged
- [ ] Bind maps to live PID/start-time, device/inode, descriptor bytes and process filesystem view; record missing/inaccessible/transient observations without new capabilities
- [ ] Retain bounded environment projection and phase-correct reported package ownership; never infer loading from ldd or SONAME
- [ ] Join/close the observer on every failure/restart/cleanup path without masking original behavior
Evidence: Ubuntu原生验收v1.py:60 owns the driver Popen; the product is its descendant. exclusive_native_acceptance.py:171 run replaces its session at restart. Existing HTTP fixture can leave GIO TLS unobserved.
Files/caps: seven runtime/harness paths in design.md. Tests RuntimeMappingTests16, RuntimeLifecycleTests12 and InstalledWorkflowTests8, including actual ordinary-user mapping and lifecycle failure controls.

## T6: Admit only the reviewed source delta (FR-8)
- [ ] Add finite profile≤360, inverse≤320 and composition cases≤500
- [ ] Add≤5 dispatcher lines and≤4 AppImage inverse lines; publication_adapters stays byte-identical
- [ ] Normalize only eight historical AppImage case source reads, preserving all original method names/assertions through complete exact inverse
- [ ] Bind34 paths/modes/full trees/line budgets, fixed M parents and D/I/J grammar; preserve every historical pin and four-document R overlay
- [ ] Keep selected content errors terminal and candidate mutations fresh; permit only reviewed fixture-local immutable-M reuse
Evidence: current publication_profile.py495 lines leaves exactly5 lines; current AppImage profile.inverse_appimage_adapter is the existing common normalization entry. Its finite previously valid byte inputs must remain accepted; arbitrary modified inputs must reject.
Tests:20 LinuxPackageCompositionTests with frozen names and digest61da1f74c937f638442ec78250d5369b3bfb3692933e287769bb9e7a6a2d6adb. Cases cover anchors, topology, full-tree equality, modes/pins/budgets, inverses, original inventories, scope, workflow gates, terminal errors and cache exclusions.

## T7: Validate one candidate and retain exact proof limits (FR-1..FR-8)
- [ ] Execute focused affected tests during implementation; preserve real failures
- [ ] Freeze exact staged source/pins, run detection, source/security review and gencommit
- [ ] Run all1174 canonical cases on clean actual D once; run835 original/structural cases on faithful I and J without re-labeling them actual GitHub merges
- [ ] Avoid redundant unaffected223 reruns; retain their exact mandatory invocation/source scope
- [ ] Publish one authorized nonforce candidate/draft PR and run the one necessary native product build plus original four installed jobs
- [ ] Independently authenticate compiler/guard/packages/mappings/artifact bytes and existing three real-byte mutation controls; no self-reported pass substitution
- [ ] Verify normal feature merge/overlay and required fresh hermetic checks when source is accepted; keep current-D proof source-specific
- [ ] Record heartbeat, focused review and convergence with all unresolved claims explicit

## Inventory and evidence
Existing815 source IDs are unchanged. Existing223 supplements are168 compiler/source and55 directly affected package/native harness cases; they are existing tests, not new coverage invented by this feature. Add68 provenance,48 RELRO and20 composition IDs, giving1174 unique intended cases. Discovery must confirm actual loaded/executed IDs and no skips/xfails/xpasses; repeated contexts are not additional coverage.

Native results also preserve the original full Rust/frontend/startup/native counts and the three named real-byte controls. Real mappings may remain incomplete for inaccessible helpers or unexercised TLS. Such observations stay incomplete; no security control is relaxed to turn them green.

## Completion and rollback
- [ ] All finite implementation, required tests, exact source reviews and actual native/artifact observations are recorded
- [ ] Protected byte/RELRO claims are separated from other-DSO/fullclosure/native-linker/retained-code/security/release claims
- [ ] Original Windows/snapshot failures, raw advisories, held PR98 paths/ref and FINAL/main/release/publication holds remain visible
Before integration keep the isolated candidate. Any later rollback is a reviewed forward revert; do not replace historical assets, tags, failed evidence or held refs.

## 需求覆盖矩阵
| Requirement | Tasks | Evidence |
|---|---|---|
| FR-1 | T1,T4,T6,T7 | Historical defaults and exact profile/source tests |
| FR-2 | T2,T3,T7 | Nine authenticated inputs and original delegation |
| FR-3 | T2,T3,T7 | Sticky records and final independent rejection |
| FR-4 | T4,T7 | One actual compiler capture |
| FR-5 | T3,T4,T7 | Actual package/member and artifact binding |
| FR-6 | T5,T7 | Actual bounded mapping/lifecycle evidence |
| FR-7 | T4,T5,T7 | Original four-job behavior and environment |
| FR-8 | T1,T6,T7 | Exact paths/inverses/inventory/source review |

## 文件变更清单
The34 exact paths, modes and caps are enumerated in design.md. There are19 additions and15 replacements; no source path outside that table is admitted.
