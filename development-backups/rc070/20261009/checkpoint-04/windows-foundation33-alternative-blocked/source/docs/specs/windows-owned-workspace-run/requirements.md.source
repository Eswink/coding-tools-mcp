# 新实现子规格：windows-owned-workspace-run / requirements

关联需求 FR-4, FR-5；父规格 windows-foundation-new。明确为新原始内容，不恢复/冒充旧文件hash。当前native生产owner与原positive gate未验证。

# 需求文档：windows-foundation-new

## 功能概述

补齐真实丢失的40路径基础为新实现，复用D6+exact73。新源码不冒充旧hash恢复。原冻结Stage11源码保持不变；本分支从未应用其有兼容阻断的prepare分支。

## 历史经验与坑

实际恢复73路径；40路径只有旧身份，没有字节。历史编译与语法parse不能代替当前类型/测试。

## 术语定义

- InputLease：持有实际根/祖先/文件句柄、原始不可变字节、检查关闭状态的非Clone owner。
- OwnedBootAssets：实际生产者创建并持有的启动与scratch资源；目前未实现，metadata不是该类型。

## 范围边界

纳入：missing40的21Rust、4Go、15规格路径及本Plan三份总规格。排除：PR98取消动作、snapshot修改、默认权限增加、用户机器原生执行、生产输出issuer、发布宣称。

## 需求列表

### FR-1: Independent actual execution root

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Independent actual execution root，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN a host is constructed THEN execution input SHALL pin its own native WindowsInputAuthority using that exact host/profile/workspace root; no snapshot target/gate provides file authority. IF pinning or exact current binding fails THEN input SHALL deny before native child opens.

### FR-2: Bounded handle-owned immutable input

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Bounded handle-owned immutable input，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN valid relative input is read THEN InputLease SHALL register each opened handle before identity/type/read validation, enforce same fixed volume and single-link regular file, read at most 1MiB in 32KiB chunks, check identity/size/cursor/cancellation/deadline before and after reads, and retain original immutable bytes through checked close. IF close/read state is uncertain THEN whole claim/permit/root/cloud/handles/bytes SHALL remain retained.

### FR-3: Detached bounded data-only transfer

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Detached bounded data-only transfer，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN transfer is requested THEN an immutable detached byte owner SHALL be bound to exact host/profile/caller/source/session/operation/input/output names and SHA256/size; repeated or mismatched session/chunks/offset/end/hash SHALL reject. WHILE native VM/output issuer is absent THEN wire transfer SHALL never authorize native input/VM/output or claim complete installation.

### FR-4: Native owner and closed writeback boundary

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Native owner and closed writeback boundary，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN real workspace execution is claimed THEN the current real three-scope local permit and actual ClaimedDispatch SHALL remain owned through root/cloud work, native read/VM cleanup and all file/native handles. IF any retirement is unknown or panics THEN whole owner SHALL retain all resources; output publication SHALL remain unavailable until a separate actual closed VM+IO+output lease issuer exists.

### FR-5: Three execution scopes versus new asset effects

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Three execution scopes versus new asset effects，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN execution consumes already genuinely provisioned owned boot/scratch assets THEN it SHALL use the original three scopes; the protected positive16assert body and request SHALL remain byteexact. WHEN a NEW archive unpack/create/scratch effect is requested online THEN the distinct operation SHALL consume real vm.assets.stage local ticket plus actual Claim before that effect. IF no concrete owned asset producer exists THEN configuration/path/hash/environment/registry metadata SHALL not create permission and native creation SHALL deny.

### FR-6: Fresh evidence and cancelled boundaries

**优先级:** Must
**用户故事:** 作为发布维护者，我需要Fresh evidence and cancelled boundaries，以便新候选的权限与真实资源证据相同。

#### 验收标准（EARS）

1. WHEN this newly written foundation is validated THEN its tests/compiler/CI SHALL bind exact fresh source revision and remain separate from old40 hashes/historical passes. PR98 cancelled10 and snapshot pause SHALL remain untouched. IF compiler/positive native/production output/install gates have not run THEN status SHALL remain BLOCKED and no tested development commit or final RC completion SHALL be claimed.

## 非功能需求

- NFR-1：单输入1MiB、32KiB块、64路径组件；无无界复制/缓存。
- NFR-2：权限与数据类型分离；实际owner非Clone/非Deserialize，默认deny。
- NFR-3：旧positive16assert、三scope请求、四默认scope、九prompt/catalog原字节保留。

## 依赖关系

复用exact73 root/nt/path/retained/owned_run/archive reader、真实authorizer/execution_gate/ClaimedDispatch和现有WorkScope；类型/Windows验证尚未运行。

## 检查清单

- [x] 六条唯一FR关联设计任务。
- [x] 原样保护、资源关闭失败、取消边界有可测要求。
- [ ] 新compiler/Windows native positive/输出与安装证据完成。
