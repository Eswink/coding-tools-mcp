# Publisher TLS order, native close and cancellation — finite read-only proposal02

## 功能概述

本轮只有规格、原源码与 fresh impact 实读；生产 source/reorder/new helper/ordinary component/original method 均未实施。原 pure SUT b9cf/1878，原85=83success/2FAIL整体FAIL，300NOTRUN。Diag6同一个真实request的recvTimeoutError早于auth返回、后sendall returned/BrokenPipe，是本次有限事实，不借它证明旧85因果。Git2.55.0真实V4工具构建/安装已独立PASS，仅工具组件，不是本规格的CI或Publisher资格。

## 需求列表

### FR-1 准入与完整流准备先结束，后连接并再次核原对象

WHEN 原 authenticate、remote_constraint、authorize 或完整 prepare_stream 尚未全部成功 THEN 候选 mutation 请求 SHALL 不创建该 mutation socket；原 metadata GET/read 所需独立只读连接仍执行原路径。

候选原 snapshot 创建后立即 pin 实际 session stage/ordinal/snapshot stream/asset，不能 connect 后才把当前 stage 称为原 stage。认证、原三个 hardreject、原完整流 hash/EOF/rewind、active 均先结束，再执行原TLS构造与全部证书/hostname验证、Reader.check。对于 upload，消费前必须准确核同原stage、原snapshot stream/实际stage handle与ordinal/asset绑定；执行原stage._check_handle的真实rootFD检查/退休、fstat五字段与snapshot._identity比较、tell0、active；不重复完整hash、不移动consume提前、不用FD号或metadata等值mint权限。只有原一次consume完成、possible=True，才考虑write；新增原Reader.check调用在consume之后/header前检查既有deadline和cancel，若失败仍unknown而不是零字节就none。这个额外调用是候选_request AST改变，Reader函数自身AST不变。

原session/client/credential/selection/scope/deadline/nativeFD/stage隔离及原stream权威不变；hash结束之后metadata等值并不等于不可变内容证明。Stage callback、snapshot安全暂停、Reader、fixture2s和原owner1800/7200/7/2/2均保持。真正issuer/sameclient/server-held-tag均未提供，三个default hardreject继续阻断，无新grant/provider。

### FR-2 原因、规范wire效果、真实close与UNKNOWN独立保留

WHEN 在底层delegate或新观察/检查中发生异常 THEN 候选 SHALL 先保留实际原对象，不以typenames代替对象、不格式化args/body/header/token，真实owned close仍尝试一次；WHEN 原primary与close/observer cancel同时发生 THEN 底层边界 SHALL 同时保留所有实际对象、保原primary并独立完成必要实际close，不重试可能已经关闭的FD/socket。

原_request的close位于catch之后，**不是finally**。原_connect的wrap失败后raw.close、stage._check_handle的finally retirementclose、PrivateRoot._root的except retirementclose均可能mask原异常。新候选若修改这些函数，必须列出真实AST/字节delta；不得改完再称原函数AST相同。StageRootOwner.close_fd的uncertain/sticky-retention原则保护；在close失败时原stageowner仍uncertain，不把source入口或路径当closed证明。TLS close失败的强对象保留生命周期必须另具体实现/负控，未决定之前是SOURCE STOP，不能靠GC/进程后来退出称allIO已闭。

WHEN 已存在真实canonical WireFailure(effect=unknown或confirmed) THEN 候选_request SHALL 强保留其实际原对象及全部规范字段，不因possible=False或cleanup把原效果改成none。规范性与当前operation关联是两项检查：只有本请求真实响应与原op/client/scope对应且符合原typed id/asset规则，才可作为当前op的confirmed；来自authenticate或前一op的confirmed不能凭类型借给当前op。当前op归属不成立时结果不得声称本请求confirmed，必须保守UNKNOWN，同时私有holder保留原confirmed对象而不是重写其效果。原none/普通本地异常仍按原possible边界映射；原_publication_failure规范验证保护不改，它不认可任意cause/group为canonical wire失败。

当前有限合同不能同时保证“原confirmed对象公开同一返回”和“非本op confirmed不能绑定当前op”。新_request的公开typed projection、关联失败如何保守映射，以及私有raw-holder与Session清理的真实生命周期均为实施前STOP。候选普通C21/C22必须分别验证当前op绑定正链与foreign/previous-op负链，不把同kind/id值相等当关联证明。不选择该合同就不得实施重排或称规范effect已闭合。

**当前有限范围限制：** 最窄候选先证明底层_request/连接/rootFD close边界的对象保全和规范effect；_safe.call会克隆WireFailure，Session._run会捕获BaseException并经_failure形成结果，当前无法证明public取消原对象传播。不能向canonical WireFailure随意加cause/notes后声称canonical不变（原规范会拒绝）；不能把聚合group交外层后假定confirmed仍保留。公开同原cancel对象语义如成为本次目标，必须另明确新增_safe/_run/_failure修改面、退役/失败结果和原测试合同，独立授权再实现。本规格不暗含该授权；此OPEN足以阻止任何全链闭包或FINAL声明。

新观察/控制器必须透明delegate一次、同返回对象、原异常对象；普通observer Exception记录INVALID/UNKNOWN并保原delegate异常，observer BaseException cancel必须sticky实际对象并在真实fixture/session/资源cleanup后传播，不能被原生产catch归一化后消失。实close不能因preobserver失败跳过。该外部控制协议不等于生产公开API取消已修好。

### FR-3 最多28项failure-first普通方向与新独立准入

WHEN 新源码未得到具体root授权、普通真实负控/源码封存/备份/独立审查尚未完成 THEN Agent SHALL 不实现source或执行原method/85/300；WHEN 普通case通过 THEN Agent SHALL 只报告其真实组件/直接边界，不将测试fixture issuer当生产grant。

最多28个普通case方向见design，包含真正ownedFD、同源码native credential clone/session/stage、真实本地TLS/socket/process、原2s timeout和失败first原primary+cancel+close组合；不修改原positive/assertions/库存，不继承旧76/44/25等通过。普通source-first failure本轮也NOTRUN。之后每个source/执行/备份阶段独立准入，任何原一个方法仍由root唯一启动；85/300自动启动禁止。

## 非功能需求

manualCRITICAL：publisher效果/规范failure、nativeclose/cancel/UNKNOWN、流一次消费、真实授权及同client身份；fresh保护_publication_failure CRITICAL184/direct6；_safe MEDIUM40、root35、retirement39不是零风险；newhelperUNKNOWN非0。所有原时限/2MiB原controller日志保持，普通控有限预算不得借延期扩大SUT；不编译/安装/主机/Docker/CI发布或真实授权。真正issuer缺失导致生产deny。用户授权普通工程推进，不是grant创造许可。

## 依赖关系

原b9cf代码；只读TLS3FR frozen01和postconnect addendum；Diag6真实FAIL与独立terminal8c5dc；本轮V4工具真实组件PASS95349；SOURCE与28控均NOTRUN，公开传播合同/新TLSUNKNOWN保留生命周期尚待独立设计与root范围决定。
