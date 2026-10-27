# Gateway Ops Console（本机回环运维控制台）— S2/S3

> **本机回环控制台 ≠ 公网 admin。**  
> Loopback operator console ≠ public HTTP administrator surface.  
> 不挂在网关 `origin`/`prefix` 上；不改变「gateway 二进制无 HTTP 管理员入口」的承诺。

## 启动

```bash
# 准备一个绝对路径的私有工作根（示例）
mkdir -p /tmp/ops-console-ws && chmod 700 /tmp/ops-console-ws

python3 deploy/cloud-gateway/ops-console/server.py \
  --workspace-root /tmp/ops-console-ws \
  --bind 127.0.0.1:18765
```

浏览器打开：`http://127.0.0.1:18765/`

可选：`--gateway-bin /path/to/coding-tools-gateway` 或环境变量 `CODING_TOOLS_GATEWAY_BIN`。

## 硬边界

- 只绑定回环；`--bind 0.0.0.0:…` / 非回环 → 进程退出码 2，`bind_must_be_loopback`。
- 写 API 需要头：`Content-Type: application/json` + `X-Ops-Console: 1`。
- 配置 API **拒绝** `database_url` / `identity_key` / `password` / `client_secret` 等密钥键；GET 会剥离误存的密钥键（只回键名列表）。
- 设备列表只扫 `workspace_root/devices/invitation*.json` 与 `connection*.json`；**不查 DB**；无文件 → `[]`。
- CLI 包装仅：`check-config` / `register-client` / `invite-device`；密钥只经 `--secrets-file`（0600）。
- **S3**：`invite-device` 的 `output_rel` **必须**落在 `devices/` 下（如 `devices/invitation.json`）；拒绝绝对路径、`devices/../…` 逃逸、空前缀。错误码 `output_rel_must_be_under_devices`。

## 依赖

Python 3.11+ **标准库 only**（`http.server` 等）。无 pip 依赖。

## 测试

```bash
python3 deploy/cloud-gateway/ops-console/tests/test_s2.py   # 16
python3 deploy/cloud-gateway/ops-console/tests/test_s3.py   # 10
python3 -m unittest discover -s deploy/cloud-gateway/ops-console/tests -v  # 26
```

CONNECT / RUNBOOK 入口：见 [`../CONNECT-CHATGPT-AND-DESKTOP.md`](../CONNECT-CHATGPT-AND-DESKTOP.md) §5、[`../kit/RUNBOOK.md`](../kit/RUNBOOK.md) §10。

eng ≠ QUALIFIED ≠ FINAL
