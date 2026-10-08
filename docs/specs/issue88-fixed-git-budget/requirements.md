# 需求文档：受预算约束的固定 Git 读取

## 功能概述

实际基线 F 为 8bdd5f327b4603c5570dc764e2d62fecbe6e02d2，树 b75fdae6b9a2cb9589b51d832d7ba638384cb6b8。
现有发布会话已把同一个 deadline/check_active 传入下载、归档和校验和处理；云产物源码验证中的四个 Git 读取仍走无界继承环境子进程。
本增量只完成这条实际消费调用链的 Git 预算、输入支持边界和已知子进程所有权，不产生完整 bundle/native 接受或真实发布授权。

## 需求列表

### FR-1 原预算贯穿既有消费链
- `_verify_bundle_bytes` → `verify_consumed_bundle` → `verify_consumed_cloud` → `verify_build` → `exact_build_audit.verify` SHALL 传递完全相同的期限和回调对象。
- 四个现有模块仅增加可选关键字；省略控制时 SHALL 保持原调用形状、原 Git 路由和无新时钟读取。
- 单次受控 verify SHALL 保持一个 Reader，跨源码身份与后续 tracked inventory 使用原期限，不按命令续期。

### FR-2 固定且不启动 helper 的只读来源验证
- 受控读取 SHALL 只执行固定可信 `/usr/bin/git` 的六项原生命令，保留原四项并增加原生 config 与 index-stage 预检。
- SHALL 以原生 `config --no-includes` 在仓库外解析保留描述符指向的有限配置；不自行解析 Git 配置或二进制 index。
- SHALL 在 status 前拒绝 gitlink、非零 stage、非白名单配置、替代对象/借用对象/promisor/工作树间接引用和非普通 SHA1 独立仓库。
- SHALL 使用全新固定子进程环境、禁用 helper/协议/替换/可选写锁并固定输出上限；不得改写用户仓库配置或依赖继承 PATH。
- 可信已安装 Git 是前提；观察到的哈希只证明身份稳定，不是假称上游签名认证。

### FR-3 原期限、有限输出和粘性清理
- 每次预检、启动、有限管道读取和成功返回 SHALL 检查原控制；64KiB 最大读取且最多读取剩余上限加一字节。
- 原 HEAD 不匹配、脏源码、命令失败、输出超限及配置/index 内容错误 SHALL 保持明确优先级，不被后置超时覆盖。
- 真实已知子进程 SHALL 在取消、超时或其他失败后有限 TERM/KILL/reap；回调不得介入失败清理。
- 任意子进程/管道/selector/保留句柄清理不确定 SHALL 使用既有 `transport_cleanup_uncertain`，让 Stage 保留已知产物而不删除。
- SHALL 不以 leader 退出声称进程树静默，也不声称可中断原生解析或系统调用。

### FR-4 有限来源组合与真实回归
- SHALL 精确绑定实际 F、完整树、受控路径、模式、上限、七项全字节逆变换及十四项历史输入；选中拓扑后的内容错误必须终止。
- 原 1493 个独立 ID 及 strict303/contracts755/consumer452 SHALL 全部保留；新增 36 运行用例和 12 组合用例。
- SHALL 在真实 CPython3.12 和原生 Git 上验证命令顺序、脏文件、恶意 helper 输入、真实子进程/管道/取消/TERM/KILL/reap与完整两次下载调用链。
- SHALL 维持全局发布阻断、固定主机、权限、凭据、原收据字节、默认根保留和已关闭退休所有权行为。

## 非功能需求

- 有限范围 17 路径，7 修改、10 新增，1813 树条目；总 Git 差异行不超过 2400，所有文件最多 500 行。
- Git config 及解析输出各64KiB，index64MiB，index/status/ls-files 输出各16MiB，SHA1输出恰41字节；超限拒绝，不截断接受。
- 固定 binary64MiB、元数据条目262144、保留FD1024、层级64；单次失败子进程清理2秒含250ms TERM期。
- 输出只含固定错误码，不泄露配置、环境、stderr 或凭据；已知无并发写入前提不得升级为抗恶意TOCTOU保证。

## 依赖关系

- 复用现有消费者、出版会话控制、私有根和清理不确定处理；不修改这些权威边界。
- 仅 Linux 受控路径；不支持的系统、Git 能力或仓库结构失败关闭，默认历史路径不受影响。
- 源码观察 `_observe` 的另一条 Git 链和 JSON/TOML/原生解析中途硬中断仍在范围外；缺失真实门禁继续阻断。
- Windows、PR98取消载荷、快照实现、最终版本/tag/Release、远程保护与凭据不在本增量内。
