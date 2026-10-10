# 需求文档：暂存源码观察的共享 Git 预算

## 功能概述

把既有 Stage._observe/_source 的完整 Git 调用链纳入调用方原 deadline/check_active。
复用 PR143 已经真实双 Ubuntu 验证的固定 Reader，覆盖版本、源码一致性、父审 manifest、tag 和 workflow blob。
准备基线7eb98b76已由正常PR144 merge推进；本增量绑定实际F649dc0fcb0bd299ebf7910e567e09c32b7962a9b/tree956807f8c35b6ce12272b3abcfbbd85493e9c9f9及最新Windows dispatcher。
本增量不启用真实发布，不把 caller 报告变为授权，也不完成其他仍缺失的发布门禁。

## 需求列表

### FR-1 完整观察链保持同一预算
- 初始进入和进入时的最终重验 SHALL 使用原 activation deadline/check_active；后续重验 SHALL 使用本次操作传入的 pair。
- 同一原期限 SHALL 贯穿 RC 版本/source、reviewed provenance、所有 manifest 路径和 tag/workflow 读取，不按 Reader 或命令续期。
- 省略控制 SHALL 保持旧调用形状、空 kwargs 和无新增时钟；不得把后续操作替换为保存的旧 activation pair。

### FR-2 仅增加九类 typed 只读 Git 操作
- SHALL 仅增加 commit HEAD、tracked diff、all-untracked、ancestry、单树项、原始 blob、name/status diff、tag OID 和 tag kind；复用已有 HEAD tree。
- SHALL 保留固定可信 binary、原生配置/index 预检、精确子进程环境和全部输出边界；动态操作数在启动前检查。
- SHALL 禁止调用者提供 argv、flags、可接受退出码集合、cap、可执行文件或环境；diff 显式禁用外部 diff/textconv。
- diff/ancestry 的退出码1 SHALL 仅作为这两类操作的既有语义失败，其他非零码失败关闭。

### FR-3 既有验证内容与错误顺序不变
- SHALL 保留六版本字段、源码 SHA、tracked/全部 untracked（含 ignored）、祖先、manifest schema/排序/完整 before-after 哈希、树、tag 和 workflow 检查。
- SHALL 不用 status 代替 tracked+all-untracked，不合并 tag 两次读取，不省略 manifest 第二次读取，也不跳过任何变更路径。
- 已观察到的内容/退出/IO 失败 SHALL 在后置成功预算检查之前保留原原因；阶段普通错误继续由既有 snapshot._call 清理，ConsumerError 透传。
- 受控 RC/reviewed 成功 SHALL 在语义比较和自有 Reader 关闭后再次检查原预算；source 最后 workflow 比较和关闭后的检查 SHALL 先于 live-tag API 读取。
- 受控 provenance 的 stable 路线 SHALL 失败关闭；无控制的 stable 行为保持原样，不改 stable verifier。

### FR-4 所有权与清理不确定性保持粘性
- SHALL 复用现有已知 child/pipe/selector/FD 所有权与有限 TERM/KILL/reap，不以 leader 退出声称树静默。
- 早期 source 失败 SHALL 不创建私有暂存根；后期重验失败 SHALL 保留已发生的效果和现有清理状态。
- 清理不确定 SHALL 保持 transport_cleanup_uncertain 和私有字节保留；不增加删除、重试或系统安全设置变更。

### FR-5 有限组合与真实证明
- SHALL 保留所有原测试 ID/断言 AST；两个已知测试适配仅转发 kwargs、把原六-child 观察限定原 bundle phase。
- SHALL 在原 source 路线本身测试新操作和初始/后期预算，不能通过绕过 _source、提高旧计数或放宽 owner0 取得通过。
- SHALL 冻结实测路径/caps/新 ID、全字节 inverses 和历史输入后才编辑实现；最终基线采用实际 post144 F。
- SHALL 使用真实 Git/child/pipe、源码绑定的双 Ubuntu 证据和全部必要当前上下文检查；环境不支持的本地失败不记为 PASS。

## 非功能需求

Reader 必须保持清晰且不超过500行；若需有限提取，先报告准确新增路径与影响，再冻结范围。
原生解析/系统调用只能在返回边界协作检查，不声称硬解析终止或抗恶意并发写入。
须先测量完整 manifest 路径循环的大小与操作成本；拟定输出上限不是已通过的性能证明。
原30/60s正例和3s后期故障用例须到达其真实预期阶段；新增 source 开销不能靠提高期限或提早错误代替原断言。

## 依赖关系

Windows admission 与本次共享最新 dispatcher；Windows 先整合，禁止 sibling-profile 或宽 ancestry 接受捷径。
PR98取消载荷、snapshot实现、凭据、远程保护、主分支/tag/Release及真实发布启用均在范围外。
