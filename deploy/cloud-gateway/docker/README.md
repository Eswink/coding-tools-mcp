# 云网关 Docker Compose 部署（单机）

本目录让 `coding-tools-cloud-gateway` 在一台 Linux 主机上用 Docker 直接部署：
网关 + PostgreSQL + 内置 ingress（nginx），**只**在主机回环地址发布一个端口，由宿主机上的
宝塔 / Nginx / Caddy 负责 TLS 证书并反代到 `127.0.0.1:${CTM_PORT}`。

| 文件 | 作用 |
| --- | --- |
| `compose.yaml` | 拓扑（与 `runtime_topology.compose()` 一致）：`namespace` 持有网络命名空间并发布 `127.0.0.1:${CTM_PORT}->8080`；`gateway`、`ingress` 共享该命名空间；`postgres` 只在 `internal` 网络；`operator` 为一次性 CLI（profile `operator`）。 |
| `.env.example` | 非机密设置模板：镜像（必须是 `sha256:` 镜像 ID 或 `@sha256:` digest）、私有目录、域名、端口。 |
| `ctm_docker.py` | 运维助手（仅标准库，需 root）：`setup`、`invite-device`、`redeem-device`、`select-device`、`migrate`、`check`。 |
| `smoke.py` | 一次性端到端冒烟（占位域名 `gateway.example.invalid`，结束后 `down -v` 并删除临时目录）。 |

## 前提

- Docker Engine ≥ 28（回环端口发布安全修复）+ Compose v2（CI 固定 2.27.0）。
- 发布页下载 `coding-tools-gateway-image-<版本>.tar` 与其 `.sha256`，校验后 `docker load -i`，记下打印的 `sha256:` 镜像 ID。
- 拉取并固定官方镜像 digest：`docker pull postgres:16-bookworm`、`docker pull nginx:stable-alpine`，
  用 `docker image inspect --format '{{index .RepoDigests 0}}'` 取 `postgres@sha256:…`、`nginx@sha256:…`。**不要用 `latest` 或任何可变 tag。**

## 部署步骤

```bash
cd deploy/cloud-gateway/docker
# 1) 一次性初始化：生成私有文件（0700 目录 / 0400 文件，属主 65532 或 999）、
#    启动 postgres、建角色（psql stdin）、migrate、授权、创建 owner、注册 OAuth 客户端。
#    机密只在内存里生成，写入私有文件或经 stdin 传给容器；不会打印，也不会写进 .env。
sudo python3 ctm_docker.py setup \
  --private-root /opt/coding-tools-gateway/private \
  --domain gw.example.com --port 28880 \
  --gateway-image sha256:<镜像ID> \
  --postgres-image postgres@sha256:<digest> --ingress-image nginx@sha256:<digest> \
  --redirect-uri https://<客户端回调地址>        # owner 密码交互输入，或 --owner-password-file <0600 文件>

# 2) 设备登记（网关在选定设备前会以 provisioning_not_ready 拒绝启动，这是 fail-closed 设计）
sudo python3 ctm_docker.py invite-device --output /root/ctm-invitation.json   # 0600，交给桌面端 MCP 应用
#    桌面端用邀请生成 proof（coding-tools-agent prove-enrollment），把 proof 文件拷回主机（0600）
sudo python3 ctm_docker.py redeem-device --proof /root/ctm-proof.json --output /root/ctm-connection.json
sudo python3 ctm_docker.py select-device --device <redeem 输出的 device UUID>

# 3) 启动
sudo docker compose up -d
sudo python3 ctm_docker.py check            # 拓扑守卫 + 私有目录权限检查
```

`setup` 会写 `./.env`（0600，已在 `.gitignore`）。之后所有 `docker compose` 命令在本目录执行即可。

## 安全约束（与验收标准对应）

- 镜像内无机密：`Dockerfile.runtime` 只复制 4 个二进制、manifest、README；用户 `65532:65532`。
- 数据库 DSN、identity key 只在 `gateway-private/runtime.json`（0400，属主 65532，父目录 0700）。
  网关的 `read_protected` 会拒绝 root 属主 / 组或其他可读 / 符号链接 / 硬链接，因此不使用 Docker 默认的 `/run/secrets`（root 属主）。
- 只有 `namespace` 发布端口且只绑定 `127.0.0.1`；PostgreSQL 无端口、只在 `internal: true` 网络。
- 不挂载 `docker.sock`；所有容器 `read_only`、`cap_drop: ALL`、`no-new-privileges`。
- `ops-console` 不在 compose 中；如需使用，按其 README 在主机回环地址单独运行。
- 健康检查：`/coding-tools/health/ready`（容器内 bash `/dev/tcp`，Host 必须等于配置域名，否则 421）。

## 宿主机 TLS 反代示例（宝塔 / Nginx）

```nginx
location / {
    proxy_pass http://127.0.0.1:28880;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 3600s;
}
```

如需让 ingress 信任来源 IP，`setup` 时加 `--trusted-proxy <宿主到容器的网段 CIDR>`；默认不信任任何代理头。

## 升级 / 回滚

`docker load` 新镜像 → 修改 `.env` 中 `CTM_GATEWAY_IMAGE` → `sudo python3 ctm_docker.py migrate`
（为 `ctm_migration` 临时设置一次性随机密码、经 stdin 执行 migrate、重新授权，然后再次轮换密码；迁移密码从不落盘）→ `docker compose up -d`。回滚：把 `CTM_GATEWAY_IMAGE` 改回旧 ID 再 `up -d`（数据库迁移只前进，回滚前请先备份卷 `database-data`）。

## 冒烟

```bash
sudo python3 smoke.py --gateway-image sha256:<ID> --postgres-image postgres@sha256:<d> --ingress-image nginx@sha256:<d> --evidence /tmp/smoke.json
```
