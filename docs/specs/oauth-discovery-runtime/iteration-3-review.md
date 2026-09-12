# Iteration 3: awaited configuration application

Base commit: 3e3ad9e8035ba42bca398e4b6b6e0abb51c0aed3 (exact source artifact verified against tree dcb1a82e580b7ba59c421b26d372679561ebea4b).

## Confirmed implementation defects

`update_workspace` previously persisted without synchronizing the running listener. The UI attempted a separate restart based on its cached running state and swallowed that restart failure. Workspace secret setters did not restart; shared setters and regeneration scheduled background restarts and returned before their result. The MCP supervisor unconditionally passed no client secret, despite the configured secret displayed by the desktop. These are reproducible code-path defects; none alone proves the source of the user's public HTTP 404.

## Countermeasure and impact

A single backend lifecycle gate covers configuration persistence, affected-service selection, awaited shutdown and restart. The new configuration module revalidates the profile after await, leaves affected listeners stopped when persistence fails, and reports application failures rather than restoring weaker authentication. It revokes affected chat grants and never starts consumers that were stopped. Shared credentials select only consumers using the shared pool; MCP and Actions keys are scoped separately. Actual saved client authentication now matches the MCP metadata. User credentials are not copied into tests or logs.

Manual upstream review: workspace update/delete and secret commands enter the configuration transaction; runtime start/stop/restart share its gate; Tauri invoke adapters are the public IPC callers. No standard-library data/runtime mutex crosses await. The existing native test driver must supply a fixture client secret after this intentional enforcement repair. Frontend duplicate-restart removal and full native installation validation are separate mandatory follow-up gates.

Graph analysis was attempted using the repository toolchain. GitNexus indexing failed with an lbug file-sync I/O error, including on a temporary local filesystem; impact/detect-changes could not open an index. Exact diff and direct caller inspection are used as the declared fallback, not represented as successful graph validation. Risk: HIGH (authentication and lifecycle).

## Tests and review

Added real HTTP configuration tests: noauth-to-OAuth while running, saved client-secret enforcement, rotation and grant invalidation, stopped-consumer preservation, failure during persistence, failed start reporting, serialized concurrent writes and shared-consumer selection. These tests use only the test DataStore and disposable workspaces.

Initial manual self-review: 89/100, rejected before submission for stale frontend restart prompts and incomplete failed-start status handling. Revisions correct the latter and prepare frontend changes separately; backend candidate 92/100 pending real Windows/Linux CI. No score overrides failed gates. Seven existing no-dependency frontend checks passed locally. Rust and complete frontend execution require CI; this container has neither cargo nor installed project npm dependencies. This is not final product acceptance and must not be merged or released yet.
