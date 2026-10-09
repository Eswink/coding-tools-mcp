# Compatible disposable publisher CI — source-only design

## 概述

FR-1/FR-2/FR-3新有限准备范围，当前只读。旧rc-native-recovery-probe workflow的no compiler/install scope原样保留，不伪称新genuine install没有发生。当前观察不是未来资格：stockCI完整/usr/bin flags曾成功而/usr/local/bin/git缺失，说明这个具体runtime要求未满足，不能因此替换系统Git或重新运行已成功的本地V4工具。

## 技术方案

### 合法候选运行域与前置STOP（FR-1）

优先候选是一次全新的hosted ubuntu-24.04 setup-only job（run37913922195实际已有systemGit full flags/Python3.12/openssl，仅缺usrLocalGit）；历史证据不能代本次前置。备用候选是同一新CI job中的新disposable容器/文件系统：builder阶段验证官方Git2.55.0并完整build/install到容器里的预先不存在/usr/local Git安装项，保其已存在原/usr/bin/git全部identity；probe阶段只读取真已装runtime、执行原source恢复/owner/runner。Setup所有安装事实由单独新controller记录，不调用原probe未改NFR作whole-run证明。

本轮公开只读metadata已固定buildpack-deps:trixie的amd64 digest，详FIRST-PREPARATION-SCOPE01；它仅候选，真实dependency/runtime/daemon/native权限仍UNKNOWN，不能从Dockerfile包名推定兼容。缺Python3.12/Rust/GNUmsgfmt等角色即BLOCKED0SUT，不在Git安装scope临时apt/sudo/下载compiler填补。若选择hosted runner直接/usr/local目录，必须实际证明可在限定新路径无sudo/权限变化安装，不凭典型runner具有sudo推定授权；否则选择新isolated owned container scope由root另授权。容器root创建的是容器真实filesystem对象，不是publisher权威；不能修改宿主/usr目录、给worker生产token、mount用户目录、借另cargo进程mintgrant或探测会话。不能把仅新/usr/local Git装好当原/usr/bin nativeflags成功，后者必须独立实测且前后原字节不变。

真实官方source/sign/key每次CI重新下载并校验/签名；禁止复制本地V4 ELF或借其PASS。完整工具依赖与compiler/native loader/GNUmsgfmt身份必须本次固定，V4 helper有本地绝对路径/Toolchain SHA常量，**不可未经新参数/ASTscope审查直接在CI换constants或照用而称exact原helper**。新CI-only adapter如必要，原4991/Makefile/PO、安全flags和boundedsourcephase逻辑需比对、新增路径/identity参数需新impact/普通controls/freeze。现不写adapter。

两真实owned configs FILEorigin：core/config.mak和git-gui/config.mak同真正GNUbase无--check，原core+=check保留；GUI原--tcl保持；gitk缺configinclude，实际upstreamfallback独立记录，不能新增第三config/export/NO_GETTEXT/TCLTK/PO补丁逃避。Build完整namespace与新增2配置/关闭状态独立封存；Fullmake480真实自然0才install60，再共同30s nativeprobes完整flags；完整/usr/local安装namespace/ELF/hash/resources/hardlinks/sourcecorrespondence才可供probe租约。

### 实际profile语义（FR-2）

原Reader用/usr/bin/git；原runner RUNTIME额外包含/usr/local/bin/git只是完整工具identity snapshot。原PATH以/usr/bin:/bin为先，保持；不把/usr/local加到优先位置。新安装在其真实字面位置，不symlink为alias/shim。原源tree b9cf/1878与schema精确恢复；一旦未来TLS源码修订新tree不同，就需另外的新同源candidate profile与原vector准入，不能仍填b9cf。

Carrier管理tree与Pure SUT分离；nativefetch/gitshow是真CI执行，不能用APIbyte adapter充nativeproof。镜像digest/本次builder真实输入/安装manifest/运行container imageid/native namespace需建立链，dockerlabel不够；原profile owner会实读子进程proc/pidfd/prctl/ECHILD，容器seccomp/cgroup/namespace必须ordinary一次前置核，不假设Docker自然满足。

原rc_native_probe.py声明no_install_or_binary_replacement/ no_compiler_install_or_privilege只能描述原probe阶段（源码无setup），新overall CI必须明示genuine新增工具安装已执行并保系统Git unchanged；不可只展示旧字段让审阅者以为wholeCI未安装。原BRANCH固定与11FILES guard不可偷偷改argv fakeGITHUB；若新entry必要，明确新增/修改source作用面与独立启动审查，不更换原runner/kernel/receipt_gate。

### 原始准入与证据（FR-3）

新独立前置审查后原85一次→原8文件实际重读/rebuiltreceiptgate→300一次；原全vector/natural0/sourcebeforeafter固定，任一85失败300NOTRUN。不能将本地installedgit工具资格或source静态control替本次85。原1800/7200/7/2/2和operation timings保持。源码恢复/git命令30秒、genuineGPG30/build480/install60/probe30/setup日志2MiB保持独立；workflow envelope调整如需单独有限行政授权，不回填controllerpassed。

安全export不覆盖原8/原seal：PUBLIC-SAFE-EXPORT-DESIGN01固定仅四个JSON的exact typed字段/枚举/hash/计数，禁arbitrary fields和所有raw文件体；完整原raw留实际私有owned evidence并需持久化可供root独立重读。Public GitHubartifact的访问性质与原白名单native/raw字段不能凭filename称安全。尚无本次合法私有持久化通道实证，保持OPEN；不上传TLS/私钥/secret/env/rawhostproc/源码对象库/整个容器包。原FAIL必须保留，不能因扫描阻断上传而称原raw已安全备份。首次独立准备仅tool component/SUT0；原85/300另外准入，私有通道缺失不能借public摘要闭合。

## 文件结构

当前本目录三规格+SAFE原schema摘要/STATUS，所有bootstrap/Dockerfile/workflow、新CIadapter/控制与SUT均NOTRUN。root决定新scope且manualCRITICAL披露后，才允许有限source草稿；真正启动另独立freshseal/ordinaryruntime/native review/root唯一执行。没有merge/tag/release/issuer实现许可。
