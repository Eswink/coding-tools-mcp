# 设计文档：device-enrollment-bootstrap
## 概述
Covers FR-1, FR-2, FR-3, FR-4 and NFR-1/NFR-2. Existing library operations stay unchanged. Extend gateway and Agent CLI entry routing with focused enrollment modules, not another binary.
## 技术方案
Gateway -> protected config/secrets -> existing IdentityStore -> enrollment transaction -> protected invitation or native config document. Agent -> locally generated key -> protected invitation -> domain proof -> protected proof document. Operator explicitly transfers only invitation/proof/public configuration. Device selection remains existing control-gateway select-device; local approval remains native desktop.
## 数据模型
InvitationDocument: version1, origin, prefix, connector, token. ProofDocument: same identity/token plus public_key and signature. KeyDocument: pkcs8 only, matching existing native import and recovery Agent. ConnectionConfig: version1, origin, prefix, connector, device, device_epoch, authority_epoch1, public_key, run_seconds3600. Authority epoch here initializes a local namespace, never creates a grant.
## API 设计
Gateway invite-device/redeem-device/revoke-device via service/enrollment.rs. Agent generate-key/prove-enrollment via service/enrollment_device.rs using private module helpers. Explicit input documents through --input-file or --input-stdin; key through --key-file or --key-stdin; output through --output-file or --output-stdout. Two stdin consumers forbidden. Standard stdout is a deliberate document channel only when explicitly selected and nonterminal; diagnostics remain fixed stderr. No private data in argument values.
## 文件结构
Add service/enrollment.rs, enrollment_device.rs, enrollment_io.rs; update service/mod.rs and two CLI modules. Add tests/enrollment_contracts.rs, tests/run_enrollment_process.py and enrollment PG cases. Extend existing run_agent_process canary setup to shipped command bootstrap. Add these specs and operator documentation. No dependency/migration edits.
## 设计决策
Reuse existing Ed25519 and SQL row-lock operations. Never duplicate invitation verification/consumption. Unix output uses pinned owner directory descriptor/openat(create_new,no_follow,0600); Windows explicit output pipe avoids claiming native file ACL validation. Failure after a consumed invitation is not retried automatically; operator explicitly creates a new invitation and revokes unusable enrolled identity if necessary.
## 测试策略
FR-1/4 real separate-process disposable PostgreSQL bootstrap and invalid/replayed/concurrent proof tests; FR-2 key remains local and mismatched key/domain denied; FR-3 portable negative argument/JSON/stdin tests and Unix unsafe-output/no-overwrite tests. Existing WSS driver connects enrolled identity. Exact-source Windows compile and portable tests plus Ubuntu PG/WSS required in final CI.
## 风险评估
Credential output requires explicit protected destination; stdout terminals prohibited. Authority initialization remains configuration only. Output failure may leave orphan enrollment: fail closed, preserve state, no silent replay. GitNexus exact CLI impacts and manual callsite review before production changes.
## 检查清单
- [x] All FRs covered; existing crypto/transaction boundaries reused
- [x] Four binary package interface preserved
- [ ] Exact-source tests and post-change review

## Local review and evidence
Exact CLI entry impacts LOW; graph has known Rust caller-resolution limits, so main.rs/agent_main.rs routing was manually reviewed. Staged additive scope14files/137symbols/3flows MEDIUM. No existing invitation, signature, token, transaction, approval, migration or dependency behavior changed. Native identity grammar is checked before invitation issuance/consumption so legacy gateway-only prefixes cannot produce unimportable desktop configuration. Windows native CI and cumulative release review remain required.
