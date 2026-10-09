# Finite proposal tasks

## 交付物清单

- 三份只读有限规格及 fresh per-symbol graph/manual-risk 摘要。
- 原 _request/_prepare_stream/_consume/_check/source SHA/AST 真实性声明；当前只有实读，没有修改。
- 独立设计意见；未来实现/普通 controls/原方法启动各另需授权。

## 任务列表

- [x] FR-1 实读原调用顺序及 stream完整 hash/rewind，区分只移 auth 与 auth+stream后 connect。
- [x] FR-2 fresh request/auth/remote/authorize/connect/stream/consume/snapshotcheck impact；识别动态0非安全0。
- [x] FR-2 明确当前 catch取消归一化、close masking、authorize未来 transport条件和 consume前 FD再核验未闭合。
- [x] FR-3 提出28有限 ordinary failure-first cases；本轮全部 NOTRUN。
- [ ] 独立设计审查及 root 具体 SOURCE 授权。
- [ ] 明确 stream 有界再核验与 before_write真实源码影响，必要新增有限规格。
- [ ] 源码实现/必要原组件 controls、完整 rawsource/runtime/native audit。
- [ ] fresh detect_changes/gencommit/source-only backup 与独立新启动审查。
- [ ] root 唯一原单方法启动/终态审核；不是85/300准入。

## 需求覆盖矩阵

| 需求 | 设计 | 后续验证 | 当前状态 |
| --- | --- | --- | --- |
| FR-1 | 两段耗时工作均在 mutation connect 前 | C01–07、C22–24 | SPEC_ONLY/NOTRUN |
| FR-2 | 保原身份/deadline/TLS/Reader/once/effect/exception边界 | C08–21、C25–28 | SPEC_ONLY/NOTRUN；provider/cancel/close风险保留 |
| FR-3 | 普通控/封存/backup/独立/root分阶段 | 各阶段独立证据 | 原85FAIL/300NOTRUN/issuer不可用 |

## 文件变更清单

当前新增 isolated 三规格、SAFE-IMPACTS、STATUS；原 pure b9cf/1878、carrier37109/1860、原 owner/runner/fixture/test assertion没有修改。源码实现尚未授权，production functions修改0；当前spec/source新增符号尚无生产资格。
