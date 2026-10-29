# 任务清单：共享下载期限与取消
## 概述
按 FR-1、FR-2、FR-3、FR-4 与设计章节实施一个现有下载器前置能力。
## 交付物清单
预计新建 6 文件、修改 8 文件；规范路径共 14，final/delta 上限如下，实际总增删≤2000。
## 文件变更清单
| 文件 | final/delta | 操作 |
|---|---:|---|
| `scripts/rc_consumer_transport.py` | 400/200 | 修改 |
| `scripts/rc_pretag_join_once_tests.py` | 498/2 | 修改 |
| `scripts/rc_consumer_proof_fixtures.py` | 85/40 | 修改 |
| `scripts/rc_pretag_ownership_tests.py` | 385/12 | 修改 |
| `scripts/rc_pretag_publication_adapters.py` | 260/8 | 修改 |
| `scripts/rc_pretag_final_admission_profile.py` | 270/6 | 修改 |
| `scripts/rc_pretag_final_admission_cases.py` | 430/55 | 修改 |
| `.github/workflows/issue88-publication-executor.yml` | 120/40 | 修改 |
| `scripts/rc_consumer_download_budget_cases.py` | 480/480 | 新建 |
| `scripts/rc_pretag_download_budget_profile.py` | 400/400 | 新建 |
| `scripts/rc_pretag_download_budget_cases.py` | 410/410 | 新建 |
| `docs/specs/issue88-download-budget/requirements.md` | 40/40 | 新建 |
| `docs/specs/issue88-download-budget/design.md` | 70/70 | 新建 |
| `docs/specs/issue88-download-budget/tasks.md` | 60/60 | 新建 |
## 任务列表
- [ ] 1. 扩展父进程期限与活动检查并保持原清理字节
  - 证据块：scripts/rc_consumer_transport.py:223 `owner = _Download(clock() + TOTAL_TIMEOUT, clock)`；:151 `process.wait(timeout=remaining(self.deadline, self.clock))`。
  - 涉及文件：transport 与新 download_budget_cases，预算见上表；需求 FR-1、FR-2；设计 API 设计。
- [ ] 2. 实施精确历史逆变换与有限候选分派
  - 证据块：scripts/rc_consumer_proof_fixtures.py:24 `info.st_size != size`；:28 `hashlib.sha256(data).hexdigest() != digest`。
  - 涉及文件：proof_fixtures、ownership_tests、join_once_tests、publication_adapters、final_admission_profile/cases 与新 profile/cases，预算见上表；需求 FR-3；设计 历史来源与精确组合。
- [ ] 3. 登记真实子进程测试和只读工程清单
  - 证据块：.github/workflows/issue88-publication-executor.yml:63 `names = admission.inventory()`；原 workflow 已保存 loaded/executed 与 source-before/after。
  - 涉及文件：workflow、两个新 cases；预算见上表；需求 FR-4；设计 测试策略。
- [ ] 4. 核验 D/I/J、源 pin、旧 ID、远程 CI 并按授权工程整合
  - 证据块：scripts/rc_consumer_transport.py:239 `if not owner.cleanup():`；原 cleanup 的失败覆盖主错误，不可绕过。
  - 涉及文件：本三份规格与上述路径；需求 FR-1、FR-2、FR-3、FR-4；设计 风险评估。
## 需求覆盖矩阵
| 需求 | 任务 | 验收 |
|---|---|---|
| FR-1 | 1,4 | 默认/显式/边界/巨大值与真实进程期限 |
| FR-2 | 1,4 | 取消、回调错误、EOF区分、清理不确定及迟到成功拒绝 |
| FR-3 | 2,4 | 八个逐字节逆变换、七个历史 passthrough、拓扑/源/预算负面测试 |
| FR-4 | 3,4 | 原1304及新增24、D1328/I989/J989、hosted144与既有门禁 |
## 检查点
- [ ] check_spec、人工 CRITICAL 影响与独立设计审查通过后实现。
- [ ] 必要聚焦测试与精确源审查通过后草稿 PR；独立 CI 和剩余本地矩阵并行。
- [ ] 所有必要门禁通过后普通 merge；核验父序、树、四文档 overlay 与五个 postmerge checks。
## 检查清单
保持 worker/default/cleanup/held sources；没有新文件删除或发布激活；未完成验收必须如实保留。
