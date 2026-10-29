# 需求文档：issue88-reap-safe-group-cleanup

## 背景
独立审查发现两处进程组清理的 PID/进程组复用风险（M1/M2），与 issue86/88 的发布准入线相关：
- M1：`scripts/Ubuntu原生验收v1.py` 只在 `poll() is None` 时 `killpg`；`poll()` 会提前回收 leader，leader 被回收后组内残留进程不再被清理，且 SIGKILL 后第二次 `wait(timeout=5)` 的超时未处理。
- M2：`scripts/linux_runtime_provenance.py` 在 `getpgid(pid) == pid` 与 `killpg` 之间存在 TOCTOU：worker 若被别处回收，pgid 可能被复用。

## 需求列表

### FR-1: 不回收的存活判断
WHEN 原生会话需要判断 leader 是否仍在运行 THEN 系统 SHALL 使用 `waitid(WNOWAIT)`，不得调用会回收 leader 的 `poll()`。

### FR-2: leader 固定 pgid 的组清理
WHEN 清理本测试创建的进程组 THEN 系统 SHALL 持有 leader 的 pidfd，确认 leader 未被回收，对记录的 pgid 依次发送 SIGTERM 与 SIGKILL（SIGKILL 总是发送以覆盖残留进程），仅在组清理结束后回收 leader。

### FR-3: 超时失败关闭
WHEN SIGKILL 之后 leader 仍未在预算内退出 THEN 系统 SHALL 抛出明确错误并保持 leader 未回收（不复用 pgid），不得静默继续。

### FR-4: 已回收不发信号
WHEN leader 已被本所有者回收 THEN 系统 SHALL 不再向其 pgid 发送任何信号。

### FR-5: M2 证明未回收
WHEN observer worker 停止 THEN 系统 SHALL 在 `start()` 后立即 `pidfd_open` 并持有；每次 `killpg` 前通过 `waitid(P_PIDFD, WNOHANG|WNOWAIT)` 证明 worker 未被回收；缺失 pidfd 时失败关闭。

### FR-6: 新增顶层组合准入层
WHEN 本变更进入 issue88 发布执行器链 THEN 系统 SHALL 按 PR145 模式新增 `rc_pretag_reap_safe_profile.py` 顶层层（M=13cd343d），通过 FRAGMENTS 将新字节逆转为 M 字节，旧层与其历史 pin 保持不变。

## 非功能需求
- NFR-1：不重写既有 16 层 profile 的 pin；旧失败/取消证据不变。
- NFR-2：本层与其用例不构成原生证据或发布授权。

## 验收标准（EARS）
1. 顶层用例 14 个全部执行且成功，计入工作流总数 427。
2. `normalize` 对每个基线路径恢复 M 的精确字节；任何单字节偏差拒绝。
3. 组清理用例在真实子进程上证明：残留进程被杀、leader 最后回收、超时时 leader 保持未回收。
