# 设计文档：issue88-reap-safe-group-cleanup

## 设计决策

### 决策1: waitid(WNOWAIT) 代替 poll()
`poll()` 会回收已退出的 leader，从而释放其 PID/pgid。`leader_running()` 使用 `waitid(P_PID, WEXITED|WNOHANG|WNOWAIT)`，只观察不回收。

### 决策2: stop_owned_group
1. `returncode is not None`（已回收）→ 直接返回，不发信号。
2. `pidfd_open(leader)` 并在整个清理期间持有。
3. 断言 `getpgid(leader) == leader`。
4. 对 pgid 发送 SIGTERM，等待至多 term 秒；随后总是发送 SIGKILL（覆盖 leader 已退出后的残留组成员），等待至多 kill 秒。leader 未回收期间其 PID 不可被复用，因此 pgid 不会指向无关进程组。
5. 若仍未退出 → `RuntimeError`，leader 保持未回收（失败关闭）。
6. 否则 `process.wait(timeout=5)` 回收 leader。
若他处已回收 leader，`waitid(P_PIDFD)` 抛 `ChildProcessError`，同样失败关闭。

### 决策3: M2 持有 pidfd
`self.worker.start()` 之后立即 `pidfd_open`；`_stop_worker` 每次 `killpg` 前以 `waitid(P_PIDFD, WNOHANG|WNOWAIT)` 证明未回收；`worker.close()` 后关闭 pidfd。

### 决策4: 顶层准入层
新增 `scripts/rc_pretag_reap_safe_profile.py`（M=13cd343d，单父 D[M]、I[M,D]、J[R,I]），在 `rc_pretag_source_observation_profile.py` 的 `select`/`normalize` 开头分派到本层，旧层读取经 `normalize` 链恢复的 M 字节。`rc_pretag_source_observation_cases.py` 的工作区读取同样经本层 `normalize`。工作流新增本层 14 例并将总数改为 427。

## 测试策略
- 组合：M 绑定、SOURCE_PINS、normalize 精确逆转与拒绝、D/I/J 拓扑、错误拓扑委派、额外路径拒绝、预算。
- 行为：真实子进程（含组内残留进程）验证 FR-1..FR-5。

### 决策5: 无 pidfd 回退
仅支持 Linux >= 5.3 与 Python >= 3.9（`os.pidfd_open`、`waitid(P_PIDFD)`）。不可用时直接抛错失败关闭，不回退到 PID/pgid 猜测。

### 决策6: 已回收与残留成员
- leader 已被本所有者回收时，`stop_owned_group` 抛出 `not cleanable: leader already reaped`，不再静默返回。
- 回收 leader 之前轮询 `/proc` 确认同组没有其他非僵尸成员；超时则抛错并保持 leader 未回收。
- M2：worker 被外部回收时 `waitid(P_PIDFD)` 抛 `ChildProcessError`，记录为失败且不调用 `killpg`；pidfd 在 `finally` 中关闭。

## 残余风险
`waitid(WNOWAIT)` → `getpgid` → `killpg` 之间仍是三次独立系统调用。由于 leader 未被回收（僵尸或运行中）期间其 PID 不能被复用，只有当其他代码在此窗口内回收该 leader 时才可能失效；本层不在测试进程中安装 SIGCHLD=SIG_IGN/SA_NOCLDWAIT，且该路径以 pidfd 证明失败关闭。Linux 无 `pidfd_send_signal` 的进程组版本，因此该窗口无法完全消除。
