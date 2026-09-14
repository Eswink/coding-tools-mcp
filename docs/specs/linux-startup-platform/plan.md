# Linux Startup Recovery and Platform-aware Tools

Status: APPROVED / EXECUTING. Product release is NOT approved until the gates below pass.

## Authorization and frozen baseline

User report: Ubuntu DEB and AppImage both exit immediately; Windows works normally. User approved the proposed staged plan: "确认 Plan，开始 迭代任务！循环迭代任务启动！ @GitHub".

- Repository: Eswink/coding-tools-mcp.
- Starting main: `5780302c123f8aa308017f2d2767fc18e3ef7c5b`.
- Published v0.5.0 product source: `63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076`.
- Implementation branch: `fix/linux-startup-platform`.
- Do not move v0.5.0, replace its assets, change its release channel, revive PR #11, modify production Nginx, or touch user credentials.
- Earlier successful CI proves only its recorded environment. This new operator report is an unresolved P0; neither historical success nor a synthetic reproduction proves the cause on the user's machine.

## Goals and sequencing

First stop unobservable Linux startup failures; then make the existing platform abstraction authoritative for tools, UI, paths and processes. Keep Windows behavior and all authorization boundaries intact. Use Windows/Linux/macOS/unsupported explicitly: non-Windows does not universally mean Linux.

Candidate design: fail-safe bootstrap + capability snapshot + platform-aware MCP execution. Stable semantic tool names remain stable. Do not translate PowerShell strings to Bash, silently turn existing direct commands into shell evaluation, or broaden execution permissions. Detailed host information remains behind the applicable existing authorization gate. Dynamic capabilities must represent unavailable/unknown as such and be refreshable; environment availability is not immutable after startup.

## Rounds and evidence gates

| Round | Work | Required evidence |
| --- | --- | --- |
| 01 | Save plan, read rules/context, freeze refs, create isolated branch | Plan committed before product edits; baseline identities |
| 02 | Reproduce published DEB/AppImage startup failures | Verified original bytes, normal-user isolated config, exit status, bounded stderr and exact environment; record missing user-machine evidence |
| 03 | Early bootstrap logs and diagnosis | Phase markers before app-state creation; safe log location; no secret/body/environment dump; loader/native-signal limits stated |
| 04 | Recoverable app-state initialization | Unavailable/locked/missing keyring and invalid config show locked recovery rather than panic; ciphertext unchanged; retry is local only |
| 05 | Optional tray/notification/tunnel startup | Optional errors cannot terminate app; no hide-to-tray when no usable tray; no remote services while locked |
| 06 | WebKitGTK/display/package isolation | Separately test runtime-only installs, X11 and actual Wayland where available; do not relabel Xvfb as Wayland; conditional rendering workaround only with evidence |
| 07 | Platform/capability context | Compile-target OS + runtime capabilities; no browser/user-agent inference; unsupported platforms fail explicitly |
| 08 | MCP environment contract and startup prompts | Existing names and authorization preserved; accurate OS, path and command-mode information |
| 09 | Linux command execution | Direct argv as default; explicit shell mode and policy checks; missing tools return actionable errors; no automatic command translation |
| 10 | Linux paths/open/executable discovery | Case/symlink/permissions/GUI PATH and paths with spaces covered; Windows paths not silently rewritten |
| 11 | Linux task and process lifecycle | Real child start/termination, descendants, timeout/cancel/draining; no successor while cleanup uncertain |
| 12 | Tunnel/software/credential capabilities | Executable availability, architecture and permissions validated; no auto-sudo or plaintext fallback |
| 13 | Recovery/safe mode and environment UI | Local retry/export; safe mode starts no MCP/Actions/tunnels/jobs; inaccessible display gets CLI diagnostics, not a promise of a GUI |
| 14 | Ubuntu package/MCP/security regression | DEB and AppImage from exact source; ordinary user; install/start/restart/persist; OAuth/exclusive/refresh/history |
| 15 | Windows full regression | Preserve existing command/Job Object/UNC/UI/security behavior; actual installed NSIS evidence |
| 16 | Candidate and operator acceptance | Private-to-task CI candidate first; user's real Ubuntu validates both formats before Stable/Latest |
| 17-20 | Bounded follow-up for new evidenced failures | Each round names failure, hypothesis, patch, tests, rejected alternatives and next step; no rerun-until-green |

## Failure hypotheses, not assumed causes

H1: `AppState::new().expect(...)` converts configuration/keyring failure into panic. H2: `setup_tray(app)?` makes tray failure fatal. H3: native WebKitGTK/display/GPU failure. H4: packaging/runtime libraries/architecture or AppImage loader/FUSE. H5: early notification/tunnel startup. Test shared startup layers before attributing both formats to AppImage-only FUSE. Preserve errors even when multiple issues coexist.

## Startup contract

States: detecting -> initializing -> ready, or locked/recovery; optional degraded capabilities do not mean full readiness. Configuration is encrypted as a whole; a locked app must not fabricate a normal workspace list, create replacement keys, write defaults over encrypted data, start listeners, refresh credentials, or restore jobs. Retry checks actual dependencies and initializes exactly once. Local diagnostic UI/CLI must work without successfully loading DataStore. Optional workers start only after readiness and outside locks. No blanket panic catching to continue with corrupt state. Native loader failures and SIGSEGV need external launcher/system evidence because a Rust panic hook cannot catch them.

## Test matrix

- Ubuntu 22.04 and 24.04, DEB and AppImage, fresh and existing configuration, regular desktop user.
- D-Bus/Secret Service usable, absent and locked; missing encryption key; corrupt/future configuration; unwritable state directory.
- Tray and notifications absent; display absent; graphical startup via desktop entry and terminal.
- Default AppImage mount path separately from extract-and-run. Preserve sandbox/AppArmor protections. No permanent GPU/X11 override without confirming a causal fix.
- Window ready plus >=60s process liveness, close/reopen/restart, no undisclosed panic, no plaintext canary in logs/config/export.
- Git/Python/executable absence, POSIX paths, stdin/stdout/stderr, timeouts and real process drain; Windows negative compatibility checks.

Build and install environments must be distinct. A headless runner with installed desktop support is not the operator's actual desktop. Record toolchain/runtime versions and normal-user identity. Final Ubuntu acceptance requires user's real-machine reproduction and retest; collect Ubuntu version, CPU architecture, desktop session, launch method and sanitized startup output when available, without blocking independent safe work.

## Version and release policy

Leave version fields at 0.5.0 while making source-only diagnostic changes; never distribute modified bytes as replacement v0.5.0 assets. Before producing a candidate installer, synchronize all version fields to a unique 0.6.0 candidate version and validate packaging contracts. Prefer CI candidate artifacts without creating a public pre-release automatically. Stable v0.6.0/Latest follows both exact-source automated gates and user-machine acceptance. No release action is permitted in the diagnostic workflow.

## Engineering tooling

Read AGENTS.md and `.agents/skills/mcp-probe-kit/SKILL.md` before implementation. Discover native Probe/GitNexus; if absent attempt the pinned 4.0.1 launcher/install and preserve failures. Current session found no matching native plugin; launcher absent, pinned install timed out (exit 124), container GitHub DNS unavailable. Retry restored channels when possible. Do not call manual source review a successful GitNexus analysis. Scope/impact review must be recorded before each symbol change, and diff review before each commit; high-risk startup/auth changes need explicit disclosure. Old project-context/graph snapshots are historical and cannot override current encrypted storage and code.

## Completion record

Each iteration writes `iteration-XX.md` and updates `state.json` with exact candidate, evidence source and outstanding gates. Freeze/check current branch before updating it; do not overwrite concurrent work. Only one feature PR; no duplicate implementation PRs. Completion requires no unresolved P0, no regression on Windows, no secret downgrade, reproducible packages, and explicit operator acceptance. Until then report partial progress, not task completion.
