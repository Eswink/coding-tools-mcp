# 子规格：Focused CI execution and honest artifact verification

## 范围
One dedicated read-only assembly workflow and targeted frontend artifact checks; exact commands/matrix from the parent requirements.md and subspecs/source-evidence/spec.md.

## 需求回链
- FR-3
- FR-4
- FR-5

## 验收标准（EARS）
1. WHEN the focused workflow runs THEN all3 OS portable selections,4 locked manifests,4 compiled version outputs,233 frontend tests,147 existing JS tests and88 discovered delivery methods SHALL execute unchanged; Windows SHALL explicitly show4 Linux-only delivery skips, never88 passes. Portable Cargo SHALL retain exact ordered per-suite counts: Linux standalone[50,23] and RC[50,11,23]; Windows standalone[49,18] and RC[49,10,18], with zero failed/ignored/measured/filtered tests.
2. WHEN Ubuntu24 portable execution succeeds THEN all4 real browser suites SHALL run with sandbox enabled, exact original state/scenario/viewport/screenshot assertions, source/build hashes and unchanged raw npm audit. Sandbox-disabled/missing/nonzero/incomplete output SHALL fail the focused frontend result.
3. WHEN Linux native jobs run THEN Ubuntu22/24 SHALL each require11 golden,7 lifecycle,14 kernel and6 stdin cases with actual isolated Secret Service, unchanged payload hashes, cleanup/restoration and no hidden skips.
4. WHEN audits execute THEN fresh4 lock reports, raw vulnerabilities/warnings, GLib source/paired proof and actual tool/database identity SHALL be retained. A separate downloaded-artifact verifier SHALL bind trusted capture-output digest, source/ancestry/blobs and actual run/attempt; integrity success SHALL not imply security acceptance.
5. WHEN any stage fails/times out/skips or has missing/zero-count evidence THEN it SHALL remain failed/blocked with diagnostics uploaded. ZIP/digest/inventory/source/exit/count checks SHALL precede result reporting. Every command SHALL match its exact reviewed argv and executed form, including exact multiline shell bytes and no contradictory timeout. Complete per-suite exit inventories and current-source discovered unittest counts SHALL match actual logs; both assembly test modules SHALL execute. The finalizer kind SHALL equal the freshly verified source job.
6. WHEN source preflight passes THEN only named input/version/source scope SHALL be reported, bound to the actual source SHA and0.7.0-rc.1 version. Full RC integration, missing final manifest, known Windows599pass6fail4warnings and held lanes SHALL remain unresolved; no final_release_eligible or package/release approval SHALL be asserted.

## 涉及文件
.github/workflows/rc-source-assembly.yml; scripts/rc_source_assembly_frontend.py; scripts/rc_source_assembly.py; scripts/rc_source_assembly_tests.py; scripts/rc_source_assembly_evidence_tests.py.

## 不做项
No PR89/schema/PR97 stack, Windows security driver, Issue86 opened-root binding, consumer malformed-redirect cleanup, runtime production edits, secrets, security weakening, main/canonical advancement, tag or Release. Preserve every original workflow/guard/test/lock/payload. No held-action retry.

## 设计要点
Focused seven execution jobs are distinct from complete seven-job release integration. Existing PR90/91/93/94/96 workflows and strict guards remain byte-identical. Reuse only their real commands/fixtures, with honest new assembly identity. Pin official actions, contents read, no persisted checkout credentials, no secrets, bounded timeouts, always-upload failures. Preserve actual stdout/stderr/status/tool/source manifests.

## 真实执行入口
- Portable: cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --lib --test service_contracts; then same command with --test enrollment_contracts added
- Metadata: cargo metadata --locked --format-version 1 for src-tauri, services/cloud-gateway, services/cloud-agent and services/local-agent Cargo.toml
- Compiled versions: cargo build --locked --bins --manifest-path services/cloud-gateway/Cargo.toml, then each actual binary --version with exact0.7.0-rc.1 outputs and capabilities identity-only/recovery-only/control-only/control-plane, exit0 and empty stderr
- Frontend: npm ci; npm run check; npm run build; node scripts/前端完整回归v4.mjs; node --test tests/cloud-gateway/*.test.mjs tests/delivery/*.test.mjs
- Static: python -m unittest discover -s tests/delivery -v; original16 engineering capture tests and original dependency/release contract script suites; new scripts/rc_source_assembly_tests.py and scripts/rc_source_assembly_evidence_tests.py, each with independently discovered/actual counts; the original rc_packages dpkg skip remains platform-specific and separate from delivery skips
- Native: unchanged tests/cloud-gateway/sandbox-dispatch/run_probe.py and sandbox-lifecycle/run_probe.py; cargo test --locked --manifest-path services/local-agent/Cargo.toml --test linux_sandbox; cargo test --locked --manifest-path src-tauri/Cargo.toml --test exec_input_contract inside actual isolated dbus-run-session/gnome-keyring fixture
- Browser: tests/cloud-connection-browser.py, tests/ui-refactor-browser.py, tests/policy-hooks-browser.py, tests/workspace-snapshots-browser.py using Playwright1.58.0, hosted Chrome and chromium_sandbox=True; npm ls devalue --json and npm audit --json with no filters
- Dependency: scripts/engineering_dependency_capture.py collect and verify using expected-sha/version, fresh external output/audit DB, pinned cargo-audit0.22.2; separate verifier and its finalizer receive the receipt digest from capture job outputs; capture summaries bind current SHA/tree/manifest/lock/run/attempt and retain raw findings without security acceptance
- Source inputs: original verify_metadata_transition over e61aaf2da99baccdb99db4922b39f7d8d5997096; rc_version_gate.py and release_preflight.py input-only reports; their passed flags never prove final-release eligibility
