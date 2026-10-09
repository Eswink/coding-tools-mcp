# Finite TLS-close/order design02 — SOURCE NOT AUTHORIZED

## 概述

FR-1/FR-2/FR-3 的最窄候选方向，所有代码与普通controls仍NOTRUN。旧三规格和冻结备份不覆。本设计将原对象出处、真实close、规范effects和公开异常归一化分开，不将内部对象捕获称public cancellation已修复。

## 技术方案

### 准确调用面（FR-1）

原_request构造snapshot后，仅upload从snapshot._scope._owner._session pin实际原_stage、ordinal、snapshot._stream/_asset；用原active核client/credential/native session/scope的当前有效身份。在auth/remote/authorize前就保该引用，任何stage/handle/selection替换应随后拒绝，而不是connect后重新pin替代对象。

原authenticate→remote_constraint→authorize→prepare_stream(active)→active在mutation socket建立前完成。之后原_connect与全部TLS peer gate、Reader.check。消费前使用同snapshot、stagepin、ordinal与stream，依次：active；stage当前is pin且entered/notclosed、stage._handles[ordinal] is snapshot._stream，asset/ordinal与原snapshot/op/plan仍绑定；原_check_handle(ordinal)；fstat `(dev,ino,size,mtime_ns,ctime_ns)`==snapshot._identity；tell()==0；active；原consume；possible=True；原Reader.check；原write/response。

stream端新有界核验可作为_request inline或新_checked_stream_after_tls，**尚未选择/实现**。新helper只检查原强对象链，不写授权、不读完整body/hash、不改变stage/stream位置。若ordinal/indexing或attribute观察失败，它是原真实失败，不能跳过close。功能函数执行一次，没有observer为了证明而多调用delegate。

原PublisherSession._before_write只核active/inflight/transition/pending/attempted再add，无auth/stream读，但同步callback/调度和rootFD I/O仍未有硬实时证明。其剩余长负控应允许真实timeout/remote关闭/unknown，不能要求所有平台必同BrokenPipe；候选消费后Reader.check只保原deadline/cancel检查，不延长原2s、不把consume提前。它不能打断阻塞在同步callback里的调用；外层原owner fail-only边界仍须实际native闭包。

### 最窄source delta 与保护（FR-2）

| 候选函数 | 可能真实delta | 本轮状态 |
| --- | --- | --- |
| GitHub._request | auth+完整streamprep先于TLS、stagepin/bounded核验、finally实际socketclose、规范unknown/confirmed保留、consume后Reader.check | SPEC_ONLY；AST将变，不能称same |
| _connect | wrapprimary+raw.close错误对象同时保留；raw未知不得自动retry/GCclose当证明 | SPEC_ONLY；必要close delta |
| StagedAssets._check_handle | 原rootFD获取/检查/finallyretire不变功能，primary+close对象累积避免mask | SPEC_ONLY；必要close delta |
| PrivateRoot._root | 获取失败时原retirementclose必调，primary/close/cancel同时保留、uncertain不清除 | SPEC_ONLY；必要close delta |
| 新_checked_stream_after_tls（如选）/新close-only helper（如选） | 真实原stage/handle/FD强引用核验或有限close对象组合 | UNKNOWN/manualCRITICAL；没source |

Reader、snapshot methods、consume/before_write、Stage callback、3provider default hardreject、_publication_failure、StageRootOwner.close_fd/_retirement_close暂保护原AST。_safe/_run/_failure当前保护原AST，意味着public原cancel identity仍OPEN；若root选择此闭包目标，另授权扩scope，不能通过补外部sidecar假称public语义已改。

直接底层 close组合可以BaseExceptionGroup保实际primary/cancels，但规范wireeffect输出不能自动等于group字段。_request需分别握住rawcause/cleanup errors与canonical失败；内部原unknown/confirmed原对象不修改，none保持原映射。当前op的confirmed还必须绑定本次真实响应、actual client/scope/op及原typed id/asset条件；canonical格式、同kind/id值或upstream auth失败本身都不能证明当前op远端确证。foreign/previous-op confirmed原对象强保留，当前op保守UNKNOWN，不重写原对象；公开projection与其原Session合同尚未选择，是SOURCE STOP。规范_failure不支持任意notes/cause/group；给公开传递的格式必须先独立设计确认，不能在SOURCE时临时改canonical规则。新TLS UNKNOWN强对象holder的所有权/退役/上限/lifetime仍OPEN，不能用字符串state或raw FD号获得authority，源码实施前明确。（真实stageFD原owner有uncertain保留机制，可复用原返回对象，不mint新owner。）

### 最多28项普通failure-first方向（FR-3，全部NOTRUN）

| ID | 触发及真实边界 | 有限验收 |
| --- | --- | --- |
| C01 | owned accepted TLS `_connect` wrapprimary+rawclose regularfail | 实close一次，两个原对象可重建，UNKNOWN不retry |
| C02 | 同上close KeyboardInterrupt/SystemExit cancel | 原primary+原cancel对象同在，不被观察mask |
| C03 | stage真实rootFD检查primary+retireclose regularfail | rootclose实调一次；stageowner uncertain且保留 |
| C04 | 同上rootclose cancel | 原primary/cancel对象均在、neverretryFD |
| C05 | `_root`获取/identity失败+closing失败 | 原inner primary可见，不假装helper看到所有原原因 |
| C06 | observer preclose regularfail/cancel | 同原真实close仍执行一次，stickycancel保对象 |
| C07 | observer afterdelegate regularfail | 原返回/primary保，不将INVALID观察升级SUT失败原因 |
| C08 | observer afterdelegate cancel | 真实fixture/session cleanup后原cancel重传播 |
| C09 | auth拒绝 | mutation socket0/write0/consume0 |
| C10 | 原remote/default authorize拒绝 | 无productiongrant，仅defaultdeny |
| C11 | auth花完deadline或实际cancel | 同deadline0connect，无budgetreset |
| C12 | native stream完整hash/EOF拒绝 | mutation socket0/consume0 |
| C13 | 原完整stream准备耗尽deadline | 尚未connect，同原scope/callback |
| C14 | 真实native credential constructor clone正链与foreign-equal负链 | equality不授权，不改defensivecopy |
| C15 | snapshot创建后stage被替代 | stage原pin必须拒绝，不能晚pin |
| C16 | connect期间handle/ordinal/asset漂移 | beforeconsume拒绝，close实际执行 |
| C17 | connect期间streamFD/identity变化 | fstat5身份拒绝、无consume |
| C18 | stream closed或position非0 | 不seek掩盖；原stageclose边界实核 |
| C19 | 真TLS bad hostname/CA/cert | 原peer gate，未消费/无写 |
| C20 | TLS timeout/cancel+socketclose失败 | 原预算/raw对象/UNKNOWN闭包，不减少effects |
| C21 | 已有WFunknown且possibleFalse+close异常 | unknown同对象/字段不降none（直接_request边界） |
| C22 | 当前op真实响应typedconfirmed正链及foreign/previous-op confirmed+close异常 | raw原对象/字段不改；只有actual同op绑定才输出confirmed，负链当前opUNKNOWN；公开projection合同未选即STOP |
| C23 | 消费前普通none/本地异常 | 保原code/effect映射，未消费 |
| C24 | 原_once消费后二次调用/写异常 | exactlyonce、unknown保留、无retry |
| C25 | 真实server2s+auth长/stream长，candidateconnect后原响应 | 只证明两段离开mutation idle，不fakeissuerproduction |
| C26 | 真实server2s+before_write剩余长 | 允许本轮实际timeout/BrokenPipe/closed unknown，不能把idle完全解决 |
| C27 | 原_safe/_run/_failure对rawcancel/group/confirmed的边界观测 | 如公传播丢对象/效果明确OPEN，不算闭包PASS |
| C28 | 多个owned实际close分别fail/cancel、最后sidecar失败 | 每owner真正独立尝试，原objects/raw结果保，anyUNKNOWN不qualified |

这些是方向而非已写tests或已执行。真实TLS component仅本地自有fixture；其测试issuer/authorizer若为正路径必要必须准确声明mock/ordinary fixture边界，永不证生产授权。必须先本轮failure-first raw/source/ownership普通负控，严格不超过28，不替换任何85原method/assert。

## 文件结构

当前仅isolated规格与SAFE-IMPACTS、原source truth/STATUS。源码编辑尚需root manualCRITICAL披露和独立有限设计；为保公开异常合同可能需另scope，所以当前不发布“实施可直接启动”的结论。所有旧失败/Freeze保持，后续source-onlybackup必须带UNKNOWN与NOTRUN状态，不上传TLS/keys/headers/host/env/rawobjects。
