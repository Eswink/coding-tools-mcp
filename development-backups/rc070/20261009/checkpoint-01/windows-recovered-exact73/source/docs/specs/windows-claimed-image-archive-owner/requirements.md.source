# 真实 Claim 所属镜像归档 owner 需求

## 功能概述

以实际公有 D6 `c60f9667fa8431e27fabbc497c19b4abfef5b965` 和有限108个冻结 Windows 源码/规格路径为基线，新增具体 native 归档读 lease，接到实际 Claim、三 scope permit、workspace authority 和 HCS 整包 owner。已批准 OCI 归档的哈希只验证本次实际读取的数据，不证明导入后 boot tree、scratch、可写映射排除或 native launch 权限。缺失的创建所属 boot 资源仍拒绝 HCS 创建，后续继续接真实 Guest/privateIO/wholeVM/allIO/issuer。

## 历史经验与坑

已冻结 Guest11 的目录作用和 creation16 三个 native 边界缺口保留原报告。Boundary7 修正仅组件通过、native未运行。不得用 ENV/hash/路径/JSON/VM ID、generic G 或 CloneCompletion 替代实际 nonClone grant；known file close 不是目录或 VM retirement。原 Probe metadata、first checker、自动审批拒绝和编辑顺序 erratum 不回填。

## 范围边界

本增量纳入严格相对归档选择器、两份源码固定 OCI digest/size、64KiB 增量哈希、原生 opened-root 相对读取与整包 retention、实际 native caller 接入和精确测试。实际 layer import/boot tree/scratch/VM启动/GuestIO/输出 issuer 由后续创建所属资源机制闭合；不能使用旧 Go privilege import 或用户/生产环境设置。本增量不改冻结包、root、snapshot/restore、PR98、source profile、workflow、Git index、锁文件、工具链、F2/tag/release。

## 需求列表

### FR-1: 接实际 permission owner

WHEN actual claimed native callback已验证请求、当前 caller、三个 scope并 commit permit，系统 SHALL 把实际 WorkspaceRunGrant/context/authority/input/archives 放入同一 Retained wholeBox，再首次打开归档。选择器本身不含权限；None Claim或其它 host/profile不得得到归档 owner。正常生产入口仍 DENY。

### FR-2: 验证固定归档数据

WHEN 读取 `layer0.gz` 或 `layer1.gz`，系统 SHALL 使用既有源码固定 digest/size，要求原实际 offset、每块不超过65536 bytes、累计不超预期、真实 EOF、最终 byte hash严格相等。两归档不可重排、重复、用任意 manifest/路径替换。取消/deadline/read/offset/EOF/hash失败必须 sticky拒绝，数据不形成 output或boot许可。

### FR-3: 绑定实际 root/parent/file

WHEN 准备归档，系统 SHALL 从同实际 WindowsInputAuthority acquire host/profile一致的 retained root chain，每层 relative NtCreateFile/no-reparse、实际 local fixed volume、完整 volume64/FID128、directory/file类型及单链接一致；每个新句柄先归入 wholeBox再 info/read。归档 read-only/shareREAD禁止新 write/delete handles，父链 denyDELETE；不能声称它排除了此前 writable mappings。实际 source cursor/info在每块前后与结束核对，归档root identity与原 InputLease root严格相等。

### FR-4: 明确资源退出

IF 任意 checked CloseHandle失败或 panic，系统 SHALL 保 whole actual claim/permit/context/authority/input transfer/归档manifest/uncertain raw handles；不能只保 guard/fence。只有所有归档和 input source实际 checkedclose且无 VM effect才可 complete guards/drop permission。单独取消不是 retirement。归档无新增文件/目录作用，不删除用户内容。

### FR-5: 禁止数据升级为 boot authority

WHEN 两归档数据通过，系统 SHALL 返回明确 `WINDOWS_HCS_BOOT_ASSET_OWNER_UNPROVEN` 并阻止首次 Compute API，直到新的实际 creation-owned verified boot tree/scratch producer纳入同owner。原 fixture 无归档 owner也不得借新方法 launch。不能从归档路径、哈希、ENV、host UUID、configuration或 Guest数据 mint nonClone output issuer，existing overwrite继续 DENY。

### FR-6: 真实验证边界

WHEN portable运行，系统 SHALL 留 exact named streaming/retention/parser当前源日志、命令、tool/runtime/source before/after；新功能不存在旧行为fail-first时不把缺符号编译错误当行为失败。Windows实际 root/fullFID/share/cursor/closefailure/panic/claimed caller和完整 NativeHost/HCS/所有关联组件必须未来同源CI，本地NOTRUN。不安装 compiler/privileges、不跑本机VM。

## 非功能需求

NFR-1 内存恒定一块64KiB加hash状态，不缓存3GiB归档。期限每块前后检查；同步 File::read尚不能保证底层阻塞取消中断，production deny/native全量资格保持。NFR-2 编辑前只用 LOCAL GitNexus never/index-only/drop-embeddings和 exact UID impacts；人工 native permission HIGH/既有HCS CRITICAL由root统一告知。NFR-3 所有旧失败/冻结/metadata恢复原件保留，不声称连续 whole-source clean、F2或canonical63闭合。

## 验收标准

WHEN短EOF、超长chunk、超size、错误hash、offset drift、取消或过期，系统 SHALL拒绝且无法恢复数据接受。WHEN已批准归档读取成功，系统 SHALL仍不启动HCS或签发输出。WHEN未知关闭/panic，系统 SHALL保具体 whole grant。实际 native证据不得由 portable或crossmetadata替代。

## 依赖关系

实际D6和108 overlay provenance、WindowsInputAuthority/RootLease/Opened、actual claimed三scope issuer、Retained、源码固定 Microsoft OCI归档pins、future actual Windows CI。后续 boot import/verified creation-owned stage/scratch、same created HCS Guest/privateIO、wholeVM/allIO retirement和HostOutputIssuer仍必需。
