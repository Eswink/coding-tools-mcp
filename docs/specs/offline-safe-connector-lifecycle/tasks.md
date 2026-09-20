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
- [ ] Perform required GitNexus impact analysis before any production symbol edit — BLOCKED in current tool environment.

## Round 3

- [ ] Implement the minimum selected control/execution lifecycle split.
- [ ] Add Rust/HTTP/UI regression coverage.
- [ ] Verify OAuth refresh does not mutate chat ownership.
- [ ] Verify intentional offline does not emit auth challenge.
- [ ] Verify tunnel policy matches control-plane lifetime.

## Round 4

- [ ] Create and implement non-disclosing multi-user boundary.
- [ ] Verify no project/owner/path/task metadata leak to foreign chat.
- [ ] Document shared-account limitation separately from distinct workspace-member access.

## Round 5

- [ ] Run full Windows installed acceptance.
- [ ] Run full Ubuntu installed acceptance.
- [ ] Run real ChatGPT offline/online lifecycle acceptance.
- [ ] Run network flap / tunnel restart cases.
- [ ] Run long-task draining/recovery cases.
- [ ] Review exact diff and affected execution flows.
- [ ] Record rollback evidence.
- [ ] Close project only when target reconnect UX is eliminated for the supported lifecycle without weakening auth.
