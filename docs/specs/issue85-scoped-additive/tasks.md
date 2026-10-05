# 任务清单：issue85-scoped-additive

## 概述
Implement only the independently reviewed compiler-input/DEB engineering proof on exact baseline44ff. Existing production contracts remain unchanged.

## 交付物清单（Scope-lock）
Expected new files:11; existing modified files:0. Contract module≤480 lines; other new source modules≤450 each (DEB≤300), collector tests≤460, other tests≤450 each, workflow≤220, specifications≤200 each. No automatic path expansion.

## 任务列表
- [x] 1.1 Read source/contracts and refresh exact baseline graph
  - **证据块**: release_dependency_contract.py:196 returns installed_desktop_bytes_verified=False; rc_packages.py:75 prepares packages without compiler input proof
  - Files: no production edit; fresh exact44ff graph analyzed, reused helper impacts LOW, trust-boundary review HIGH
  - Requirements FR-1,FR-5; design Production invocation/Trust
- [x] 1.2 Write finite requirements/design/tasks and pass specification gate
  - **证据块**: AGENTS.md requires start_feature/check_spec/impact before implementation; project-context/how-to-develop.md fixes scoped workflow
  - Files: requirements.md,design.md,tasks.md, each≤200
  - Requirements FR-1..FR-5; design entire scope
- [x] 2.1 Implement exact producer/consumer contract with source and audit retention
  - **证据块**: verify_glib_backport.py:115 verifies official exact source; :190 verifies metadata; :236 retains original advisory
  - Files: desktop_glib_build_evidence.py≤450 and desktop_glib_build_contract.py≤480
  - Requirements FR-1,FR-2,FR-4,FR-5; design Production invocation/Data model
- [x] 2.2 Implement pipelined compiler-input capture with faithful process boundary
  - **证据块**: pinned Cargo797e8a9 compiler/mod.rs:1957 selects rmeta for intermediate compiles; :629 uplifts binary outputs
  - Files: desktop_glib_link.py≤450; desktop_glib_link_tests.py≤450
  - Requirements FR-2,FR-5; design Compiler-input lineage/Copies
- [x] 2.3 Implement bounded DEB/ELF exact transformation checker
  - **证据块**: pinned Tauri8909f221 bundle.rs:36 replaces first UNK; debian.rs:94 emits three ar members; :161 derives Package from product name
  - Files: desktop_glib_deb.py≤300; desktop_glib_deb_tests.py≤450
  - Requirements FR-3,FR-5; design DEB/Resource bounds
- [x] 2.4 Implement additive engineering workflow and contract regressions
  - **证据块**: final-rc-packages.yml:287 invokes actual Tauri; existing validators retain false installed/release flags
  - Files: issue85-desktop-glib-deb.yml≤220; desktop_glib_build_evidence_tests.py≤460
  - Requirements FR-1..FR-5; design CI/Tests
- [x] 3.1 Verify all rejection cases, unchanged regressions and exact scope
  - **证据块**: existing baseline local tests343 pass (source39/dependency35/package3/exact-build22/consumer244), zero skips; no native-build claim
  - Files: new test files only; run static checks and fresh staged detect_changes before commit
  - Requirements FR-1..FR-5; design Test strategy
- [ ] 3.2 Review exact candidate before any remote write or live CI
  - **证据块**: design acceptance alone does not approve code/publication
  - Files: no extra paths; review staged source/digests/trigger inventory
  - Requirements FR-4,FR-5; design Trust
- [ ] 3.3 Run actual native engineering build and independent replay after approval
  - **证据块**: mocks and source tests cannot prove real emitted ELF/DEB relationship
  - Files: reviewed workflow only; capture successful exact-source jobs/raw ZIPs plus actual-byte mutation rejections
  - Requirements FR-2,FR-3,FR-4; design CI/Test strategy

## 检查点
Specifications pass before implementation. Exact candidate review precedes remote writes. Full evidence audit precedes scoped completion. No automatic merge or wider release acceptance.

## 需求覆盖矩阵
FR-1:1.1,1.2,2.1,2.4,3.1; FR-2:2.1,2.2,2.4,3.1,3.3; FR-3:2.3,2.4,3.1,3.3; FR-4:2.1,2.4,3.2,3.3; FR-5:all steps.

## 文件变更清单
The eleven exact paths listed in design.md are the entire scope. Four source modules, three test modules, one workflow and three specification files. Every existing tracked path remains byte-identical to baseline.
