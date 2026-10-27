# ChatGPT 连接器与桌面端“云连接”接入说明（rc.2 手动测试用）

状态：**操作员手动执行，未经端到端验证**。本文只记录能在代码里核对到的端点和行为（核对基线：
`96234102`，以及 rc.2 源码 `bdc4aeb5`），不描述 ChatGPT 的具体界面。部署步骤本身见
[`kit/RUNBOOK.md`](kit/RUNBOOK.md)；设备登记的权威说明见
[`services/cloud-gateway/ENROLLMENT.md`](../../services/cloud-gateway/ENROLLMENT.md)。
本机回环运维控制台（≠ 公网 admin）见下文 §5 与 [`ops-console/README.md`](ops-console/README.md)。
本文所有 `<...>` 都是占位符，不要把真实密钥、口令、令牌写进仓库、工单或聊天记录。

## 1. 镜像来源：rc.2 云端镜像（按镜像 ID 引用）

使用预发布 `v0.7.0-rc.2` 的附件（打包运行 40428267551，源码 `bdc4aeb5`，产品版本 `0.7.0-rc.2`）：
`cloud-image.tar`、`cloud-linux-amd64.tar.gz`、`SHA256SUMS-cloud.txt` 等。

```bash
sha256sum -c SHA256SUMS-cloud.txt          # 先校验，全部 OK 再继续
docker load -i cloud-image.tar             # 镜像没有 tag，输出 "Loaded image ID: sha256:..."
docker image inspect --format '{{.Id}}' sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a
```

渲染时把镜像 ID 原样传给 `--gateway-image`（`runtime_topology.image_refs` 只接受
`sha256:<64 位十六进制>` 形式的本地不可变镜像 ID）：

```bash
python3 deploy/cloud-gateway/kit/kit.py render ... \
  --gateway-image sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a ...
```

镜像内含 `/usr/local/bin/` 下的 `coding-tools-gateway`、`coding-tools-agent`、
`coding-tools-control-gateway`、`coding-tools-mcp-gateway`，ENTRYPOINT 是 `coding-tools-mcp-gateway`
（见 `Dockerfile.runtime`）。`cloud-linux-amd64.tar.gz` 里是同一批四个 Linux amd64 二进制。

**源码一致性（已核对）**：`git diff bdc4aeb5 96234102 -- services/cloud-gateway/src services/cloud-gateway/migrations deploy/cloud-gateway/Dockerfile.runtime`
输出为空，即网关服务端源码、迁移和运行时 Dockerfile 在 rc.2 与 `96234102` 之间**零差异**。
`services/cloud-gateway` 下的差异只在 `Cargo.lock`、`Cargo.toml`、`examples/`、`tests/`。
另外，网关链接的 `services/cloud-agent` 库在两者之间有改动（S1：`agent/host/*` 的重连逻辑，加上
`agent/config.rs`、`lib.rs`）。因此 rc.2 镜像里的二进制**不含 S1**，`96234102` 的锁文件依赖版本也和 rc.2 不同。

## 2. 在 ChatGPT 中添加 MCP 连接器

以下 URL 由 `services/cloud-gateway/src/config.rs`（`PublicIdentity`）生成，并经
`deploy/cloud-gateway/current_nginx_include.py` 的源码契约与 location 渲染核对；前缀固定为 `/coding-tools`。

| 用途 | 地址 |
|---|---|
| **MCP 服务器 URL**（填到连接器里的就是这个） | `https://<GATEWAY_DOMAIN>/coding-tools/mcp/<CONNECTOR_UUID>` |
| 受保护资源元数据（RFC 9728） | `https://<GATEWAY_DOMAIN>/.well-known/oauth-protected-resource/coding-tools/mcp/<CONNECTOR_UUID>` |
| 授权服务器元数据（RFC 8414） | `https://<GATEWAY_DOMAIN>/.well-known/oauth-authorization-server/coding-tools/oauth` |
| issuer | `https://<GATEWAY_DOMAIN>/coding-tools/oauth` |
| authorization_endpoint | `https://<GATEWAY_DOMAIN>/coding-tools/oauth/authorize` |
| token_endpoint | `https://<GATEWAY_DOMAIN>/coding-tools/oauth/token` |

- `<GATEWAY_DOMAIN>` 和 `<CONNECTOR_UUID>` 必须与 `gateway-private/config.json` 的 `origin`、`connector`
  以及 `kit.py render --domain/--connector` 完全一致。origin 必须是 `https://` 且不能带路径，网关不会替你做规范化。
- MCP 端点只接受 `POST`。未带令牌时返回 401，并带
  `WWW-Authenticate: Bearer resource_metadata="<上表受保护资源元数据 URL>", scope="mcp"`。
- 元数据里声明的能力：`response_types_supported=["code"]`、
  `grant_types_supported=["authorization_code","refresh_token"]`、`code_challenge_methods_supported=["S256"]`、
  `scopes_supported=["mcp"]`、`token_endpoint_auth_methods_supported=["client_secret_post","none"]`。
- **没有动态客户端注册**：元数据中没有 `registration_endpoint`，代码里也没有注册路由。客户端只能由操作员用
  `coding-tools-gateway register-client` 预先登记，而且每份配置只有一个 `client_id` / `redirect_uri`
  （来自 `config.json` 的 `client_id`、`redirect_uri`、`client_authentication`）：
  - `client_authentication: "public"`：令牌端点不使用 client secret（`none`）。
  - `"confidential"`：`register-client` 必须经 stdin/密钥文件提供 `client_secret`，令牌端点用 `client_secret_post`。
  - `redirect_uri` 必须是 `https`，不能带 fragment，查询串里不能有 `code`/`state`/`iss`/`error`，而且必须与
    ChatGPT 实际使用的回调地址逐字一致。ChatGPT 的回调地址要以 ChatGPT 当时显示的为准，本文不提供，也未验证。
  - ChatGPT 是否提供填写 client_id / client secret 的入口、入口在哪，本文**未验证**；如果它只支持动态注册，就无法接入本网关。

授权流程（代码行为）：

1. ChatGPT 访问 MCP URL 后收到 401，然后按 `resource_metadata` 依次读取资源元数据和授权服务器元数据。
2. 浏览器打开 `GET /coding-tools/oauth/authorize`。必须带齐 `response_type=code`、`client_id`、`redirect_uri`、
   `resource`（等于上面的 MCP 服务器 URL）、`scope=mcp`、`code_challenge`、`code_challenge_method=S256` 和 `state`，
   缺一项或取值不对都会被拒绝。
3. 网关返回登录页，提交到 `POST /coding-tools/oauth/login`（CSRF + 口令）。这里的口令就是操作员执行
   `provision-owner` 时设置的所有者口令（密钥文档中的 `password` 字段）。
4. 随后在同意页提交到 `POST /coding-tools/oauth/consent`，网关带授权码重定向回 `redirect_uri`。
5. ChatGPT 在 `POST /coding-tools/oauth/token` 用授权码和 PKCE verifier 换取访问令牌和刷新令牌，
   之后可以用 `refresh_token` 续期。刷新令牌用一次就作废并换新；如果重放已用过的刷新令牌，整个令牌族都会被吊销。

内层 Nginx 限流见 `kit/RUNBOOK.md` §4：OAuth 和发现端点 10r/m（burst 5），`/coding-tools/mcp/` 10r/s（burst 40）。
宝塔外层 location 片段（`baota-locations.conf`，由 `current_nginx_include.locations` 生成）包含：两个精确的
`/.well-known/...` 元数据路径、`^~ /coding-tools/` 前缀、`= /coding-tools/agent`（WSS），以及对 `= /coding-tools` 返回 404。
每个 location 都先校验 Host，不匹配返回 421。

OAuth 授权**不等于**执行授权：桌面端还要导入连接、选中设备、在本机批准会话（见下节）。

## 3. 桌面端“云连接”的两个 JSON 从哪里来

桌面端 rc.2 的 CloudConnectionPanel 依次让你选择两个本地文件：“云连接配置 JSON”和“本机签名私钥 JSON”。
Tauri 命令 `import_cloud_connection_files` 要求两个都是绝对路径的普通文件（不接受符号链接），配置不超过 16 KiB，
私钥不超过 4096 B。导入只保存连接身份，不会自动连接，也不会授权聊天。桌面端**自己不生成密钥**。

完整流程（命令来自 `services/cloud-gateway/ENROLLMENT.md` 和 `src/service/enrollment*.rs`）：

1. **设备端生成私钥**（私钥只留在这台设备上，不要上传或发给网关）：
   `coding-tools-agent generate-key --output-file <ABS_PRIVATE_DIR>/key.json`
   生成的就是“本机签名私钥 JSON”，格式只有一个字段：
   ```json
   {"pkcs8": "<BASE64URL_NO_PAD_ED25519_PKCS8>"}
   ```
2. **网关端签发邀请**（5 分钟内有效，只能用一次；邀请也是凭据）：
   `coding-tools-gateway invite-device --config <GATEWAY_CONFIG_JSON> --secrets-file <SERVICE_SECRETS_JSON> --output-file <ABS_PRIVATE_DIR>/invitation.json`
   邀请内容为 `{"version":1,"origin":...,"prefix":...,"connector":...,"token":"<INVITATION_TOKEN>"}`。
3. **设备端单独固定网关身份**：写一个公开的 JSON，只能有 `origin`、`prefix`、`connector` 三个字段，
   不要直接信任邀请里携带的身份值：
   ```json
   {"origin": "https://<GATEWAY_DOMAIN>", "prefix": "/coding-tools", "connector": "<CONNECTOR_UUID>"}
   ```
4. **设备端生成证明**：
   `coding-tools-agent prove-enrollment --config <PINNED_IDENTITY_JSON> --input-file <ABS_PRIVATE_DIR>/invitation.json --key-file <ABS_PRIVATE_DIR>/key.json --output-file <ABS_PRIVATE_DIR>/proof.json`
   只把 proof 交回网关操作员。proof 里有邀请令牌、公钥和签名，不含私钥。
5. **网关端兑换**：
   `coding-tools-gateway redeem-device --config <GATEWAY_CONFIG_JSON> --secrets-file <SERVICE_SECRETS_JSON> --input-file <ABS_PRIVATE_DIR>/proof.json --output-file <ABS_PRIVATE_DIR>/connection.json`
   输出的就是“云连接配置 JSON”（桌面端 `ConnectionConfig` version 1，未知字段会被拒绝）：
   ```json
   {
     "version": 1,
     "origin": "https://<GATEWAY_DOMAIN>",
     "prefix": "/coding-tools",
     "connector": "<CONNECTOR_UUID>",
     "device": "<DEVICE_UUID>",
     "device_epoch": <DEVICE_EPOCH>,
     "authority_epoch": 1,
     "public_key": "<BASE64URL_NO_PAD_ED25519_PUBLIC_KEY_32B>",
     "run_seconds": 3600
   }
   ```
   桌面端导入时会校验：`origin` 是规范的 https origin；`prefix` 只有一段，由小写字母、数字和 `-` 组成；
   `connector`、`device` 是非 nil 的小写连字符 UUID；两个 epoch 都大于 0；`run_seconds` 在 1 到 3600 之间；
   `public_key` 必须与私钥 JSON 里的公钥匹配，否则报 InvalidBinding。
6. **网关端显式选中设备**：
   `coding-tools-control-gateway select-device --config <GATEWAY_CONFIG_JSON> --secrets-file <SERVICE_SECRETS_JSON> --device <DEVICE_UUID>`
   已有的不同选择不会被覆盖。
7. 桌面端为工作区导入上面两个文件，然后在桌面端分别选择工作区、批准会话（这两步是独立的必需操作）。

说明：

- 网关端命令在 VPS 上可以按 `kit/RUNBOOK.md` §6 的方式，以 `operator` 服务运行镜像内的
  `/usr/local/bin/coding-tools-gateway` / `coding-tools-control-gateway`，例如
  `docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json run --rm -T --no-deps --entrypoint /usr/local/bin/coding-tools-gateway operator invite-device --config /run/gateway/config.json --secrets-stdin --output-stdout`。
  用 `--output-stdout` 时 stdout 就是凭据通道，不要 tee 进日志。这种容器内调用方式本文**未实际执行验证**。
- `<SERVICE_SECRETS_JSON>` 的字段是 `database_url`、`identity_key`，`provision-owner`/`rotate-owner` 时还要加
  `password`，confidential 模式的 `register-client` 还要加 `client_secret`。只经 stdin 或 0600 私有文件传入。
- rc.2 **只提供 Linux amd64 的 `coding-tools-agent`**。在 Windows 上，按 ENROLLMENT.md 的说法，凭据文件读写会被拒绝，
  只能走 `--output-stdout` / `--bundle-stdin` 管道模式，而 rc.2 没有 Windows 版 agent 二进制。
  本文**不提供** Windows 桌面生成密钥的已验证路径。

## 4. 版本组合（全部未经端到端测试）

| 组件 | 版本 / 来源 |
|---|---|
| 桌面端 | `v0.7.0-rc.2`（DEB / AppImage / NSIS；**Windows 安装包未签名**），源码 `bdc4aeb5` |
| 网关镜像 | `v0.7.0-rc.2` 的 `cloud-image.tar`，镜像 ID `sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a`，源码 `bdc4aeb5` |
| 设备端 CLI | `v0.7.0-rc.2` 的 `cloud-linux-amd64.tar.gz` 里的 `coding-tools-agent`，源码 `bdc4aeb5` |
| 部署套件（kit.py / RUNBOOK / 本文） | 分支 `feat/gateway-s1-agent-resilience`，基线 `96234102`（S1 之后）；预发布 `gateway-v0.1.0-rc.1` 发出后以它为准 |

- 桌面端 rc.2 配 rc.2 网关镜像：同一份源码（`bdc4aeb5`），是推荐的配对。但这个组合**没有**在真实 VPS +
  真实 ChatGPT 上测试过（ENROLLMENT.md 也把真实 ChatGPT、VPS 列为待观察）。
- 套件 `96234102` 渲染加 rc.2 镜像：网关服务端源码零差异（见 §1），套件的 129 个单元测试只覆盖本地渲染和检查逻辑，
  **没有**用这个镜像跑过。所以这个组合也是**未测试**的。
- S1（cloud-agent 断线重连韧性）**不在** rc.2 桌面端里，也不在 rc.2 的 `coding-tools-agent` 里。
- 不要混用 `v0.7.0-rc.1`。没有按 rc.1 与 rc.2 交叉组合做过任何验证。

## 5. 本机打开运维控制台（loopback ops console）

状态：**本机演示 / 联调入口，不是公网 admin**。控制台只绑回环，不挂到网关 `origin`/`prefix`，
也不改变「gateway 二进制无 HTTP 管理员入口」的承诺。权威细节见
[`ops-console/README.md`](ops-console/README.md)。

### 启动

仓库根目录执行（`<ABS_PRIVATE_WS>` 必须是**绝对路径**、私有目录，建议 `chmod 700`）：

```bash
mkdir -p <ABS_PRIVATE_WS> && chmod 700 <ABS_PRIVATE_WS>

python3 deploy/cloud-gateway/ops-console/server.py \
  --workspace-root <ABS_PRIVATE_WS> \
  --bind 127.0.0.1:18765
```

浏览器打开：`http://127.0.0.1:18765/`  
（Open loopback ops console: bind `127.0.0.1` only; browser URL above.）

可选：`--gateway-bin /path/to/coding-tools-gateway`，或环境变量 `CODING_TOOLS_GATEWAY_BIN`。

### 硬边界（必读）

- **回环 ≠ 公网 admin**：`--bind 0.0.0.0:…` / 非回环 → 进程拒绝启动（退出码 2）。
- **不查 DB 设备列表**：UI 只扫 `<ABS_PRIVATE_WS>/devices/invitation*.json` 与 `connection*.json`；无文件 → `[]`。
- **密钥**：只经 `--secrets-file`（文件模式建议 0600）；写 API 还要头 `Content-Type: application/json` + `X-Ops-Console: 1`。
- **invite `output_rel`**：必须落在 `devices/` 下（如 `devices/invitation.json`）；拒绝绝对路径与 `devices/../…` 逃逸。
- 配置 API **拒绝**写入 `database_url` / `identity_key` / `password` / `client_secret` 等密钥键。

SSH 隧道到远端机器上的回环端口可以，但**不要**把该端口暴露到公网或反向代理。  
本控制台**不会**替你打新的 gateway 预发布；预发布仍走单独 P 门。

