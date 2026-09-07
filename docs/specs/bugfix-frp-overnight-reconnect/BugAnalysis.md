# BugAnalysis — FRP 隔夜断网后失联

## summary

路由器凌晨关机约 1 小时后恢复，应用与隧道仍显示运行中，但公网 MCP 失联，需手动停启。昨日加的自动恢复未真正把线路救回。

## tbp.phenomenon

| 理想 | 实际 | Gap |
|------|------|-----|
| 隧道处于已连接时，断网再恢复后 frpc 自动恢复公网可达 | 公网失联，需手动停止再启动 | 自动恢复链路在断网期间失败后永久放弃监督 |

## tbp.timeline（来自本机 frpc-mcp.log）

1. `03:25` 路由器断网：`i/o timeout` / `no such host`
2. `03:26` `[health] auto-restarting frpc: reconnect loop`
3. `03:26` **重启失败**：`loginFailExit enabled` → frpc exit 1；supervisor 已 remove 进程且未再 insert
4. 此后 `heal` / `network recovery` 只扫 `frpc.keys()`，**该工作区从监督集合消失**
5. 网络抖动还多次误触发 `[health] host network restored`，造成无意义重启与 `proxy already exists`

## tbp.boundary

失控层：`TunnelSupervisor` 健康循环 + `spawn_frpc` / `frpc.toml` 登录失败策略。不是 frps 服务端配置问题。

## rootCauseAnalysis

**因果句**：断网时健康检查杀掉并重拉 frpc，但 frpc 默认 `loginFailExit` 在 DNS/登录失败后直接退出；spawn 失败后 supervisor 不再把该工作区留在 `frpc` 表，后续网络恢复检测与 heal 都看不到它，因此公网永久失联直到手动停启。

### ruledOut

- 未安装新包：日志已有 `[health] host network restored` / heartbeat 配置
- 单纯「进程僵死未检测」：实际是进程被重启失败后丢弃

## fixPlan

1. frpc.toml 写入 `loginFailExit = false`，断网时进程自愈重连
2. heal / network recovery 以 `frp_routes` 工作区为监督集合，进程缺失时在线则补拉
3. 网络离线期间不因 reconnect loop / Unreachable 强制杀进程
4. 网络探测防抖：连续离线后才记 offline；恢复时只救缺失/不健康实例，不 thrash 健康 frpc
5. spawn 时网络性 login 失败不当作永久配置错误杀掉

## testPlan

- 单元：toml 含 `loginFailExit = false`
- 单元：reconnect loop + 离线 → 不判需重启；进程缺失 + routes → 判 unhealthy
- 单元：网络防抖需连续离线才标记 outage
- 手动：装新包后模拟断网 1 小时，确认日志有持续重连且恢复后无需手动停启
- **用户验收（2026-09-07）**：隔夜断网场景已确认恢复正常

## preventionMeasures

1. FRP 健康循环必须以 `frp_routes` 为监督集合，禁止仅依赖 `frpc.keys()`
2. 断网窗口禁止因 reconnect loop 杀进程；配置必须 `loginFailExit = false`
3. 网络恢复探测必须防抖，且只救缺失/不健康实例
4. 发布前用真实隔夜断网或长时断网复验，不以短时本地断网替代
