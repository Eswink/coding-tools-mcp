<p align="center"><img src="src-tauri/icons/128x128.png" width="80" alt="Coding Tools MCP"></p>
<h1 align="center">Coding Tools MCP · Eswink</h1>
<p align="center">Local workspaces, exclusive conversation approval, long-running tasks and recoverable development records for ChatGPT.</p>
<p align="center">
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest"><img src="https://img.shields.io/github/v/release/Eswink/coding-tools-mcp?label=Release" alt="This repository's full release"></a>
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0"><img src="https://img.shields.io/badge/Stable-v0.7.0-2ea44f" alt="Stable v0.7.0"></a>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420" alt="Ubuntu amd64">
</p>
<p align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0">v0.7.0 stable (Latest)</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases">All releases</a></p>

This is the **Eswink/coding-tools-mcp** desktop distribution, built with Rust, Tauri 2 and Svelte 5 / SvelteKit. It exposes selected local projects through MCP so an approved AI conversation can read files, apply patches, run commands, inspect tasks/logs and save development checkpoints.

This fork focuses on **personal, sustained development through ChatGPT**. OAuth authenticates the connection; each conversation still needs fingerprint verification and approval on the local desktop. By default, only one conversation owns a workspace. Other conversations cannot take over or create additional approval notifications.

## Download and install

> **Current stable release: v0.7.0 (Latest)**, superseding v0.6.0 and the 0.7.0 release candidates (rc.1 / rc.2 / rc.3). Download from the [v0.7.0 Release](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0) (or [releases/latest](https://github.com/Eswink/coding-tools-mcp/releases/latest)). The release notes on that page are authoritative for upgrade steps, rollback behaviour and the full list of known issues.

### Desktop: v0.7.0

| Platform | Package | SHA256 | Notes |
| --- | --- | --- | --- |
| Windows x64 | [MCP_0.7.0_x64-setup.exe](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_x64-setup.exe) | `8fa1bc2fcd2fd3a2f81ea7e2de606d4b083e8acc412e5964af38e9f4bdf148e6` | Per-user NSIS installer; **unsigned**, shows an unknown publisher |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0_amd64.deb](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_amd64.deb) | `64341529d69d89204757eea34ea0c6d6ab2097807acad64eebecd26756ed2197` | Preferred; for a logged-in, non-root desktop user |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.7.0_amd64.AppImage](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/MCP_0.7.0_amd64.AppImage) | `34793babb5eb485d74676ff697263fa31dae0d714f7dfbeb12e2885fb970e7db` | Not verified on every FUSE/Wayland environment |

Checksums: [SHA256SUMS.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS.txt) (also covers `cloud-linux-amd64.tar.gz`). Built from tag `v0.7.0` (source `36e0c265`); every binary comes from packaging run [40814802175](https://github.com/Eswink/coding-tools-mcp/actions/runs/40814802175) and nothing was built locally. The Linux packages were built on Ubuntu 22.04 and install-accepted on Ubuntu 22.04 and 24.04; the Windows NSIS installer passed standard-user installed acceptance. No macOS, ARM or headless Linux Server packages are provided.

**Known issues (summary):** the Windows installer is unsigned; there are no macOS packages; the CI baseline failures shared with rc.2 / rc.3, the dev-only deepmerge advisory exemption (expires 2026-11-30 UTC) and other items are listed in the [v0.7.0 release notes](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0).

### Cloud components: v0.7.0

| File | SHA256 | Notes |
| --- | --- | --- |
| [cloud-linux-amd64.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/cloud-linux-amd64.tar.gz) | `137cfa80b5d601b5ff18341d49a59c5968e8459d126dfa2aefb0c9adcc445f7b` | Linux amd64 cloud binary bundle (gateway / control-gateway / mcp-gateway / agent), with [archive-receipt.json](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/archive-receipt.json) and [versions.json](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/versions.json) |
| [coding-tools-gateway-image-0.7.0.tar](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-image-0.7.0.tar) | `04d4c59ab88a33aeb2dcafe6162debe18c9f344a4a0d789e91602fafc8847fee` | CI-built gateway runtime image (OCI archive, untagged); checksum file [coding-tools-gateway-image-0.7.0.tar.sha256](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-image-0.7.0.tar.sha256) |

Verify the cloud binary bundle with [SHA256SUMS-cloud.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS-cloud.txt). Image labels: `org.opencontainers.image.version=0.7.0`, `org.opencontainers.image.revision=36e0c265a2bb5f93fe61a504468bf584706519e2`.

### Cloud gateway Docker deployment: v0.7.0

| File | SHA256 |
| --- | --- |
| [coding-tools-gateway-docker-kit-36e0c265.tar.gz](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/coding-tools-gateway-docker-kit-36e0c265.tar.gz) | `4cb586324fa27db03ec2f3c869f991555b38a7d24a9bfb89d313b8329bba4867` |

Checksums: [SHA256SUMS-docker-kit.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.7.0/SHA256SUMS-docker-kit.txt). The kit is a deterministic `git archive` of [deploy/cloud-gateway/docker](deploy/cloud-gateway/docker/README.md) at the tagged commit; the reproduction command is in the release notes. After import, **reference the image by its ID**, not by a tag:

```bash
sha256sum -c coding-tools-gateway-image-0.7.0.tar.sha256
sha256sum -c SHA256SUMS-docker-kit.txt
docker load -i coding-tools-gateway-image-0.7.0.tar
docker image inspect --format '{{.Id}}' sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b
# in .env: CTM_GATEWAY_IMAGE=sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b
```

- The image ID **must be** `sha256:9246a4faed40a41cbd5dce52d4e9f7a2c743e97501543c1f83b2edcae653db7b`. Pin `CTM_POSTGRES_IMAGE` / `CTM_INGRESS_IMAGE` by `@sha256:` digest; **never use `latest` or any mutable tag**.
- **Deployment order is mandatory: init → desktop device registration → `up -d`.**
  1. `ctm_docker.py setup`
  2. `invite-device` → desktop `prove-enrollment` → `redeem-device` → `select-device` (at least once; without a registered and selected device the gateway refuses to start with `provisioning_not_ready`)
  3. `docker compose up -d` + `ctm_docker.py check`
- See the kit's [README](deploy/cloud-gateway/docker/README.md) for details.

### Upgrading from v0.6.0

- **Windows**: run `MCP_0.7.0_x64-setup.exe` (per-user, unsigned, SmartScreen may warn; check the SHA256 first). It installs over v0.6.0 or any 0.7.0 RC.
- **Linux**: `sudo apt install ./MCP_0.7.0_amd64.deb` upgrades in place; or replace the AppImage and `chmod +x` it.
- **Cloud gateway**: load the new image, set `CTM_GATEWAY_IMAGE` in `.env` to the image ID above, then `docker compose up -d` and `ctm_docker.py check`. Upgrade the desktop app and the gateway together.
- In the desktop app, Settings → General → "Check for updates" now reports v0.7.0.
- **Rollback behaviour**: the desktop app has **no auto-updater**. "Check for updates" is a manual button that reads `releases/latest` from the GitHub API and only shows a dialog / opens the release page; nothing is downloaded or installed automatically. If Latest is ever switched back to v0.6.0, users already on 0.7.0 are told they are up to date and stay on 0.7.0 (no downgrade prompt, no automatic downgrade); any fix ships as 0.7.1 or later.

### Earlier releases

- **v0.6.0** (previous stable): [v0.6.0 Release](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.6.0) (its assets are the `MCP_0.6.0-rc.4_*` packages plus `SHA256SUMS_v0.6.0.txt` and `Verification_v0.6.0.md`).
- **v0.7.0-rc.1 / rc.2 / rc.3** (historical pre-releases): superseded by v0.7.0, kept for the record only and no longer recommended; see the [Releases page](https://github.com/Eswink/coding-tools-mcp/releases).
- **gateway-v0.1.0-rc.1** (historical pre-release): contains only the VPS deploy kit (`kit.py`, RUNBOOK, templates, render scripts and the connection guide), no gateway binaries or image; see [gateway-v0.1.0-rc.1](https://github.com/Eswink/coding-tools-mcp/releases/tag/gateway-v0.1.0-rc.1).

### Verify SHA256

Linux (downloaded files and `SHA256SUMS.txt` in the same directory):

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

Windows PowerShell:

```powershell
Get-FileHash .\MCP_0.7.0_x64-setup.exe -Algorithm SHA256
```

The output must match the table / `SHA256SUMS.txt` exactly. Do not install on a mismatch.

### Install

- **Windows**: run `MCP_0.7.0_x64-setup.exe`. The installer is unsigned, so SmartScreen may report an "unknown publisher"; verify the SHA256 before choosing to continue.
- **Ubuntu DEB**: in the directory containing the file, run

  ```bash
  sudo apt install ./MCP_0.7.0_amd64.deb
  ```

- **Ubuntu AppImage**: `chmod +x MCP_0.7.0_amd64.AppImage`, then run it; use `--appimage-extract-and-run` where FUSE is unavailable.

Installing a system package needs elevated privileges; **running the desktop application does not**. Do not launch the GUI with sudo. Linux secret recovery needs the user's D-Bus session and an available, unlocked Secret Service. Do not disable the sandbox to work around startup failures.

**Update source:** from v0.6.0 on, "Check for updates" points to this repository's `releases/latest`, so it **only sees stable releases and never offers pre-releases**. Binaries from v0.5.0 and earlier still point to upstream; do not treat an upstream-suggested version as an update for this fork. [Source](src-tauri/src/update/mod.rs)

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

## Option 2: connect ChatGPT through the cloud gateway (not tested end to end in a real environment)

The v0.7.0 desktop app provides a "Cloud connection" panel in the workspace: import a cloud connection configuration JSON and a local signing private key JSON from local files, and the desktop app connects **outbound** to the cloud gateway. ChatGPT connects to the gateway's MCP endpoint instead of reaching your computer directly.

- **Deploy the gateway**: use the v0.7.0 gateway image and Docker kit, following "Cloud gateway Docker deployment: v0.7.0" above and the [kit README](deploy/cloud-gateway/docker/README.md); prerequisites are Docker Engine ≥ 28 and Compose v2. The manual VPS `kit.py` and [RUNBOOK](deploy/cloud-gateway/kit/RUNBOOK.md) are also in the repository. You must supply your own `--domain` (domains in the docs are placeholders).
- **Authorization boundary unchanged**: neither the cloud, the model nor OAuth can approve local permissions; after connecting you still verify the chat fingerprint and approve on this computer. Pause and revoke are decided locally.
- **Connect ChatGPT and the desktop app**: the connector URL, OAuth endpoints, `register-client` pre-registration and desktop import steps are in the [connection guide](deploy/cloud-gateway/CONNECT-CHATGPT-AND-DESKTOP.md) (written for rc.2 manual testing; use the v0.7.0 image and versions from this page).
- **Status**: **not tested end to end on a real VPS or with real ChatGPT**; see "Known limitations" below.

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

- **Full known issues are in the release notes**: the CI baseline failures shared with rc.2 / rc.3, the dev-only deepmerge advisory exemption (expires 2026-11-30 UTC) and more; see the [v0.7.0 release notes](https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.7.0).
- **Windows installers are unsigned**.
- **The cloud gateway combination is not tested end to end**: the v0.7.0 desktop app + the v0.7.0 gateway image have not been tested on a real VPS or with real ChatGPT; only in-CI tests passed.
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
