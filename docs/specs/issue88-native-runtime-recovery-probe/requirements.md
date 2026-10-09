# 需求文档：issue88-native-runtime-recovery-probe

## 功能概述

为 RC 恢复维护者提供一次性、同源、原生 GitHub Ubuntu 24.04 发布器测试探针。本地原 Git 2.43 的完整 FixedGitReader.PREFIX 返回 129；本地首次85实测50 named PASS、35 non-success，一直保留，不作为 CI 通过。管理 checkout 只提供 bootstrap；待测源码始终为独立 pure b9cf、1878 files。

## 历史经验与坑（来自记忆库）

- 可复用经验：独立完整源码审查冻结02、原103行 runner、V5实际 pidfd/WNOWAIT/subreaper ordinary controls。
- 必须规避的坑：本地 Git 参数不支持；跨 invocation PID namespace 不同；children 文件不可用；等待无限、取消后启动新子进程、收据通过但原生 exit 非0、收据后扫描源码遗漏，都不能提供通过资格。
- 原首85 FAIL、旧有限11 FAIL、诊断原delegate一次和历史未知结果保留各自状态。

## 术语定义

- Pure SUT：从 F13 和两份固定 patch 还原的 b9cfb8a0b58f8e0863c764e50cf3d38920eefeae，1878 tracked files。
- Carrier：独立 D6 管理分支上的工作流、helpers、原库存与规格，不进入 Pure SUT。
- Qualified：实际全部 named PASS、原生自然 CLD_EXITED0、收据原文件 hash 和源码/工具/realm/owner 完整向量均通过。

## 范围边界

In Scope：一个固定同仓测试分支、一次 GitHub Ubuntu 24.04 probe；恢复源验证；原85门后原300一次；无敏感数据的证据白名单。
Out of Scope：生产/defaultReader/signers 更改；编译、安装、特权、主机配置；tag、Release、用户机器；替代原库存或自动重试；当前未审定的488启动。

## 需求列表

### FR-1: 精确恢复独立 Pure SUT

**优先级:** Must
**用户故事:** 作为恢复维护者，我要从真正公布的不可变备份恢复原源，以便测试实际冻结候选。

#### 验收标准（EARS）

1. WHEN bootstrap 开始 THEN 系统 SHALL 从 immutable dab238dc34d5a59f471aff935c728c1ed809cc78 的 checkpoint01/full52 和 checkpoint02/only8 读取字节并核对 SHA。
2. WHEN 在真实 F13 13cd343d942b7a68912d42a8f9235c02ed647764 应用 patch THEN 系统 SHALL 原生核对733a/1877中间树与最终b9cf/1878全部 mode/blob/size/SHA，并创建唯一 parent F13 的本地 private commit；不得将 Carrier 文件纳入树。
3. IF object、patch、任一路径/模式/字节/树不符 THEN 系统 SHALL SUT0/FAIL，不提供推测的备份或历史 runtime 信用。

### FR-2: 原生 runtime 前置门与最小环境

**优先级:** Must
**用户故事:** 作为恢复维护者，我要核实真实 runner 原生工具，以便解决具体 Git 兼容阻断而不松绑安全参数。

#### 验收标准（EARS）

1. WHEN 启动测试之前 THEN 系统 SHALL 实际执行原完整 PREFIX 与 OVERRIDES 的 --version，原生 /usr/bin/git 失败就 SUT0/FAIL；不得削弱参数、替换二进制、下载 compiler 或安装工具。
2. WHILE worker 运行 THE 系统 SHALL 使用明确最小 environment allowlist；不得继承/export 实际 token、全部环境或持久凭据；只读取固定 official GLib fixture 267679B/SHA233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5。
3. WHEN 前后证据完成 THEN 系统 SHALL 核对原 runner 要求的 native tools、源码/index、fixture、helper、每次实际 realm 均未改变。

### FR-3: 原库存同源85到300准入

**优先级:** Must
**用户故事:** 作为恢复维护者，我要实际原85与300验证，以便区分源码审查和候选通过。

#### 验收标准（EARS）

1. WHEN native runtime 前置门通过 THEN 系统 SHALL 用原103行6259B runner SHA687ec2a408507284b557806569d6f5df0ead625b9c282b9c8bbb74782d633f0a 运行85 exact unique names一次。
2. IF 原85 qualified 完整向量、封存的seal SHA及实际重读的全部原始receipt/LAUNCH/nativeclosure/8rawfile hashes 或自然 exit0 有任一不满足 THEN 系统 SHALL 不启动300且保留失败，不重跑85。
3. WHEN 同源85 qualified THEN 系统 SHALL 仅一次运行原300 unique inventory267+13+20；named loaded/executed/passed相等、无skip/xfail/xpass/负向subtest失败、所有source/runtime/native向量均通过才有资格。

### FR-4: 有限原生自有进程与取消

**优先级:** Must
**用户故事:** 作为恢复维护者，我要私有有限 native owner，以便超时和取消也保留真实退休边界。

#### 验收标准（EARS）

1. WHILE 运行 THE 系统 SHALL 保留所有原 test/operation timers，新增 fail-only whole controller85=1800s、300=7200s；超界仅失败，不延时/重试。
2. WHEN 取消或异常 THEN 系统 SHALL sticky cancel、取消前不启动child、用真实 pidfd/starttime/native PID与proc namespace绑定的自有 leader、TERM7/KILL2、dynamic adopted children family2 退休至真实 ECHILD；任何未知标FAIL/UNKNOWN。
3. WHEN 自然通过 THEN 系统 SHALL 证明 CLD_EXITED0、si_pid与created/held identity、heldZ、私有subreaper ECHILD；不得用目录为空、合成 grants 或别的 profile 闭包代替。

### FR-5: 只读工作流和安全原证据

**优先级:** Must
**用户故事:** 作为恢复维护者，我要可独立审阅的源与安全证据，以便真实 CI 不泄露测试 TLS key 或实际凭据。

#### 验收标准（EARS）

1. WHEN workflow 运行 THEN 系统 SHALL 只contents:read、同repo固定测试分支 push、固定 checkout actionSHA、persist-credentials:false；不得tag/Release/生产授权。
2. WHEN 上传 artifact THEN 系统 SHALL 只白名单 receipt/log/identity/hash 报告，先敏感值与PEM/privatekey扫描；失败不上传，原字节hash不可静默改写；不上传临时工作区、TLS/cookies/env。
3. WHEN 提交前 THEN 系统 SHALL fresh impact、check_spec、真实必要静态/source-restoration checks、独立冻结审查、detect_changes、gencommit，非强推 draftPR并检查真实 CI。

## 非功能需求

- NFR-1（性能）：控制器严格有限，Git元数据bootstrap命令30秒，workflow envelope180分钟大于原85+300150分钟及有限cleanup；不改SUT计时。
- NFR-2（安全）：不读取或修改外国进程；无privilege/compiler/install，token不进入worker，不发布。
- NFR-3（兼容性）：普通Linux CPython3.12、实际native Git支持全安全参数；不预设 runner image Git版本或 /usr/local/bin/git 实体存在。

## 依赖关系

固定已回读GitHub checkpoint01+02、原库存与原runner、冻结02全源码静态审查、V5六项ordinary controls，native GitHub hostedUbuntu24。

## 检查清单

- [x] 原失败与未知保留、范围固定、五项FR可验收。
- [x] 全部FR将在design与tasks逐条关联。
