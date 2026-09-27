# 设计文档：desktop-sandbox-prerelease
## 概述
覆盖 FR-1、FR-2、FR-3、FR-4、FR-5、FR-6。原链路为 MCP/Actions -> 共用 call_tool -> 会话授权/策略 -> exec_command/run_command；后台任务再次走共用入口。原生PTY库和桌面TTY标志不是同一接口。
## 技术方案
### 技术选型
Linux目标的本地path依赖复用 coding-tools-local-agent，不复制内核过滤器。新增 safe configure_command 只准备及附加 pre_exec；授权仍由桌面已存在的两阶段准入负责。
### 架构设计
ToolContext固定 LinuxSandbox 目录句柄，background_snapshot克隆同一策略。Linux远程执行先检查模型参数与原策略；创建隔离配置后，在spawn前提交本地票据；普通进程及TTY标志均使用受管进程组。权限只从远程已验证会话进入，不新增公开LocalAdmission构造器。
## 数据模型
上下文新增Linux-only的Result<LinuxSandbox,SandboxError>；失败值持续保留，使损坏配置不能按调用自动降级。授权许可是内存不可序列化值，不改变持久授权格式。
## API设计
LinuxSandbox::configure_command(&mut tokio::process::Command) -> Result<(),SandboxError>。只读取实际命令的program/cwd，清空环境后附加准备好的内核动作；调用者必须先完成授权和策略，不提供远程参数开关。桌面linux_sandbox模块处理票据、错误及元数据；未成功spawn不能声称enforced。
## 设计决策
FR-1：在宿主上下文固定句柄，不在模型派发时重建根目录。
FR-2：保持所有syscall策略不变；使用现有ProcessTree建立进程组，再由pre_exec施加Landlock/seccomp，所有已有工作控制API保持。
FR-3：保留现有“撤销先禁止新工作，已提交工作排空”的语义，不把撤销偷偷改成全平台强杀。取消或超时会清理受限进程组；新票据复核暂停/重启/撤销。票据许可覆盖启动提交；会话仍归已有工作注册表管理。
FR-4：子进程只继承固定PATH/LANG/HOME/TMPDIR，不透传宿主机密；TMPDIR='.'限制临时文件在工作目录。内建诊断并无子进程，不能报OS隔离成功。环境API区分要求隔离与已实际探测。
FR-5：复用PR77原样断言及分类器；不删除失败标记或允许零匹配通过。不把Windows兼容测试当作Windows沙箱证据。
FR-6：候选产物与GA/完整路线图准入分开陈述。未完成工程不因生成ZIP而改为verified。
## 文件结构
services/local-agent/src/sandbox/mod.rs；src-tauri/Cargo.toml及Cargo.lock；src-tauri/src/tools/{context,exec,dispatch,session,mod,linux_sandbox,linux_sandbox_tests}.rs；tests/cloud-gateway的原样PR77探针；专用只读CI；本规格。
## 测试策略
FR-1目录替换/后台共享；FR-2原样MCP越界/网络/TTY与Linux库级测试；FR-3旧授权完整回归、取消/超时/后台任务/重启；FR-4模型开关/环境/元数据；FR-5双平台完整回归；FR-6版本/源码/哈希/包内容检查。
## 风险评估
上下文构造CRITICAL/58上游，执行入口HIGH/8；已逐个阅读直接调用者并限定Linux路径。图谱FTS不可用，Rust解析不完整；风险评级不能当作安全认证。已有Windows策略型执行不因此获得新隔离承诺。使用受限环境可能让依赖用户HOME或外部缓存的工具失败；不为兼容而扩大授权。
## 回滚
仅普通revert候选提交；不覆盖共享分支、不删除持久授权或任务墓碑，不回放不确定工作。

## 准入锁等待复核
FR-3：原票据只在commit函数入口校验过期，等待授权/执行门锁后可能已过期。新增两次最后边界复核及锁竞争回归，失败时释放临时执行许可，不增加在途工作。新增auth/local_admission_expiry_tests.rs，其他授权语义不变。
