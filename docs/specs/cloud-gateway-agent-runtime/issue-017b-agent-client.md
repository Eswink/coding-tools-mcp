# ISSUE-017B — Outbound recovery-only Agent and managed control service

Tracking: #47; dependency #46; parent #32. Baseline 99ed3d061b8c72bde36fcb64b9a29aca6c703a6d.
Status: DESIGN_FROZEN_FOR_IMPLEMENTATION. Workstation/VPS/ChatGPT acceptance is deferred by user.

## Scope and authority

Add two independent native binaries: coding-tools-agent and coding-tools-control-gateway. The existing coding-tools-gateway serve command remains identity-only. The new control service requires explicit local-operator device selection and mounts the existing authenticated channel behind the same HTTP bounds. No HTTP administrator or enrollment shortcut, no local executor, no cloud shell, no offline work queue.

This first shipped signer is deliberately recovery-only. It can prove device possession and sign a locally constructed RecoveryRequired/Offline snapshot with no grant and no drain acknowledgement. It cannot accept scopes, conversation, phase, grant, revision or execution requests from server/model input. Existing active authority cannot be replaced by an empty snapshot; projection rejects that mismatch and the client stops for reconciliation. The future actual local authority provider is a separate issue, not an untrusted input file accepted here.

## Local configuration / signing

The validated non-secret config fixes HTTPS origin/prefix/connector/device/registry epoch/local authority epoch, expected public key, and an absolute local revision journal path. The client derives wss://<configured authority>/<prefix>/agent; redirects, credentials, query and path substitutions are never followed. Optional private-CA DER comes from an explicit protected local file, selects a separate explicit local trust store and does not disable chain/name verification. Normal public-WebPKI verification is default.

Device private key is bounded base64 PKCS8 input through non-terminal stdin or the existing Unix owner-only file contract. No secrets in CLI flags/environment/logs, and no Windows plaintext file fallback while ACL validation is unavailable. A decoded key must match the locally pinned public key. The key is not a generic signing API; only validated connect claims and generated recovery snapshots are signed.

A separate exclusive OS file lock holds the revision journal for the process lifetime. Validated append-only records bind configuration identity and public key, revision and a domain-separated device signature. Each revision is fsync'ed BEFORE sending a snapshot. Missing state on run, corruption, duplicate/reordered records, mismatched identity, concurrent process, overflow or exhausted bounded journal fails closed. Explicit init-state alone creates the first record without truncating existing state. Kernel lock release permits process crash/restart without stale PID lock deletion. Same-UID hostile processes/whole-machine rollback are not a sandbox guarantee; the cloud revision fence rejects old journals.

## Protocol / lifecycle

WSS upgrade must return exactly the expected subprotocol. Validate typed deny-unknown-fields server messages, boot/attempt/nonce, 10-second proof window, issuer/resource/connector and epochs before signing. Never reflect unknown JSON into a signature. Validate sequence and operation reply type. Only expected control messages are accepted; no command forwarding exists.

Client operations are sequential and bounded: handshake/receive 10s, send 2s, heartbeat every 8s, independent recovery snapshot every 16s bounded by the server's connection-lease ceiling and locally verified current time. A server time outside the proof window fails (no automatic clock correction). Default overall run limit 1h, configurable 1..3600s; each reconnect attempt has a timeout and exponential capped jitter. Auth/protocol/TLS/redirect/projection rejection is terminal; only bounded transport interruption retries. No request replay, no indefinite invalid-credential loop. Cancellation is always observed and closes the socket within a bounded period. Logs are fixed event names/counts, never private keys, challenge/proof or server payloads.

Managed channel router returns a shutdown handle. The service stops accepting HTTP, signals all upgrade tasks (including pre-auth), drains transport permits and then shuts down its matching controller generation before closing PostgreSQL. Hyper enables with_upgrades explicitly; the HTTP semaphore is not claimed to cover detached WebSocket lifetime. Channel's existing independent 8-connection bound covers upgraded sessions. Late cleanup is conditional on session/generation. Default identity-only routes still return 404 to /agent.

## Tests and release truth

Pure client tests: config canonicalization/key matching/strict reply parse/challenge identity/time/signature domain/journal replay or corruption/exclusive lock/reconnect classification. Actual independent gateway/client process tests with enrolled keys and disposable PostgreSQL: handshake, recovery-only projection, heartbeat vs snapshot, SIGTERM/restart, revoke, no arbitrary authority. TLS: private CA success, wrong name/untrusted CA/expired cert and HTTP redirect rejection before device proof. Existing 194 Rust tests and 30 service/process cases remain mandatory. Portable tests run Windows/Ubuntu; full DB/TLS/process suite initially Ubuntu and is labeled as such.

No browser, VPS, WAF or ChatGPT acceptance is claimed by this increment. No production release allowed while the complete MCP business path/admission/no-replay integration is missing. CI can package source-linked development binaries, never call them production-ready.

## Source impact and review

Graph refreshed before edits: service/runtime.rs::serve HIGH (9 inferred impacts/3 direct), including unrelated health tests whose axum::serve names are misresolved. Reported before editing; manually check actual standalone caller and keep desktop source unchanged. Existing channel route/upgrade are LOW, run_socket one direct caller LOW; shared read_protected LOW and unchanged. Keyword FTS unavailable and Rust graph incomplete, so no-caller reports are not proof. New code lives in agent/ and control CLI; modify only the common service runtime and managed upgrade lifecycle under independent process regressions.

References checked 2026-09-22: Rust std::fs::File lock/try_lock (OS handles release on close); tokio-tungstenite pinned 0.26.2 connect source; Hyper 1.11.1 with_upgrades; OWASP WebSocket Security. No Codex source copied. Version-pinned dependencies and local/source-tree evidence retained.
