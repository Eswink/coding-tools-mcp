# Iteration 6: safe credential display and async diagnostic results

Base: remote 00ddba538b8ba48047cfab4144b77745451b6b40, exact tree 8e9c0de91bab9947bed65c828bcb18487d9b8157.

## Observed defects

SecretInput defaulted to visible=true; QuickCopy rendered unmasked client secrets/passwords. QuickCopy retained previous values during context changes, had no load-error handling, and did not react to a credential rotation without a profile change. A delayed health response could populate a different workspace. Backend skipped results would previously render as failures.

## Repair

Secrets are hidden by default and re-hidden when context/value changes; copying remains an explicit user action. Disabled secret inputs cannot copy. QuickCopy clears its previous values before reads, captures its workspace/service inputs, rejects obsolete requests, handles failures without echoing backend strings and does not substitute a workspace ID when the shared ID failed to load. A small request-ticket helper protects navigation/destruction. The credential store holds only revision/pending counters; every mutation invalidates before and after, including a persistence-success/restart-failure. While writes are pending, QuickCopy stays empty/loading. Health skips have an explicit neutral badge, never PASS.

## Impact and evidence

Exact-symbol GitNexus impacts for health, credential API and QuickCopy are recorded; static Svelte component references and aliases were also inspected because graph coverage of template wiring is incomplete. Risk HIGH: credential display. Graph FTS is unavailable. No credential values, dependencies, server policies or package versions are changed. The existing Rust gate is unchanged. The push workflow now runs both platforms' full frontend checks/build/regressions; its short-retention reviewer artifact contains only the exact installed TypeScript/Svelte compiler directories (no config/env/secrets) for offline local reviews.

Added actual transpiled-TypeScript tests for read-only behavior, success/error invalidation and overlapping writes, plus request-ticket races and Svelte compilation/AST masking checks. These are not native-browser evidence. Initial manual review 89/100 rejected the success-only invalidation and stale shared-ID fallback; both are corrected. Revised candidate 94/100 pending CI. Frontend configuration forms and duplicate restart cleanup remain iteration 7, followed by strict installed native gates and release.
