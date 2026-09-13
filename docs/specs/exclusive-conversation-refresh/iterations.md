# Iteration evidence

## 01 — Plan, baseline and tool channel

Plan saved first in c2462cf6ee2aee6f3bd3f134dba534bf54f123dd. Validation workflow committed in2d13411e426e3a8048fb4204d6a5b91231741f1a. Unmodified source tree77dc7f47a529c917a891390a9b959ef2b0b8827a (main tree plus docs/workflow) passes both full regression jobs in run34741653492. Ubuntu job103682256996 and Windows job103682257002 have successful frontend and Rust check/test/production-warning steps. These are BASELINE results, not candidate results.

Probe 4.0.1 install: EAI_AGAIN registry.npmjs.org. Local launcher start_feature: missing executable127. Offline GitNexus impact: ENOTCACHED. Manual source/call-chain inspection is a declared downgrade, not successful orchestration/graph output.

## 02–05 — Candidate owner lifecycle and draining

Implemented default-exclusive reservation, no-noise locked errors, scope/local-approval checks, configurable finite lease and admission epoch. Added tests for16 simultaneous contenders,100 foreign requests, pending timeout, stale decisions and unchanged binding after access renewal. Inspection identified that revocation alone must not release a shared workspace with a live process: added DRAINING and durable dirty/recovery fence, restoration of known task namespaces, local cancellation and generation-bound recovery confirmation. Rust execution is pending CI; no PASS claim.

## 06–07 — Candidate global approval UX

Added global modal, authoritative bounded inbox, server invalidations, foreground/background distinction, generic native notice and tray indicator/menu. Kept workspace recovery/revocation UI and removed the conflicting temporary exclusive toggle. Added explicit fingerprint confirmation and countdown. During review, found A->B->A stale settings completion could affect a successor form; added operation sequencing distinct from draft generation.

Local Svelte compiler5.56.4 compiles new components without warnings. Existing frontend124 tests pass before and after initial integration. With7 new policy/presentation tests, local suite131 passes,0 failures/skips. Production component browser test initially cannot navigate localhost: Chromium returns ERR_BLOCKED_BY_ADMINISTRATOR. Do not bypass browser policy; execute this fixture on GitHub Actions instead. No native notification acceptance claimed.

## 08–10 — Candidate refresh and configurable durations

Implemented bounded encrypted refresh families, authenticated opaque refresh tokens, atomic rotation, reuse revocation, family-linked JWT and explicit offline consent. MCP discovery advertises implemented refresh grants; legacy Actions remains authorization-code-only. User settings validate both UI/backend and preserve old profile defaults. Notification dependency pinned2.4.0 requires a reviewed lockfile generated in CI; container has no Rust toolchain/DNS. Test sources cover persisted reopen/corruption/client/resource/scope/replay/race/I/O, plus actual HTTP code->refresh->same-owner and live-process drain. Not executed yet.

## Next gate

Publish exact candidate source, resolve only the new notification dependency, run locked candidate builds and tests on Windows/Ubuntu plus browser/failure-first jobs. Do not merge, publish installers, modify PR #11 or production Nginx while these gates remain open. Every subsequent failure and fix gets a new evidence entry; do not retry until green or replace old release assets.


## 11 — Recovered implemented candidate and preserved CI failure

Recovered candidate 83558bc1e4d6dd009324c6598e52be458ba9948a from the source artifact of run34744014562. Recomputed its Git tree as941b2bcf03c827897eb27301f1d2cf1bf87a6267. The full source regression artifacts show Ubuntu411 and Windows422 Rust tests, plus131 frontend tests on each platform; failed/ignored/skipped counts are zero. The workflow as a whole nevertheless FAILED because the production-component browser job timed out after five successful scenarios. Do not label this candidate completely green.

## 12 — Browser predicate root cause and concurrent upstream fix

A string predicate evaluating to a function is invoked by Playwright. `window.releaseConfirm` and `window.releaseSave` are Promise resolvers; observing them that way unexpectedly resolves the pending operation with JavaScript null and keeps returning a falsey result. The fix observes `typeof ... === "function"` instead. A zero-network blank-page Playwright contract test reproduced the old side effect/timeout and verified zero resolver calls with the fixed predicate. The first diagnostic incorrectly expected undefined; inspection established Python's default arg=None becomes JS null, and the test now checks that exact result.

The remote branch independently advanced to ecf5ca9449a82122f26f2bef3f50ce6d0afd5488 with the same predicate fix. Run34749675645 completed successfully. Downloaded and digest-checked Ubuntu/Windows/browser artifacts confirm411/422 Rust tests,131 frontend tests per platform and10 production-component browser scenarios. These browser scenarios use synthetic IPC, not installed native notification acceptance. The local baseline was aligned without a remote write and its tree matches729b851322fb77d9b587588a6c85872038f67104.

## 13 — Approval queue completion ordering, local red/green

The production `ChatAuthorizationHost::decide` refreshed the inbox while `busy` was still true. The next candidate could not be selected and waited for the five-second fallback. Move successful resynchronization after releasing `busy`; preserve error/disposal/fingerprint/scope behavior. Eight function-level tests extract and execute the actual production function with synthetic IPC. The unmodified upstream function has two exact assertion failures (six successes); the local function passes all eight. This is not a full Svelte DOM test. Two additional production-component browser scenarios cover queue advancement and authoritative empty-inbox dismissal; they require new CI.

## 14 — Pending deadline at the privileged decision lock, local candidate

Code inspection found a time-of-check/time-of-use gap: `decide` only reconciled before reacquiring the decision mutex. A blocked reconciliation or mutex acquisition could cross the90s pending deadline. The mutex-protected decision now refreshes the record at its linearization point, expires/drains it and emits invalidation before rejecting a late approval. Exact profile/request/binding and nonempty requested-scope-subset checks remain. Added three deterministic Rust tests for exact/post-deadline rejection, the just-before-deadline boundary and stale IDs. These new Rust tests have NOT executed in this container or CI.

## 15 — Coherent global inbox and final-workspace deletion, local candidate

The old inbox derived its revision from the maximum per-workspace snapshot. With no workspaces, that became0; the global frontend discards revisions below its last accepted value, leaving an obsolete pending UI. Replace per-profile aggregation with one mutex-protected pending snapshot after external executor reconciliation. The global revision is preserved even for an empty selection; rows and revision describe the same state; expired/nonselected requests are filtered and the256-row bound remains. Added three Rust tests for deletion/empty revision, expiry/filtering and capacity. They have NOT executed yet. No refresh-token implementation changes were made in this continuation.

## 16 — Local verification and handoff; not release acceptance

The local frontend suite passes139 tests with zero failures/skips; eight decision-function cases are included in that total. Two real production Svelte components compile with Svelte5.56.4 and zero warnings. The blank-page Playwright contract test passes for both resolvers. Python syntax, workflow parsing and git diff whitespace checks pass. The real HTTP browser fixture remains locally blocked by ERR_BLOCKED_BY_ADMINISTRATOR; no policy or sandbox workaround was used. Cargo is unavailable. GitNexus/Probe attempts remain unavailable and manual impact/diff review is explicitly a fallback.

The GitHub tool channel exposes read/search/download but not code-write, ref update or workflow dispatch. Preserve a base-pinned incremental patch, file digests, local evidence and continuation checkpoint. Do not claim these local edits are committed remotely, that the six new Rust tests pass, or that native desktop/real-ChatGPT acceptance is complete. Resume by applying the patch to the exact ecf5ca9 base, then run the changed candidate's full locked Windows/Ubuntu, browser, native and real-host gates. PR#11 and the published v0.3.2 installers remain outside this patch's scope.


## 17 — Restore and validate the saved continuation

Published exact tree `450f23accbb55dc5318a70df5b7b0c8c83906543` on feature commit `4cede8049d7042a53e4421aa5bca0c361faa5a39` and opened Draft PR #12. This preserves the earlier ecf5ca9 callback fix. Import run34750945195 validated both patch digests and source tree, but the standard Actions token could not push a workflow change. It was not a test failure or a successful import. The already-authorized GitHub connector then created the exact tree/commit and fast-forwarded the feature branch without a force push. Temporary transport data is confined to the isolated build branch.

Candidate run34751029564: source/failure-first/Ubuntu/browser jobs completed successfully while Windows was still running at this entry. Final counts must be read from the new run, not copied from ecf5ca9. A downloaded source archive revealed that the first local git add omitted already-tracked `old/` files due to .gitignore; forced adding ONLY the archive's verified paths restored the exact remote tree. No old source was edited.

## 18 — Installed acceptance and 0.4.0 packaging (in progress)

The v0.3.2 native acceptance deliberately approved A and B concurrently and used a temporary exclusive toggle. Reusing it would contradict the approved default-exclusive product contract. Preserve it as a legacy fixture and add a separately named installed scenario with strict new evidence schema. Windows standard-user bootstrap gains an allowlisted scenario selector, not an arbitrary executable or a permission bypass. All source-copy hashes, standard-user checks, scoped ACLs, process ownership and cleanup remain enforced. Manual impact: test launcher child/run, release evidence validation, no business authorization entrypoint changes. Probe/GitNexus still unavailable as already recorded.

Before packaging, synchronize the five version files/six fields from0.3.2 to0.4.0 using the existing version tool. The new installed scenario covers default policy, persisted durations, real offline PKCE/refresh HTTP, native fingerprint and reduced-scope approval,100 silent foreign requests, unchanged lease after refresh, live-child draining/local cancellation, readonly successor/native denial, an actual90-second pending deadline, restart without approval and refresh reuse revocation. Code existence is not PASS; native runs remain required.

OS toast display and real ChatGPT account provenance remain distinct observations, not inferred from successful in-app modal or HTTP fixture checks. Do not substitute an old installer or weaken the exact-source/package/payload gates.


Round18 local review before upload: new native-contract unit suite9/9 passed; existing Windows/native/release helper suite105/105 passed. New entrypoints compile with Python. Workflow parses into one Ubuntu22.04 package build, four installed Ubuntu system/format combinations, and one strict standard-user Windows install job; there is no Windows-defer branch. Candidate4cede80 now has all five validation jobs successful in run34751029564, including the six added Rust regressions and expanded browser suite. Exact counts will be recorded from downloaded artifacts. These results do not validate the new0.4.0 packaging scenario yet.
