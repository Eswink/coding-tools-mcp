# Execution tasks

Parent: [plan.md](plan.md)

## Planning baseline

- [x] Read current repository architecture, MCP listener, runtime stop flow, session policy and chat authorization code.
- [x] Confirm repository GitHub Issues feature is currently disabled.
- [x] Create independent planning branch `plan/offline-safe-connector-lifecycle`.
- [x] Save five-round execution plan before implementation.
- [x] Open file-backed ISSUE-001 for host reconnect classification.
- [ ] Review Round 1 harness design before adding any fault-injection code.

## Round 1 — ISSUE-001

- [ ] C1 healthy baseline with real ChatGPT host.
- [ ] C2 current workspace-stop reproduction.
- [ ] C3 HTTP 503 behavior.
- [ ] C4 protocol-valid typed workspace-offline behavior.
- [ ] C5 access expiry with token endpoint unavailable.
- [ ] C6 successful refresh baseline.
- [ ] C7 refresh rejection control.
- [ ] C8 abrupt connection reset behavior.
- [ ] C9 valid OAuth + chat unauthorized.
- [ ] C10 valid OAuth + exclusive non-owner.
- [ ] Sanitize and record traces.
- [ ] Review findings and freeze reconnect trigger classification.
- [ ] Move ISSUE-001 to DONE only after evidence review.

## Round 2

- [ ] Create ISSUE-002 after Round 1 hard gate.
- [ ] Freeze `WorkspaceAvailability` semantics.
- [ ] Freeze auth/transport/business error taxonomy.
- [ ] Perform required code impact analysis for every symbol planned for modification.
- [ ] Select architecture Level A, B or C based on evidence.

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
