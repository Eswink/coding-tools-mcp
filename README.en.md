<p align="center"><img src="src-tauri/icons/128x128.png" width="80" alt="Coding Tools MCP"></p>
<h1 align="center">Coding Tools MCP · Eswink</h1>
<p align="center">Local workspaces, exclusive conversation approval, long-running tasks and recoverable development records for ChatGPT.</p>
<p align="center">
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest"><img src="https://img.shields.io/github/v/release/Eswink/coding-tools-mcp?label=Release" alt="This repository's full release"></a>
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0-rc.2"><img src="https://img.shields.io/badge/Pre--release-v0.7.0--rc.2-orange" alt="Pre-release v0.7.0-rc.2"></a>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420" alt="Ubuntu amd64">
</p>
<p align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0-rc.2">v0.7.0-rc.2 pre-release</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest">Stable (Latest)</a></p>

This is the **Eswink/coding-tools-mcp** desktop distribution, built with Rust, Tauri 2 and Svelte 5 / SvelteKit. It exposes selected local projects through MCP so an approved AI conversation can read files, apply patches, run commands, inspect tasks/logs and save development checkpoints.

This fork focuses on **personal, sustained development through ChatGPT**. OAuth authenticates the connection; each conversation still needs fingerprint verification and approval on the local desktop. By default, only one conversation owns a workspace. Other conversations cannot take over or create additional approval notifications.

## Download and install

> **Current pre-release: v0.7.0-rc.2 (PRE-RELEASE — NOT FINAL)**, for manual testing only; it is not a stable release. The stable (Latest) release is still **[v0.6.0](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.6.0)**. The live [Releases page](https://github.com/Eswink/coding-tools-mcp/releases) is authoritative for release status.

### Desktop: v0.7.0-rc.2 (pre-release)

| Platform | Package | SHA256 | Notes |
| --- | --- | --- | --- |
| Windows x64 | [MCP_0.7.0-rc.2_x64-setup.exe](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/MCP_0.7.0-rc.2_x64-setup.exe) | `0933837e6011adb1839ec0f128ed5dd2b699f432f263f1d909b62040f7d0cb90` | NSIS installer; **unsigned**, shows an unknown publisher |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0-rc.2_amd64.deb](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/MCP_0.7.0-rc.2_amd64.deb) | `1a65a6a515a8dc47319e4c7cb6e5522cdc842b3a095fda118cb082098bab5273` | Preferred; for a logged-in, non-root desktop user |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0-rc.2_amd64.AppImage](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/MCP_0.7.0-rc.2_amd64.AppImage) | `6e1e652ccdde15d34f2802b28440b3ad887e71af8851b79678a5a86685bb3f40` | Not verified on every FUSE/Wayland environment |

Checksums: [SHA256SUMS.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/SHA256SUMS.txt). Built from tag `v0.7.0-rc.2` (`bdc4aeb5`), packaging run [40428267551](https://github.com/Eswink/coding-tools-mcp/actions/runs/40428267551). No macOS, ARM or headless Linux Server packages are provided.

### Cloud components: shipped with v0.7.0-rc.2 (pre-release)

| File | SHA256 | Notes |
| --- | --- | --- |
| [cloud-image.tar](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/cloud-image.tar) | `82c485832dc1f2b145b45a7b0480229f3b4cc213f07d2cdb732cea052f7ed0bb` | Cloud gateway Docker image (import with `docker load`; the image has no tag) |
| [cloud-linux-amd64.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/cloud-linux-amd64.tar.gz) | `c7c37a3c7549589d46aafa392ded1ce9a5c5077c284502abac9618b2ad830418` | The same Linux amd64 binaries (including `coding-tools-gateway` and `coding-tools-agent`) |

Checksums: [SHA256SUMS-cloud.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0-rc.2/SHA256SUMS-cloud.txt) (also covers `archive-receipt.json`, `image-archive.sha256` and `versions.json`). After import, **reference the image by its ID**, not by a tag:

```bash
sha256sum -c SHA256SUMS-cloud.txt
docker load -i cloud-image.tar
docker image inspect --format '{{.Id}}' sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a
```

### Cloud gateway deploy kit: gateway-v0.1.0-rc.1 (pre-release)

[gateway-v0.1.0-rc.1](https://github.com/Eswink/coding-tools-mcp/releases/tag/gateway-v0.1.0-rc.1) contains only the VPS deploy kit (`kit.py`, RUNBOOK, templates, render scripts and the connection guide). It **does not contain gateway binaries or an image**; use the rc.2 `cloud-image.tar` above. Source commit `e43728285af66beac7807376ff7764c708c2b631`.

| File | SHA256 |
| --- | --- |
| [coding-tools-gateway-deploy-kit-e4372828.tar](https://github.com/Eswink/coding-tools-mcp/releases/download/gateway-v0.1.0-rc.1/coding-tools-gateway-deploy-kit-e4372828.tar) | `260bdbedd5c7ff1c402c5ef1028f92cb183f7caadc09f1f736104536430ab3d2` (canonical hash; the `.tar` is authoritative) |
| [coding-tools-gateway-deploy-kit-e4372828.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/gateway-v0.1.0-rc.1/coding-tools-gateway-deploy-kit-e4372828.tar.gz) | `7d001ea55deea715f2ecf1eaf9ec1039bae5a11c331b271431c107fffd6b7e97` (depends on the gzip implementation; informational) |

Checksums: [SHA256SUMS.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/gateway-v0.1.0-rc.1/SHA256SUMS.txt); the reproduction command is in the release notes. Documentation pinned to the source commit: [Deploy RUNBOOK](https://github.com/Eswink/coding-tools-mcp/blob/e43728285af66beac7807376ff7764c708c2b631/deploy/cloud-gateway/kit/RUNBOOK.md) · [ChatGPT and desktop connection guide](https://github.com/Eswink/coding-tools-mcp/blob/e43728285af66beac7807376ff7764c708c2b631/deploy/cloud-gateway/CONNECT-CHATGPT-AND-DESKTOP.md).

### Version combinations

| Purpose | Desktop | Cloud gateway image | Deploy kit | Status |
| --- | --- | --- | --- | --- |
| Manual cloud gateway testing | v0.7.0-rc.2 | rc.2 `cloud-image.tar`, referenced by ID `sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a` | gateway-v0.1.0-rc.1 | Pre-release; **this combination has not been tested end to end (not on a real VPS or with real ChatGPT)** |
| Everyday use | v0.6.0 (Latest) | Not used | Not used | Stable; used on its own, without the cloud gateway |

### Stable: v0.6.0 (Latest)

For a stable version, use the [v0.6.0 Release](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.6.0) (its assets are the `MCP_0.6.0-rc.4_*` packages plus `SHA256SUMS_v0.6.0.txt` and `Verification_v0.6.0.md`).

### Verify SHA256

Linux (downloaded files and `SHA256SUMS.txt` in the same directory):

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

Windows PowerShell:

```powershell
Get-FileHash .\MCP_0.7.0-rc.2_x64-setup.exe -Algorithm SHA256
```

The output must match the table / `SHA256SUMS.txt` exactly. Do not install on a mismatch.

### Install

- **Windows**: run `MCP_0.7.0-rc.2_x64-setup.exe`. The installer is unsigned, so SmartScreen may report an "unknown publisher"; verify the SHA256 before choosing to continue.
- **Ubuntu DEB**: in the directory containing the file, run

  ```bash
  sudo apt install ./MCP_0.7.0-rc.2_amd64.deb
  ```

- **Ubuntu AppImage**: `chmod +x MCP_0.7.0-rc.2_amd64.AppImage`, then run it; use `--appimage-extract-and-run` where FUSE is unavailable.

Installing a system package needs elevated privileges; **running the desktop application does not**. Do not launch the GUI with sudo. Linux secret recovery needs the user's D-Bus session and an available, unlocked Secret Service. Do not disable the sandbox to work around startup failures.

**Update source:** from v0.6.0 on, "Check for updates" points to this repository's `releases/latest`, so it **only sees stable releases and never offers pre-releases**; download rc builds manually from the tables above. Binaries from v0.5.0 and earlier still point to upstream; do not treat an upstream-suggested version as an update for this fork. [Source](src-tauri/src/update/mod.rs)

## Interface and pages

Since v0.5.0, five pages share a navy sidebar, semantic status colors, grouped cards and light/dark/system themes without changing route URLs:

| Page | Implemented capabilities |
| --- | --- |
| Workspace | Identity, startup prompt, local chat approval, MCP / Actions selection, configuration, tasks, logs and health checks |
| General | Appearance, application information, existing proxy and UI-maintenance settings |
| Shared keys | Mask, reveal, copy, regenerate and save the actual credential types; unreadable fields remain disabled |
| FRP | Manage FRP server profiles; live per-workspace tunnels remain on their workspace page |
| Software | Manage supported software and actual installation paths, without invented version/latency/health data |

The refactor also fixes stale unsaved-change prompts after saving/reverting, late asynchronous navigation results, partial-secret-load bindings and approval-dialog keyboard focus boundaries. Unsupported language/autostart/sound/component-inventory concepts from the design references are not rendered as fake working controls.

[UI-evidence_v0.5.0.zip](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/UI-evidence_v0.5.0.zip) contains actual built-page and installed-app screenshots. They use isolated acceptance workspaces and synthetic data, not your real service status.

## Connect one conversation (option 1: direct to this computer)

### 1. Configure the workspace and public endpoint

Start the desktop app, add a project directory and configure its MCP port and **OAuth**. Save and start the service. A typical local URL is `http://127.0.0.1:28766/mcp`; use the actual port shown by your app.

The usual deployment exposes a public HTTPS `/mcp` endpoint through FRP, Cloudflare or an existing reverse proxy. Software management handles supported tunnel clients, while FRP server parameters are managed separately. A localhost URL is not a public endpoint reachable directly by ChatGPT's cloud service.

Your proxy must forward the following paths to the **same workspace upstream**, not a static-directory or certificate-validation handler:

```text
/.well-known/oauth-authorization-server
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
/oauth/authorize
/oauth/token
```

Run the desktop health checks first. Discovery documents should be JSON; unauthenticated business requests must remain protected. Do not disable OAuth or remove ACME certificate-validation rules merely to suppress a discovery failure.

### 2. Add the MCP connection in ChatGPT

Use the developer-mode/custom-MCP entry available to your account. Eligibility, permissions and menus follow [OpenAI's current guidance](https://help.openai.com/en/articles/12584461), not old screenshots. For an example public origin of `https://mcp.example.com`, this server's contract is:

| Field | Value |
| --- | --- |
| Server URL | `https://mcp.example.com/mcp` |
| Authentication | OAuth with preconfigured Client ID / Client Secret |
| Client credentials | Must match the corresponding desktop workspace |
| Token endpoint authentication | `client_secret_post` when a secret is configured; `client_secret_basic` is also supported |
| Authorization endpoint | `https://mcp.example.com/oauth/authorize`, normally discovered automatically |
| Token endpoint | `https://mcp.example.com/oauth/token` |
| Issuer / authorization-server base | `https://mcp.example.com` |
| Resource | `https://mcp.example.com/mcp` |
| Scopes | `mcp`; request **`mcp offline_access`** for refresh tokens |
| Registration URL | Leave blank; dynamic client registration is not implemented |
| OIDC | Off; do not request `openid profile email` |

Default scopes can remain blank with the required values in the base-scopes field; the effective authorization request is authoritative. **Register the exact Callback / Redirect URL shown by ChatGPT in the workspace's OAuth configuration.** Do not guess it or match only its domain. Enter any first-authorization passphrase in the browser flow as directed by the desktop app, never into the chat.

### 3. Approve on the local desktop

An OAuth connection does not authorize computer access. In the selected chat, check `auth_status`, then call `request_chat_authorization` for the minimum required scopes and display its fingerprint.

Open the desktop approval entry or the workspace's ChatGPT authorization panel. **Compare fingerprints, review/reduce scopes, then approve.** A global approval entry and modal are available; OS notification banners depend on platform settings. Pending requests expire after 90 seconds. MCP does not expose a remote self-approval action.

Only after approval should the chat call business tools such as `server_info`, `get_default_cwd` and `git_status`.

```text
OAuth connection → Conversation request → Local fingerprint approval → Tool access → Checkpoint
```

## Option 2: connect ChatGPT through the cloud gateway (pre-release, untested)

The v0.7.0-rc.2 desktop app adds a "Cloud connection" panel to the workspace: import a cloud connection configuration JSON and a local signing private key JSON from local files, and the desktop app connects **outbound** to the cloud gateway. ChatGPT connects to the gateway's MCP endpoint instead of reaching your computer directly.

- **Deploy the gateway**: download the [gateway-v0.1.0-rc.1](https://github.com/Eswink/coding-tools-mcp/releases/tag/gateway-v0.1.0-rc.1) deploy kit and follow the [RUNBOOK](https://github.com/Eswink/coding-tools-mcp/blob/e43728285af66beac7807376ff7764c708c2b631/deploy/cloud-gateway/kit/RUNBOOK.md) manually. Prerequisites: a dedicated subdomain with TLS, Docker Engine ≥ 28, Compose 2.27.0, python3 ≥ 3.11, and the imported rc.2 gateway image (`--gateway-image sha256:7e69b9ade56ce598264f23f3504e465670a6f2c0119293f04937645963b2ee3a`). You must supply your own `--domain` (shown as the `<GATEWAY_DOMAIN>` placeholder in the docs). `kit.py` only performs local file operations; it never calls docker or ssh or reloads Nginx.
- **Authorization boundary unchanged**: neither the cloud, the model nor OAuth can approve local permissions; after connecting you still verify the chat fingerprint and approve on this computer. Pause and revoke are decided locally.
- **Connect ChatGPT and the desktop app**: the connector URL, OAuth endpoints, `register-client` pre-registration and desktop import steps are in the [connection guide](https://github.com/Eswink/coding-tools-mcp/blob/e43728285af66beac7807376ff7764c708c2b631/deploy/cloud-gateway/CONNECT-CHATGPT-AND-DESKTOP.md).
- **Status**: pre-release, **not tested end to end (not on a real VPS or with real ChatGPT)**; see "Known limitations" below. The deploy kit source lives on the development branch `feat/gateway-s1-agent-resilience` and is not merged into main.

## Exclusive ownership and long sessions

Default exclusivity is **per workspace/profile**, not one owner for the entire application. The first valid request reserves the workspace; local approval makes it the Owner. Other chats receive `EXCLUSIVE_CHAT_LOCKED`, create no new Pending record and cannot evict that Owner.

When ownership is revoked or expires while old tasks are unfinished, the workspace enters **draining**. Ownership is not transferred until old work is resolved. The plugin may remain visible in another ChatGPT conversation: the server can deny calls, not hide the Host's menu.

The workspace's remote-session security panel exposes:

| Setting | Default | Range |
| --- | --- | --- |
| Exclusive conversation | On | Per workspace |
| Pending approval | 90 seconds | Fixed |
| Access Token lifetime | 60 minutes | 5–480 minutes |
| Refresh Session lifetime | 30 days | 1–90 days |
| Conversation lease | 24 hours | 1–720 hours |
| Idle auto-release | Off (0) | 0 or 30–1440 minutes, no longer than the lease |

Refresh-token rotation and reuse detection are mandatory. **The client decides when to refresh. Refreshing does not extend the conversation lease, transfer ownership or replace local approval.** Saving a policy requires local confirmation, revokes current chat grants and restarts the listener through the existing configuration flow. Previously issued refresh sessions retain their original deadlines. A full application restart requires a new local approval. Command timeouts/task budgets are separate from conversation lifetimes.

Sources: [session policy](src-tauri/src/auth/session_policy.rs), [chat authorizer](src-tauri/src/auth/聊天授权v1.rs), [remote-session settings](src/lib/components/RemoteSessionSettings.svelte).

## Conversation history without cross-chat leakage

After approval, copy the workspace's ChatGPT startup prompt. `history_session_bootstrap` stores the verbatim `initial_user_input` and returns a stable `session_key`, `current_path` and bounded state. Use `history_session_search` and paginated `history_session_read` with `next_cursor` for earlier details. At each completed task, call `history_session_checkpoint` with the unchanged target and verbatim `raw_user_input`. Only a successful, matching response establishes that progress was saved.

Archives live under the project's `docs/history-session/`. **A conversation can restore its own records; a different chat does not automatically inherit another chat's archive or grant merely by connecting to the same directory.** Cross-chat handover must be explicitly arranged by the local operator. The server cannot read chat content that was never passed as tool arguments. [Startup prompt](src/lib/components/ChatGptSessionPrompt.svelte)

## Capabilities and boundaries

The embedded runtime provides file reading/search/patching, command execution, Git, task management, logs and health checks. Track asynchronous commands using returned task IDs rather than assuming that a long chat lease makes a process immortal.

Actions remains a separate OpenAPI gateway: start its service and use its actual `/openapi.json` and authentication settings. **Actions authentication, MCP OAuth scopes and local conversation scopes are not interchangeable.** An arbitrary REST client does not automatically provide the ChatGPT metadata used by conversation isolation.

This software operates real directories and processes with the current system account's access. Conversation binding/approval is a logical authorization boundary, **not a separate container/filesystem for each chat or cryptographic proof of Host identity**. Shared directories remain shared. Grant minimum privileges; never put Client Secrets, passphrases, access/refresh tokens or unredacted configuration into screenshots, logs, README, issues or chats.

## Upgrade, recovery and known limitations

Exit the old app and back up configuration plus the corresponding system account's key-recovery material before upgrading. Do not delete project/history files to install the UI, run competing app versions against one configuration, or force unfinished draining work to become free. An encrypted configuration file alone is not a cross-user recovery guarantee. Keep the stable installer and a compatible backup for rollback.

Known limitations:

- **A pre-release is not a stable release**: v0.7.0-rc.2 is marked PRE-RELEASE — NOT FINAL; Latest is still v0.6.0.
- **Windows installers are unsigned**.
- **The cloud gateway combination is not tested end to end**: v0.7.0-rc.2 + the rc.2 gateway image + gateway-v0.1.0-rc.1 have not been tested on a real VPS or with real ChatGPT; only the in-CI container topology test passed.
- **rc.2 binaries do not include S1** (the agent reconnection/resilience changes): S1 exists only on the development branch of the deploy kit; the rc.2 desktop app, `cloud-image.tar` and `cloud-linux-amd64.tar.gz` do not contain it.
- **The gateway has no dynamic client registration (DCR)**: an operator must pre-register the client with `coding-tools-gateway register-client`; whether ChatGPT accepts this is **not verified**.
- **There is no Windows build of `coding-tools-agent`**: only Linux amd64 is available.
- **You must supply `--domain` yourself**: domains in the docs and examples are placeholders and cannot be used as-is.
- Long-duration real-account ChatGPT refresh, OS notification banners and every hardware/FUSE/Wayland combination are not fully tested; no macOS or ARM packages are provided.

Acceptance records for earlier versions are in the [v0.5.0 release and acceptance notes](docs/releases/stable-v0.5.0.md) and each release's assets.

## Local development

Read [AGENTS.md](AGENTS.md) first. Use Node.js 22, npm, Rust stable and the platform-specific [Tauri 2 prerequisites](https://v2.tauri.app/start/prerequisites/).

```bash
git clone https://github.com/Eswink/coding-tools-mcp.git
cd coding-tools-mcp
npm ci
npm run desktop
```

Windows also provides `dev-desktop.cmd`. `npm run dev` starts Vite only, not the complete Tauri application. Use the repository's frontend driver to prepare required generated test modules:

```bash
npm run check
npm run build
node scripts/前端完整回归v4.mjs
cargo check --locked --all-targets --manifest-path src-tauri/Cargo.toml
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo rustc --locked --lib --manifest-path src-tauri/Cargo.toml -- -D warnings
python scripts/release_preflight.py
```

| Directory | Responsibility |
| --- | --- |
| `src/routes/`, `src/lib/components/`, `src/lib/styles/` | Pages, components and styles |
| `src/lib/api/` | Tauri IPC wrappers |
| `src-tauri/src/auth/` | OAuth, ownership leases, local approval and refresh sessions |
| `src-tauri/src/tools/` | File, patch, command, Git, task and history tools |
| `src-tauri/src/mcp/`, `src-tauri/src/actions/` | MCP and OpenAPI listeners |
| `src-tauri/src/tunnel/` | FRP / Cloudflare lifecycle |
| `tests/`, `src-tauri/tests/`, `scripts/` | Frontend, Rust, native and release validation |
| `docs/specs/ui-refactor-v1/` | UI plans, iterations and delivery records |

## Attribution and licensing

This repository derives from [mybolide/coding-tools-mcp](https://github.com/mybolide/coding-tools-mcp). Credit remains with the original authors and contributors. Upstream and this fork have distinct versions, packages and release channels. Package metadata declares Apache-2.0; dependencies retain their respective licenses and existing attribution is preserved.
