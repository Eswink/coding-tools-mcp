# 设计文档：暂存源码观察的共享 Git 预算

## 概述

覆盖 FR-1 至 FR-5。复用 PR143 Reader 的所有权和监督循环，补齐既有 source 观察链。
准备源码为已验证的 7eb98b76/tree2862d635；最终组合必须等待 Windows PR144 的实际继任提交，不把同树或祖先关系当作最终绑定。

## 技术方案

### 预算与调用顺序（FR-1、FR-3）

StagedAssets.__enter__ 给 _observe 传原 activation pair；revalidate 给它传本次操作 pair。
_source 将相同对象传给 rc.verify_source、reviewed.verify 和 typed source reads；没有控制时继续旧调用与空 kwargs。
RC 验证先读六版本字段和预期版本，再解析 commit、检查 tracked diff，最后比较预期 source SHA。
随后检查全部 untracked（包括 ignored）与 cloud 版本；reviewed.verify 依次检查 provenance、祖先、manifest、完整变更清单和树。
保留 manifest 第二次读取及每条变更路径的 before/after blob 内容哈希。
最后比较 source tree、local tag OID/kind、三个 workflow blob，再执行原 live tag/run/job/artifact/receipt 观察。
控制不能丢在 provenance 分发中；受控 stable 分支明确拒绝，未传控制的 stable 默认路线保持原样。

### 固定原生操作（FR-2、FR-3）

在已有四个 read 操作、config/index 预检之上，新增以下九种 typed 方法，复用现有 HEAD tree：

| 含义 | 固定后缀 |
|---|---|
| commit HEAD | rev-parse --verify HEAD^{commit} |
| tracked clean | diff --quiet --no-ext-diff --no-textconv HEAD -- |
| all untracked | ls-files --others -z |
| ancestry | merge-base --is-ancestor BASE SOURCE |
| 单树项 | ls-tree -z REV -- PATH |
| 原始 blob | cat-file blob OID |
| 变更清单 | diff --name-status --no-renames --no-ext-diff --no-textconv -z BASE SOURCE |
| tag OID | rev-parse --verify refs/tags/TAG |
| tag kind | cat-file -t refs/tags/TAG |

操作数是 canonical40hex ID、安全有限相对路径或严格 v+RC tag；启动前拒绝不支持的形状。
不得向调用者暴露任意 argv、可接受退出码、caps、binary 或 env。保留固定 root-owned ELF、配置白名单、no-lazy-fetch、全部 inherited-env 拒绝。
第一次 tracked 工作树 diff 前执行已有 gitlink/nonzero-stage 预检；不拿忽略 ignored 文件的 status 替代旧规则。
quiet diff/ancestry 只接受0/1，1由各自调用点转换为原语义失败；其他非零退出与异常 stdout 失败关闭。
blob 保持原始 bytes；tree/path/mode/kind、NUL framing 和 tag 原比较均不可弱化。

### 资源所有权与错误（FR-3、FR-4）

RC gate 内部拥有其 commit/diff Reader；Stage 内部拥有后续 source读取 Reader；reviewed gate 在 provenance 后拥有覆盖整个 manifest循环的 Reader。
不按每条 manifest路径重新创建 owner；内部嵌套 owner 可以使用同一原期限，但不提供 caller-reader 注入或跨模块隐式上下文。
保留 EOF+exit、有限读取、known-child TERM/KILL/reap、每个已知关闭仅尝试一次及 transport_cleanup_uncertain。
已知 dirty/祖先/manifest/tag/workflow错误先于后置成功检查；_call保留 ConsumerError并清理普通 gate/OS/subprocess错误。
RC在expected-SHA语义比较与Reader关闭后、reviewed在返回值生成与owner关闭后检查成功预算；source在最后workflow比较与owner关闭后先检查再读live tag。
不在_run/typed读取层新增成功poll，不在失败unwind上poll；默认省略控制时不新增这些调用/import或时钟。
初始 source失败在创建私有根之前；后续重验保留已发生效果和粘性保留状态，不新增删除权限。
原生解析与系统调用仍只能在边界协作检查；无 hostile-writer、native sandbox 或全进程树静默保证。
本次只完成 source Git 路线预算；原API读取的独立超时和JSON/版本解析边界不在此增量内，不声称完整观察或bundle硬期限完成。

### 有界性与性能测量（FR-2、FR-5）

输出上限要与原 verifier 语义共同冻结：SHA1恰41B、类型不超过8B、单树项有限、untracked/name-status有限、blob有限，manifest仍受原8MiB限制。
初始拟定 blob64MiB、untracked/name-status16MiB和tree4096+128B；这些是待实测支持上限，不是性能通过证据。
现有 publisher_fixture 静态数据为19条变更（14A/5M）、24个existing-side blobs、5538B manifest。
完整新 observation预计87个Git child；两次 activation observation加原bundle六个child为180。
Reader现有binary身份重验会使每次observation读取本地4,082,768B binary共91次；必须真实测量原30/60s期限可行性，不先提高timeout或放松检查。
同次原生验证须确认原3s后期故障用例仍到达bundle/download目标；新增完整预算用例先于旧重型suite运行，不重复验证来凑性能证据。

### 测试与来源组合（FR-5）

复用现有真实Git/child/pipe与publisher/source-manifest fixture；现有36 native用例继续执行。
旧 staging-budget observed wrapper只增加kwargs转发；旧Git-budget六-child记录/故障限定原 _verify_bundle_bytes phase，保留全部ID和断言AST。
新增 typed操作和source预算用例覆盖完整初始/后期路径，包含ignored、manifest/tag/workflow拒绝、0/1优先级、原期限、真实reap及不确定清理保留。
不为旧fixture的core.autocrlf=false扩大支持集；新受控正例构造符合现有白名单的私有fixture，并保留不支持配置拒绝证据。
最新dispatcher由actual post144F决定；new D[F]/I[F,D]/J[R,I]只允许原四个R文档overlay，完整inverse/历史pins和原ID继续保留。
当前完整范围为19路径；最终caps、唯一ID和byte inverses必须随实测draft冻结，再做独立审查和check_spec。

## 文件结构

runtime仅修改rc_publication_stage.py、rc_consumer_fixed_git.py、rc_version_gate.py、reviewed_source_gate.py、source_provenance_gate.py。
两处既有runtime测试适配、两份新的focused runtime cases；最新profile/cases适配、new profile/cases、既有publisher workflow及本三份spec。
额外历史git-budget/stage-retirement cases仅适配三个直接读取操作数，恢复原全字节/断言AST校验；不删除测试或放宽断言。
Reader须保持清晰且<=500行；若需提取，则先报告有限新增路径，不能压缩代码来满足行数。

## 数据模型与接口

公共增量只有可选deadline/check_active与固定typed Reader方法；原观察tuple、schema、发布效果和authenticity语义不变。
无新增凭据、远程写入、授权布尔、持久访问或系统设置。

## 风险与依赖

GitNexus遗漏_call/module alias边；手工风险按source认证的CRITICAL处理，精确UID evidence与独立review一起约束范围。
Windows PR144已先整合；实际F649dc0fcb0bd299ebf7910e567e09c32b7962a9b、tree956807f8c35b6ce12272b3abcfbbd85493e9c9f9、ordered parents[7eb98b76,970b5aba]和原始commit已独立核对。所有其他原门禁与PR98/snapshot边界保持。
