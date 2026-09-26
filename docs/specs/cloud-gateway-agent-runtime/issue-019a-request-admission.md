# ISSUE-019A — bounded admission and durable no-replay reconciliation

Tracking: #49; parent Epic #32 / Draft PR #36. Depends on #47 outbound client and #43 device-owned projection. Physical workstation, VPS and real ChatGPT acceptance remain deferred by user and are not treated as PASS.

## Scope frozen for this increment

This increment adds only a cloud-side metadata admission ledger. It does **not** execute a tool, enqueue offline work, provide a shell, or replace the future Agent's authoritative local execution gate. The ledger accepts a bounded request only while the current device-signed projection, channel generation and local-grant projection are simultaneously valid. `begin_execution` rechecks the same fence immediately before a future dispatcher could hand work to an Agent.

A request binds a non-nil request ID, HMACed conversation binding, known local scope, bounded tool name, canonical SHA-256 argument digest, trusted request class, deadline, selected device/registry epoch, gateway boot, channel session/generation, local grant ID, projection revision and authority epoch. Raw tool arguments, command output, source files, Host sessions and bearer credentials are never persisted. Canonical JSON sorts object keys recursively so semantically identical object order is one digest.

## No-replay state machine

Durable states are `not_admitted`, `admitted`, `running`, `completed`, `outcome_unknown` and `cancelled`. Exact duplicate submission returns the already durable state and never launches twice. Reusing the request ID with changed arguments, scope, tool, class or deadline is a conflict. A request rejected while Offline stays terminal even if the workspace later comes online; a caller needs a fresh request ID.

Before moving `admitted -> running`, the transaction rechecks the current device, grant, conversation, scope, authority epoch, projection revision floor, gateway boot, exact channel session/generation, channel lease, projection freshness and execution state. Pause, revoke, reconnect, drain, expiry or changed generation therefore prevents dispatch. Cancellation of already-running work is `outcome_unknown`, not a claim that side effects were undone. A lost response or old-boot nonterminal row is likewise fenced to `outcome_unknown` and is never automatically replayed.

At most 32 admitted/running rows are allowed per connector. A channel-row lock serializes this bound. Retries sharing one request ID additionally use a transaction-scoped advisory lock, preventing the unique-key race without creating global execution authority. Deadlines are at most five minutes. Cleanup is bounded to known terminal metadata only; `running` and `outcome_unknown` are never garbage-collected by the terminal purge API.

## Authorization and privacy ordering

Conversation ownership is checked before scope and availability. A foreign conversation receives the generic authorization denial regardless of online/offline state. Scope denial is returned only after a matching conversation grant. Recovery and Offline are evaluated after the grant boundary. No pending authorization record or notification queue is created by this module.

The cloud projection remains an eligibility fence, not the final local execution permit. A future locally approved Agent provider must recheck authoritative local grant/scopes/epochs and acquire its local execution gate before any tool side effect. This issue deliberately stops before that integration.

## Failure-first evidence retained

Initial PostgreSQL tests exposed two defects before publication: concurrent exact duplicate submissions could both observe no ledger row and race on the primary key, and a test decoded PostgreSQL `octet_length` (`int4`) as Rust `i64`. The request path now takes a transaction-scoped advisory lock before the existence check, and the test uses the correct type. The failing run is retained in `round8-validation.md`; assertions were not weakened.

## Rollback and release boundary

Migration `0005_request_ledger.sql` is additive and contains metadata/hashes only. Code rollback must not delete migration history or unknown-outcome rows. Stop future dispatch first, retain durable rows for reconciliation, then roll code back. No main merge, production DNS/Nginx/WAF/VPS change, installer or release is authorized by this engineering result.

## Publication status

Engineering source is published as `1e1db5faa0fdcf34133b615f9842b93a40fe7b9a`, exact tree `2ec47d544a1d5bd3d001fcf912516e01c6b56176`. Independent source verification run `35694160510` passed before native publication. Current-source request-admission CI `35694473116` passed Ubuntu PostgreSQL plus Windows/Ubuntu portable jobs. Full publication evidence is in `round8-publication.md`.

This closes the isolated cloud admission/no-replay engineering increment only. The locally approved authority provider/execution gate bridge remains the next dependency; no local tool side effect is authorized by this module.
