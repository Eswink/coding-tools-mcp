# Tasks: bounded pretag metadata implementation

## 交付物清单 — current scope and stopping condition

Implement the16 additions in design.md plus only the exact pinned historical scope-test replacement. All1627 other PR97 predecessor blobs/modes stay unchanged. Local implementation is approved; publication requires final source, tests, staged graph, full diff, independent review, gencommit and root approval. Hosted execution must bind the actual source/run/attempt/job/artifact before it is claimed. Release eligibility remains blocked throughout.

## 任务列表 — completed pre-edit work

- [x] T1: Resume PR97 and separate design Plans; confirm baseline and duplicate/active PR ownership
- [x] T2: Create exact published PR97 worktree; read AGENTS/Probe/context and preserve source identity
- [x] T3: Build isolated GitNexus1.6.9 index offline, validate UIDs/source and report HIGH/CRITICAL dependencies
- [x] T4: Write the bounded source/network/receipt design and adversarial matrix
- [x] T5: Check specs and resolve independent pre-edit review
- [x] T6: Hand off the checked finite packet; obtain scoped local implementation approval

## Implementation tasks

- [x] I1: Start/resume the separate implementation Plan with root-reviewed scope amendments and current impacts
- [x] I2: Implement immutable metadata types, real GET fixed-route API and bounded standalone worker
- [x] I3: Implement source/newest-attempt/review/revalidation logic and adversarial fixtures
- [x] I4: Implement exact parent/tree/index/working-byte source gate and one pinned compatible historical assertion; preserve earlier failure evidence
- [ ] I5: Finish completion-protocol/strict-test-accounting review corrections, then run every actual-source test group with exact counts and zero nonpass outcomes; run byte/mode/static/compile checks
- [ ] I6: Obtain independent exact final code review, current full staged graph detector, architecture validate/drift, Probe review/gencommit, exact tree and root publication review
- [ ] I7: After separately authorized publication, verify exact remote commit and real readonly GET diagnostic source/run/attempt/job/artifact. Missing integration/FINAL/pretag facts remain explicit blocked negatives; fixtures do not prove hosted execution or release acceptance

## 需求覆盖矩阵 — adversarial test matrix

Each row is required behavior, not a claimed test count or executed test.

| Group | Cases and required result | FR |
|---|---|---|
| Schema/authority | Roundtrip exact receipt; duplicate/missing/extra fields; bool-as-ID; oversized/nonfinite JSON; attempts to set authenticated/approved/finalized/atomic true; no fake PreTagCandidate/TrustedProducer; every GATE_ID blocked |1,6|
| Source | Wrong repo/name/ID/head repository; wrong commit/tree/ref/intermediate-tree response/ref object; moved ref; truncated/missing trees; duplicate tree names; symlink/workflow mode; absent pretag file; wrong workflow ID/path/blob; expected version never upgraded |2,3|
| Network | All nonallowlisted method/routes rejected before transport; query/path/userinfo/percent/fragment/CRLF injection; all3xx including same origin; malicious Link; proxy ignored; TLS failure;401/403/404/429/5xx; close/read failure; no retry/public fallback; raw error/token sentinels absent from output |2|
| Worker | Real stdlib adapter under synthetic wire; DNS/connect/TLS/header/body drip/close stall deadlines; timeout/cancel/IPC corruption/worker crash/terminate failure; no surviving child/socket or completed receipt on unproved teardown; actual GET smoke after review |2,6|
| Bounds | Per-response/aggregate bytes, request count, total/per-request time, depth/object/array/string/integer limits and output cap; exact-boundary behavior; passB budget reservation; no evidence truncation |2,6|
| Counted pages | Zero/one/full/multipage sets; duplicate IDs within/across pages; count changes/overflow; short nonterminal; missing total; max1000 filtered runs; malformed shape; disagreeing second-pass inventory |4,6|
| Newest | Older success plus newer pending/failed/cancelled; newest unsupported event/ref/path; duplicate run_number; conflicting time order; all-states selection; no caller run-ID bypass; list/direct mismatch |4|
| Attempts/jobs | FINAL attempt2, integration attempt3; rerun changes mid-pass; missing run_attempt; wrong source/run/attempt/job ID; exact7/13 names; missing/extra/duplicate names; skipped/in-progress jobs; nullable prestart/end times |4,6|
| Bare arrays | Reviews/commits vs counted-envelope confusion; terminal short/empty page; exactly full boundary; missing/contradictory/cross-origin Link; duplicate reviewID/SHA; review count cap; PR commit count mismatch and249/250/>250 cap; complete second pass |5,6|
| Review truth | Stale commit, dismissed/changes_requested/pending/unknown; multiple reviews same user; public200 without entitlement proof; author association spoof; wrong PR/repo/head/base; unmerged merge_commit_sha; source changes and dismissal between passes |1,5,6|
| Revalidation | Newer run, selected rerun, job completion/change, source/ref/tree/workflow/PR/review mutations; deleted/inaccessible second read; budget exhausted; original fact retained as partial with blocked status; no third attempt to get green |6|
| Compatibility | Retained53/159/135/208 suites with only the pinned historical scope-method correction; pure successful-subset equivalence with old schema/helpers; old no-tag candidate failure retained; old evaluate always blocked; AST deny consumer transport/artifacts/mutators/shell/external execution and library environment/file IO; permit only the fixed reviewed standalone interpreter/worker launch path |1,2|

## Evidence blocks and impact policy

- `rc_pretag_types.SourceIdentity/parse_json/encode`: exact-source graph/AST identities in external graph packet. Existing codecs are reused unchanged; CRITICAL reuse dependencies must not be casually extended
- `rc_pretag_evidence.SelectedRunObservation/PreTagEvidenceReceipt`: success-only, unverified receipts; create separate negative-capable metadata schema
- `rc_release_eligibility.evaluate`: always blocked; HIGH dependency, no edit
- `rc_consumer_snapshot.resolve_candidate`: requires existing lightweight tag; HIGH dependency, no reuse as pretag controller
- `release_tag_gate.GitHub.get/paginate/latest_run/successful_run`: dictionary-only and completed-success helper assumptions; references only, no extraction or contract change
- API documentation: PR commits cap250 and array shape differ from Actions count envelopes; review capability/provenance remains unproved

## Verification accounting

Current final acceptance requires actual candidate53 pretag,159 consumer,135 publication,208 original and all new tests; each must have exact loaded/executed counts and zero failures, errors, skipped, expectedFailures and unexpectedSuccesses. Record source hashes before/after. Earlier134/135 candidate failure and historicalPR97 135 pass remain separately labelled in the engineering evidence; neither substitutes for the current candidate. Intermediate partial runs never imply aggregate green. Real GET and hosted checks are pending until explicitly executed after review.

## Rollback and handoff

No merge/canonical/tag/Release/source-assembly operation is included. Keep this Plan separate from held transport, Issue86 and cancelled procfs work. Final local handoff includes the exact source/tree, complete test counts and hashes, graph risks/limitations, independent review and pending hosted prerequisites. Rollback affects only the16 additions and pinned scope-method correction.

## 文件变更清单

Exactly the16 new paths in design.md and scripts/rc_publication_boundary_tests.py at blob85627ca59cc6b7d700af30867c1e7aa0c8fb547f. No other old path, file-map count or guard pin may change without precise review.

Requirement coverage: FR-1 -> I2/I5; FR-2 -> I2/I5; FR-3 -> I3/I4/I5; FR-4 -> I3/I5; FR-5 -> I3/I5; FR-6 -> I3/I5/I7. I6 reviews the entire implementation and evidence boundary.

## Completion and error-output protocol

Entry<=230 lines, workflow<=180, each Python module<500. Exclusive ordinary payloads precede a bounded exclusive pending manifest. Confirm flush/fsync/close before a no-overwrite hard link to completion.json; keep the pending bytes immutable. Linkcount2 is allowed only for this known pair. Never delete, overwrite, repair or retry uncertain files. No atomic multi-file snapshot is claimed.

A successful collect step, final completion marker and exact manifest byte-hash set are all required. Failure/collision/late-close/incomplete output rejects even when local residue exists. Failure artifacts upload only explicit bootstrap/fixed-error names; success uses the fixed payload+completion allowlist. Test partial write/close/fsync/link/collision/marker absence/history preservation and expectedFailure/unexpectedSuccess rejection. Independent review precedes publication.
