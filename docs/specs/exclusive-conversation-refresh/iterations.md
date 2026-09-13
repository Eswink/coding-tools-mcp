# Iteration evidence

## 01 — Plan, baseline and tool channel

Plan saved first in c2462cf6ee2aee6f3bd3f134dba534bf54f123dd. Validation workflow committed in2d13411e426e3a8048fb4204d6a5b91231741f1a. Unmodified source tree77dc7f47a529c917a891390a9b959ef2b0b8827a (main tree plus docs/workflow) passes both full regression jobs in run34741653492. Ubuntu job103682256996 and Windows job103682257002 have successful frontend and Rust check/test/production-warning steps. These are BASELINE results, not candidate results.

Probe 4.0.1 install: EAI_AGAIN registry.npmjs.org. Local launcher start_feature: missing executable127. Offline GitNexus impact: ENOTCACHED. Manual source/call-chain inspection is a declared downgrade, not successful orchestration/graph output.

## 02–05 — Candidate owner lifecycle and draining

Implemented default-exclusive reservation, no-noise locked errors, scope/local-approval checks, configurable finite lease and admission epoch. Added tests for16 simultaneous contenders,100 foreign requests, pending timeout, stale decisions and unchanged binding after access renewal. Inspection identified that revocation alone must not release a shared workspace with a live process: added DRAINING and durable dirty/recovery fence, restoration of known task namespaces, local cancellation and generation-bound recovery confirmation. Rust execution is pending CI; no PASS claim.

## 06–07 — Candidate global approval UX

Added global modal, authoritative bounded inbox, server invalidations, foreground/background distinction, generic native notice and tray indicator/menu. Kept workspace recovery/revocation UI and removed the conflicting temporary exclusive toggle. Added explicit fingerprint confirmation and countdown. During review, found A->B->A stale settings completion could affect a successor form; added operation sequencing distinct from draft generation.

Local Svelte compiler5.56.4 compiles new components without warnings. Existing frontend124 tests pass before and after initial integration. With7 new policy/presentation tests, local suite131 passes,0 failures/skips. Production component browser test initially cannot navigate localhost: Chromium returns ERR_BLOCKED_BY_ADMINISTRATOR. Do not bypass browser policy; execute this fixture on GitHub Actions instead. No native notification acceptance claimed.

## 08–10 — Candidate refresh and configurable durations

Implemented bounded encrypted refresh families, authenticated opaque refresh tokens, atomic rotation, reuse revocation, family-linked JWT and explicit offline consent. MCP discovery advertises implemented refresh grants; legacy Actions remains authorization-code-only. User settings validate both UI/backend and preserve old profile defaults. Notification dependency pinned2.4.0 requires a reviewed lockfile generated in CI; container has no Rust toolchain/DNS. Test sources cover persisted reopen/corruption/client/resource/scope/replay/race/I/O, plus actual HTTP code->refresh->same-owner and live-process drain. Not executed yet.

## Next gate

Publish exact candidate source, resolve only the new notification dependency, run locked candidate builds and tests on Windows/Ubuntu plus browser/failure-first jobs. Do not merge, publish installers, modify PR #11 or production Nginx while these gates remain open. Every subsequent failure and fix gets a new evidence entry; do not retry until green or replace old release assets.
