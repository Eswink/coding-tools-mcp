# Requirements: authenticated two-hop native integration

## 功能概述

Add bounded engineering proof for issues #40/#81 at base M `a88be4901623f7c8629b93df984166587253f0be`, tree `246213487851c01a6def74b7519e58a6d709c180`. This is test infrastructure, not production deployment or release approval.

## 用户故事

As the maintainer, I need native authorization, authenticated WSS lifecycle and TLS rejection tested through both real Nginx hops on one exact integration-ready candidate, while prior proofs remain intact.

## 需求列表

- FR-1: Reuse shipped enrollment/key generation, actual HostAgent, NativeLiveHost, ChatAuthorizer and real HTTPS MCP calls. Never add a signer/mock native host or production inspector endpoint
- FR-2: New geometry: isolated native client to TLS outer443, unchanged inner8080, Gateway127.0.0.1:28880. Preserve canonical gateway.example.invalid and exact Host guards; network-local alias only
- FR-3: Run current native baseline11 unchanged in meaning, plus exact new9 cases: pending/grant/read/foreign denial; reconnect generation and no replay; native revoke encrypted-state reopen; device revoke across DB/Gateway restart; authenticated socket drain; managed callback/journal drain; untrusted CA; wrong SAN; expired leaf
- FR-4: Keep same-candidate45 single-hop and57 runner-host-published two-hop proof. Do not claim the new Agent traversed that older published-port geometry
- FR-5: Use dedicated opt-in nginx-agent-integration-tests Cargo feature, no ignored/early-return pseudo-pass, dependency/version/lock changes or production runtime edits
- FR-6: Batch the closed exact composition amendment in the first CI candidate. Preserve all historical pins and209 IDs; add exactly24 approved strict cases, making233
- FR-7: Native/source P has exactly13 approved paths. Amendment A has exactly6 more, and is the first published candidate. Validate complete tree, source and non-self amendment pins, exact parents, finite per-file/aggregate budgets, and reviewed external profile self pin
- FR-8: P is structural-only; allowed new candidate grammar is A=[P], I=[M,A] with tree=A, L=[R,I] with only existing four exact release-document overlays. No arbitrary descendants, fallback, skip or widened historical profile

## 非功能需求

- UID65532, capsDropALL, no-new-privileges, read-only roots and disposable private mounts. No host443, host DNS/hosts/system trust, caps or sysctl change. Stop if existing nonroot namespace cannot bind443
- Local test CA retains normal TLS chain/name/time validation. CA canonical single-link file and parent owned by currentUID, mode0600/0700
- Private bounded AF_UNIX control accepts fixed ops only; no arbitrary SQL/command/path input. SQL returns observations, never synthesized authorization verdicts
- No secrets in command lines, logs, Docker logs or artifacts. Allowlist/redact evidence; preserve source/image/compiler/audit provenance and failure status
- Keep every source file within500 lines and tighter approved budgets; report scope shortfall before expanding

## 依赖关系

Existing shipped Gateway/Agent CLI, native HostAgent/NativeLiveHost/ChatAuthorizer, private Nginx topology, local-CA helper, exact composition profiles and authorized Actions runtime are required. No new runtime library dependency is added.

## 验收标准

When each fixture completes, it SHALL satisfy every applicable criterion below; any missing observation SHALL fail the case.

- All source-declared, compiled-listed and executed baseline11/new9 names match once; zero failures/ignored/zero-match passes
- Pending request creates real native pending and no canary before local approval; files.read permits real canary; foreign scope fails without disclosure
- Native revoke test drops all prior native objects and reopens encrypted authority/projection/execution state, without claiming an OS-keyring/process restart
- Gateway-only stop produces zero exit/stopped receipt, false presence, real native disconnect and original WSS443 tuple closed within8 seconds, while Agent stays alive and receives no local stop
- Managed native callback retains exclusive journal lock until actual callback completion and Drained receipt
- TLS cases terminate promptly with exact AgentError::Tls; HTTPS also rejects, channel generation stays0/disconnected, and native pending remains empty
- Current deployment/native source guards, rustfmt/actionlint, strict233 and consumer/contracts regression checks pass on the candidate; failures and unavailable native stages remain explicit
- Evidence and cleanup bind exact candidate A (optional I/L hermetic evidence separately); PR89 stays draft and #40/#81 remain open

## 不在范围

Production/live VPS, real ChatGPT or GUI approval, release/tag/publication, main, PR98/held refs, cancellation86 retry and snapshot work are excluded. No permanent host security/setup changes.
