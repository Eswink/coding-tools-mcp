# Design: authenticated two-hop native integration

## 对应需求

This design covers FR-1 through FR-8 with native authority/transport proof, isolated TLS geometry, exact inventory and immutable candidate identity.

## 概述

Keep production unchanged. Factor actual native-host construction from existing wss_tests.rs, retaining all11 baseline assertions and its existing native_desktop_fixture inspector. A new opt-in module owns9 tests against the actual shipped Gateway behind real outer TLS Nginx and unchanged inner Nginx.

The new native client has a disposable container/network namespace. The existing gateway/inner ingress namespace owns outer443 and a Docker-network-local gateway.example.invalid alias. Outer443 has no host publication; existing inner8080 loopback mapping stays unchanged. Both generated include bytes, actual running config hashes, canonical origin and Host/header rejection guards are checked. If the existing nonroot low-port policy cannot bind443, stop; never modify sysctl/caps.

## 文件结构

Native/source P, parent exactly frozen M, modifies7/adds6 paths (1676 tracked files):
- container_fixture.py: retain shipped key and redeemed connection privately; final320/delta32
- new run_current_nginx_agent.py: owned fixture, TLS/IPC, baseline/new test supervisor and safe evidence; final500/delta500
- host_agent_support/relay.py: reusable CA/leaf generation retaining localhost baseline; final160/delta180
- wss_tests.rs: shared real host construction and gated adjacent module; final500/delta180
- new wss_two_hop_tests.rs:9 native tests; final500/delta500
- new wss_two_hop_support.rs: test-only harness/OAuth/IPC split required by exact rustfmt; final500/delta500
- src-tauri/Cargo.toml: dedicated feature only; final100/delta4
- test_current_nginx_two_hop.py: identity/source/secret/control/cleanup helper regressions; final480/delta260
- issue40-current-nginx-include.yml: fresh build/run/source evidence; final440/delta240
- current-nginx-include.md: precise proof/operator boundaries; final320/delta150
- these requirements/design/tasks specs: final120/200/120 respectively, same deltas
Aggregate P delta<=2200. The four abbreviated existing paths above retain their repository directories documented in the implementation task list.

Amendment A, parent exactly P, modifies4/adds2 paths (1678 tracked files):
- scripts/rc_pretag_composition_tests.py final500/delta24
- scripts/rc_pretag_desktop_tests.py final400/delta32
- scripts/rc_pretag_nginx_tests.py final480/delta40
- scripts/rc_pretag_two_hop_tests.py final480/delta48
- scripts/rc_pretag_authenticated_two_hop_profile.py final360/delta360
- scripts/rc_pretag_authenticated_two_hop_tests.py final480/delta480
Aggregate A delta<=900. Four historical profile files stay byte-identical. Exact adapter function allowlists and approved inventory are fixed in the reviewed external design packet before code.

## 数据结构与接口

Private bootstrap is bounded synthetic JSON, generated from the actual shipped CLI outputs. Validate exact redeemed Connection schema; preserve all identity/key/epochs, remove only version and add owned revision_file/ca_der_file for AgentConfig. Unknown/missing fields fail closed. Protect all private input files and parent directories forUID65532; canonical CA path, regular single-link mode0600 file under mode0700 parent. Use private per-test workspaces/journals. Native control socket uses AF_UNIX: supervisor binds/listens before transferring directory/socket ownership, retains the open descriptor, and verifies peerUID65532. Bounded JSON frames carry monotonic IDs and fixed enums inspect/gateway_stop/gateway_start/revoke_device/restart_database. No SQL/commands/paths as inputs. Replies expose only raw bounded channel/projection/device observations and fixed status receipts, not secret/key/grant material or manufactured eligibility.

## 技术方案

1. Verify source identity, hosted-runner/local-Docker gates, official immutable images and ownership before effects
2. Build exact native test executable and baseline example on Ubuntu22/Rust1.98.1 from a fresh target, with python3/OpenSSL plus matching native runtime libraries available in the final image; verify no unresolved ldd entries and exact --list underUID65532. Derive executable from Cargo JSON and preserve source hash
3. Run baseline11 in a separate owned PostgreSQL/test-container namespace; source mounted read-only at its build-time CARGO_MANIFEST_DIR so existing relay resolves
4. For each new test, create a separate fresh Fixture and shipped enrollment; start unchanged Gateway/inner and nonroot TLS outer, then native client. Never reuse revoked/negative fixtures
5. Acquire positive-case OAuth authorization/login/consent/PKCE tokens through the new verified HTTPS443 client route; do not use the plaintext historical OAuth helper. For negative TLS cases send no owner credentials. Wait for connected/reconciled channel and initial sequence>=5 plus real native link; prove pending/approval/read/denials through HTTPS and native decision
6. Test same-Agent reconnect with new boot/session/generation then explicit Agent journal reopen with same current boot and another higher generation. Duplicate denial is end-to-end no-replay (Gateway Existing may satisfy it); do not claim local-tombstone causality or reset SQL. Require unchanged canary/ledger and fresh-ID positive control. revoke requires dropping all old native objects and reopening encrypted authority/projection/execution state with initialize=false. This is same-process encrypted-state reopen, not OS-keyring/process persistence proof
7. For gateway drain keep Agent running; observe native disconnect and the original outbound443 tuple leaving ESTABLISHED within8 seconds concurrently with Gateway-only stop. Observe a fresh heartbeat/lease refresh and record database now/lease_until plus conservative native30-second expiry lower bound from monotonic pre-Agent-start time. Require both remaining bounds exceed the full8-second window with margin; finish before both bounds so expiry cannot mimic drain. Disable HTTPS idle pooling; require stopped receipt/exit0 and false channel presence
8. Managed callback cancellation must retain exclusive execution journal until actual callback drain; only then allow reopen
9. For untrusted root/wrong leaf SAN/expired leaf, keep canonical Host and configured authority unchanged. Exact AgentError::Tls within deadline and HTTPS certificate rejection; no channel or pending records. Before these negatives verify Nginx config/process/TCP readiness and actual leaf/issuer/SAN/validity independently. Require the HTTPS error chain names the intended certificate cause; absent listener, generic connect, configuration or unrelated TLS defects fail
10. After device revoke/DB restart, prove an actual bounded shipped-service startup refusal provisioning_not_ready; Compose return/SQL flag alone is insufficient. Use the bounded CLI refusal path, not a restart:unless-stopped loop. Always reap native processes/control listener/outer before cleanup; verify no owned containers/networks/volumes remain; cleanup failure is failure

## 组合来源与证据

P is a local immutable source anchor, never an integration-ready CI claim. First remote candidate A includes the guard and preserves13 P pins exactly. Profile stores13 source and5 non-self amendment pins; reviewed external manifest binds all6 amendment bytes including self, whole tree and parents. Specs refer to P/A symbolically because embedding their own SHA would be cyclic.

Only A=[P], I=[M,A] with entire A tree and L=[R,I] with four exact historic release overlays are accepted. No P-only candidate, arbitrary child, broad ancestry, shadow ref or failure fallback. Historical209 names remain frozen; new24 make strict233, exact declared/loaded/executed once. Full A source and runtime evidence comes from A; I/L hermetic evidence is not fresh native proof.

Artifact allowlist contains source/tree, compiler/example/test hashes, images, actual configs/includes, exact inventories/results, nonroot/cap/namespace observations, safe receipts and cleanup. Exclude private bootstrap/config/key/token/CA-key/database data and raw stdout that could reveal them. Preserve prior build/audit provenance and known warnings. The same A also reruns45/57 existing runtime cases.

## 风险与回滚

Fresh GitNexus index:22638 nodes,50314 edges,286 flows; FTS unavailable but exact contexts/impact succeeded. Existing Harness.start has6 direct callers/MEDIUM risk; Fixture.prepare2/LOW; CA helper1/LOW. Reuse-only private_config6/MEDIUM. No runtime authority edits. Regenerate graph/staged detect_changes before commit.

All effects stay inside labeled disposable CI projects and owned images/artifacts. On bind/TLS/source/permission/drain failure, stop and report, do not change security or reinitialize journals. No production rollback action. Operator documentation must prevent restoring revoked authority and state exact immediate upstream/namespace, source-checked inner config, collisions, TLS/WAF prerequisites and rollback limits.
