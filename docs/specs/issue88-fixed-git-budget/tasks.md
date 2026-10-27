# 任务清单：受预算约束的固定 Git 读取

## 交付物清单

精确17路径，7修改、10新增，实际F之上1813条目。每个文件最多500行；总Git差异行上限2400，各路径差异上限之和2367。
旧1493个ID不删除或改名；新增36运行用例和12组合用例，D1541/I1202/J1202；strict303/contracts755/consumer452不变。
同树草稿不是实际F提交证据；实际F/raw/tree/parent绑定及7完整inverse、14历史字节输入必须独立复核。

## 任务列表

- [ ] 1. 完成精确边界、规格和手工CRITICAL影响复核（FR-1、FR-2、FR-3、FR-4；设计：全部技术方案）
  - 证据：`scripts/exact_build_audit.py:261` 的旧 git 使用 `execute(["git", *args], root)`；调用继承环境且无共享期限。
  - 涉及文件：本三份spec，预算60/90/70行；复用实际同树GitNexus UID结果，保留FTS/动态调用限制。
  - 独立审查精确runtime、12组合case合同、7反变换和14历史字节，不用设计宣称测试通过。
- [ ] 2. 透传同一控制并加入六项固定原生Git读取（FR-1、FR-2、FR-3；设计：预算接线、六项固定命令、有限管道）
  - 证据：`scripts/rc_artifact_consumer.py:175` 原verify_consumed_bundle调用未传已有budget；contracts:127和dependency:121继续丢失控制。
  - 涉及文件：四个现有runtime差异上限2/12/6/48，新rc_consumer_fixed_git上限420行。
  - 固定binary/环境、原生config/index预检、原错误顺序和真实child清理；省略控制保持旧route，无新删除/authority。
- [ ] 3. 加入真实Git/child/完整stage接线回归（FR-1、FR-2、FR-3；设计：测试策略）
  - 证据：`scripts/rc_publication_stage.py` 已把transport_cleanup_uncertain记为粘性清理；其生产字节不变。
  - 涉及文件：新support120、policy225、supervisor210、wiring260行；共36个唯一ID。
  - 保持真实Git、pipe/EOF、cap+1竞争、ready驱动SIG_IGN、TERM/KILL/reap、双下载及保留产物证据。
- [ ] 4. 接入有限D/I/J来源组合与只读工程工作流（FR-4；设计：有限组合）
  - 证据：`scripts/rc_pretag_stage_retirement_profile.py` 是当前最新normalize/select；原profile只能拓扑不匹配时回退。
  - 涉及文件：new profile350、cases450；latest profile差异6、cases差异24；workflow差异14。
  - 原始source读取仅做8个受影响operand wrapper加一import；完整byte inverse恢复原断言及全部旧IDs。
  - 既有Ubuntu22/24工程job从309增至357例；只读permission/触发器/超时/checkout pins不变。
- [ ] 5. 验证最终源码与实际CI，按普通门禁整合（FR-1、FR-2、FR-3、FR-4；设计：测试策略、风险）
  - 证据：原workflow按全树source-before/after和exactID inventory验证真实CPython3.12；新增case加入同一流程。
  - 涉及文件：不新增源路径；独立checkout、最多两个本地CPU队列；保留失败/源范围并复用证明相同的hosted子集。
  - focused及独立源码审查通过后draftCI与剩余矩阵并行，全部必要门禁后正常merge；禁止admin bypass。

## 需求覆盖矩阵

| 需求 | 设计章节 | 任务 |
|---|---|---|
| FR-1 | 预算接线 | 1、2、3、5 |
| FR-2 | 六项固定命令、数量上限 | 1、2、3、5 |
| FR-3 | 有界管道和已知进程所有权 | 1、2、3、5 |
| FR-4 | 有限组合、测试策略 | 1、4、5 |

## 文件变更清单

| 文件 | 操作 | 最终行/差异行上限 |
|---|---|---|
| scripts/rc_artifact_consumer.py | 修改 | 260/2 |
| scripts/rc_consumer_contracts.py | 修改 | 300/12 |
| scripts/release_dependency_contract.py | 修改 | 300/6 |
| scripts/exact_build_audit.py | 修改 | 480/48 |
| scripts/rc_consumer_fixed_git.py | 新建 | 420/420 |
| scripts/rc_consumer_git_test_support.py | 新建 | 120/120 |
| scripts/rc_consumer_fixed_git_cases.py | 新建 | 225/225 |
| scripts/rc_consumer_git_supervisor_cases.py | 新建 | 210/210 |
| scripts/rc_publication_git_budget_cases.py | 新建 | 260/260 |
| scripts/rc_pretag_stage_retirement_profile.py | 修改 | 220/6 |
| scripts/rc_pretag_stage_retirement_cases.py | 修改 | 380/24 |
| scripts/rc_pretag_git_budget_profile.py | 新建 | 350/350 |
| scripts/rc_pretag_git_budget_cases.py | 新建 | 450/450 |
| .github/workflows/issue88-publication-executor.yml | 修改 | 175/14 |
| docs/specs/issue88-fixed-git-budget/requirements.md | 新建 | 60/60 |
| docs/specs/issue88-fixed-git-budget/design.md | 新建 | 90/90 |
| docs/specs/issue88-fixed-git-budget/tasks.md | 新建 | 70/70 |

## 检查点

所有路径/ID/断言、原错误顺序、原默认kwargs、7逆变换及14历史输入在提交前重新核对；detect_changes/gencommit及独立完整树审查不可省略。
原安全门禁/默认根保留/固定主机/凭据/原收据字节不变；Windows、PR98和snapshot保留操作不属于本次授权。
