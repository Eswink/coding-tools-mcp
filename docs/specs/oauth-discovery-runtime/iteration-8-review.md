# Iteration 8: atomic tunnel configuration application

Base: b7d885f8248928e8b158e745cbb5a0f7150d3cd1 / tree 2a09e90fa5074c1d7c331d0de6624d9299c678b7. This iteration preserves existing remote iterations 5–7.

## Causal assessment and acceptance contract

The token field wrote a credential in one IPC request before the parent saved its route in another. If route validation/persistence failed, only the credential had changed. A token-only save could also leave a live connector using its old token, since the backend only selected authentication keys. The route then attempted a second tunnel restart after the backend had already restarted the service. Awaiting secret persistence before dereferencing live workspace callbacks allowed navigation to redirect subsequent UI actions. These are code-path defects; none proves the user's public 404 source.

The repaired contract is one write-only optional tunnel credential alongside the workspace update. Backend validation binds the key to the submitted provider/channel/source before any stop or write. The route and credential share one encrypted snapshot, with existing conflict detection and rollback. Stopped services stay stopped; actual running consumers are applied once. Legacy inline Actions tokens are cleared in that same snapshot. Explicit tunnel commands share the lifecycle gate; health/configuration observations invalidate on both success and error. A strict configuration restart reports connector errors without restoring weaker authentication; explicit local start retains its separate local-only behavior.

The frontend token field prepares a draft, never writes independently. Both tunnel saves use canonical readback. Captured workspace/service/callbacks and disposal checks prevent stale test/save continuations from operating on a different workspace. Credentials are not recorded in global state, logs, or review output.

## Risk and verification

HIGH: configuration persistence, public tunnel lifecycle, IPC and UI callbacks. Graph indexing failed at lbug file sync; direct exact-symbol impact was attempted and reported no usable index. Direct callers inspected: workspace update -> configuration transaction -> datastore snapshot/runtime start, plus tunnel command adapters and route/form callbacks. This is a declared graph fallback, not a successful graph result.

Four of five new frontend regressions failed on the base. After repair all 21 targeted behavioral/compiler/AST tests pass. New Rust cases cover provider/source/channel validation, invalid input before live shutdown, stopped atomic save, legacy override removal and snapshot failure rollback. Real Windows/Linux Rust and complete frontend CI are still mandatory. No versions/dependencies/security gates changed.

Initial self-review 89/100, rejected for a hidden tunnel-start error and legacy inline credential precedence. Fixed by strict apply-result handling and atomic override removal. Revised candidate 94/100 pending CI; no merge/release approval. Remaining credential-form races and exact installed native matrices are separate mandatory follow-ups.
