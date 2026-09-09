# Ubuntu修复自审v7：Windows功能预算与发布重验

## 合并后真实复审：90/100，停止发布并打回

PR #4在候选a7c8fbd全部门禁通过后合并为cc8f730b。发布运行34366631756的Ubuntu22.04/24.04两种包原生作业和Linux基线成功，但Windows完整Rust一项失败，故acceptance/publish跳过，未公开v0.2.5。

Windows工件10110432345的ZIP SHA256已核对为64c546f2e8103393924127f4a1fab15ae2240119bbff4e2481d206a9929da33f。原始日志253通过、1失败：windows_workspace_scripts_and_python_unicode_execute_successfully中的powershell -NoProfile命令在10186ms因测试显式timeout_ms=10000终止，exit1、stdout为空。原同端口回归本次通过，不是AddrInUse复发。

该测试验证脚本和中文输出，却将启动和完成限制为10秒；Python模块循环又没有显式yield，默认等待仅1秒。执行器按测试预算超时已确认；冷启动/宿主调度可能诱发延迟，但未唯一确定内部原因，不能宣称10秒启动性能已修复。

## 最小修订

只改此cfg(windows)+cfg(test)函数，功能执行与等待显式30秒，等于生产默认执行预算；保留cmd、ps1、直接cmd、直接PowerShell、中文Python五类真实命令，重复5轮，每次失败立即断言而非失败重试；保留Python模块10轮。新增child_process、exit_code=0、termination_reason=exited和每条stdout内容断言，拒绝空输出。

原200ms执行截止回归保持不变。生产exec_command/超时监控/策略/会话、依赖和Linux发行入口不变；没有全局串行化、ignore、关闭安全检查或跳过原生门禁。35条实际命令需由Windows全量测试全部执行。

## 验证与影响

新增4项离线Python防回退检查：预算/等待、runner及输出断言、生产执行实现摘要不变、200ms截止不削弱。修复前2失败，修复后4通过；这是源码契约检查，不是Rust或原生Windows运行。

修改前exec.rs blob4b838143de73edd15ec4143926da5348cf9315fc与当前main逐字节核对。GitNexus1.6.9 upstream：目标测试0直接调用、0业务流程，LOW。本地旧规则快照的目标完整文件与当前main相同，但并非全仓最新图谱；FTS离线不可用，精确符号可用。提交前变更分析另外执行并保存原始JSON。

候选38/40正确性+28/30验证+20/20范围安全+10/10证据=96，仅准入新CI；任一真实失败继续打回。修复PR通过全部门禁再合并，最终main重建四组合原生、双平台Rust、20轮同端口及发布匿名校验。旧Windows v0.2.4不动。

官方参考：Cargo默认并行 https://doc.rust-lang.org/cargo/commands/cargo-test.html ；PowerShell启动排查 https://learn.microsoft.com/en-us/powershell/scripting/dev-cross-plat/performance/startup-performance 。评分为执行者自审，不是第三方审批或无缺陷保证。
