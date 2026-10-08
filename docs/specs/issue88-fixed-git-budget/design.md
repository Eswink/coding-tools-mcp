# 设计文档：受预算约束的固定 Git 读取

## 概述

覆盖 FR-1、FR-2、FR-3、FR-4。基线为实际 F 8bdd5f327b4603c5570dc764e2d62fecbe6e02d2，不能用同树的旧 D 替代提交身份。
预算已有来源；本设计把现有调用链中的四个 Git 读取接入同一生命周期，同时用两个必要原生预检限制 helper 启动条件。

## 技术方案

### 预算接线（FR-1）

四个既有模块透传可选 deadline/check_active；空控制分支仍使用空 kwargs 和旧 execute 路由。
exact.verify 的原有验证体移入私有 `_verify`；受控入口先验证 expected SHA，再建立一个内部 Reader，直至后续 ls-files 完成。
公开 git/source_identity 可使用相同可选控制，但不能提供 binary、环境、命令、launcher、reader 或新的时限。
Reader 是可信进程内私有边界，不声称抵御任意 Python 猴补丁。

### 六项固定命令和原错误顺序（FR-2、FR-3）

1. 原生 `config --null --no-includes --file=/proc/self/fd/<owned-config> --list`，从已验证 `/` 且 `/.git` 不存在的仓库外目录执行。
2. 原 `rev-parse HEAD`；先判断 wrong_checkout_sha。
3. `ls-files --stage -z --no-recurse-submodules`，拒绝160000 gitlink及非零stage。
4. 原 `status --porcelain --untracked-files=all`；真实 staged/unstaged/untracked 保持 unclean_source，ignored语义不变。
5. 原 `rev-parse HEAD^{tree}`。
6. 原有 envelope/stream/metadata 校验确实到达后才执行原 `ls-files`。

每项固定带 no-pager/no-replace-objects/no-optional-locks/no-lazy-fetch；不支持能力直接失败，无降级或第七次版本命令。
仓库命令使用保留 dirfd 指向的明确 git-dir/work-tree。禁止协议、helper、hook、fsmonitor、untrackedCache，禁止继承外部 GIT、loader、PATH、pager、askpass、SSH、trace、token 值。
配置由原生 Git 解析，程序只核对有限输出键值；未知、重复、多行、隐式值、include/filter/credential/remapping/submodule/extension全部拒绝。
白名单仅支持format0/barefalse、原样常见布尔值、有限ASCII惰性name/email/origin和固定fetch/branch形状。
.git须实际独立目录，nofollow保留身份，拒绝gitfile/commondir/alternates/grafts/promisor/config.worktree/split index等间接能力。
元数据扫描仅接受声明根名字、合法对象与pack名字；objects根不能放任意普通文件。
固定 `/usr/bin/git` 经root-owned不可组/全局写父目录nofollow打开，普通单链接ELF可执行文件；每次启动前核对保留身份及观察SHA256。
观察SHA256是普通替换检测，不是上游内容pin；固定已安装原生Git及无并发源码写入是显式前提。

### 有界管道和已知进程所有权（FR-3）

Popen成功立即登记所有权，然后才做回调/selector设置。真实EOF和退出都必要，任意一个独立到达不能判成功。
selector最多25ms等待；每次读取最多64KiB且剩余上限加一，超限在后置回调前失败；所有预检输出也受限。
错误返回保持原源码/证据错误类型；新支持边界使用固定 ConsumerError，不返回stderr/config/env。
失败清理只处理已知子进程，用独立2秒上限、250ms TERM后KILL/reap，无调用方回调，不续期原操作。
成功且已reap的退出无额外时钟；selector/pipe/FD关闭各一次，模糊所有权不重试。
清理不确定覆写主错误为 transport_cleanup_uncertain，既有Stage粘性处理保留私有字节；无新增删除。
不把leader退出当作进程树静默；通过固定native命令/配置/对象和实际sentinel测试建立无helper假设。
系统调用/原生解析只在返回后检查，仍属协作预算，不是硬解析器终止保证。

### 数量上限（FR-2、FR-3）

config输入/输出各65536B；HEAD/ref文件4096B；其他根元数据4MiB；index64MiB。
index-mode/status/ls-files stdout各16MiB，HEAD/tree stdout恰40小写hex加LF。
Git ELF64MiB，以64KiB哈希；普通对象64MiB、pack1GiB仅stat；条目262144、FD1024、层级64、路径4096B、组件255B。
实际F测量：158元数据条目、index207839B、config92B、index输出168793B、ls-files输出91121B、最大pack8838218B，均低于边界。
未来真实测试必须证明适用夹具也满足上限；以上测量不是新实现的运行证明。

### 有限组合（FR-4）

D[F]、I[F,D]、J[R,I]，J仅替换既有四个R文档；未匹配拓扑才走旧profile，匹配后内容错误不可回退。
新层只修改最新retirement normalizer/selector与其必要原始source读取operand；全字节反变换恢复旧文件。
7修改路径逐一反转到实际F字节；14历史输入保持为确定输出，未知变体拒绝。
17路径/1813条目/2400差异行；原1493+新48=1541，I/J1202，publisher357；strict303/contracts755/consumer452保持。
新层16个非self源码pin与独立完整树审查绑定self，旧内容验证始终fresh；不扩大缓存。

## 文件结构

四个现有runtime模块：rc_artifact_consumer、rc_consumer_contracts、release_dependency_contract、exact_build_audit。
新增rc_consumer_fixed_git及一个fixture support、三组12例runtime测试；新增rc_pretag_git_budget_profile.py / rc_pretag_git_budget_cases.py。
只改最新stage_retirement profile/cases和既有issue88-publication-executor workflow的有限清单/回归段。
三份本规格；完整路径和单文件预算见tasks.md。

## 数据模型与接口

无外部持久化schema变更。可选keyword deadline/check_active贯穿现有调用；内部Reader拥有descriptor/child/pipe/selector。
缺失或不支持输入失败关闭；不添加可由调用者设置的eligibility或mutation许可。

## 测试策略

36新增runtime：12真实Git策略/配置/脏源码，12真实child/pipe/trickle/TERM/KILL/reap，12完整bundle与双下载stage预算。
12新增组合覆盖F/raw/tree、路径/pin/上限、7全字节inverse/14历史、错误不回退、原ID/断言保留、工作流只读与异常失败。
延迟SIG_IGN子进程先读真实ready字节再启动测试期；独立startup-inclusive覆盖保留。cap+1例同时武装取消，验证错误先后。
完整D/I/J和真实Ubuntu22/24 CPython3.12工作流；可证明同源同命令同ID时复用hosted子集，明确混合覆盖。

## 风险与限制

严格支持集可能拒绝普通但不在白名单的仓库；不得自动放宽、修复配置或fallback。
另一条_observe Git链、解析器系统调用中途、全部bundle/native真实性和最终发布仍未完成；本增量不改变全局阻断。
GitNexus FTS不可用，复用精确同树新索引和UID影响，动态调用补充AST逐点检查；完整独立审查与manual CRITICAL必需。
