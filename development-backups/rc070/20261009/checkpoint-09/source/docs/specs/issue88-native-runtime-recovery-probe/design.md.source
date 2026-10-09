# 设计文档：issue88-native-runtime-recovery-probe

## 概述

覆盖FR-1、FR-2、FR-3、FR-4、FR-5与NFR-1/2/3。管理分支从D6创建，Pure SUT从F13还原，两个checkout及artifact目录分离。

## 技术方案

### 技术选型

| 类别 | 选择 | 理由 | 关联需求 |
|---|---|---|---|
| Runtime | Ubuntu24原生git与CPython | 实际支持检查，不安装/替换 | FR-2 |
| Source | 固定git objects、原patch、native Merkle与全manifest | 不信聊天或FETCH_HEAD | FR-1 |
| Owner | 原V5 namespace-aware pidfd/WNOWAIT/subreaper helper | 实际自有自然退出与失败退休 | FR-4 |
| Suite | 原103行runner与85/300 names | 保留原所有预算和负向断言 | FR-3 |
| CI | 只read权限、无持久凭据、扫描白名单 | 不产生Release grant | FR-5 |

### 架构设计

Carrier工作流调用restore helper，从checkout可读的immutable备份对象读取白名单数据；private SUT唯一parent F13，写树b9cf。前置原PREFIX失败即退出。controller在独立进程的私有subreaper中启动immutable runner。85所有完整向量重新核对后同源300一次；每轮ownrealm与自身前后相等，跨轮只比较稳定UID/GID/uname/boot-id，不能要求两个独立namespace相同。当前488未启用，未来新profile必须独立明确树/库存/runner/ref/预算及peer准入。

## 数据模型

| 实体/字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| Profile | literal mapping | publisher85/300 only、无输入任意code/ref | 固定源、SHA、inventory、bounds |
| WholeSource | path→mode/blob/size/SHA | 全1878、无symlink/hardlink/路径逃逸 | physical与native index相等 |
| Launch | JSON | actualpidfd/kernel/source/runtime/realm/helper/库存 | fsynced nooverwrite |
| Closure | JSON | natural0/heldZ/ECHILD/allfences才qualified | failure同样保留 |
| SafeArtifact | rawbytes+SHA | allowlist且敏感扫描通过 | 不借redactedbytes称原hash |

## API 设计

| 方法/函数 | 路径/签名 | 入参 | 出参 | 关联需求 |
|---|---|---|---|---|
| restore | rc_native_probe_restore.py | management root、fresh outside root | pure private commit与manifest | FR-1 |
| kernel/owned_family_close | rc_native_probe_kernel.py | actual owned pidfd/deadline | native identities/ECHILD | FR-4 |
| run_owned/receipt_gate | rc_native_probe_owner.py | immutable context+profile | receipt+closurequalified | FR-2/3/4 |
| main/safe_artifacts | rc_native_probe.py | fresh runner.temp root | original safe raw evidence | FR-5 |

## 文件结构

3个docs/specs/issue88-native-runtime-recovery-probe规格；.github/workflows/rc-native-recovery-probe.yml；scripts/rc_native_probe.py、rc_native_probe_restore.py、rc_native_probe_kernel.py、rc_native_probe_owner.py、rc_native_probe_original_runner.py、rc_native_probe_inventory.json、rc_native_probe_checks.py。共11新增文件，0已有production修改。

## 设计决策

### 决策1: Carrier与Pure SUT分开（FR-1）

问题：新增CI workflow会污染原1878guard。选项：修改guard；或分开管理与pure源码。决策：分开checkout，恢复真实F13+immutable两patch，原全manifest校验再private commit同源证明。理由：复用原源码审查和原计时，不改变候选。

### 决策2: 实际runtime前置支持（FR-2）

问题：本地2.43不支持原参数。选项：松绑参数/装Git；或现成GitHub原生工具实际检查。决策：检查现成runner，失败SUT0。原runner runtime()包含/usr/local/bin/git，若host没有该原路径则失败记录，不创建alias或删路径。

### 决策3: 失败有限controller（FR-3/4）

原历史runner没有whole绝对预算。新1800/7200明确是fail-only恢复supervisor，不冒充原有budget。复用V5kernel与cleanup核心语义；最小workerenv仅PATH、UTF8/locale、PYTHONDONTWRITEBYTECODE、固定GLib路径。取消先检查再Popen、finally保留真实退休与异常链。原始raw hashes、allloaded/executed/namedPASS及naturalexit是300前门。

### 决策4: 原证据安全上传（FR-5）

原85结束后封存LAUNCH、NATIVE-CLOSURE、receipt、cases3logs及controller2logs八个原文件的独立seal，保存seal SHA；300前按nofollow逐级dirFD实际重读seal和全部原文件，比对原byteSHA/size及完整JSON原对象，再运行原完整向量门。

artifact仅allowlist、最多32MB总量、禁止PEM/TLS/privatekey/secret/token值；原报告不含任意环境。扫描失败不上传原报告并FAIL；错误报告只安全类型/静态帧，不含locals或任意异常字符串。

## 测试策略

FR-1实际在当前nativeGit执行固定objects恢复，核全1878和privateparent；negativepatch/hash/path拒绝。FR-2 local原PREFIX129明确SUT0不重跑。FR-3校验原103行6259BSHA、85/300uniqueinventory与receipt负向向量阻断。FR-4 exactV5helper AST对照、ordinary自然退出/取消/TERM7KILL2/escape/lateadopt证据映射；新修改owner由peer重新审。FR-5检查YAML权限、branch、固定action、无setup/install/exporttoken，敏感PEM与secret值负向扫描。freshGitNexus/precommit范围检查和全source peer复核后才实际CI一次。

## 风险评估

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Runner原生路径或参数不支持 | HIGH | 前置failclosed/SUT0，无install |
| 信号/namespace/adoption失去闭包 | HIGH | heldrealpidfd、finite动态reap、unknown不qual |
| 备份路径被污染或不是原源 | HIGH | immutableSHA+完整native/physicalmanifest |
| 原失败被误作CI资格 | HIGH | currentlocalFAIL与freshCI结果分离 |
| artifact泄露TLS或secret | HIGH | 最小env、白名单scan、原bytes不静默redact |

## 检查清单

- [x] 全FR有具体实现与负向检查；0production edits，pure tree不变。
- [x] 明确新wholebounds、原runnerpaths和host真实失败边界。
