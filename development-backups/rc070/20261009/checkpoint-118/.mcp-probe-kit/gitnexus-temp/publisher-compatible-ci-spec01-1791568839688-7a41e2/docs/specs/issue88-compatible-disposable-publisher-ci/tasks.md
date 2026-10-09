# Read-only compatible CI tasks

## 交付物清单

- 三份新范围规格：真实Git2.55.0安装与原noinstall Probe阶段明确区分。
- 原BINARY/PREFIX/RUNTIME/runner/inventory/restore/nativeowner/receiptgate/schema准确只读摘要。
- 合法genuine安装、真实CI运行域、source与证据持久化链的明确OPEN。

## 任务列表

- [x] FR-1 纠正工具版本为实际2.55.0，不借2.51；旧NFR不安装冲突显式列出。
- [x] FR-2 实读原Reader BINARY=/usr/bin/git、RUNTIME还需/usr/local/bin/git；不会PATHshim/移flag。
- [x] FR-2 原schema/source恢复/精确6259B runner/1800+7200原nativegate实读。
- [x] FR-3 原8raw严格重读到300/FAIL保留、安全artifact私有原证据OPEN。
- [ ] 核真正存在的compatible nativebase/image/daemon权限/compiler/GNUmsgfmt/native capabilities（本轮不探测主机、不启动Docker）。
- [ ] 新CI-only helper/entry与路径参数有限source范围、freshimpact/ordinarycontrols/独立设计/root授权。
- [ ] source-onlybackup、真正一次CI normalpush；不空提交/借历史rerun。
- [ ] 本轮genuinebuild/install及strictpreconditions完整raw/source/runtime审查。
- [ ] root唯一原85→严格8raw再核→300，原失败不可覆盖/重跑。

## 需求覆盖矩阵

| FR | 设计 | 当前状态 |
| --- | --- | --- |
| FR-1 | 新disposable准备scope/官方源码/GPG/完整makeinstall | READONLY/NOTRUN，原noinstallNFR仍保护 |
| FR-2 | 原/usr/bin保留、真实/usr/local新装、sourceb9cf/runtime/native域 | READONLY/NOTRUN；具体image/工具权限UNKNOWN |
| FR-3 | 原85/8raw/nativevector准入300+安全private evidence | READONLY/NOTRUN；旧85FAIL/300NOTRUN |

## 文件变更清单

只有isolated三规格/摘要；原workflow/carrier/reader/runner/kernel/owner/restore/inventory/production source0变化。安装genuineGit的CIadapter/Dockerfile/workflow没有source稿；必要新source的AST/path/constants真实性需另声明，不能自称复用原absolute本地helper不变。新builder/container运行和任何hostinstall均未授权执行。
