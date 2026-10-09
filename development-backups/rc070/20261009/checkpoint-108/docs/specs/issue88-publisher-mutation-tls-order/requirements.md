# Publisher mutation TLS ordering — read-only finite proposal

## 功能概述

仅规格与只读影响分析；没有生产修改、组件执行或原方法启动许可。纯 Publisher 基线 tree b9cfb8a0b58f8e0863c764e50cf3d38920eefeae，原 85 为 83 success/2 FAIL、整体 FAIL，300 NOTRUN。Diag6 的原单方法仍 FAIL：本轮同一个真实 request 的 server recv TimeoutError 先于 authentication 返回，其后 client sendall returned/BrokenPipe；没有 handler close 的时间戳，不由 auth>2s 或 operation kind/id 推历史 85 原因。

## 需求列表

### FR-1 延迟 mutation socket 建立，先完成所有本地准入与流准备

WHEN authentication 或完整流准备尚未成功结束，候选 mutation 路径 SHALL 不创建其 mutation TLS socket；WHEN 原三个 hardreject 任一拒绝，系统 SHALL 保持未消费、零 mutation 写入和默认拒绝。

候选仅调整 GitHub._request 的 mutation 路径顺序：原 request snapshot/active → 原 authenticate → 原 remote_constraint → 原 authorize → 原 prepare_stream → active → TLS connect/完整 peer verification → 原 Reader.check → active → 原 scope consume → possible=True → 原 write/response。认证和完整流 hash/FD 验证都应在 mutation socket 建立前结束；仅把 connect 移到认证后仍使 stream 准备耗时占用远端 idle 时段，不满足此需求。GET/read 路径保持原顺序；metadata 认证可以执行其原只读请求，不能声称整个 admission 无网络。

每个调用使用同一个真实 client/selection/credential/session/scope/snapshot/stream 与原 deadline/callback。预算不重置，不缓存旧准入、不新增授权、不延长 fixture 2s、Reader TIMEOUT 或实际原 1800/7/2/2 owner 期限。没有真正 issuer、同 client grant、server-held-tag 实现时，原三个 hardreject 继续阻断，永不建生产 mutation socket/写字节。

### FR-2 完整身份、一次消费、效果及异常边界保持

WHEN admission、stream 或 TLS 阶段发生身份漂移、deadline 到期或取消，候选 SHALL 在原 consume 前拒绝并尝试真实 owned socket close；WHEN 已消费后写入或响应失败，候选 SHALL 保持原 unknown 效果边界与既有异常映射，不宣称原 public cancellation identity 被保持。

保持原 authenticate/remote_constraint/authorize/prepare_stream/_consume/_check/_Reader/_connect 函数 AST 与原 hardreject；候选只移动 _request 的调用位置并增加必要的原 active 再核验调用，不能把“新布局规格”称为源码修改完成。

流必须完成原 hash、EOF、真实 FD/object metadata 比较、rewind 到 0，再建 socket；建 socket 后、scope consume 前再次核 snapshot/client/credential/session/selection/deadline 与真实 stream/stage 身份及位置。具体 postconnect stream 再核验应复用现有只读 stage handle/fstat/tell 边界，不能再次完整读流引入同一 idle 缺口；如复用现有接口不足，必须另报新符号影响并扩有限规格，当前不授权新增 helper。

TLS hostname、check_hostname、CERT_REQUIRED、server_hostname 和 peer certificate 条件原样执行。建连、TLS验证、准入、流准备或取消失败在原 consume 之前保持 possible=False/effect=none、零写入和未消费；consume 后 failures 仍 unknown，确认结果/close 故障原规则保持，不以 historical connection pin 证明 live connection 或远端无效果。消费仅一次且在任何 header/body write 之前。

原 _request BaseException normalization、实际 socket close 和原 _safe wrapping 不在本次 reorder 授权中改变。原 catch 会将取消对象归一化为 WireFailure；不能宣称保持 public API 原取消对象 identity。控制需记录原 cause 到原 catch 的对象与既有映射；如最终任务要求在 public API 传播原取消对象，属独立尚未闭合需求，应另规格/impact，不由移动 connect 假称解决。原 _connect close masking、_request close catch 行为同样需真实负控准确报告，不借外部 observer 的 sticky 机制替生产实现。

### FR-3 新有限控制与独立准入

WHEN 新源码、controls、封存、独立设计/启动与 root 授权尚未全部具备，Agent SHALL 不执行原方法、85、300或发布；WHEN 有限原方法通过，Agent SHALL 不升级历史整体门禁资格。

后续源码实现前先独立设计审查与 root 授权。后续必要普通控制按 design 清单执行，涵盖真正原 owned credential constructor/deepcopy/session/stage/native stream/socket/TLS，真实 server 原 2s，不把 equality/fake owner/fixture grant 当生产权限。component controls、单方法、85/300 各独立严格准入。保留旧 85、诊断和行政失败；source freeze、fresh detect_changes/gencommit/source-only backup 完成后才新独立启动审查，root 唯一启动原一个方法。

## 非功能需求

manual CRITICAL：same-client authority、snapshot、单次流、mutation effects、deadline、cancel/close；fresh graph authenticate HIGH110/direct14，其函数保护不改。request LOW15/direct4 不是授权安全证明；prepare_stream/consume 的 graph LOW0 与源码真实调用不符，动态边漏覆盖 UNKNOWN。预算、日志上限、原测试 assertions、TLS/fixture 源码、Reader、默认拒绝、Issue86 snapshot 暂停/PR98 取消保护不改。原 native process/family ECHILD 和 raw/source identity 必须由新运行证明，不借历史。

## 依赖关系

纯 b9cf/1878 和 carrier37109/1860；Diag6 independent terminal8c5dcabb 和 author8f973e；当前真实 issuer/sameclient/serverheldtag 均未提供；所有新代码、控制执行和原方法启动尚未授权。本规格只产生可审查有限设计。
