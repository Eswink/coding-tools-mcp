# 任务清单：issue88-reap-safe-group-cleanup

- [x] 1. M1：`leader_running()` 与 `stop_owned_group()`，`close()` 改用二者（FR-1..FR-4）
- [x] 2. M2：worker pidfd 持有与 `waitid(P_PIDFD)` 证明（FR-5）
- [x] 3. 新增 `rc_pretag_reap_safe_profile.py` 顶层层与 source_observation 分派（FR-6）
- [x] 4. `rc_pretag_source_observation_cases.py` 读取经本层 normalize
- [x] 5. 新增 `rc_pretag_reap_safe_cases.py` 14 例，工作流总数 427
- [ ] 6. 真实 CI（ubuntu-22.04/24.04）执行全部 427 例
