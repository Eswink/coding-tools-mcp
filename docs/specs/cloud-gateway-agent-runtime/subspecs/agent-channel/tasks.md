# 子任务：Cloud OAuth, local approval and outbound device transport

- [ ] 2.1 Implement production OAuth and signed local grant projection
  - 证据块: src-tauri/src/tools/聊天运行域v1.rs:94-134; threat-model.md
  - 涉及文件: future cloud auth/local approval adapters
  - _需求: FR-4_

- [ ] 2.2 Implement enrollment, outbound WSS, fencing and durable request reconciliation
  - 证据块: design.md; protocol.md
  - 涉及文件: future agent transport and journal
  - _需求: FR-5_

## Round 2 partial increment — not a completed 2.1/2.2

- 2.1: standalone PostgreSQL identity core and metadata/token HTTP adapter; PKCE, rotation/replay, absolute expiry, unchanged identity across a real database and process restart verified locally. Ed25519 grant envelope verification only; no authoritative local/cloud grant projection or owner consent controller.
- 2.2: expiring single-use device invitations, proof-of-possession and revocation verified locally. No authenticated WSS or durable remote request journal; no real workspace tools wired.
- Evidence: `../../round2-validation.md`. GitHub publication and Windows CI remain pending in this read-only session. Do not mark either parent checkbox complete.

## Round 3 / ISSUE-013B (#41) — partial 2.1

Owner browser login and one-time CSRF-bound consent are implemented in the standalone library. 68 Rust tests (30 new browser tests), including real PostgreSQL transactions, pass locally. Two independent process/database restart probes pass with no Agent. The browser/PKCE flow is not local workspace approval. Production entrypoint, ingress safeguards, authoritative grant projection, authenticated Agent channel, native CI and actual browser/Host gates remain open; do not check off 2.1 or 2.2. See `../../round3-validation.md`.

## Round 4 / ISSUE-013C (#42) — bounded executable increment of 2.1

- [ ] 2.1C Runnable identity-only service, trusted local provisioning, protected secret
  input, pre-bind readiness, request/connection limits and real Chromium acceptance.
  Evidence/design: `../../issue-013c-runnable-service.md`. This does not complete 2.1
  (local grant projection remains open) or 2.2 (Agent channel not implemented).

Round-4 local evidence: 91 Rust tests + 30 separate-process HTTP/PG cases PASS;
13 renderer + 32 protocol + 8 UI-source + 8 proxy regressions PASS. Executable/CLI
implementation is present. Browser gate BLOCKED; native CI/publication pending.
The 2.1C checkbox intentionally stays open; see `../../round4-validation.md`.

## Round 5 / ISSUE-014A (#43) — partial 2.1; physical gates deferred

The user requested continued non-physical development. Historical browser-policy
BLOCKED and VPS/real-ChatGPT UNCONFIRMED are retained as release gates, not
prerequisites for this isolated projection increment.

- [x] 2.1D Device-owned signed snapshots, durable owner/drain/revocation floor,
  restart challenge fences, non-disclosing projection decisions; 16 pure and
  32 PostgreSQL contracts locally PASS. Full paired Agent/UI integration and
  actual local execution admission remain in parent #38 / ISSUE-021.
- [ ] 2.2A Authenticated outbound channel: device proof, connection generation,
  heartbeat/disconnect and bounded framing before business routing.

Evidence: `../../issue-014a-grant-projection.md`, `../../round5-validation.md`.
Round4 source is preserved; publication/native CI are tracked separately. Neither
parent 2.1 nor 2.2 is marked complete by a passing projection library test.
