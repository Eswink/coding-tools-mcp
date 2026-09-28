# 需求文档：ubuntu-execution-sandbox

## 功能概述
Issue #73 / Epic #32 的受限首个增量：为 local-agent 的受信任宿主调用方提供 Linux x86_64 沙箱执行接口，在普通进程和 PTY 子进程 exec 前实施 Landlock 和 seccomp。基线为 593b173cb7c36d3ac7b8b633f1410399756ad7e5。
这是库级隔离能力，不是桌面、云端或真实机器的上线。已有 LocalAdmission / ExecPolicy 仍先于宿主执行；沙箱不签发授权，不提供模型可控的降级或联网开关。

## 历史经验与坑（来自记忆库）
暂无外部记忆服务。沿用 #74 的句柄持续持有方法：不要把检查得到的路径/端口在释放后当成仍然拥有的资源。GitNexus Rust/FTS 覆盖不完整，需要源码和实际回归补证。

## 术语定义
- 宿主策略：仅受信任 Rust 调用方创建的不可反序列化 LinuxSandbox。
- 沙箱启用：ExecSpec/PtySpec 明确携带宿主策略；无策略的既有低层 API 保留兼容，不宣称它自动变成沙箱。
- 失败关闭：隔离请求不能实施时不执行用户程序，不自动转用既有无沙箱路径。

## 范围边界
In Scope：Linux x86_64 的受信任根目录句柄、Landlock ABI >=3、seccomp、进程和 PTY 接入、自动测试及只读 CI。
Out of Scope：Linux 其他架构的成功隔离承诺、Windows 沙箱、真实工作站/VPS/ChatGPT、桌面/云 Agent 挂载、授权服务改造、网络放行、Hooks、worktrees、快照、安装器、部署、main 合并或发布。
宿主挂载仍是明确的后续集成事项；不得把本首增量描述为整个 #73 或父项目完成。

## 需求列表
### FR-1: 保留宿主授权与执行边界
**优先级:** Must
**用户故事:** 作为宿主调用方，我需要在授权后附加隔离策略，而不是由隔离机制产生授权。
#### 验收标准（EARS）
1. WHEN 调用 Registry 与 ExecPolicy THEN 系统 SHALL 保持原检查顺序且不扩展 capability。
2. WHEN 宿主指定 LinuxSandbox THEN 进程与 PTY SHALL 在用户程序执行前使用同一策略。
3. IF 策略请求失败 THEN 系统 SHALL 返回独立沙箱错误且不重试无沙箱执行。

### FR-2: 限定文件内容读写与继承描述符
**优先级:** Must
**用户故事:** 作为工作区所有者，我需要限制子进程读取或修改工作区之外的数据。
#### 验收标准（EARS）
1. WHEN 启动沙箱 THEN 系统 SHALL 以保留的 O_PATH 句柄授权工作区读写，只允许固定系统运行时和已选程序的只读/执行权限。
2. IF cwd 位于根外或通过符号链接逃逸 THEN 系统 SHALL 拒绝启动。
3. WHEN 子进程 exec THEN 系统 SHALL 关闭标准输入输出以外的继承描述符。
4. IF 尝试读写外部文件、符号链接目标或改变外部元数据 THEN 系统 SHALL 拒绝相应操作。
路径存在性/stat 等只读元数据隐蔽性不在 Landlock ABI3 的保证中；不宣称完整 mount namespace。

### FR-3: 默认拒绝网络及进程组逃逸
**优先级:** Must
**用户故事:** 作为所有者，我需要阻止未经批准的网络和从受控进程树脱离。
#### 验收标准（EARS）
1. WHEN 沙箱运行 THEN 系统 SHALL 拒绝 IPv4/IPv6/Unix socket 创建及网络/IPC 和危险跨进程能力。
2. IF 子进程尝试 setsid、setpgid、命名空间或不兼容系统调用 ABI THEN 系统 SHALL 拒绝。
3. WHEN 正常派生进程 THEN 子进程 SHALL 继承 Landlock/seccomp，不能卸载它们。

### FR-4: 缺失原语与不安全宿主失败关闭
**优先级:** Must
**用户故事:** 作为宿主，我需要可区分的隔离不可用错误。
#### 验收标准（EARS）
1. IF Landlock ABI <3、openat2/close_range/seccomp 不可用 THEN 系统 SHALL 拒绝启用沙箱。
2. IF 以 root 或提权身份请求沙箱 THEN 系统 SHALL 拒绝。
3. WHEN 隔离失败 THEN 公开错误 SHALL 不泄露主机路径、命令和环境。

### FR-5: 保留执行生命周期和平台兼容性
**优先级:** Must
**用户故事:** 作为客户端，我需要原有超时、取消、输出上限和 PTY 行为仍然有效。
#### 验收标准（EARS）
1. WHEN 超时、取消、输出超限或父进程退出 THEN 系统 SHALL 清理受控后代且保持有界 I/O。
2. WHEN PTY 请求输入或窗口大小变化 THEN 系统 SHALL 保留已有语义。
3. WHEN Windows 编译和测试 THEN 系统 SHALL 不启用 Linux 沙箱、不改变原平台实现。

### FR-6: 可核验自动验收与恢复
**优先级:** Must
**用户故事:** 作为维护者，我需要精确源码与自动测试证据。
#### 验收标准（EARS）
1. WHEN CI 完成 THEN 证据 SHALL 记录源码提交/树、平台、测试结果及哈希。
2. IF 未执行真实机器或宿主挂载 THEN 状态 SHALL 保持未验收，不标记通过。
3. WHEN 发布候选 THEN 维护者 SHALL 先复读远端分支，只允许普通快进且保留回滚说明。

## 非功能需求
- NFR-1：不新增根依赖/锁文件；子进程准备不访问网络。
- NFR-2：fork 后仅系统调用和已分配内存；策略仅作用于子进程，父进程不受限。
- NFR-3：新增 Rust 文件控制在500行内；既有超大文件只增加小范围接线。

## 依赖关系
现有 ProcessManager/PtyManager、LocalAdmission/ExecPolicy、libc；Ubuntu24.04 x86_64 的 Landlock ABI3+ 和 seccomp。
官方依据：https://docs.kernel.org/userspace-api/landlock.html 与 https://docs.kernel.org/userspace-api/seccomp_filter.html 。

## 检查清单
- [x] 六项 FR 明确、可测且有范围边界。
- [x] 真实验收和宿主挂载未被自动测试替代。
