# 公网 MCP OAuth 路由修复与验收

## 已观测到的故障，不等于已读取服务器配置

2026-09-12 的独立 GitHub Actions 运行 `34691913140` 在不携带凭据、
不跟随重定向且校验 TLS 的条件下得到：

| 请求 | 实际结果 |
|---|---|
| GET /mcp | 200 application/json，匹配 v0.3.2 MCP 身份 |
| POST /mcp（未认证 initialize） | 401，包含正确的 Bearer resource_metadata 挑战 |
| GET /.well-known/oauth-authorization-server | 404 text/html，Server 标识 Nginx |
| GET /.well-known/oauth-protected-resource/mcp | 同上 |
| GET /.well-known/oauth-protected-resource | 同上 |

原始脱敏结果见 `../specs/public-oauth-routing/evidence/public-baseline.json`。
这表明发现链在元数据请求处断开，不能解释成 MCP 未启用 OAuth。
Server 响应头只是线索，不是可信来源认证；尚未读取实际 Nginx 配置，
不能认定是某个面板或某一条 location 导致。

## 正确的路由契约

`/mcp`、三个发现 URL、`/oauth/authorize` 和 `/oauth/token` 必须到达同一
预期 MCP 运行实例，保留请求路径、查询参数、POST 表单和认证头。
不要将 metadata 静态伪造成 200；不要通过修改 issuer、关闭 OAuth、
清除工作区或重置用户凭据来掩盖反向代理 404。

FRP 的 HTTP 虚拟主机转发与 Cloudflare Named 的远程 ingress 都要覆盖
这些路径。当前仓库 FRP 生成器没有设置只限 `/mcp` 的 locations；
Named Tunnel 的远程路由不受本地安装包自动管理。更新桌面程序不等于
已修改公网 Nginx 或 Named Tunnel 配置。

## Nginx 最小修复模板

模板：`nginx-mcp-oauth.conf.template`。它只为五个 OAuth 路径增加精确
`location =`，不改变已有 `/mcp` 转发、ACME 证书验证和隐藏文件保护。

先在实际处理该域名 HTTPS 的 Nginx 上确认 `server_name`、include 文件、
`/.well-known/` 静态目录/正则、错误页、rewrite 与实际 `/mcp` 上游。
不要直接把未经脱敏的 `nginx -T` 输出上传，它可能包含内部地址或秘密。

把 `__MCP_UPSTREAM__` 替换为已有 `/mcp` 转发使用的 HTTP 上游 origin，
不附加 `/` 或 `/mcp` 等 URI；把 `__MCP_HOST__` 替换为该转发所需的
Host 表达式或值（通常是 `$host`，FRP 虚拟主机可能需要固定域名）。
**不要假定网关的 `127.0.0.1:28766` 就是桌面服务。** 两者不在同一主机
时应复用已经验证的 FRP/隧道/内部代理目标，而不是猜端口。

该模板仅演示现有 HTTP 上游跳转；已有 HTTPS 上游还必须复制并核对
SNI、信任链与 `proxy_ssl_verify` 等配置，不能降级为不验证 TLS。
已有 server 级 rewrite、认证网关或 WAF 限制仍需按权限边界单独检查；
模板不自动移除任何访问控制。发现文档应公开读取，但不能因此关闭
MCP 的 OAuth、授权表单校验或本地聊天审批。

在站点原有 HTTPS `server` 内纳入替换后的内容。若已有相同精确
location，请修改已有块，不要添加重复块；多个 MCP 共用同一 origin
时先分配独立 origin，不能覆盖另一个服务的发现文档。

Nginx 精确 location 优先于正则和普通前缀，因此能避免通用
`/.well-known/` 静态块或隐藏路径规则吞掉 OAuth 发现。仅添加
`location /` 并不保证覆盖这些规则。`proxy_pass` 无 URI 时保留原始
请求路径；添加 URI 可能改变转发位置，务必独立核对。

## 应用、回滚与停止条件

先备份实际将编辑的配置，保留当前已工作的 `/mcp` 上游参数。
执行 `nginx -t`；失败时不要 reload。语法通过后再使用服务器既有管理
方式 reload，并从服务器外执行本文的公网验收。模板不会自动执行
reload，也不会修改 DNS、隧道 token 或其他站点。

若出现 5xx、其他站点异常、ACME 验证路径异常或认证边界变化，恢复
备份、再次 `nginx -t` 并 reload。配置语法正确不代表请求一定到了
目标 server：仍需核对域名、SNI、实际生效的 include 与运行实例。

## 公网验收（本机通过不能替代）

使用 `python scripts/probe-public-oauth.py` 对用户报告的固定 origin
进行无凭据发现检查，非通过退出码必须保留。读取公开 metadata
不等于登录授权成功；它不会携带用户密码或调用业务工具。

必须同时满足三份 JSON 元数据字段匹配、未认证 `/mcp` 的 401 挑战
正确，并且挑战中的 URL 可公开读取。`/oauth/authorize` 缺参数的 400
和 GET `/oauth/token` 的 405 仅供定位，不代表登录或换票已验收。
随后由用户在真实 ChatGPT 账号完成 OAuth 登录与本地聊天审批。
禁止将合成测试账号、CI 原生窗口或安装成功当作真实账号授权成功。

## 参考

- Nginx location：https://nginx.org/en/docs/http/ngx_http_core_module.html#location
- Nginx proxy_pass：https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass
- MCP 授权：https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
