# 如何开发

> 从[项目上下文](../project-context.md)、仓库 `AGENTS.md` 和 `.agents/skills/mcp-probe-kit/SKILL.md` 开始；当前工程已经存在。

## 工作流与作用域

1. 继续已存在的任务时先 `resume_plan`，恢复成功后执行返回的下一步，不创建重复 Plan
2. 完整功能用 `start_feature`，完整修复用 `start_bugfix`；单项分析、审查或文档能力不必强套完整功能流程。不确定首工具时再用 `workflow`
3. `project_root` 使用本次 checkout 的实际绝对路径；按返回 Plan 选择规格布局，必要的 `add_feature` / `check_spec` 闸门通过后再实施
4. 托管 Plan 首次 `plan_heartbeat` 附完整 Plan，每完成、跳过或阻塞一步记录证据。规格、实现、测试、审查和 `converge` 结果都必须指向当前 revision
5. 修改函数、类、方法前运行 GitNexus upstream impact；HIGH / CRITICAL 风险先报告。暂存后运行 `gitnexus_detect_changes(scope="staged")`，确认真实范围，再用 `gencommit` 生成提交说明。这些工具不授予提交、推送或发布权限

MCP 不可见时使用项目锁定的 Probe CLI，版本与 Skill 保持 `4.0.1`；安装/恢复方法见 Skill，不使用 `@latest`。`docs/graph-insights/latest.md` 仍是 2026-07-13 历史记录，不能将其状态、符号数量或测试结果当作新鲜分析。

只改文档时保持作用域最小，核验路径、命令、版本和验收用语；无需为了刷新上下文改动运行时、依赖或发行台账。

## 本地开发命令

使用当前 CI 对齐的 Node.js 22、npm、Rust 1.98.1 和平台 Tauri 构建依赖；Python 驱动的 CI 使用 3.12。Linux 依赖和 Secret Service 会话设置见 `.github/workflows/dot-rc-integration.yml`。

在仓库根目录执行：

```bash
npm ci
npm run desktop       # 完整 Tauri 开发应用；Windows 也可用 dev-desktop.cmd
npm run dev           # 仅 Vite，不包含 Tauri 原生 IPC
npm run check
npm run build         # 仅前端生产构建
cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml
```

桌面安装包构建入口为 `npm run desktop:build`，但运行构建命令不代表通过发布门禁。独立 Rust 服务须使用自己的 manifest，例如 `cargo check --locked --all-targets --manifest-path services/cloud-agent/Cargo.toml`；仓库根目录没有统一的 Cargo workspace。完整验证见[如何编写测试](./how-to-test.md)。

## 修改实现时

- 前端以 `src/lib/api/` 的真实 IPC、`src/lib/types.ts` 和当前组件为准；不要复制已过时的伪 Command 或状态机示例
- MCP / Actions 工具实现共用 `tools::call_tool`，云端身份、原生批准和最终工具准入不可混为一层
- 配置写入保持加密、迁移、失败保留和当前系统凭据边界；测试使用隔离配置/凭据，不能重置真实用户数据
- 当前安全限制与未完成项见 [RC 台账](../releases/next-rc-ledger.md)。不得为获得绿灯跳过正向隔离测试、放宽权限、隐藏警告或将 deferred 改写成 PASS
- 保留单个源文件不超过 500 行、超出时拆分的开发约定；已有超限文件需在相关工作中处理，文档维护本身不扩展为源码重构
- Issue #86 的 opened-root authority 安全门槛仍未解决，快照相关验收须按 RC 台账跟踪

## 版本与安装包门禁

当前桌面六个版本字段均为 `0.6.0-rc.4`。纯文档维护无需递增版本；下一发布版本必须明确选择并与已有 tag/Release 核对，不能仅按“默认递增 patch”推导或覆盖已有版本。

确定的新版本必须同步：

1. `package.json:version`
2. `package-lock.json` 顶层及 `packages[""].version`
3. `src-tauri/Cargo.toml:package.version`
4. `src-tauri/Cargo.lock` 中 `coding-tools-mcp-desktop` 的版本
5. `src-tauri/tauri.conf.json:version`

不要替换依赖自身的同号版本。服务内部 crate 当前为 `0.1.0`，最终产品版本对齐需另行明确。候选版本与源码校验由 `scripts/rc_version_gate.py` 检查；含未提交文档的树也不应被宣称为干净发布源码。稳定版门禁和 RC 门禁不可互相替代。

台账中保留 `0.6.0-rc.4` 的工程诊断包不是新发布或最终资产。最终包必须绑定获准版本、冻结 source/tree、实际构建/安装载荷哈希和完整证据，不覆盖旧 tag/附件，也不靠改文件名升级。版本校验、某个安装步骤或单平台测试成功均不等于完整发布 PASS。

macOS 工作流仍为显式请求后的手动流程；Windows/Ubuntu 的集成、工程包和最终门禁以对应 workflow 为准，不因本文列出命令而获准触发发布。

---
*返回索引：[../project-context.md](../project-context.md)*
