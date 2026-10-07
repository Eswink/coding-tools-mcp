# 需求文档：共享下载期限与取消
## 功能概述
为既有受监督下载器提供调用方绝对期限与取消检查，供后续 bundle 验证直接复用。
## 历史经验与坑
复用现有真实子进程、管道和 trickle 夹具；历史 C 证明必须继续运行精确历史字节，不能冒充当前实现证明。
## 术语定义
操作期限是调用方期限与启动时默认 300 秒期限的较小值；EOF 阶段限额仍为 READ_TIMEOUT。
## 范围边界
仅下载监督、历史源码精确逆变换及既有只读工程测试；不新增 bundle/native/security PASS、暂存、发布或文件删除。
## 需求列表
### FR-1: 保持单一绝对预算（Must）
作为验证调用方，我需要下载共享总期限，以防重置预算后超时仍成功。
WHEN 提供 deadline THEN 系统 SHALL 仅接收内置 int 或有限 float，拒绝 bool/子类/非有限值，巨大整数安全收敛。
WHEN 操作期限已到 THEN 系统 SHALL 在启动前或后续检查点以固定 transport_deadline_exceeded 失败。
### FR-2: 监督取消并保留清理边界（Must）
作为验证调用方，我需要取消停止下载且确认子进程回收。
WHEN check_active 返回非 None 或抛异常 THEN 系统 SHALL 按固定代码映射，清理后脱离原始异常上下文返回。
WHEN 清理不确定 THEN 系统 SHALL 以 transport_cleanup_uncertain 覆盖主错误并仅保留安全代码。
WHEN 仅 EOF 阶段限额到期 THEN 系统 SHALL 保留 artifact_transport_failed；清理后迟到成功必须拒绝。
### FR-3: 保留历史源码与有限组合（Must）
作为工程维护者，我需要历史证明不变且当前候选精确可审查。
WHEN 选择 D[M]、I[M,D] 或 J[R,I] THEN 系统 SHALL 核验精确源、父序、四文档 overlay、模式、预算和八个逐字节逆变换。
IF 已选择的候选或历史内容无效 THEN 系统 SHALL 终止，不得回退或缓存候选验证。
### FR-4: 执行真实回归并保留证据（Must）
作为维护者，我需要真实子进程、背压、trickle、文件边界和清理失败测试。
WHEN 验证候选 THEN 系统 SHALL 保留旧 1304、strict303、consumer452 IDs，并新增恰好 12 运行时和 12 组合测试。
WHEN 工程 CI 运行 THEN 系统 SHALL 在 Ubuntu22/24 执行既有 120 加新增 24，记录完整执行清单和前后源绑定。
## 非功能需求
NFR-1：回调模式以 50ms 轮询；同步系统调用不可抢占，迟到完成失败。清理独立实时时限仍为 5 秒。
NFR-2：默认调用、固定主机、worker IPC、凭证边界与清理实现不变；无新增依赖。
NFR-3：14 路径、8 修改、6 新增、1764 项，实际行增删不超过 2000，逐文件上限见 tasks。
## 依赖关系
依赖现有 rc_consumer_transport、PrivateRoot、历史 composition 与只读 publication-executor workflow。
## 检查清单
需求覆盖 FR-1、FR-2、FR-3、FR-4；实现、真实测试、精确审查和远程门禁完成前不声明交付。
