# Verified primary sources and adaptation decisions

Reviewed 2026-09-21. Source research informs contracts, not proof of ChatGPT UI behavior.

| Primary source | Observed design | Adaptation / limitation |
|---|---|---|
| [MCP Streamable HTTP 2026](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) | Required header/body mirrors, no protocol sessions, Origin validation | Separate modern and legacy adapters; mismatch -32020 |
| [MCP discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover) | Independent discovery and per-request metadata | Gateway answers without a worker |
| [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | Tool failure is a result with isError, protocol failure remains distinct | Offline is not fabricated transport success for every error |
| [MCP schema](https://modelcontextprotocol.io/specification/2026-07-28/schema) | resultType and UnsupportedProtocolVersionError -32022 | Version-correct test fixtures, not guessed field names |
| [OpenAI plugin reference](https://developers.openai.com/plugins/reference) | mcp/www_authenticate requests OAuth; session/subject context provided separately | Never attach auth challenge to mere worker offline; session is not employee identity |
| [Codex core](https://github.com/openai/codex/blob/a86631502d49274cb47208925c7d3dcece032029/codex-rs/core/README.md) | UI-independent core and platform sandbox boundaries | Extract tool core later, do not transplant whole agent loop |
| [Codex execpolicy](https://github.com/openai/codex/blob/a86631502d49274cb47208925c7d3dcece032029/codex-rs/execpolicy/README.md) | allow/prompt/forbidden with testable examples | Prefix policy is not an OS sandbox; cargo/npm may execute arbitrary repository scripts |
| [Codex daemon](https://github.com/openai/codex/blob/a86631502d49274cb47208925c7d3dcece032029/codex-rs/app-server-daemon/README.md) | Experimental detached lifecycle and serialized operations | Local convenience only; not a prerequisite for cloud availability |

Codex reference commit: `a86631502d49274cb47208925c7d3dcece032029`, verified via GitHub ref. Repository license is Apache-2.0; any future copied code requires source pinning and attribution/NOTICE review. **This batch copies no Codex implementation and does not install Codex or invoke model inference.**

## Source evidence in this repository

Baseline `758c60a6e74e624e144f9c19c5f19d04d17f7a13`:

- `src-tauri/src/mcp/server.rs:13-78`: dispatch and initialize currently use legacy 2025-06-18; inspected directly, not inferred from empty search results.
- `src-tauri/src/tools/聊天运行域v1.rs:82-134`: guarded allocation, authorization before availability, chat-scoped dispatch.
- `src-tauri/src/runtime/execution_gate.rs`: atomic local admission separation already exists.
- `docs/specs/offline-safe-connector-lifecycle/completion.md`: prior engineering evidence and explicit unconfirmed real-host gate.

Stale July project-context prose and graph FTS search gaps are not current product facts. A fresh graph was built; direct impact resolves even when FTS extension is unavailable in the offline container.
