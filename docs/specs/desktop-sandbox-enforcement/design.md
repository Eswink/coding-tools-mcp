# 设计文档：desktop-sandbox-enforcement
## 概述
覆盖FR-1至FR-6。复用9b2639d现有内核实现，不复制隔离规则。
## 技术方案
### 技术选型
Linux-only path dependency到coding-tools-local-agent。configure_command只准备并附加已有allocation-free pre_exec闭包，不启动命令、不签发授权。Tokio、现有进程组、SessionStore与ExecTaskStore保持。
### 架构设计
本地配置 -> 固定ToolContext目录句柄 -> 既有call_tool授权/策略 -> sandbox.configure -> 现有ticket issue/commit -> 已管理的child -> 既有会话与任务监督。
## 数据模型
Linux-only Arc<Result<LinuxSandbox,SandboxError>>携带原目录句柄或永久失败状态；background_snapshot只clone；不存在模型可反序列化许可。
## API设计
LinuxSandbox::configure_command(&mut tokio::process::Command)要求明确绝对program与cwd。desktop helper不公开工具路由。
## 设计决策
FR-1固定根而非每次按路径重开；FR-2强制准备且绝不fallback；FR-3采用已有桌面LocalAdmissionPermit而非开放shared LocalAdmission构造器；FR-4环境白名单与逐次内核检查；FR-5保留在途drain，普通Linux/tty也持有进程组；FR-6源码和测试分离留证。
## 测试策略
原始PR77的Rust探针5284c554f92064fc41d46af6b1e4c4b0fd135ff1和runner1fdb18eae060c7a9c9903f86f5687e272f9ca1d0按不可变SHA读取，以acceptance模式运行。新增库适配测试、桌面根替换/环境/缺失策略/模型字段及后台共享测试，双平台全套和生产库-D warnings。
## 风险评估
上下文构造CRITICAL（5条流程/7模块）；执行入口HIGH。已在前轮警告后继续进行固定范围接线和全套回归，不将图谱等级当安全认证。图谱FTS不可用；新源码须原生编译。要求Linux x86_64 Landlock ABI3+，系统runtime目录有限，不宣称所有开发工具链支持。
## 回滚
功能分支普通revert本增量；不删除授权数据、任务记录或历史迁移，不force更新main。

## 文件结构
修改services/local-agent/src/sandbox/mod.rs及库适配测试；src-tauri/Cargo.toml/Cargo.lock、tools/{context,dispatch,exec,session,mod}.rs；新增tools/linux_exec_sandbox.rs和对应测试；三份本规格与精确范围守卫。
