# Design: authentic FINAL packaging admission

## 概述
FR-1 through FR-7 extend one existing read-only admission boundary at M08bd1c79d3394321578444a2d2722c2bf9e8eb1d/tree6b3a3f98a2a6d24ef5033ca0c1a648f7928182a8. This is metadata authentication, with global release eligibility still blocked.

## 技术方案与 API
Keep authenticate_integration(api, selection, *, check_active, deadline), its one-gate private report, canonical rc-full-integration-v1 bytes and26-request sequence. Parameterize private source/evidence helpers by two fixed roles: integration subject.runs[1]/job_ids[1], FINAL subject.runs[0]/job_ids[0]. No caller selects roles or injects a transport. Each authenticates its own ref and fixed workflow blob; equality of refs is neither required nor assumed. (FR-1, FR-3)

New authenticate_packaging uses one concrete GitHub owner, identical frozen Selection, one validated deadline min(caller, monotonic+300), one _Reads and one _ObservedAPI. Order: both source projections; evidence pass1 for integration/FINAL; pass2 for each and exact comparison; newest/current for each; both source projections again; canonical digest checks; final cancellation/deadline check. Each FINAL observation uses strict(final=True), fixed active final-rc-packages.yml and FINAL_JOBS. This retains bounded non-atomic semantics and catches integration changes during FINAL. No per-gate timeout reset or cached authority. (FR-1 through FR-4)

FINAL digest schema rc-final-packaging-v1 contains gate_id, exact SourceIdentity/InvocationIdentity, observed repository/ref/commit/tree-chain/workflow blob and strict run/sorted jobs. Incidental repository fields and job order are excluded consistently. Source version is a selected binding, not independent version approval. The new immutable private aggregate passes exactly two rows while status/approval/visibility stay blocked/false/unknown. wire._authenticate changes only the authenticator target, retaining all-gate/visibility checks and every direct mutation fence. No staging occurs. (FR-3, FR-5)

## 数据模型与所有权
No persistent state, filesystem staging, transferable authority or new production caller flags. Existing Selection and PublicationSubject remain byte-identical contracts. The report carries only the two verified digest bindings and the unchanged globally blocked projection. Existing consumer/stage/archive ownership remains separate. (FR-3, FR-5)

## 兼容测试夹具
At the end of IntegrationTLS.__init__, a local import calls add_final(self) from the new final-case module. This extends data only, after integration initialization; preserve integration fields/reference_digest/expected_paths and append the FINAL workflow blob after the original entry. Set final_* data and packaging_paths without import-time fixture construction. Every existing integration-negative aggregate call has a complete FINAL baseline. Direct integration tests retain their original trace. Four production-boundary tests, executor entry and policy assertion receive reviewed two-gate extensions with unchanged IDs. The anti-masking case asserts each intended mutated integration endpoint was consumed. (FR-5, FR-7)

## 历史源组合
New profile dispatches from integration.select before its topology handler. Grammar is D[M], I[M,D], J[R,I]; M has exact ordered parents c2b5afb2c46318e2c54283f8442d5996e55f0a73,c0d04e87de6d00f5d1117dd817c0e16654a6b9ba,1752 entries. R=e2e011f7f2a3a1df838bbd588106205b999db610 and four exact R documents are unchanged. New candidate has1758 entries,6 additions/9 replacements. Every other entry matches M. Fresh historical M validation,14 nonself source pins, exact modes/digests/size/lines and real delta budgets are mandatory. Profile self bytes are bound by independent complete-tree review. Content/inverse/budget/history errors are terminal, including selected callback TopologyError. (FR-6)

New final.normalize reverses only exact sealed replacement bytes to complete M; exact M and five enumerated older blob/SHA pairs are passthrough. It has no I/O or mutable cache. integration.normalize calls it first; older adapters remain unchanged. Six old integration composition methods wrap only historical source operands. Candidate content reads remain raw. All old assertions survive after exact inverse, except enumerated intentional two-gate assertions. (FR-6, FR-7)

## 文件结构与行数预算
Exactly15 paths, aggregate additions+deletions at most2000. Pairs below are final lines/delta ceiling; all modules at most500.
- scripts/rc_publication_admission.py 300/230; scripts/rc_publication_github.py 486/4; scripts/rc_release_policy.py 195/60
- scripts/rc_publication_admission_cases.py 430/100; scripts/rc_publication_executor_cases.py 308/4; scripts/rc_pretag_policy_tests.py 256/8
- scripts/rc_pretag_integration_admission_profile.py 350/6; scripts/rc_pretag_integration_admission_cases.py 360/32
- .github/workflows/issue88-publication-executor.yml 105/36
- New scripts/rc_publication_final_admission_cases.py 480/480
- New scripts/rc_pretag_final_admission_profile.py and scripts/rc_pretag_final_admission_cases.py each400/400
- New requirements/design/tasks here:45/45,80/80,60/60

## 测试策略
Preserve original1268 digest bb3590b82c95b989e9a7e4ce90b2ca139568a05a5240409036f86767d90e83dd and strict303 digest0ecc366c2018a6a1e20d3f59ed9ca66645d9334324cd517682894cabde923125. New36 digest d8b43ffb2a0e1168285244bc11b85bb56cc41d357900cd29ead095021dc10b9a:24 final TLS/aggregate cases and12 composition cases. Runtime subcases cover exact positive shapes, all identity/ref/workflow/run/job mismatches, newer all-status shadowing, pagination/parser limits, both-pass drift, cancellation/deadline accumulation, no authority/cache/staging/mutation and legacy negative causality. Composition covers exact grammar/pins/inverses/budgets/terminal failures/full inventories/protected sources. (FR-1 through FR-7)

Existing Ubuntu22/24 workflow runs old48+integration36+final36=120, keeping events, permissions, pinned actions, Python3.12, timeout30 and before/after complete source checks. Full required D1304/I965/J965 coverage may reuse exact hosted subsets only after source/command/setup/ID joins; mixed coverage is explicitly labeled. Strict303/contracts755/consumer452 hosted gates remain required. Focused/source review precedes draft publication; independent CI and remaining local checks may run in parallel, all before integration. No native build is needed for unchanged native bytes. Synthetic results confer no actual FINAL acceptance.

## 风险评估与设计决策
Normalization is CRITICAL (33 direct callers/65 symbols/10 flows), dispatch HIGH (3/9/3); root manual acknowledgment and independent nine-whole-byte inverse review are required. FTS is unavailable; fresh exact-M graph impact and AST/source review remain recorded. The shared observer preserves finite existing contracts rather than introducing a verifier registry. Complete TLS baseline prevents wrong-cause negatives. Source-specific test evidence and a private durable checkpoint preserve recovery provenance. (FR-6, FR-7)

## 不涉及的发布条件
No live write/tag/main/credential/protection change. Remaining artifact/native/security/ownership/version/manifest/remote tag-race gates, caller-report authentication, PR98 cancelled payload and snapshot implementation hold remain unchanged. No fixture or engineering run is promoted to final RC admission.
