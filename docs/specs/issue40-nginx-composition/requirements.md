# 需求文档：issue40-nginx-composition

## 功能概述
为 PR114→PR89 增加显式版本 `engineering/issue40-nginx-composition-v1` 的工程组合校验；只形成本地待审候选，不授予合并、原生或发布资格。依据经 root 批准的 2026-10-05 integration-readiness packet，SHA256 `0f41eacae6296c7e6db6d8c7f5b86f419102ae686f79ded2711735c970be067b`。

## 历史经验与坑（来自记忆库）
未依赖记忆库经验。已核验现有代码与评审：P/I/L1 的旧167测试仅当前树检查失败，L0通过；452通过不能覆盖前一步失败；两次167执行不是334个唯一测试。
历史桌面夹具使用工作树字节，适配后会破坏旧 pin；必须取固定 F 的六项历史 amendment，并在当前适配器逆变换后继续全部旧断言。

## 术语定义
- F=`310ad16c8aa9cc8182c4b0f6a196184fcf34bc52`，tree=`66b0dde07e5dd83883e3978886b61a82badafcd6`，有序 parents=[`44ff88373d76b54a22d72eba17c0c7989e0be805`,`afca8585ebb231d247080b184f47ceb2012accac`]
- P=`cf3e59b4b411b7a92bb7d6ef8783c2720fb2fb1d`，tree=`fcdaef969403255b9ba6221437ea0916ac348677`，唯一 parent=F
- R=`e2e011f7f2a3a1df838bbd588106205b999db610`，tree=`c0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3`；A=唯一一层已定稿 amendment；I'=[F,P或A]；L'=[R,I']

## 范围边界
In Scope：修改两个测试适配器，新增纯校验 profile、20项测试和三份规格；精确七路径，修改2/新增5，七项均100644/blob；A应为1664项=P1659项+5。
Out of Scope：P九项源码、历史 profile/脚本、Rust/runtime/auth/renderers、版本、workflow、依赖、发行文档及无关测试；不扩大旧 ALLOWED/CAPS、旧预算、可执行位策略或父节点语法。
不执行 source commit、push、PR变更、merge、手动dispatch、FINAL、release/main合并、tag、Release、真实部署、凭据变更、PR98/Issue86变更；额外授权前停于本地评审。

## 需求列表
### FR-1: 封闭拓扑与终结式分派
**优先级:** Must；**用户故事:** 作为审查者，我要仅接受固定组合，以保持旧信任边界。
#### 验收标准（EARS）
WHEN 调用 selector THEN SHALL 仅解析一次可变 ref，先 ownership 拓扑再 desktop 拓扑；已接受拓扑的内容成功或失败均终结，仅两者 TopologyError 才进入新语法；未知 profile 版本在内容读取前拒绝。
WHEN 新拓扑成立 THEN SHALL 验证固定 F/P/R；F必须经未改动 desktop.selected_profile 及 ownership/J前驱检查；只接受精确P、唯一parent[P]的A、[F,P或A]且全树等于第二parent的I'、[R,I']且四文档覆盖的L'。
IF 锚点未知、同树伪锚点、缺失/反转/重复/额外parents、A→A2、后继、squash/rebase、嵌套或任意祖先遍历 THEN SHALL 拒绝；[R,A]、[R,L']、[F,I']、[A]均非法。
### FR-2: 完整源码与版本保护
**优先级:** Must；**用户故事:** 作为审查者，我要精确字节、模式和路径证据，防止组合扩大源码权限。
#### 验收标准（EARS）
WHEN 校验P THEN SHALL 全树恰为已验证F1650项加九项固定blob/SHA256/大小/行数；L'只允许固定R四文档替换；其余历史条目逐项完全相同，包括唯一历史desktop collector可执行位。
IF 九项任一hash/blob、四文档任一路径/字节/模式/删除、受保护条目或六个产品版本槽独立变化 THEN SHALL 拒绝；六槽保持F的`0.6.0-rc.4`，版本变化不得选择另一profile。
### FR-3: 有界 amendment 与无环 pin 引导
**优先级:** Must；**用户故事:** 作为审查者，我要完整pin加独立外部核验，而非仅预算准入。
#### 验收标准（EARS）
WHEN 校验A THEN SHALL 唯一parent[P]、恰好七路径变化、其余P条目不变；两适配器、测试、三规格共六完整blob/SHA256须先定稿再以评审字面量固定。
WHEN 完成候选 THEN SHALL 外部独立审查manifest绑定全部七blob及候选tree，尤其profile自身；禁止自认证、候选派生预期pin、可变分支pin；预算不能代替认证。
IF 超过composition500行/24变更行、desktop tests400/80、profile400、new tests480、每spec80、总delta1250或更严旧预算 THEN SHALL 停止并回到设计评审，不默扩。
### FR-4: 保留两个适配器的历史断言
**优先级:** Must；**用户故事:** 作为维护者，我要新入口兼容旧fixture且证明全部旧断言仍有效。
#### 验收标准（EARS）
WHEN 修改composition THEN SHALL 仅新增import、替换当前树test的selector、追加不交叠inventory组；_feature_profile/_selected_profile/run_inventory、Git隔离、index/worktree和其它旧test不变。
WHEN 修改desktop tests THEN SHALL 仅改setUp及两个兼容test；先验证F父/tree，再取F六项历史fixture；当前composition仅逆三片段精确恢复F，再执行全部F→X逆变换/AST断言；保留全部20旧方法及历史拒绝断言。
### FR-5: 冻结187项与独立负例
**优先级:** Must；**用户故事:** 作为审查者，我要每个拒绝边界可独立触发且不靠过滤获得绿灯。
#### 验收标准（EARS）
WHEN strict runner和普通discovery执行 THEN SHALL 各恰好同一167旧ID+design所列20新ID=187，loaded=executed=declared且无重复、缺失、过滤、skip、xfail、xpass；两次执行不叠加唯一数。
WHEN 测试非法parents THEN SHALL 先独立证明全树内容有效，再证明内容reader未调用；内容负例先证明parents有效，逐一变异全部源码/历史保护/版本/文档/amendment pins，并覆盖binary、类型/模式、symlink、gitlink、删除、重命名、额外路径和未知规格。
### FR-6: 当前候选矩阵与真实证据边界
**优先级:** Must；**用户故事:** 作为root，我要当前revision可复核证据及明确保留最终决策权。
#### 验收标准（EARS）
WHEN 定稿后验证 THEN SHALL 在独立干净A、[F,A]、[R,feature]上下文各运行187 strict/discovery、原452、deployment68、desktop129、source-backport39；完整对象库无commondir/alternates/hardlinks/shared index，清除Git重定向并禁system/global config，固定GLib并记录命令/数量/退出码/日志hash/完整树及ID审计。
WHEN 汇报 THEN SHALL 保留旧P红灯记录；P原生run37284577334 attempt1不得移记A/merge；原生、unsupported-host、installed desktop、security、release、publish、raw-zero及生产声明仍false或未证；五条历史hermetic lanes仅是将来授权merge后的观察目标。

## 非功能需求
- NFR-1：仅Python标准库、惰性数据常量及只读callback；无导入时I/O/执行、副作用或网络
- NFR-2：语义信任边界风险HIGH已报告root；新鲜符号impact与精确diff审查独立于静态LOW分数；旧模块逐字节不变
- NFR-3：每次检查绑定实际revision；失败、未运行、被阻断分别记录，不能由合成/历史结果推导原生或发布成功

## 依赖关系
复用未修改ownership/desktop和固定R覆盖检查；Probe4.0.1 fresh Plan、check_spec、fresh graph、最终diff/manifest独立评审是交付闸门。允许本地暂存、tree snapshot及staged detect_changes用于精确候选评审；source commit及publication仍需未来授权。

## 检查清单
- [x] 范围、六项FR、EARS、预算、拓扑、版本与证据边界已明确
- [ ] 当前候选实现、187矩阵、完整pins与独立外部评审完成后才允许报告通过
