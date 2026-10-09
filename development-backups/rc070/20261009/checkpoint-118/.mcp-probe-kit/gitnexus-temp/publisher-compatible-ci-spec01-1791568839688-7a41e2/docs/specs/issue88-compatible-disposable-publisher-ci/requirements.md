# Genuine Git2.55.0 in a fresh disposable CI realm — read-only proposal

## 功能概述

只读规格，没有workflow/bootstrap/Docker/container/host安装或SUT执行。实际V4工具是 **Git2.55.0**，非2.51：archive git-2.55.0.tar.xz、actual installed-0.log为`git version 2.55.0`；其真实本地fullmake/install/probes已独立PASS，仅本地工具，不是CI信用。原stockCI缺/usr/local/bin/git而SUT0，不说明Actions整体禁用或Git flags不兼容；原85仍83/2FAIL，300NOTRUN。

原FixedGitReader.BINARY实际是/usr/bin/git，PREFIX四flags/OVERRIDES不改；原native runner额外hash /usr/local/bin/git。新增 genuine /usr/local 安装不能代替证明原/usr/bin/git本来支持full flags，也不能让Reader改用新工具或做PATH shim。

## 需求列表

### FR-1 单独新的安装准备范围与真实来源

WHEN 准备兼容CI realm THEN 新controller SHALL 只在全新可丢弃CI/container文件系统、预先不存在的/usr/local/bin/git与其新增安装名字执行genuine源码完整构建/安装；不得替换/修改原/usr/bin/git、host runtime/用户机器、权限或Reader。原存在路径/任一不符即setupFAIL/SUT0，不把symlink/alias/复制本地ELF称genuine安装。

WHEN genuine准备执行 THEN 系统 SHALL 在同一实际CI运行验证官方archive8177180B/SHA457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357、sign566B/SHA8673501946204c38ebfed09603c1f3a041ed8d12b31f0aa06a474d41e359e254、完整Ubuntu key68820B/SHAfd2809d850e844b614ac60f13ded554c55d9052e5c799a5814abcba2a68a063c，并实际GPG VALID原primary96E07AF25771955980DAD10020D04E5A713660A7/subE1F036B1FEE7221FC778ECEFB0B5E88696AFE6CB。原tar51916800B/4991路径；core+GUI两owned FILEorigin MSGFMT configs，不用CLI覆盖/root--check污染GUI、不删除原GNU本地化/TCLTK；gitk原fallback独立诚实记录。整个make480成功才install60，原probes共同30秒/phase2MiB/TERM2及cleanup2+2不扩大。

**权限/范围区别：** 原probe requirements明确Out-of-Scope编译、安装、特权、host配置，FR-2.1禁止安装工具，NFR-2无privilege/compiler/install。因此不能把准备步骤直接塞到原workflow后仍称原NFR满足。必须新的明确限定CI准备规格/入口/安装 provenance；原probe阶段保持它自己no setup/install逻辑，新的whole run报告明确setup实际install，不把原stage字段`no_install_or_binary_replacement=True`解释成wholeCI未安装。真实image/daemon权限、预已有compiler/GNUmsgfmt/完整sys工具identity尚未核，UNKNOWN，不得自行启动Docker/下载compiler/sudo/改权限来填证明。

### FR-2 原冻结source、工具身份和运行域严格分离

WHEN 准备之后启动probe THEN 系统 SHALL 用新的实际CI image/realm前后native identity证明原/usr/bin/git完整PREFIX+OVERRIDES实际成功；原/usr/bin/git原始bytes/mode/realpath等setup前后完全相同，同时新增/usr/local/bin/git和完整安装前缀与本次genuinebuild ELF/resource全对应。原路径必须真实regular native executable，不能借PATH、env、标签或虚构version。

原CPython3.12、openssl、/usr/bin/python3、sys.executable与所需native pidfd/WNOWAIT/subreaper/ownedfamily closure需本次真实兼容前置ordinary proof；image digest/构建输入/holder与真实正在运行容器/CI job身份要闭合，不能仅写docker标签或把本地PATH当CI自然兼容。尚无已实证满足这些工具的pinned image，本轮保持UNKNOWN。

WHEN Pure SUT恢复 THEN 系统 SHALL 从固定F13 13cd343d942b7a68912d42a8f9235c02ed647764与真实immutable备份dab238dc34d5a59f471aff935c728c1ed809cc78 checkpoint01/full52、checkpoint02/only8，用原nativefetch/gitshow恢复733a中间与最终b9cfb8a0b58f8e0863c764e50cf3d38920eefeae/1878，逐bytes/SHA/mode/blob/tree/privateparent/source manifest/index vector核实，carrier/bootstrap/config extras永不混入Pure SUT。原runner6259B SHA687ec2a408507284b557806569d6f5df0ead625b9c282b9c8bbb74782d633f0a/原inventory85+300逐字不改；官方GLib fixture267679B/SHA233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5保持。

### FR-3 本轮原85→完整8raw严格准入→本轮原300

WHEN 所有真实setup/native前置和新启动独立审查通过 THEN 系统 SHALL 执行原85 unique ordered names一次，原loaded/executed/namedpassed全85、failure/error/skip/xfail/xpass全0、native自然CLD_EXITED0/heldZ/同createdleader/pidfd/真实ECHILD以及完整runtime/source/index/runner/fixture/carrier/realm前后向量通过才可认为本轮85qualified。

WHEN 准入300 THEN 原控制器 SHALL 实际重读本次85原RAW-EVIDENCE-SEAL及全部8文件的原字节/bytes/SHA，重建原receipt_gate，固定同source/runtime/carrier/fixture/runner对应，才启动原300 unique ordered一次；任一缺失/失败UNKNOWN则300NOTRUN，不能借localV4、local83/2、旧历史85或JSON顶层PASS。

原85fail-only1800、3007200、TERM7/KILL2/family2、SUT原operation/fixture/Reader计时不改，wrapper workflow180分钟如保留必须实际足够新setup与85+300+cleanup；若真实envelope需调整只是CI行政上限，不得扩大原两个controller预算，必须规格准入不默改。取消sticky、原createdchild/namespace/native realfamily关闭要由当前容器/CI执行证明。不给真publisher issuer/tag/Release/产品安装资格。

## 非功能需求

No worker tokens/全部env、noPATHshim/flag移除/系统Git替换/宿主机安装/权限改动/新grant。只contents:read同repo明确新normalpush；真实Actions首次执行渠道由root，不能空提交/rerun历史造信用。新setup SOURCE尚未授权。安全artifact需新scope，只保允许safe projection与hash，原8私有raw不可改或借projection冒充；TLS/keys/env/原rawhostproc/对象库/工具二进制不进入source备份或公开artifact，敏感扫描失败即不上传。原白名单包含nativeidentity，不盲拷到新publicsafe范围；完整私有原8的持久化通道未定则整个可审查CI资格仍OPEN。

## 依赖关系

原carrier37109与原source b9cf/1878；原schema及owner/kernel/restore/runner/inventory；真Git2.55.0官方输入和本次genuinebuild控制规格；新的disposableCI/容器owned安装授权/真实兼容image和权限/工具provenance尚未核；真实publisher issuer/sameclient/serverheldtag仍缺，保三hardreject。
