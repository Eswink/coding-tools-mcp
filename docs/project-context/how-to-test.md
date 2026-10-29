# 如何编写测试

> 测试入口来自[项目上下文](../project-context.md)基线中的真实源码和 workflow。本文列出运行方法，不声明这些测试已在本次文档维护中执行或通过。

## 测试层次

| 层级 | 入口 / 位置 | 证据边界 |
|------|-------------|----------|
| 桌面 Rust 单元测试 | `src-tauri/src/` 中的测试模块 | 部分配置测试使用内存凭据替身 |
| 桌面 Rust 契约/集成测试 | `src-tauri/tests/` | `call_tool_contract`、`call_tool_security`、`exec_input_contract`、harness / history 等实际 targets |
| 共享运行时 / 云网关 | `services/*/Cargo.toml`、网关 `tests/` | portable 与真实 PostgreSQL / WSS 测试需区分 |
| 前端回归 | `tests/*.test.mjs` / `*.test.cjs` | Node 内置 runner；完整驱动先编译 TypeScript 测试输入 |
| 浏览器交互 | `tests/*browser*.py` 等 | Playwright；模拟 IPC 不构成原生/真实账号验收 |
| 原生与安装包 | `scripts/`、Linux / Windows package workflows | 实际平台、凭据服务、已安装载荷和来源绑定 |
| 部署与交付契约 | `tests/cloud-gateway-deployment/`、`scripts/*_tests.py` | 容器拓扑、审计与归档验证，不等于真实 VPS 验收 |

## 常用本地入口

在仓库根目录执行，先满足平台依赖：

```bash
npm ci
npm run check
npm run build
node scripts/前端完整回归v4.mjs
node --test tests/cloud-gateway/*.test.mjs tests/delivery/*.test.mjs

cargo fmt --all --check --manifest-path src-tauri/Cargo.toml
cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo rustc --locked --lib --manifest-path src-tauri/Cargo.toml -- -D warnings

# 精确集成 target；路径应在当前 src-tauri/tests/ 中存在
cargo test --locked --manifest-path src-tauri/Cargo.toml --test call_tool_contract
cargo test --locked --manifest-path src-tauri/Cargo.toml --test call_tool_security
cargo test --locked --manifest-path src-tauri/Cargo.toml --test exec_input_contract

# 独立 crate；网关这里只选择不依赖真实数据库的 portable 集合
cargo test --locked --manifest-path services/cloud-agent/Cargo.toml
cargo test --locked --manifest-path services/local-agent/Cargo.toml
cargo test --locked --manifest-path services/cloud-gateway/Cargo.toml --lib --test service_contracts --test enrollment_contracts
```

当前没有 `tests/compliance/` 或 `cargo test --test compliance` 目标，也没有 Vitest 配置；不能用这些旧计划命令代替实际回归。全量前端驱动覆盖根 `tests/` 的 Node 测试，网关/交付子目录另行运行。

## 原生和集成前提

- Linux 桌面集成测试中的生产库使用真实系统凭据，需隔离的 D-Bus / 已解锁 Secret Service 会话及 Tauri 原生库；普通单元替身通过不能证明凭据生命周期正确
- `native-keyring-tests` 是显式 opt-in 的真实凭据测试，`cloud-agent-integration-tests` 需要独立 PostgreSQL / TLS 网关夹具；不要只打开 feature 而遗漏 fixture
- `.github/workflows/dot-rc-integration.yml` 定义 Windows、Ubuntu 22.04/24.04、真实传输和进程/浏览器的独立 jobs；复用其设置及精确测试选择，记录非零测试数量
- 容器拓扑需要 Docker；原生 GUI 和安装验收需要相应系统会话。环境缺失时报告 blocked / 未运行，不能改成测试通过

## 交付契约与验收

局部交付逻辑可运行 `python scripts/release_preflight_tests.py`、`python scripts/rc_version_gate_tests.py` 等契约测试；它们验证校验器，不等于产品发布验收。最终候选还需准确来源、完整矩阵、依赖审计、安装载荷和归档证据，详见[RC 台账](../releases/next-rc-ledger.md)及 `.github/workflows/final-rc-packages.yml`。

编写和报告测试时：

1. 先明确行为与拒绝条件，使用当前 schema/契约；`old/` 只作历史参考
2. 修复先保留可复现失败，再运行原断言和关联回归；不要仅靠改超时、过滤失败或弱化断言获得绿色
3. 区分单元、模拟 IPC、真实原生、真实传输和已安装应用证据，并绑定 source SHA、平台、命令、数量和失败/未运行项
4. 过滤到零个测试不是 PASS；前一提交、单个组件或某个安装步骤的成功不能替代当前完整候选
5. Windows 隔离与快照仍有未完成门槛，包括 Issue #86 的 opened-root authority。真实主机、VPS、ChatGPT 验收仍 deferred，不得补写成功

---
*返回索引：[../project-context.md](../project-context.md)*
