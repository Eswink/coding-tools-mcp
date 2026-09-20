# Execution tasks

Parent: [plan.md](plan.md)

## Planning baseline

- [x] Read current repository architecture, MCP listener, runtime stop flow, session policy and chat authorization code.
- [x] Confirm repository GitHub Issues feature is currently disabled.
- [x] Create independent planning branch `plan/offline-safe-connector-lifecycle`.
- [x] Save five-round execution plan before implementation.
- [x] Open file-backed ISSUE-001 for host reconnect classification.
- [x] Review Round 1 harness design before adding fault injection.
- [x] Add allowlisted test-only fault proxy; no production runtime symbols modified.
- [x] Add isolated proxy contract tests.
- [x] Validate harness on Ubuntu and Windows CI.

## Round 1 — ISSUE-001

- [x] Build deterministic C1/C3/C4/C5/C7/C8 fault harness.
- [x] Validate harness on Ubuntu and Windows.
- [x] Record failure-first CI defect and repair.
- [x] Explicitly defer real ChatGPT host validation to Round 5.
- [ ] C1-C10 real-host observations — DEFERRED, not waived.
- [ ] Final reconnect-trigger classification — DEFERRED, remains unconfirmed.

## Round 2

- [x] Create ISSUE-002 after explicit real-host gate deferral.
- [x] Freeze connector-control vs execution-availability semantics.
- [x] Freeze auth/transport/business error taxonomy.
- [x] Freeze atomic pause/admission gate semantics.
- [x] Freeze offline drain-control allowlist.
- [x] Select provisional Level A architecture.
- [x] Prepare exact Round 3 impact-analysis target list.
- [x] Perform required GitNexus impact analysis before and during production edits; preserve HIGH/CRITICAL and Svelte-indexing limitations as evidence.

## Round 3

- [x] Implement the minimum selected control/execution lifecycle split.
- [x] Add Rust/HTTP/UI regression coverage.
- [x] Verify OAuth refresh does not mutate chat ownership.
- [x] Verify intentional offline does not emit auth challenge.
- [x] Verify tunnel policy matches control-plane lifetime.

## Round 4

- [x] Create and implement non-disclosing multi-user boundary.
- [x] Verify no project/owner/path/task metadata leak to foreign chat.
- [x] Verify Online/Offline does not override stronger authorization/exclusive/recovery denial.
- [x] Verify repeated foreign authorization noise creates no new pending record/event.
- [x] Verify per-chat task isolation remains intact while execution is Offline.
- [x] Document shared-account limitation separately from distinct workspace-member access.

## Round 5

- [x] Run full Windows source + NSIS install/uninstall acceptance — run `35509843023`.
- [x] Run full Ubuntu source + DEB install/purge acceptance — run `35509843023`.
- [ ] Run real ChatGPT offline/online lifecycle acceptance — DEFERRED by user; still required for HOST_VALIDATED.
- [x] Run available network/tunnel restart/recovery regressions on Windows and Ubuntu source suites.
- [x] Run long-task draining/recovery regressions on Windows and Ubuntu source suites.
- [x] Review exact Round 5 diff and affected execution flows; retain focused CRITICAL/UNKNOWN impact findings.
- [x] Record bounded rollback evidence in `round5-rollback.md`.
- [x] Reach `ENGINEERING_CANDIDATE_PASS` without publishing a tag/release.
- [ ] Close project only when target reconnect UX is validated on the real ChatGPT host without weakening auth.


## Post-Round-5 hardening

### ISSUE-006 — Streamable HTTP Origin boundary

- [x] Compare MCP spec / TypeScript SDK / Rust SDK / Rust gateway Origin patterns.
- [x] Run focused pre-edit GitNexus impact; retain CRITICAL/lower-bound evidence.
- [x] Add failure-first Origin matrix and record real 200-vs-403 gap.
- [x] Protect MCP and OAuth control routes with live Origin validation.
- [x] Require exact current public Origin by scheme/host/effective-port.
- [x] Keep missing-Origin compatibility for non-browser clients.
- [x] Verify live Quick/public-origin replacement without listener restart.
- [x] Verify generic non-reflective 403 behavior.
- [x] Run Windows and Ubuntu full source regression.
- [x] Rebuild/install/remove Windows NSIS and Ubuntu DEB artifacts.
- [ ] Verify normal real ChatGPT traffic against the Origin guard — DEFERRED with the host gate.

### ISSUE-007 — Host / authority / Fetch Metadata

- [x] Freeze topology-aware design from open-source references.
- [ ] Capture sanitized Host/:authority behavior for each FRP/Cloudflare tunnel mode.
- [ ] Implement only after tunnel topology evidence.

### ISSUE-008 — intent-aware lifecycle UX

- [x] Identify current UI gap: primary running MCP action still performs hard stop.
- [x] Freeze Pause/Resume-primary, Stop-Connector-secondary design.
- [x] Add failure-first cross-platform UI contract.
- [x] Make Start / Pause / Resume the normal MCP lifecycle actions.
- [x] Keep hard Stop Connector explicit and confirmation-gated.
- [x] Remove duplicate MCP hard-stop control from generic ServicePanel.
- [x] Keep ChatGPT Actions lifecycle unchanged.
- [x] Run Svelte check/build and old/new UI contracts on Ubuntu and Windows.
- [ ] Validate the actual reconnect UX on real ChatGPT host — DEFERRED.


### ISSUE-009 — offline authorization noise

- [x] Reproduce new pending approval creation while execution is Offline.
- [x] Run focused GitNexus impact and retain lower-bound/UNKNOWN findings.
- [x] Preserve recovery / exclusive / malformed-request precedence.
- [x] Suppress only NEW pending authorization allocation while Offline.
- [x] Make pause-vs-allocation behavior linearizable with a short Online hold.
- [x] Verify zero pending record/event and no local notification trigger while suppressed.
- [x] Verify error is a non-OAuth MCP tool error with no `WWW-Authenticate`.
- [x] Verify Resume restores normal pending authorization creation.
- [x] Verify OAuth refresh behavior remains unchanged.
- [x] Run final Ubuntu + Windows full source regression.
- [x] Run final Ubuntu DEB + Windows NSIS install/remove revalidation.
- [ ] Verify behavior through the real shared ChatGPT host/account UI — DEFERRED.
