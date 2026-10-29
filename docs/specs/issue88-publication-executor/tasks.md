# Tasks: bounded publication executor

## 交付物清单
Thirteen additions and one four-line replacement across14paths; aggregate<=3400 and no module>500 lines. Existing core, consumer, policy, eligibility, native/lock/security and held source bytes remain unchanged. No source edit begins before exact boundary review, impact acknowledgment and spec gate.

## 任务列表
- [ ] Freeze exact M source and impacts, then resolve independent admission/ownership/HTTP/dispatch review
  - Evidence: rc_release_policy.py:42 requires verifier=='unimplemented'; rc_release_eligibility.py:95 accepts blocked only
  - Files: three specs requirements<=50/design<=90/tasks<=60; FR-1, FR-7, FR-8; Design: Production admission/Finite composition
- [ ] Implement owned exact receipt/archive staging and six retained nofollow streams
  - Evidence: rc_artifact_consumer.py:117 regenerates verified_at; :178 consume owns and closes ExitStacks; rc_consumer_io.py:153 PrivateRoot owns its descriptor
  - Files: rc_publication_stage.py<=300, stage_cases.py<=350; FR-3, FR-4; Design: Exact receipts and staging
- [ ] Implement fixed HTTPS operations with bounded protocol parsing and streamed bytes
  - Evidence: rc_publication_contract.py:15 defines seven operation kinds; :240 OperationResult distinguishes none/confirmed/unknown
  - Files: rc_publication_github.py<=500, github_cases.py<=450, https_fixture.py<=300; FR-1, FR-5, FR-6; Design: Closed HTTP contract
- [ ] Connect unchanged core to one owned session and real protocol tests
  - Evidence: rc_publication_contract.py:383 start, :391 advance and :452 request_publish own the existing sequence
  - Files: rc_publication_executor.py<=300, executor_cases.py<=350; FR-1, FR-2, FR-6; Design: Session and outcomes
- [ ] Admit exact finite source and read-only CI without broad ancestry or stale pin acceptance
  - Evidence: rc_pretag_yoke_repair_profile.py:139 select delegates only topology mismatch; unchanged historical content is terminal
  - Files: new publisher profile<=220/cases<=300/workflow<=100; yoke profile<=160/four-line delta; FR-7, FR-8; Design: Finite composition/Tests
- [ ] Freeze actual source pins, all48 IDs and external full-tree manifest; validate every negative and required context
  - Evidence: existing1184/strict303 inventory and frozen new48; retain source-before/after and zero skips
  - Files: same listed14 only; FR-1 through FR-8; Design: Tests
- [ ] Complete actual-source independent review, staged GitNexus detect_changes, Probe review/gencommit and source-bound CI before normal integration
  - Evidence: exact remote commit/tree/parents, D1232/I893/J893 and existing303/755/452 plus new48 on both Ubuntu rows
  - Files: no additional source; FR-7, FR-8; Design: Risks and limits

## 需求覆盖矩阵
FR-1: blocked real entry and direct mutation callbacks; no caller-enabled authority; fixed unavailable authenticators patched only by tests.
FR-2: exact25 trace, pause/request, duplicate/reentrant/order, idle close and non-resume.
FR-3: exact selected run/job/artifact/archive, original JSON bytes/clock, six/checksum and no ambient reselect.
FR-4: nofollow retained handles, replacement/link/inventory/in-place drift, every closure path.
FR-5: exact methods/headers/bodies, pagination, JSON/types/limits, direct/redirect/anonymous/TLS and stable/latest identities.
FR-6: before/after dispatch cancellation, owner scope,502/lost/truncated/mismatched replies and cleanup outcomes.
FR-7: M identity/history, D/I/J/overlay, path/mode/pin/cap/inverse, terminal failures and fresh candidate validation.
FR-8: exact unchanged inventories, new48, read-only workflow and all context gates.

## 文件变更清单
scripts/rc_publication_{executor,github,stage,executor_cases,github_cases,stage_cases,https_fixture}.py
scripts/rc_pretag_publisher_executor_{profile,cases}.py
scripts/rc_pretag_yoke_repair_profile.py (exact four-line addition)
.github/workflows/issue88-publication-executor.yml
docs/specs/issue88-publication-executor/{requirements,design,tasks}.md

## 检查点
Pre-edit: exact review/spec/impact; pre-publication: focused48/actual source review/pins/detect_changes/gencommit; pre-integration: all context/hosted gates. Preserve any failed/interrupted evidence with source scope. Final component convergence does not close RC admission, Windows, snapshot, PR98 hold or authorize live publication.
