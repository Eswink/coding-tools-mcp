# 任务文档：windows-foundation-new

## 任务总览

当前仅context/spec准备；新实现与fresh compiler/native尚未通过。

## 任务列表

- [ ] T1（FR-1, FR-2）：fresh graph/impact、HIGH通知；实际opened root/input owner/lease、boundedchunks，注册current NativeToolHost，原scope权限不改。
- [ ] T2（FR-3）：Detached InputTransfer exactbinding+1MiB/32KiB边界，新增数据和Windows租约回归测试。
- [ ] T3（FR-3）：Go纯数据传输状态及实际句柄身份验证，执行available compiler或source-qualified GitHub CI，绝不本机VM。
- [ ] T4（FR-4）：输出defaultdeny+不存在issuer的逆向测试；whole owner unknown/panic保留。
- [ ] T5（FR-5）：单独具体CI OwnedBootAssets producer边界/spec；原positive保持byteexact且未producer前BLOCKED。
- [ ] T6（FR-6）：真实fresh syntax/types/data/Windows necessarytests、peer review、detect_changes/gencommit后小步commit/非强推+真实CI，required未过不宣称tested。

## 测试任务

- [ ] 原positive全文SHA、16assert、三scope与默认权限字节守卫（FR-5, FR-6）。
- [ ] 1MiB/块限/重复hash-offset身份、data-only无native权限（FR-2, FR-3）。
- [ ] Windows actualhandle根/卷/link/reparse/cancel/cursor/closeunknown（FR-1, FR-2, FR-4）。
- [ ] 完整必要compiler和Windows38/组合门禁真实fresh源码（FR-6）。
- [ ] 原native16assert真实运行无skip/xfail/降级（FR-5）。

## 交付物清单

40新源路径、此Plan3规格、fresh impacts、exact source/patch manifest、真实失败和CI结果、未解门禁列表。

## 验收清单

- [ ] 六FR均有独立真实证据。
- [ ] check_spec、necessarytests、peer/detect/gencommit全部通过。
- [ ] RC release/public anonymous install完成前不报告项目完成。

## 需求覆盖矩阵

| 需求 | 任务 | 必要证据 |
|---|---|---|
| FR-1 | T1 | actual root conflict/opens |
| FR-2 | T1,T2 | boundedread/closeunknown |
| FR-3 | T2,T3 | exactbinding/offset/hash |
| FR-4 | T4 | output defaultdeny/retained |
| FR-5 | T5 | protected16assert +actualnative |
| FR-6 | T6 | fresh CI/type/review |

## 文件变更清单

- docs/specs/independent-unqualified-windows/design.md
- docs/specs/independent-unqualified-windows/requirements.md
- docs/specs/independent-unqualified-windows/tasks.md
- docs/specs/windows-execution-opened-root/design.md
- docs/specs/windows-execution-opened-root/requirements.md
- docs/specs/windows-execution-opened-root/tasks.md
- docs/specs/windows-execution-transfer/design.md
- docs/specs/windows-execution-transfer/requirements.md
- docs/specs/windows-execution-transfer/tasks.md
- docs/specs/windows-owned-workspace-run/design.md
- docs/specs/windows-owned-workspace-run/requirements.md
- docs/specs/windows-owned-workspace-run/tasks.md
- docs/specs/windows-private-workspace-stream/design.md
- docs/specs/windows-private-workspace-stream/requirements.md
- docs/specs/windows-private-workspace-stream/tasks.md
- services/windows-vm-broker/transfer.go
- services/windows-vm-broker/transfer_identity_linux_test.go
- services/windows-vm-broker/transfer_identity_windows.go
- services/windows-vm-broker/transfer_test.go
- src-tauri/src/tools/cloud_host.rs
- src-tauri/src/tools/cloud_host/tests.rs
- src-tauri/src/tools/cloud_host/windows_input.rs
- src-tauri/src/tools/cloud_host/windows_input_tests.rs
- src-tauri/src/tools/cloud_host/windows_workspace_tests.rs
- src-tauri/src/tools/windows_vm.rs
- src-tauri/src/tools/windows_vm/input/chunk_tests.rs
- src-tauri/src/tools/windows_vm/input/chunks.rs
- src-tauri/src/tools/windows_vm/input/lease.rs
- src-tauri/src/tools/windows_vm/input/mod.rs
- src-tauri/src/tools/windows_vm/input/owner.rs
- src-tauri/src/tools/windows_vm/input/publication_tests.rs
- src-tauri/src/tools/windows_vm/input/tests.rs
- src-tauri/src/tools/windows_vm/input/transfer.rs
- src-tauri/src/tools/windows_vm/input/transfer_tests.rs
- src-tauri/src/tools/windows_vm/output_stage/gate.rs
- src-tauri/src/tools/windows_vm/output_stage/mod.rs
- src-tauri/src/tools/windows_vm/output_stage/native_tests.rs
- src-tauri/src/tools/windows_vm/output_stage/nt.rs
- src-tauri/src/tools/windows_vm/output_stage/owner.rs
- src-tauri/src/tools/windows_vm/output_stage/tests.rs

总Plan额外三规格 paths docs/specs/windows-foundation-new/{requirements,design,tasks}.md。
