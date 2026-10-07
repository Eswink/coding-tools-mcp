# Requirements: authentic full integration admission

## 功能概述
The publisher performs authenticated, exact-source GitHub reads for its seven-job full_integration gate. This is one implemented gate inside a still-blocked publisher; caller reports and prior engineering receipts confer no authority.

## 历史经验与范围边界
Reuse the existing TLS transport, strict run snapshots, newest-run pagination and immutable source composition. Avoid older-green fallback, per-request deadline reset, caller API injection and historical test fixtures built from unrelated current bytes. FINAL, native/runtime acceptance, version/source preparation, remote tag constraints, owner-action authorization and held PR98/snapshot work remain separate.

## 需求列表
### FR-1 Fixed authentic identities (Must)
WHEN admission runs THEN the system SHALL bind repository ID/name, selected source commit/tree, exact ref, fixed active workflow ID/path/source blob, selected current run/attempt/event and all seven successful job IDs using the owning concrete GitHub connection.
### FR-2 Newest complete repeated evidence (Must)
WHEN any newer exact-source run exists THEN selection SHALL use it across all statuses; IF it differs, is incomplete, denied or failed THEN admission SHALL block without older-green fallback. Repeated source/run/attempt/job observations and complete bounded pagination SHALL agree.
### FR-3 Frozen evidence digest (Must)
WHEN authentic observations agree THEN canonical source/invocation/workflow/run/job evidence SHALL hash to the already selected full_integration digest. No report or mismatch SHALL rewrite Selection or grant authority.
### FR-4 One gate with remaining global block (Must)
WHEN the one gate authenticates THEN the private aggregate SHALL report only full_integration as passed and all other gate rows unknown, with globally blocked status, false approvals and non-atomic observation. The unchanged caller-report evaluate function SHALL remain unauthenticated. Only the one policy row SHALL name the fixed verifier.
### FR-5 Actual entry and mutation fences (Must)
WHEN session activation or a direct mutation sink executes THEN the fixed authenticator SHALL perform fresh read-only verification and SHALL block before staging or mutation while other gates are missing. Entry SHALL retain blocked_no_effect and no transition. Every operation SHALL preserve one deadline and cancellation through all reads; failed observations SHALL yield no positive result.
### FR-6 Historical and current source closure (Must)
WHEN source admission executes THEN only D[B], I[B,D] and J[R,I] with exact four R documents SHALL qualify; selected/historical content errors SHALL be terminal. Exact inverse adapters SHALL recover immutable historical bytes without normalizing actual candidate trees or changing old pins.
### FR-7 Real regression coverage (Must)
WHEN validating the increment THEN original1232/strict303 IDs SHALL remain present and new36 SHALL execute without skips. Preserve the policy-test and entry-test IDs while strengthening the specified changed contracts; real TLS cases SHALL use the verified connection fixture without mocked authentication. Hermetic workflow runs SHALL be negative integration fixtures.

## 非功能需求
NFR-1: One maximum300-second monotonic deadline,15-second socket bound,2MiB metadata/32KiB headers, existing ten-page100-row Actions pagination and source-tree response limits; no retry or unbounded search.
NFR-2: Fixed GitHub origin/API/version and endpoints; no credentials in redirects/logs, no caller transport/authority override, no persistent evidence cache or mutation capability expansion.
NFR-3: Existing core, consumer, staging, eligibility, integration workflow and held paths remain byte-identical; every source module remains at most500 lines.

## 依赖关系与验收
Reuse release_tag_gate, rc_consumer_snapshot, rc_publication_stage._bind and HTTPSFixture. Existing real integration and final-release gaps remain explicit; fixture success does not authenticate a real candidate. Independent source review, exact source-bound local/hosted tests and normal repository gates are required before engineering integration.
