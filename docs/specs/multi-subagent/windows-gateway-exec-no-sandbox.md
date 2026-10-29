# Windows gateway exec: no sandbox (0.8.0, Q3 = B)

User decision 2026-10-29 (DM): Q3 = B — open Windows gateway exec without
sandbox, default permissions; restricted mode still rejected.

**Windows gateway exec has no sandbox and runs with user default permissions.**

| Platform / permission mode | Remote `exec.run` via the cloud gateway |
| --- | --- |
| Ubuntu/Linux, any mode | Unchanged: mandatory per-child kernel sandbox (Landlock/seccomp). |
| Windows, `trusted` (default) or `dangerous` | Admitted. No OS sandbox; the command runs as the desktop user with that user's default permissions. |
| Windows, `safe` (安全受限, user-selected restricted mode) | Rejected exactly as before: `SANDBOX_REQUIRED`. |
| Windows, unknown or inconsistent mode | Rejected (fail closed): `SANDBOX_REQUIRED`. |
| macOS / other | Unchanged: `SANDBOX_REQUIRED`. |

Unchanged on every platform:

- chat session authorization (`CHAT_NOT_APPROVED`, `INSUFFICIENT_CHAT_SCOPE`,
  admission ticket, nonce/expiry). The session grant with the `exec.run`
  scope is approved locally once; individual gateway commands are **not**
  separately approved in `trusted` or `dangerous` mode and are subject only to
  the command policy of the selected permission mode (allowlist, `confirm=true`
  for dangerous-looking commands, network rule);
- audit logging;
- every non-exec tool, and the local (non-gateway) execution path.

`exec_environment` on a Windows gateway in default mode reports
`workspace_exec_boundary = "unsandboxed_user_default_permissions"`,
`workspace_exec_sandbox_enforced = false`, and warnings with the sentence
above and the session-authorization sentence, so the primary agent can see that no sandbox is present.

Code: `src-tauri/src/tools/execution_sandbox.rs` (`remote_exec_gate`,
`environment`), `src-tauri/src/tools/cloud_host.rs` (`NativeToolHost::prepare`).
