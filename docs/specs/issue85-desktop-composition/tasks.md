# 任务清单：issue85-desktop-composition

## 概述
Implement only the independently reviewed versioned engineering profile015df7e8ec44b675e65d874123f5350b0bab93349cfc3a5165a1d1f35d6e87bb. Preserve immutable S proof and all historical gates. Completion evidence is maintained externally so finalized acyclic pins stay stable.

## 交付物清单（Scope-lock）
Exactly one modified path and five new paths: composition adapter≤500total/40delta; new desktop profile≤360; new20-test module≤400; three specs≤80each. Total amendment≤1100. No workflow/runtime/dependency/version/policy or desktop13 edits.

## 任务列表
- [x] 1.1 Read current source, frozen profile and real failure evidence
  - **证据块**: ownership._pure rejects nonpure_chain at S/F0; selected_profile(X) accepts1632entries; after fixture fetch147tests contain146pass/one real profile failure
  - Requirements FR-1,FR-2; design Identity and topology
- [x] 1.2 Obtain separate finite design/root scope approval
  - **证据块**: exact015df7e8 proposal accepted; OptionA explicitly permits new-source automatic native CI, with later exact publication/merge gates
  - Requirements FR-1..FR-6; design all sections
- [ ] 1.3 Refresh exact-source graph, finalize specs, pass check_spec and estimate
  - **证据块**: AGENTS requires fresh impact before edited symbols; committed graph snapshot is historical
  - Files: only three specifications; Requirements FR-1,FR-4; design Risks
- [ ] 2.1 Implement closed desktop profile and explicit legacy dispatch
  - **证据块**: legacy topology/content/pins remain unchanged; X/S/R and the13 desktop entries are independently fixed
  - Files: rc_pretag_desktop_profile.py≤360; Requirements FR-1..FR-4
- [ ] 2.2 Add20 exact adversarial cases and bounded composition adapter
  - **证据块**: current run_inventory compares loaded/executed Counters and disallows skipped/xfail/xpass outcomes
  - Files: rc_pretag_desktop_tests.py≤400; rc_pretag_composition_tests.py≤500/40delta; Requirements FR-1,FR-3,FR-5
- [ ] 2.3 Finalize five acyclic amendment pins and external exact review lock
  - **证据块**: the profile's own bytes cannot contain their final hash; external reviewed source identity is mandatory
  - Files: no extra source path; Requirements FR-4; design Content and trust bootstrap
- [ ] 3.1 Run exact P/F/L all-hermetic matrix and independent source review
  - **证据块**: same-tree malformed parents must reject before content; valid-parent mutated bytes must reject after topology
  - Files: no extra paths; Requirements FR-1..FR-5; design Verification matrix
- [ ] 3.2 Publish only the approved new P and audit its fresh native artifacts
  - **证据块**: unchanged native workflow matches current ci branch without a path filter; S's receipt cannot certify P
  - Files: no workflow change; Requirements FR-6; design CI
- [ ] 3.3 Obtain final root merge gate and verify actual integration identities/checks
  - **证据块**: GitHub mergeable is not composition acceptance; actual future R-synthetic identity may differ from local projection
  - Requirements FR-2,FR-4,FR-5,FR-6; design CI and Risks

## 检查点
No source edit before design/spec/impact gates. No publication before exact review and P/F/L tests. No merge before root's final decision. Native proof remains source-specific; no global approval flag changes.

## 需求覆盖矩阵
FR-1:1.1,1.2,1.3,2.1,2.2,3.1; FR-2:1.1,2.1,3.1,3.3; FR-3:2.1,2.2,3.1; FR-4:1.2,1.3,2.1,2.3,3.1,3.3; FR-5:2.2,3.1,3.3; FR-6:1.2,3.2,3.3.

## 文件变更清单
scripts/rc_pretag_composition_tests.py; scripts/rc_pretag_desktop_profile.py; scripts/rc_pretag_desktop_tests.py; docs/specs/issue85-desktop-composition/{requirements,design,tasks}.md. Every other tracked byte/mode remains unchanged from S.
