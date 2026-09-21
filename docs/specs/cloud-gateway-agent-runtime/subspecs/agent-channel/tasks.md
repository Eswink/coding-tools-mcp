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
