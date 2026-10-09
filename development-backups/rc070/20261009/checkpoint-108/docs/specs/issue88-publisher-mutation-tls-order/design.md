# Read-only design: mutation TLS after admission and stream preparation

## 概述

满足 FR-1/FR-2/FR-3 的候选设计，当前无实现。原 _request 先连接后调用完整 artifact authentication，原 _prepare_stream 再读/hash/rewind 整个真实 staged asset。目标是将 mutation TLS 建立移到这两段工作结束以后；保留 read 路径与所有准入、授权、Reader、effects、close 和测试原逻辑。

## 技术方案

### 候选调用布局（FR-1）

1. 原闭合 request 校验、snapshot、active。length 从原 immutable asset/body 读取。
2. 仅 mutation：原 authenticate(selection,self,active,deadline)，原 remote_constraint，原 authorize(op,subject,request=snapshot,scope=scope)，原 prepare_stream(active)，active。三个原 hardreject 不改，缺 provider 时在本步自然停止；只读 metadata 认证请求仍可连接它们自己的 owned TLS。
3. 原 _connect(host, min(TIMEOUT, remaining-original-deadline))；原 TLS certificate/hostname 验证；Reader(sock, originaldeadline, active) 与 Reader.check。
4. 仅 mutation：原 active/snapshot checks，完成真实 stream handle/current FD/stat/position=0 的有界再核验；不重新完整读取/hash asset，不新增授权。之后原 scope._consume(snapshot)，possible=True。
5. 原 header/body/stream sendall/response/mutation result。原 catch/close/active-read-finalcheck/_safe 行为保留。

原 authorize 的 Python 签名只接 op/subject/request/scope，当前 default-deny 无 TLS socket 输入；将其在 mutation TLS 前执行改变了时间关系。不存在真正 provider，不能证明未来 provider 不依赖 verified transport 或授权 lease 的新鲜性。本设计只能保留当前 hardreject；若真实 provider 以后要求 transport-bound grant，应另完整设计并阻断本候选，不用 fixture 可通过代替 provider 审查。

### 边界与明确未闭合（FR-2）

持同一个 snapshot/client/credential/selection/native sessionowner/scope/stream 强对象引用，消费前 active 再调用原 snapshot._check；原 scope.consume 内 session before_write 原 once-only 有效。资产 fstat 与原 stage._check_handle 的 bounded 再核验需精确指明实现调用面，目前只有设计，不误称 _RequestSnapshot._check 自身验证 stream（它不验证 FD/stat/tell）。原 hash/rewind 外的并发文件内容改变即使 metadata 等值仍不是本布局解决的 immutable-source 证明；必须保留原 staging/native isolation 规则与真实测试，不能将 stat 等值当完整 hash 新鲜性。

仍有从 TLS handshake 完成到首次写入的有限 active/FD/consume 工作，包含 PublisherSession._before_write 调用，时长未经真实测量。没有声称消灭所有远端 idle timeout；若 before_write 包含昂贵工作，须只读审查其依赖后再另有限规格，不能把 consume 提前或放宽 2s。Deadline 被 admission/stream 耗尽则 active 阻断 connect，TLS timeout 不刷新原 deadline。

本轮只读已核原 PublisherSession._before_write：_check_active → inflight/transition/pending/attempted identity checks → attempted.add；_check_active/_check_completion 核 closed、Event.is_set 和原 monotonic deadline，没有调用 artifact authentication 或完整流读。此源码事实不证明执行时零耗时，也不消除 callback/调度/取消与 set mutation 可能抛错的边界。保持其 AST、不移动消费，实际 ordinary before_write 延迟负控用于准确展示剩余 idle 风险。

取消与异常不新增“成功清理”声明：原 _request catch 归一化 cancel，原 _connect raw.close 失败可能遮 primary；这两处当前已有风险，重排不能保持原 public exception identity，也不能把原 close.UNKNOWN 升级 closed。ordinary instrumentation 必须在真实 delegate 后观察原异常/返回、close 不跳过、所有 observer/cleanup 原对象聚合；不写 production sticky bridge。

### 后续必要普通 controls 设计（FR-3，全 NOTRUN）

| 组 | 原组件与负向触发 | 要证明的有限事实 |
| --- | --- | --- |
| C01–04 | authenticate、remote_constraint、authorize 分别拒绝；auth cancel | mutation connect0、writes0、consume0；生产默认deny unchanged；原 cause/catch mapping |
| C05–07 | auth/完整 native stream 准备耗尽同 deadline；流 hash/EOF 失败 | connect0、consume0，不 reset budget；真实FD原对象 |
| C08–11 | native credential clone完整构造；foreign-equal selection、client/sessionowner漂移、retired scope | equality 不授予权限；snapshot/active 原身份链拒绝 |
| C12–15 | streamFD/metadata/closed/position 在 prepare 后或 connect 内漂移 | 消费前再核验拒绝，close 真实调用，未消费/零写 |
| C16–18 | 真正 owned TLS bad peer/handshake timeout/connect cancel | 原 certificate/deadline gates，effectnone；原 socket close 可证明范围 |
| C19–21 | consume 不可二次；before_write 故障/取消；成功原consume到header观察 | 每方法一次消费、write之前消费；postconsume unknown不借bytes0升级none |
| C22–24 | 原 TLS server2s：auth长、stream准备长、before_write长 | 前两段完成后才 mutation connection；后段仍可能超时必须准确FAIL/UNKNOWN；不改fixture |
| C25–28 | delegate primary + observer cancel、real close exception、observer preclose failure、多个 owned close independentattempt | 原对象/实际close/UNKNOWN安全留存，不用命名通过代替 source/raw audits |

这些 controlled fixtures 只验证组件和既有受测源码；假设授权正向 fixture 明确标记 test-owned，不证明真实 issuer/server-held-tag。先普通 failure-first、再源码 freeze/sourcepeer、root source backup、独立 startup，任何原方法由 root 一次执行；85/300 继续禁止自动重跑。

## 文件结构

当前只有本目录三规格、有限 fresh impact 摘要及安全 STATUS。候选未来编辑面仅 scripts/rc_publication_github.py 的 GitHub._request；如 stream bounded 再核验需要新 helper/source函数编辑，先新 impact/manualCRITICAL/root 授权。本轮所有原 production 函数/source AST/byte 均保持，不新建 TLS hooks、issuer/grant 或更改 Stage callback。
