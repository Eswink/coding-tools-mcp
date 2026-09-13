# Execution tasks

Follow the12+8 bounded rounds in [plan.md](plan.md). A code checkbox is not an acceptance checkbox.

- [x] Save user-approved plan on an independent branch before implementation.
- [x] Pin source and run unmodified Windows/Ubuntu baseline (34741653492).
- [x] Implement typed policy/owner state, atomic reservation, quiet non-owner refusal and admission guards.
- [x] Implement durable execution fence and local-only recovery controls.
- [x] Implement OAuth offline scope, rotating refresh families, family-linked JWT validation and durable storage.
- [x] Implement global approval host, tray/notification bridge, configurable settings and workspace panel integration.
- [x] Add unit/HTTP/browser test sources; run available local JS regression (131 tests).
- [ ] Verify failure-first assertion on pinned old code.
- [ ] Resolve and review notification dependency lockfile in the networked CI environment.
- [ ] Compile and execute the new Rust/HTTP tests on Windows and Ubuntu; fix every reproduced candidate failure.
- [ ] Run production component browser fixture in an unrestricted test runner. Local Chromium reports ERR_BLOCKED_BY_ADMINISTRATOR; do not disable its policy.
- [ ] Review exact diff/call-chain and sanitize evidence.
- [ ] Verify installed native Windows/Linux notification behavior and actual ChatGPT renewal/host metadata separately.
- [ ] Synchronize a fresh version and publish only after the applicable release gates; never overwrite v0.3.2.
