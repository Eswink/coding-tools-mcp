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
