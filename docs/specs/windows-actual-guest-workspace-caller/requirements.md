# 实际 Guest workspace 调用需求

## 功能概述
在 Windows guest 构建的真实 main 新私有 --guest-workspace 模式中接 receiveGuestWorkspaceInput、真实命令、原输出句柄写入、实际 FID/hash/单次数据流返回。此阶段仅单个 ASCII leaf 输入与标准输出 artifact，不打开宿主目录，不是 host workspace grant，不是 wholeVM/输出 issuer。宿主生产调用仍 DENY。

## 需求列表
- FR-1 私有有限闭合控制合同：<=4096 字节 JSON 控制帧；严格重复字段/未知字段/UTF8/类型/路径/source+session+operation/binding/hash检查。输入 stream 72 header/32KiB chunk/1MiB/真实 EOF 保留；旧 guest JSON 65536/aggregate1MiB 及 --guest/--child 行为不变。
- FR-2 执行前输入只读：原 RW 句柄→独立 readonly noDELETE pin→checked writer close→相同完整 FID128/volume64 readonly shareREAD reopen；保留 immutable bytes并重复 observe；任何冲突/取消/未知 close 不启命令。
- FR-3 真命令 producer：新的整包 guest owner 在 mkdir/open/input/output/process 等效果前强注册；固定 private root 下只创建独立 operation 临时目录；原 create-only output 持有真实句柄；PowerShell cmd<=2048 bytes/stdin<=1024/deadline<=30s，stdout<=1MiB/stderr<=8192且写入由原 owner 有界 chunk完成。command 不推断 native 权限。
- FR-4 命令真实 Wait 和该命令 stdin/stdout/stderr copy goroutine join 完成之后，再重复 actual input identity/hash、freeze output fullFID/hash、方向2单次 wire；取消/非零exit/IOoverflow/WaitDelay/malformed/unknown/panic失败无数据成功。发布前 input/output/parent 所有源句柄明确checked close；unknownclose/panic保留整包 command、raw handles、manifest、input和output不可变byte副本。不把该 Wait 等同 wholeVM 或 descendant quiescence。
- FR-5 Host仍 failclosed：Guest metadata/FileIDs/bools/JSON均 data，不能mint native grant或Rust seal；创建返回的实际 HCS_SYSTEM + async create completion + wholeVM exit +全部IO/sourceclose +同源实际权限链和可信非Cloneissuer未接前任何宿主写入 DENY。已有目标替换DENY，snapshot/restore/PR98持原暂停边界。

## 非功能需求
新 native cases NOTRUN，不操作本机 Windows/VM/HCS/admin/ACL/网络策略或安装编译器；portable meaningful fail-first与旧 data regressions保留具名receipt；Go精确1.24.13，源码完整离散 census前后/有限patch/独立review，actualF2未知UNSEALED。人工HIGH已root披露，6freshGitNexus LOW下界不可作为总体小风险。不得将组件crossPE/type/fixture当真实VM或release通过。

## 依赖关系
冻结 caller10/explicitIO14；既有 guest input/output registered owner、workspace_stream数据协议；后续creation-owned nativeHCS/rootgrant/wholeIO retirement issuer；canonical63当前0。旧冻结包/root/sourceprofile/WF不写。

## 验收标准
WHEN 私有workspace控制请求有效时，系统 SHALL 选择新模式并只在全部严格control和stream检查通过后准备guest输入；无效请求 SHALL 拒绝且无native权限。WHEN 进入实际命令前，系统 SHALL 保持同FID readonly pins并确认旧writerclose；UNKNOWN SHALL 拒绝命令。WHEN 命令结束时，系统 SHALL 等真实processWait和该命令IOjoin，所有源句柄checkedclose后才发布bounded数据；UNKNOWN/panic SHALL 留 wholeguestowner。WHERE 整VM/真实NativeGrant/退役链未完成时，系统 SHALL 拒绝任何宿主输出issuer/写入或生产资格。
