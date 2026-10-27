# Coding Tools 云网关 VPS 部署套件（G1）运行手册

状态：**操作员手动执行**。`kit.py` 只做本地文件操作（plan / prepare-dirs / render / check），
**从不**调用 docker、ssh、systemctl 或 `nginx -s`；下文所有容器、数据库、Nginx 重载步骤都由你手动执行，
每一步都可以先审阅再继续。本文所有 `<...>` 都是占位符，不要把真实密钥写进仓库、工单或聊天记录。

## 0. 前置条件（G4）

- 一个**独立子域名**（例如 `<GATEWAY_DOMAIN>`），在宝塔中为它单独建站点并签发 TLS 证书；
  不要复用已有站点的 vhost。
- 主机：Docker Engine ≥ 28、Compose 2.27.0、python3 ≥ 3.11（仅标准库）。
- 网关、Nginx、PostgreSQL 镜像已按固定 digest 预先拉取/导入（`pull_policy: never`）。
- 端口 `28880` 在主机上空闲（`ss -ltnp | grep 28880` 应无输出）。

```bash
python3 deploy/cloud-gateway/kit/kit.py plan        # 只打印步骤，applied=false
```

## 1. 准备私有目录（prepare-dirs）

先预览（不触碰文件系统，会列出所有 mkdir / chmod / chown 动作）：

```bash
python3 deploy/cloud-gateway/kit/kit.py prepare-dirs --root <PRIVATE_ROOT> --dry-run
```

确认无误后以 root 执行（`<PRIVATE_ROOT>` 必须是**尚不存在**的绝对路径，其父目录必须是真实目录）：

```bash
sudo python3 deploy/cloud-gateway/kit/kit.py prepare-dirs --root <PRIVATE_ROOT>
```

结果：`<PRIVATE_ROOT>` 与三个子目录均为 0700；`gateway-private/`、`ingress-private/` 属主 `65532:65532`，
`postgres-private/` 属主 `999:999`；`config.json`、`runtime.json` 以 0600 从示例复制（仍含占位符）。
该命令只作用于 `<PRIVATE_ROOT>` 内部，不修改任何全局权限。

## 2. 填写私有文件

- `gateway-private/config.json`：替换 `<ORIGIN>`（`https://<GATEWAY_DOMAIN>`）、`<CONNECTOR_UUID>`、
  `<OWNER_SUBJECT_UUID>`、`<CLIENT_ID>`、`<REDIRECT_URI>`。`bind` 保持 `127.0.0.1:28880`（`check` 会拒绝非回环地址或其他端口）。
- `gateway-private/runtime.json`：只允许 `database_url`、`identity_key` 两个键。
  `database_url` 使用 **ctm_app** 运行时角色（`postgresql://ctm_app:<APP_PASSWORD>@postgres:5432/<DATABASE>`），
  `identity_key` 为 43 位 base64url（32 字节随机数）。
- `postgres-private/password`：PostgreSQL 引导超级用户口令，0400，属主 `999:999`。

口令建议：`python3 -c 'import secrets;print(secrets.token_hex(24))'`（满足模板的固定字符集要求）。
编辑时不要让编辑器留下备份文件（`check` 会报告 `*_unexpected_entry`）。

## 3. 查找 Docker bridge 网关并决定 `--trusted-proxy`

默认**不信任任何来源**：渲染出的内层 Nginx 不含 `set_real_ip_from`，限流键是 TCP 连接地址。
由于宝塔经 `127.0.0.1:28880` 访问发布端口，内层 Nginx 看到的连接地址通常是 `edge` 网络的 bridge 网关，
所以默认情况下**所有外部客户端共享同一个限流桶**（安全但偏严格）。

如需按真实客户端 IP 分桶，在第一次 `compose up` 之后查询 bridge 网关：

```bash
docker network inspect <PROJECT>_edge --format '{{range .IPAM.Config}}{{.Gateway}} {{end}}'
# 或：docker network inspect <PROJECT>_edge  → 查看 IPAM.Config[].Gateway 字段
```

假设输出为 `172.18.0.1`，则重新渲染时加上（可重复，多个 CIDR 多次传参）：

```bash
--trusted-proxy 172.18.0.1/32
```

规则：只接受规范 CIDR（无主机位、无前导零），必须是私有或回环网段，`/0`、公网、组播、重复项、超过 8 个均被拒绝。
**只有**同时把宝塔侧 `X-Real-IP` 改为 `$remote_addr`（见第 7 步，`render` 会生成对应片段）时才应启用。
网络被重建（`down` 后再 `up`）时网关地址可能变化，需要重新查询并重新渲染。

## 4. 渲染（render）

```bash
python3 deploy/cloud-gateway/kit/kit.py render \
  --private-root <PRIVATE_ROOT> --output <RENDER_DIR> \
  --domain <GATEWAY_DOMAIN> --connector <CONNECTOR_UUID> --port 28880 \
  --gateway-image <GATEWAY_IMAGE_ID> --ingress-image <NGINX_IMAGE@DIGEST> --postgres-image <POSTGRES_IMAGE@DIGEST> \
  [--trusted-proxy <BRIDGE_GATEWAY>/32]
```

`<RENDER_DIR>`（0700，必须不存在）内生成：`compose.runtime.json`、`nginx.runtime.conf`、`baota-locations.conf`、
`manifest.json`（sha256，`applied: false`）。

内层 Nginx 限流（G3），状态码均为 429，`access_log off` 保持不变，Host 校验先于限流（421 不计数）：

| 路由 | 限制 |
|---|---|
| OAuth（authorize/login/consent/token）与 `/.well-known/oauth-*` 发现 | 10r/m，burst=5，nodelay |
| `/coding-tools/mcp/` | 10r/s，burst=40，nodelay |
| `/coding-tools/agent`（WSS） | 每 IP 并发连接 4 |

## 5. 安装内层 Nginx 配置并检查（check）

```bash
sudo install -m 0400 -o 65532 -g 65532 <RENDER_DIR>/nginx.runtime.conf <PRIVATE_ROOT>/ingress-private/nginx.conf
sudo python3 deploy/cloud-gateway/kit/kit.py check --root <PRIVATE_ROOT>
```

`check` 只读，输出仅为失败代码（不含任何值）；退出码 0 = 通过，1 = 有失败项，2 = 参数/文件系统错误。
检查项：目录 0700 与属主、文件 0400/0600 与属主、无符号链接/硬链接/多余文件、config 键集合与回环 bind、
runtime 仅两个键且无占位符。**全部通过后**再继续。

## 6. 手动启动与数据库初始化

以下命令由操作员逐条执行（`<PROJECT>` 为固定的 compose 项目名）：

```bash
docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json config --format json >/dev/null   # 语法检查
docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json up -d postgres
```

角色与授权使用 `bootstrap-roles.sql.tmpl`，**通过 psql 标准输入**传入（口令不会出现在 argv / 进程列表中）。
生成 `\set` 前导（值必须符合固定字符集，否则 kit 拒绝）后**直接管道**进 psql，口令不落盘、不进 argv：

```bash
( set -o pipefail; umask 077
  python3 - <<'PY' | docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json exec -T postgres \
    psql -U postgres -d postgres -v ON_ERROR_STOP=1
import importlib.util, getpass
s = importlib.util.spec_from_file_location('kit', 'deploy/cloud-gateway/kit/kit.py'); k = importlib.util.module_from_spec(s); s.loader.exec_module(k)
v = dict(app_password=getpass.getpass('app: '), migration_password=getpass.getpass('migration: '), database='<DATABASE>')
print(k.psql_preamble(v) + k.sql_phase('bootstrap'), end='')
PY
)
```

`getpass` 从终端读取口令，不回显；模板用 `:'app_password'` 字面量引用口令、用 `:"database"` 标识符引用库名。
不要把这一步改写成先写 `bootstrap.sql` 再 `<` 重定向。

然后用**迁移角色** ctm_migration 执行迁移（密钥文档经 stdin 传入），再以超级用户执行授权阶段：

```bash
docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json run --rm -T --no-deps \
  --entrypoint /usr/local/bin/coding-tools-gateway operator migrate \
  --config /run/gateway/config.json --secrets-stdin < <MIGRATION_SECRETS_JSON>
python3 -c "import importlib.util as u;s=u.spec_from_file_location('k','deploy/cloud-gateway/kit/kit.py');k=u.module_from_spec(s);s.loader.exec_module(k);print(k.sql_phase('grants'),end='')" \
  | docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json exec -T postgres \
    psql -U postgres -d <DATABASE> -v ON_ERROR_STOP=1
```

授权后 ctm_app：可读全部表、只能写 `ctm_*` 行；**不能** CREATE TABLE、不能 UPDATE `_sqlx_migrations`、不能 CREATE ROLE
（容器验收 `run_container_topology.py` 会逐项验证）。接着 `provision-owner`、`register-client`（同样经 stdin 传密钥），
最后 `up -d`（gateway / ingress / namespace）。`<MIGRATION_SECRETS_JSON>` 用完即删。

## 7. 合并宝塔 location 片段（手动）

把 `<RENDER_DIR>/baota-locations.conf` 粘贴进第 0 步那个子域名站点的 vhost（不要放到其他站点）。

- 未使用 `--trusted-proxy`：片段与仓库审阅过的 `current_nginx_include.py` 输出逐字节一致，`X-Real-IP` 被清空。
- 使用了 `--trusted-proxy`：片段中 4 处 `proxy_set_header X-Real-IP "";` 改为 `proxy_set_header X-Real-IP $remote_addr;`
  （宝塔直接面向客户端，`$remote_addr` 即真实客户端地址；若宝塔前面还有 CDN，请先在宝塔层正确配置 realip，否则不要启用）。

**重载前必须先测试**：

```bash
nginx -t            # 必须显示 syntax is ok / test is successful
# 通过后再由你决定是否在宝塔面板中重载
```

## 8. 回滚

```bash
docker compose -p <PROJECT> -f <RENDER_DIR>/compose.runtime.json down    # 不要加 --volumes：保留数据库卷
```

再从宝塔 vhost 中移除第 7 步粘贴的片段，`nginx -t` 通过后重载。`<PRIVATE_ROOT>` 保留以便排查；
确认不再需要后由你手动安全删除。

## 9. 验收证据

- 离线：`python -m unittest discover -s tests/cloud-gateway-deployment -p 'test_*.py'`（`test_kit.py` 覆盖 kit；
  设置 `CTM_TEST_NGINX=<nginx 路径>` 可额外跑真实 Nginx 的限流/real-IP 功能测试）。
- 容器：`run_container_topology.py`（仅在托管 CI 中运行）验证 `/token` burst 后 429、正常速率下 MCP/WSS 不出现 429、
  第 5 个并发 WSS 被 Nginx 429、伪造 `X-Real-IP` 无法换桶、信任 bridge 网关后按真实 IP 分桶，以及 ctm_app 的三项拒绝。
