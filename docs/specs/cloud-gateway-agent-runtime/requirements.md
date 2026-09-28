# 需求文档：cloud-gateway-agent-runtime

## 功能概述

将可持续在线的云端 MCP/OAuth 控制面与可以完全离线的 Windows/Ubuntu 执行端分离。保留本地授权、任务与聊天隔离，并在后续增强本地 Agent 工程能力。

## 范围边界

- In Scope：云端协议、身份与授权投影、设备出站链路；本地授权与执行核心；迁移、运行证据和双平台真实验收。
- 当前增量：只增加 `prototypes/cloud-gateway` 的回环 HTTP 实验室、`tests/cloud-gateway`、本目录与独立 CI。现有桌面源码和包不变。
- Out of Scope：云端执行 shell、默认保存代码/输出、离线 mutation 队列、无限令牌、Kubernetes、多区域 HA、自建 LLM 循环、关闭授权换取无弹窗。

## 需求列表

| FR ID | 需求摘要 | 主子规格 |
|---|---|---|
| FR-1 | 固定云端入口与独立发现/工具目录；本地离线不关闭控制面 | gateway-foundation |
| FR-2 | 分离 MCP 2026 与 legacy 握手/错误契约 | gateway-foundation |
| FR-3 | 权限先于可用性；无离线审批噪声；未知执行结果不重放 | gateway-foundation |
| FR-4 | 云 OAuth 与本地聊天授权、设备身份相互分离 | agent-channel |
| FR-5 | 有界出站 Agent 通道、generation fencing 与请求去重 | agent-channel |
| FR-6 | 独立于 UI/网络协议的本地工具运行时、进程管理和状态 | agent-runtime |
| FR-7 | 双平台策略/沙箱、项目指导、技能、补丁、追踪等增强 | agent-runtime |
| FR-8 | 可回滚云部署/迁移与最小数据持久化 | deployment-acceptance |
| FR-9 | Windows/Ubuntu 真包和真实 ChatGPT 离线/恢复验收 | deployment-acceptance |

## 验收标准

各 FR 的 WHEN/THEN/SHALL 条件见子规格。第一批的实验室合同测试不能替代生产安全评审和真实 Host 验收。

## 非功能需求

- NFR-1：生产权限失败必须 fail closed；云恢复不得复活撤销的 grant。伪造/缺失 conversation context 不得退化为 OAuth 账号级授权。
- NFR-2：本地离线已知时立即结束新请求；不得等待设备开机。实验室整体测试有界，HTTP 请求体上限 64 KiB，单请求读取期限 5 秒，连接上限 64。
- NFR-3：网关默认不持久化 payload、完整命令、输出或源文件；日志仅固定事件/计数，token、原始 session、路径不得出现。
- NFR-4：现代和 legacy 协议分别测，不按搜索未命中推断功能缺失；协议错误不能假扮业务成功。
- NFR-5：所有新增文件英文命名，单源码文件少于 500 行，变更前影响分析、提交前 diff/graph 检查。
- NFR-6：单 VPS 只是运行假设，不是零停机保证。必须设计进程重启、TLS 到期、存储/磁盘故障、备份恢复与回滚。
- NFR-7：生产性能 SLO 在 VPS 配置及真实延迟采集后冻结；当前不虚构容量、费用和延迟数字。

## 依赖关系

见 `spec-manifest.json`。接入真实本机执行依赖生产身份、local grant 和 fence，不能以 fixture token 替代。现有安装包继续作为回滚候选。
