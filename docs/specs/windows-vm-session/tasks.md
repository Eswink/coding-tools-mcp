# 任务清单：Windows VM session

## 概述

Concrete Rust/Go ownership, synthetic-only evidence, no production enablement. Existing measured source is 18f2aaaf; production baseline is 8bdd5f32. No local Windows/Rust compiler is available; native build/test claims require Actions evidence.

## 交付物清单（Scope-lock）

19 paths, at most 3,776 changed/new lines in aggregate, all source files below 500 lines; individual ceilings cannot all be saturated at once. Exactly one existing file changes: module registration. Five implementation tasks and two verification/review tasks below.

## 任务列表

- [x] 1.1 Read actual PR89 NativeGuard/cloud admission/root sources and preserve invariants; read measured Go ownership/policy/stream/quarantine sources. _需求: FR-1, FR-3, FR-4_ · _设计: 技术方案_
- [x] 1.2 Complete specification, exact upstream impacts and manual HIGH pre-edit review. _需求: FR-1, FR-7_ · _设计: 风险评估_
- [ ] 2.1 Add private Rust session/strict protocol and paired native guard ownership within listed caps. 证据块: native_drain.rs:48,107,114,136; current tools/mod.rs. _需求: FR-1, FR-2, FR-3, FR-6_ · _设计: API 设计_
- [ ] 2.2 Extract fixed Go HCS owner/guest/channels/quarantine without registry/canary code. 证据块: measured prototype.go:223; policy_host.go:243; policy_session.go:69; surface_host.go:49. _需求: FR-2, FR-4, FR-5, FR-6_ · _设计: 技术方案_
- [ ] 2.3 Add exact pins/preparation/native workflow; no lock or dispatcher changes. _需求: FR-1, FR-7_ · _设计: 文件结构_
- [ ] 3.1 Run compiled inventory, 16 Rust/12 Go pure tests and two sequential native cases; record actual counts and unrun stages. _需求: FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7_ · _设计: 验证与迁移_
- [ ] 3.2 Review exact final source, staged impact/gencommit and source-bound artifacts; preserve false admission/qualification flags. _需求: FR-6, FR-7_ · _设计: 风险评估_

## 检查点

- [ ] Before code: check_spec passes and root reviews exact specification/impact.
- [ ] Before import: native production Rust check, warnings-as-errors build, fmt, compiled test inventory and all pure tests pass; Go broker/guest builds pass.
- [ ] Before reporting: two separate known VM completions, pipe joins, root/cloud fence outcomes and quarantine disposition verified from actual artifact; unknown stages are not PASS.

## 需求覆盖矩阵

| 需求 ID | 设计章节 | 任务编号 | 状态 |
|---|---|---|---|
| FR-1 | 技术方案、设计决策 | 1.1,1.2,2.1,2.3,3.1 | Spec |
| FR-2 | 数据模型 | 2.1,2.2,3.1 | Spec |
| FR-3 | API 设计 | 1.1,2.1,3.1 | Spec |
| FR-4 | 技术方案 | 1.1,2.2,3.1 | Spec |
| FR-5 | API 设计 | 2.2,3.1 | Spec |
| FR-6 | 风险评估 | 2.1,2.2,3.1,3.2 | Spec |
| FR-7 | 验证与迁移 | 1.2,2.3,3.1,3.2 | Spec |

## 文件变更清单

| 文件 | 操作 | 行数预算 | 说明 |
|---|---|---|---|
| src-tauri/src/tools/mod.rs | Modify | +4 | Private Windows module only |
| src-tauri/src/tools/windows_vm.rs | Add | 350 | Concrete child/guard owner |
| src-tauri/src/tools/windows_vm/protocol.rs | Add | 495 | Typed bounded frames/state |
| src-tauri/src/tools/windows_vm/tests.rs | Add | 480 | 16 pure Rust cases |
| src-tauri/src/tools/windows_vm/native_tests.rs | Add | 240 | Two explicit serial VM tests |
| services/windows-vm-broker/main_windows.go | Add | 190 | Host entry/import dispatch |
| services/windows-vm-broker/owner_windows.go | Add | 330 | Concrete HCS ownership |
| services/windows-vm-broker/channels_windows.go | Add | 215 | Retained supervisor streams |
| services/windows-vm-broker/guest_windows.go | Add | 150 | Fixed guest fixtures |
| services/windows-vm-broker/protocol_windows.go | Add | 280 | Duplicate-aware shared wire |
| services/windows-vm-broker/quarantine_windows.go | Add | 200 | Synthetic retained roots |
| services/windows-vm-broker/owner_windows_test.go | Add | 480 | 12 pure Go cases |
| services/windows-vm-broker/upstream-defaults.patch | Add | 12 | Exact reviewed patch |
| services/windows-vm-broker/inputs.json | Add | 40 | Immutable official pins |
| scripts/prepare_windows_vm_session.ps1 | Add | 105 | Fixed builds/acquisition/import |
| .github/workflows/windows-vm-session.yml | Add | 106 | Standard disposable Windows job |
| docs/specs/windows-vm-session/requirements.md | Add | shared 240 | Requirements |
| docs/specs/windows-vm-session/design.md | Add | shared 240 | Ownership and trust contract |
| docs/specs/windows-vm-session/tasks.md | Add | shared 240 | Scope and validation |

## 交付前自检

- [ ] Exact path/line scope, no placeholders, spec and implementation agree.
- [ ] Rust duplicate known fields and nested Go duplicate fields actually fail; unknown/trailing/depth/aggregate bounds fail.
- [ ] Start uncertainty, wrong source/session/VM/sequence, guest cleanup spoof, missing cleanup, lost caller and quarantine ordering tested.
- [ ] Cargo/npm/Go locks and existing execution/root/admission/native-drain/snapshot sources unchanged.
- [ ] Retained-file image check explicitly does not claim production path authority; no public constructor/route activates this owner.
- [ ] No repeated static canary suite, new registry keys or unapproved host/network changes.
