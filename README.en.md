<p align="center"><img src="src-tauri/icons/128x128.png" width="80" alt="Coding Tools MCP"></p>
<h1 align="center">Coding Tools MCP · Eswink</h1>
<p align="center">Local workspaces, exclusive conversation approval, long-running tasks and recoverable development records for ChatGPT.</p>
<p align="center">
  <a href="https://github.com/Eswink/coding-tools-mcp/releases/latest"><img src="https://img.shields.io/github/v/release/Eswink/coding-tools-mcp?label=Release" alt="This repository's full release"></a>
  <img src="https://img.shields.io/badge/Windows-x64-0078D4" alt="Windows x64">
  <img src="https://img.shields.io/badge/Ubuntu-22.04%20%7C%2024.04-E95420" alt="Ubuntu amd64">
</p>
<p align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a> · <a href="https://github.com/Eswink/coding-tools-mcp/releases/tag/v0.5.0">Download v0.5.0</a> · <a href="docs/releases/stable-v0.5.0.md">Release and verification scope</a></p>

This is the **Eswink/coding-tools-mcp** desktop distribution, built with Rust, Tauri 2 and Svelte 5 / SvelteKit. It exposes selected local projects through MCP so an approved AI conversation can read files, apply patches, run commands, inspect tasks/logs and save development checkpoints.

This fork focuses on **personal, sustained development through ChatGPT**. OAuth authenticates the connection; each conversation still needs fingerprint verification and approval on the local desktop. By default, only one conversation owns a workspace. Other conversations cannot take over or create additional approval notifications.

## Download and install

Current delivered version: **v0.5.0**. The live [Eswink Releases page](https://github.com/Eswink/coding-tools-mcp/releases/latest) determines full-release/Latest status. Promotion keeps the previously verified package bytes unchanged.

| Platform | Package | Scope |
| --- | --- | --- |
| Windows x64 | [MCP_0.5.0_x64-setup.exe](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_x64-setup.exe) | NSIS installer; not commercially signed |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.5.0_amd64.deb](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_amd64.deb) | Preferred package for a logged-in, non-root desktop user |
| Ubuntu 22.04 / 24.04 amd64 | [MCP_0.5.0_amd64.AppImage](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/MCP_0.5.0_amd64.AppImage) | Automated acceptance covers extract-and-run, not every FUSE/Wayland environment |

Verify against [SHA256SUMS_v0.5.0.txt](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/SHA256SUMS_v0.5.0.txt). This release does not provide this fork's acceptance-tested macOS, ARM or headless Linux Server packages.

For Ubuntu, run this in the directory containing the downloaded DEB:

```bash
sudo apt install ./MCP_0.5.0_amd64.deb
```

Installing a system package needs elevated privileges; **running the desktop application does not**. Do not launch the GUI with sudo. Linux secret recovery needs the user's D-Bus session and an available, unlocked Secret Service. AppImage can use `--appimage-extract-and-run` as described in the original verification guide. Do not disable the sandbox to work around startup failures.

**Update-source limitation: the v0.5.0 binary's built-in update checker still points to upstream. To update this fork, use the Eswink Release links above, not a release suggested by that upstream checker.** Updating README or Release metadata cannot change compiled URLs. [Source](src-tauri/src/update/mod.rs)

## What's new in v0.5.0

Five pages share a navy sidebar, semantic status colors, grouped cards and light/dark/system themes without changing route URLs:

| Page | Implemented capabilities |
| --- | --- |
| Workspace | Identity, startup prompt, local chat approval, MCP / Actions selection, configuration, tasks, logs and health checks |
| General | Appearance, application information, existing proxy and UI-maintenance settings |
| Shared keys | Mask, reveal, copy, regenerate and save the actual credential types; unreadable fields remain disabled |
| FRP | Manage FRP server profiles; live per-workspace tunnels remain on their workspace page |
| Software | Manage supported software and actual installation paths, without invented version/latency/health data |

The refactor also fixes stale unsaved-change prompts after saving/reverting, late asynchronous navigation results, partial-secret-load bindings and approval-dialog keyboard focus boundaries. Unsupported language/autostart/sound/component-inventory concepts from the design references are not rendered as fake working controls.

[UI-evidence_v0.5.0.zip](https://github.com/Eswink/coding-tools-mcp/releases/download/v0.5.0/UI-evidence_v0.5.0.zip) contains actual built-page and installed-app screenshots. They use isolated acceptance workspaces and synthetic data, not your real service status.

## Connect one conversation

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

## Upgrade, recovery and verification limits

Exit the old app and back up configuration plus the corresponding system account's key-recovery material before upgrading. Do not delete project/history files to install the UI, run competing app versions against one configuration, or force unfinished draining work to become free. An encrypted configuration file alone is not a cross-user recovery guarantee. Retain v0.4.0 and a compatible backup for rollback.

v0.5.0 automated acceptance covers Windows NSIS and Ubuntu 22.04/24.04 × DEB/AppImage: 20 native UI screenshots and 12 authorization/refresh/draining stages per combination. Windows has 432 passing Rust tests and Ubuntu 417, with 180 frontend tests per platform. Built-page browser coverage adds 40 matrix screenshots, 10 interactions and 8 states; its synthetic IPC does not substitute for native evidence.

**Full Release is the repository's selected distribution channel, not proof that every environment is verified.** Real-account long-duration ChatGPT refresh, OS banner visibility and every hardware/FUSE/Wayland combination remain outside complete automated coverage. Windows packages are unsigned. The original build run retains a post-publication tag-lookup 404 failure; a subsequent read-only run verified public bytes. See [release and acceptance details](docs/releases/stable-v0.5.0.md). Bundled Pre-release wording records the original build stage and is not silently rewritten during promotion.

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
