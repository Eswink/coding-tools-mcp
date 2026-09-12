# 公网 MCP OAuth 路由修复与验收

## 已确认根因

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
这表明发现链在元数据请求处断开，不是 MCP 未启用 OAuth。

随后用户提供了 `research-system.eswlnk.com` 实际 BaoTa Nginx vhost。该
server 已用 `location ^~ /` 把一般请求反代到 `http://127.0.0.1:8080`，但
同时存在：

```nginx
location /.well-known {
    allow all;
}
```

这是本次 404 的确定根因。Nginx 先选择最长普通前缀；对于
`/.well-known/oauth-*`，`location /.well-known` 比 `location ^~ /` 更长，
因此 OAuth metadata 请求不会进入 8080 反代，而是按站点
`root /www/wwwroot/research-system.eswlnk.com` 作为静态路径处理。文件不存在
时就得到 Nginx HTML 404。`/mcp` 与 `/oauth/*` 不匹配这个更长前缀，所以
仍能进入 8080，这与公网观测完全一致。

仓库新增 `scripts/nginx-panel-prefix-regression.sh`，使用真实 Nginx
failure-first 复现这一精确配置形态：修复前 `/mcp` 经代理返回 200，三个
OAuth discovery 路径返回静态 404；加入精确 OAuth locations 后三个发现
路径恢复代理且 ACME 路径继续正常。

## 正确的路由契约

`/mcp`、三个发现 URL、`/oauth/authorize` 和 `/oauth/token` 必须到达同一
预期 MCP 运行实例，保留请求路径、查询参数、POST 表单和认证头。
不要将 metadata 静态伪造成 200；不要通过修改 issuer、关闭 OAuth、
清除工作区或重置用户凭据来掩盖反向代理 404。

FRP 的 HTTP 虚拟主机转发与 Cloudflare Named 的远程 ingress 都要覆盖
这些路径。当前仓库 FRP 生成器没有设置只限 `/mcp` 的 locations；
Named Tunnel 的远程路由不受本地安装包自动管理。更新桌面程序不等于
已修改公网 Nginx 或 Named Tunnel 配置。

## research-system.eswlnk.com 的最小修复

针对用户提供的实际 vhost，使用
`nginx-research-system-oauth.conf.example`。它固定复用已经工作的
`http://127.0.0.1:8080` 上游，并增加五个精确 `location =`：

- `/.well-known/oauth-authorization-server`
- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-protected-resource/mcp`
- `/oauth/authorize`
- `/oauth/token`

前三个是解除当前故障的必要路径；后两个当前已由 `location ^~ /` 转发，
但显式锁定可防止以后面板或 include 增加更具体规则时再次拆分 OAuth
控制面流量。

该 BaoTa vhost 已包含：

```nginx
include /www/server/panel/vhost/nginx/extension/research-system.eswlnk.com/*.conf;
```

因此优先将示例保存为：

```text
/www/server/panel/vhost/nginx/extension/research-system.eswlnk.com/oauth-routing.conf
```

这样无需替换面板管理的主 vhost。精确 location 在 Nginx 匹配中优先于
普通前缀和正则，所以即使原来的 `location /.well-known { allow all; }`
继续存在，OAuth discovery 也会走 8080；其他 `/.well-known/*`，包括 ACME
验证路径，仍保持原来的站点处理方式。

若已有相同精确 location，修改已有块而不是重复添加；`nginx -t` 会在
重复 location 时拒绝加载。不要删除证书申请 include，也不要把整个
`/.well-known` 改成无条件反代，否则可能破坏 ACME/其他验证文件。

## 通用 Nginx 模板

对于其他部署，可使用 `nginx-mcp-oauth.conf.template`。把
`__MCP_UPSTREAM__` 替换为已有 `/mcp` 转发使用的 HTTP 上游 origin，
不附加 `/` 或 `/mcp` 等 URI；把 `__MCP_HOST__` 替换为该转发所需的
Host 表达式或值。

模板只演示 HTTP 上游。已有 HTTPS 上游还必须复制并核对 SNI、信任链与
`proxy_ssl_verify` 等配置，不能降级为不验证 TLS。已有 server 级 rewrite、
认证网关或 WAF 限制仍需按权限边界单独检查；模板不自动移除任何访问
控制。发现文档应公开读取，但不能因此关闭 MCP OAuth、授权表单校验或
本地聊天审批。

`proxy_pass` 无 URI 时保留原始请求路径；添加 URI 可能改写转发位置，
务必独立核对。

## 应用、回滚与停止条件

先备份实际将编辑的配置，保留当前已工作的 `/mcp` 上游参数。
执行 `nginx -t`；失败时不要 reload。语法通过后再使用服务器既有管理
方式 reload，并从服务器外执行本文的公网验收。

若出现 5xx、其他站点异常、ACME 验证路径异常或认证边界变化，移除新
extension 文件或恢复备份，再次 `nginx -t` 并 reload。配置语法正确不
代表请求一定到了目标 server：仍需核对域名、SNI、实际生效 include 与
运行实例。

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
