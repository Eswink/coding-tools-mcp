# Requirements: Issue88 metadata-only pre-tag collection

## 功能概述 — purpose and stage

This specification governs the root-approved local implementation and its later reviewed engineering diagnostic. It does not grant publication, collection-result authenticity or release approval. Baseline: published PR97 `1dfe6b0f3aff7c51e90fcd624b838948e518800c`, tree `0d251466e935e4689f7350d6be56a8caad86f512`. The historical local commit `ef629f6d7a4f56a5d22d02b484d2b967ab235790` shares that tree but is not the published commit. The original independent pre-edit Plan is converged. Implementation continues in its separate scoped Plan; publication and hosted evidence require final review.

This implementation collects bounded GitHub repository/source/workflow/run/current-attempt job and PR36 review metadata through fixed-origin TLS GET requests with an existing read-only bearer credential. No new credential, persistent grant or permission change is included. The new result is a metadata observation receipt, never `PreTagEvidenceReceipt`, `TrustedProducer`, release admission or evidence finalization.

## Scope

- Fixed repository `Eswink/coding-tools-mcp`, numeric ID1360355522, GitHub.com REST origin only
- Immutable expected source SHA/tree; expected RC version remains an expectation until separately verified
- Fixed integration and FINAL workflow inventory plus observation of the expected pretag workflow's presence
- Fixed PR36 identity/head/base/merge metadata, reviews and bounded commits; no reviewer entitlement or policy approval inference
- Complete bounded lists, newest run across all statuses, current-attempt jobs, strict source identity and second full observation pass
- Sanitized deterministic metadata receipts and hermetic adversarial tests; retained contract/consumer/original regressions with one exact reviewed historical scope-test correction

Excluded: FINAL/artifact ZIP or log bytes; artifacts/storage endpoints; redirects; storage-host allowlist; consumer/controller/tag/Release/publication operations; mutating APIs; local source extraction, shell/arbitrary external-command or candidate-code execution (the later diagnostic runner permits only its exact read-only Git identity probes); production/native/security/runtime modifications; source assembly; snapshots/Issue86; cancelled procfs work; held transport; canonical/main integration; unreviewed collection workflow activation; existing fixture workflow edits; release version selection.

## 需求列表

#### FR-1: Preserve authority separation

1. Every result SHALL have `evidence_authentication=unverified`, `eligibility_status=blocked`, `authenticating_producer_unimplemented`, `artifact_bytes_verified=false`, `finalized=false`, `release_approved=false`, `publish_approved=false`, `snapshot_atomic=false`
2. All required `rc_release_policy.GATE_IDS` SHALL remain visible and blocked/unknown; metadata observations SHALL not promote any gate to passed
3. Existing pure contracts, enums, guards, source/tag requirements and success-only run/job schemas SHALL remain byte-identical
4. A failed/missing/pending FINAL, denied review or absent collector workflow SHALL be representable without manufacturing a valid PreTagCandidate or an old successful receipt
5. Metadata observed through an authenticated request channel SHALL not imply caller principal/permission proof, draft visibility, reviewer entitlement, workflow execution provenance or portable receipt authentication

### FR-2: Restrict HTTP and inputs

1. The adapter SHALL offer typed allowlisted operations, not a public arbitrary suffix/URL/method interface; method GET, fixed origin/repository, pinned API version, no redirects/proxies/alternate origin/public fallback/retry
2. Numeric IDs SHALL be strict positive integers; SHA/tree digests lower-case40 hex; branch expectations match the explicit narrow grammar; fixed PR number36 cannot be overridden
3. Credential SHALL come only from an existing caller-provided token at invocation, remain in memory/header, never appear in CLI/process arguments, receipts, errors, hashes or logs; in-memory library arguments and private pipe transport are the only transfer routes; missing/invalid-header token blocks before networking
4. Enforce response/request/time/JSON limits and reject malformed, oversized, duplicate-key, nonfinite, deeply nested or unexpected JSON shapes with fixed diagnostic codes
5. HTTP401/403/404/429, 5xx, timeout, TLS/close failure or unexpected3xx SHALL produce sanitized failed/unknown observations, no broadened read or retry

### FR-3: Bind source and workflow identity

1. Repository GET SHALL establish exact numeric ID/name; source commit GET SHALL bind expected SHA to expected tree; nonrecursive tree traversal SHALL establish exact ordinary-file workflow blob identities at that tree
2. Workflow metadata SHALL bind its ID/path to the fixed expected path; immutable workflow-file identity and run-reported source SHALL remain separate fields
3. Missing/truncated/denied trees or missing workflow SHALL block that observation; API404 alone SHALL never prove tag/Release absence, which is unobserved in this slice
4. Expected version, local clean-tree status, frozen reviewed manifest, real pretag invocation, main integration and GITHUB_WORKFLOW_SHA SHALL remain unverified; no value is synthesized from branch naming

### FR-4: Complete newest-run and attempt observation

1. Counted Actions lists SHALL exhaust exact total_count within100/page and10pages, rejecting duplicate IDs, count changes, overflows, short nonterminal pages or1000-result search boundary
2. Select newest exact-source workflow run across ALL statuses; never filter success/event/branch before newest selection or fall back to older green
3. Bind run repository/head repository IDs, source SHA, workflow ID/path, event/ref fields and current attempt; no rejected newest item may be silently removed
4. Preserve pending/in-progress/failed/cancelled/skipped conclusions and nullable timestamps honestly. FINAL attempt other than1 remains blocked; integration reruns may be observed but never admitted
5. Read only `/attempts/{current_attempt}/jobs`; preserve each job ID/run/attempt/source/name/state. Compare exact seven/thirteen expected names, reporting missing/unexpected/duplicate names without treating partial current execution as success
6. Missing run_attempt or source fields SHALL remain unverifiable, not be synthesized merely from the request URL

### FR-5: Complete reviews without approval inference

1. PR36, its complete review list and commit list SHALL bind exact repository, PR head/base/merge state, review ID/reviewer ID/state/commit/submission time and commit SHA inventory
2. Bare-array APIs SHALL use independent locally constructed numbered pages, strict terminal evidence and complete second pass; never apply total_count pagination to arrays or follow their URLs
3. PR commit count SHALL equal observed distinct SHAs and be below250; the documented250-commit cap blocks without fallback to a broader endpoint
4. Preserve stale, dismissed, changes-requested, pending and unknown states. Chronological review records or `author_association` SHALL never become reviewer authority or independent exact-tree approval
5. Do not infer real merge from `merge_commit_sha` while unmerged, equate PR head/merge SHA, or treat branch/PR labels/comments as release evidence

### FR-6: Revalidate and retain truthful bounded observations

1. Collect one bounded pass A, then reread repository/ref, workflow IDs, full run lists, selected runs/current attempts/jobs and PR/review/commit inventories in pass B; compare sanitized full identity/state inventories, not only selected IDs
2. Any changed, missing or inaccessible second observation SHALL set `collection_status=blocked`, preserve fixed reasons, and never trigger an automatic third pass; partial facts may remain explicitly partial
3. Two equal observations SHALL establish only a non-atomic bounded stable observation; receipt cannot be reused as authentication or future admission
4. Retain only strict allowlisted fields, numeric IDs, fixed labels, timestamps and domain-separated hashes of sanitized data. Discard raw bodies/headers/Link URLs/review bodies/commit messages/emails/credential material
5. Oversized output blocks rather than truncating evidence or dropping a policy row

## 非功能需求 / acceptance

- A concrete real GET adapter is required in this increment, not an unspecified callback/capability or another schema-only layer. One fixed interpreter-child/standalone collector-local standard-library network worker is permitted solely to bound blocking DNS/connect/TLS/headers/body/close; no shell, target-source execution or production runtime change
- Standard-library Python; each new Python module below500 lines; no modifications to root dependencies
- Maximum1MiB per response,16MiB aggregate body bytes,128requests,120seconds collection plus at most5seconds mandatory teardown (no completed receipt if teardown is uncertain),10seconds absolute per request, strict JSON depth16/object128/array1000/key512/value-string65536; retained identity/text512 or stricter, token4096; receipt at most256KiB
- All53 pretag +159 consumer +135 publication +208 original tests must execute on the actual candidate with zero failures/errors/skips/expectedFailures/unexpectedSuccesses. The one publication compatibility method is pinned to blob85627ca59cc6b7d700af30867c1e7aa0c8fb547f; all other1627 predecessor blobs/modes remain unchanged. The earlier134/135 candidate failure and exact historicalPR97 pass remain historical evidence, never substitutes for this gate
- Independent pre-edit review, checked specifications, exact source/index validation; later implementation requires fresh code review, staged GitNexus detector, gencommit and exact-source local/hosted verification
- Local implementation is approved; source commit, push, PR and CI activation remain subject to final reviewed gates. After implementation and exact-code review, this increment must demonstrate one actual same-repository GET metadata observation through a narrow reviewed test/CI entry, still fully release-blocked

## 依赖关系

Unchanged PR97 pure data contracts and job/policy constants; Python standard library. Complete producer bytes, genuine pretag invocation, source versions, review authority and security acceptance remain unimplemented downstream requirements. The diagnostic workflow implements only a separately reviewed metadata read.

## Current exact source contract

The candidate has exactly16 additions listed in design.md,1627 immutable PR97 predecessor blobs/modes, and only the historical scope-test replacement at Git blob `85627ca59cc6b7d700af30867c1e7aa0c8fb547f` (SHA256 `9871085d72ae4a805f307abda64888fe1657d05cf10d1e82ded675cb5b9b065a`). It must have the exact published PR97 sole parent and bind its candidate tree, ordinary100644 paths and actual working bytes. Reject missing/extra files, modified predecessors, wrong pin/mode, symlink/submodule, wrong parent/tree, intermediate or extra-parent histories and dirty source. Prospective index evidence must remain distinct from a committed source.

The preserved historical70aa/18-path fallback is selected only by successful verified absence of the source gate in both tracked index and tree. Query errors fail. Candidate evaluation executes only previously hash-verified gate bytes in a private fresh namespace. No skip, owner waiver, expected failure or synthetic placeholder satisfies the real candidate gate. Earlier13/15-path approvals, original134/135 failure and historical135 pass are retained in the engineering evidence chronology; this current16-path contract supersedes those intermediate scope counts.

## Reviewed completion protocol — 2026-10-03 14:55UTC

Keep the same16 additions and the same exact old guard85627ca5. Root approved readable caps of230lines for the entry and180 for the workflow, within the repository500-line limit, rather than adding another runtime file. Failure never deletes, overwrites, repairs or retries uncertain output. Write exclusive ordinary payload files, then a bounded name/size/SHA256 manifest to an exclusive pending file; flush/fsync/confirmclose before no-overwrite hard-link creation of completion.json. Never mutate the pending file after linking. Link count2 is allowed only for this known pending/completion pair, never payload files. No atomic multi-file snapshot or approval is claimed.

Acceptance requires successful collect-step outcome, final marker and exact manifest/file byte hashes. Incomplete/partial/collision/late-close errors fail even if local residue exists. Failure artifacts retain only explicit bootstrap/fixed-error filenames; success retains only the fixed payload+completion list, without globs. All published-state/approval flags remainfalse and evidenceunverified. Fixture count gates require failures/errors/skips/expectedFailures/unexpectedSuccesses allzero and exactloaded/executed counts. Add latewrite/close/partialmanifest/link/collision/history-preservation and xfail/unexpected-success rejection tests; independent review precedes publication.
