# Continuation Review — Exclusive Conversation and Refresh

## Delivery state

This is a local incremental candidate against upstream `ecf5ca9449a82122f26f2bef3f50ce6d0afd5488`, not a release or an upstream push. The approved execution plan remains [plan.md](plan.md); recovery and the bounded continuation are in [continuation-plan.md](continuation-plan.md).

## Findings and changes

| Finding | Evidence | Candidate handling | Validation status |
|---|---|---|---|
| Function-valued browser readiness predicates resolve the user's pending confirmation | Failed upstream browser log; local blank-page Playwright reproduction | Preserve the upstream `typeof` fix, add a side-effect-free readiness regression and explicit no-save-before-confirmation assertion | Fixed upstream CI; local contract PASS |
| Inbox refresh runs while decision is still busy, delaying the next workspace candidate | Executed actual production function: unmodified6/8, modified8/8 | Release busy before successful resynchronization; retain no-success handling on error/disposal | Local function-level PASS; expanded DOM fixture unrun |
| A pending request can cross its deadline between reconciliation and final decision lock | Source call-chain review | Recheck TTL inside the locked decision, expire/drain and reject | Three new Rust tests written; execution pending |
| Removing the last workspace resets aggregate inbox revision to zero | Source inspection of aggregate revision and frontend stale-response guard | Capture pending rows/global revision atomically; retain revision for empty selection | Three new Rust tests written; execution pending |

The privileged decision API remains local Tauri IPC. No new HTTP approval route or model-callable approve tool is introduced. Nonowners remain unable to reserve or generate approval noise while an owner exists. Fingerprint confirmation, scope reduction, default exclusive policy, finite lifetimes, strict refresh rotation and execution draining are not relaxed.

## Test evidence and its scope

Upstream run `34749675645` on `ecf5ca9`: Windows422 Rust tests, Ubuntu411 Rust tests,131 frontend tests per platform,10 browser scenarios. Downloaded artifacts were verified against their reported SHA-256 digests and source metadata. This successful run does not contain this incremental candidate.

Local incremental candidate:139 frontend tests passed;8 decision-function tests are part of139, not an additional count. The2 resolver contract cases use Playwright on a blank page with no network. Svelte compilation covers the real `ChatAuthorizationHost` and `RemoteSessionSettings`, with zero compiler warnings; it is not full-app type checking or an installed desktop run.

Six new Rust tests, full changed-candidate Rust compilation, the expanded12-scenario HTTP browser test, Windows/Ubuntu native notification behavior and actual ChatGPT refresh/reconnect acceptance remain open. The container's browser policy rejects localhost navigation; Cargo and the required orchestration/graph CLIs are unavailable. No security policy was disabled to force a result.

## Manual impact and lock-order review

`chat_authorization_control -> ChatAuthorizer::decide -> decide_locked` keeps record selection, deadline recheck, scope subset and owner phase mutation under one mutex. The helper does not acquire executor locks or call UI callbacks; events are existing bounded nonblocking invalidations. Deadline tests call the production decision helper with a controlled monotonic instant, not real sleeps.

`chat_authorization_inbox -> pending_inbox` drops workspace configuration access before authorizer/executor access. Reconciliation stays outside the final snapshot mutex; the final operation only filters/copies bounded local state. The single global revision avoids both an empty-inbox reset and mixed per-profile revisions. The frontend still rejects stale revisions.

`ChatAuthorizationHost::decide` commits one selected request through IPC, releases busy, then resynchronizes. An IPC failure does not dismiss the selected candidate or imply success. A disposed component performs no completion UI effects. A successor candidate still starts with fingerprint confirmation disabled.

## Resume and release constraints

Apply only to the recorded base (or review/rebase on any newer remote commit); never overwrite a concurrent branch update. Run locked Rust checks/tests and frontend type/build/tests on Windows and Ubuntu, then the full browser/native/actual-host gates. Keep the separate Nginx routing PR#11 untouched. Do not replace v0.3.2 assets or present a source patch as an installer. New installer publication requires the repository's normal version and release-evidence process.
