# 设计文档：共享下载期限与取消
## 概述
对应 FR-1、FR-2、FR-3、FR-4、NFR-1、NFR-2、NFR-3；基线 M=7de3244adc367fa60463d1e3b64c92f211d2fda8，tree=c499ee350af610c142652520c35da994215a6f70。
## 技术方案
复用现有父进程监督器；不改变子进程程序或 IPC。运行时与有限组合两分区并行。
### 架构设计
校验输入 → 共享期限/活动检查 → 启动并取得所有权 → 管道交换与文件写入 → EOF 等待 → 原有清理 → 最终成功检查。
默认调用保留既有时钟调用与单次 wait 路径。显式期限或回调在启动前检查。
回调模式 selector/退出等待最多 50ms；EOF 期限=min(操作期限,EOF开始+READ_TIMEOUT)，不得因轮询重置。
仅 EOF 限额到期保留 artifact_transport_failed；操作期限到期为 transport_deadline_exceeded。
## 数据模型
仅父进程内保存 deadline、clock、check_active；不新增持久化状态、报告或权限标志。
## API 设计
`download_artifact_zip(api, artifact, destination, *, opener=None, clock=time.monotonic, deadline=None, check_active=None)`。
FR-1：deadline 仅内置 int 或有限内置 float；先校验再 min，巨大整数不转 float，bool 和子类拒绝。
有效期限为 min(调用方绝对值,一次起始时钟+TOTAL_TIMEOUT)，缺省仍为后者；边界 remaining<=0 拒绝。
FR-2：回调无参且必须返回 None；安全读取精确 str code，cancelled→transport_cancelled，timeout→transport_deadline_exceeded，其余固定失败。
直接 KeyboardInterrupt/SystemExit 保留类型边界，SystemExit(1)；不传播原始参数、cause、context。
活动/期限检查覆盖回调前后、启动、selector/IPC、open/write、退出、文件上下文 flush/fsync/close。
同步调用不能抢占；返回后检查拒绝迟到完成，不能承诺所有调度延迟可控。
`cleanup` 原字节保留，独立真实时钟五秒、无回调、现有 close/terminate/kill/reap 与 sticky uncertainty 不变。
清理失败覆盖主错误且 original_error_code 仅安全代码；成功清理后仅原本成功路径再做一次安全活动/期限检查，不重复清理。
## 历史来源与精确组合
FR-3：仅历史 transport 输入允许旧 C/F 与封印新源码两种精确长度，有限读取后通过新纯逆函数恢复旧字节。
保留 lstat 普通文件约束、旧长度/哈希及全部验证后写入规则；仅逆变换 AssertionError 转固定 ValueError，异常上下文外抛出。
历史 C transport 固定 10946 字节，SHA256=2555906190830843de21c8e54d3fca3f2043bae3330a17109d72bdf7782ca703。
新 profile 从 newest final-admission seam 分派；D[M]、I[M,D]、J[R,I]，R=e2e011f7f2a3a1df838bbd588106205b999db610，四个 R 文档精确不变。
仅初始拓扑不匹配可回退；候选/历史内容错误终止；基线新鲜验证；实际候选字节不归一化、不缓存。
七个整字节逆变换、十二个非自身源 pin 与独立完整树审查；旧 pins/caps 不变，仅五个已知历史 passthrough。
## 文件结构
13 个规范路径与 final/delta 上限列于 tasks.md；新文件 6、修改 7，最终 1764 项；实际总增删≤2000。
## 设计决策
保持现有监督器和清理实现，避免新增下载架构；历史证明精确回退只作用于历史输入，不能承认无效候选。
固定错误代码及严格回调返回值避免调用方异常或秘密泄漏；保留旧 EOF 阶段错误区分。
## 测试策略
FR-4：复用现有真实子进程、部分 IPC、管道背压和 loopback trickle 夹具，新增运行时 12 方法含边界子案例。
另 12 组合方法核验拓扑、模式、上限、源 pin、七逆变换、历史拒绝、原 1304 和新增 24 唯一 ID。
必须完整 D1328/I989/J989；仅有精确命令/环境/源/ID 对接的 hosted 子集可复用，混合覆盖不得称单次整套通过。
只读 Ubuntu22/24 workflow 运行 144；保留 event/branch/permissions/actions/Python3.12/30min/前后全源检查。
strict303、contracts755、consumer452 远程门禁不变；无新增 native 或发布工作流。
## 风险评估
最新 normalize 图谱 CRITICAL：11 直接/65 符号/9 流程；下载入口 MEDIUM：5 直接/26 符号。FTS 不可用限度保留。
人工影响审查与独立设计审查先于实现；提交前 detect_changes、完整逆变换源审查、必要测试与 gencommit。
## 检查清单
受保护 core/stage/eligibility/metadata-admission/consumer/worker/proof runtime/native/locks/held sources 不变。
本增量不完成 bundle 所有权删除、可取消解析/Git、真正 FINAL/native、安全验收或 live activation。
