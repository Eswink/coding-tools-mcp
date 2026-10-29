# Round 3 — ISSUE-013B owner browser consent

Status: DESIGN_FROZEN_FOR_BOUNDED_INCREMENT; GitHub #41, parent #37, Epic #32.
Base: local `4b6f197118d818735d77d23d9f8593976abdb702`; remote base `ba9c379f08da37f2a05bb96c377a95f432da969e`.

## Scope and requirements

FR-4 / agent-channel/2.1: finish the missing owner login and explicit browser consent adapter. This is not local chat approval, Agent transport or public production deployment. Reuse the existing parent-child specification; do not replace it with a generated flat template. All source files stay below 500 lines; browser storage, credentials, HTTP rendering and tests are separate modules.

## Current source evidence and impact

`src/oauth.rs::issue_after_owner_consent` opens and commits its own transaction. A browser controller cannot consume its transaction atomically with this API; extract a transaction-taking internal helper and preserve the trusted operator API for existing tests/provisioning. `src/http.rs::boundary` validates Host/Origin and no-store headers but no browser route exists yet. Existing desktop `src` and `src-tauri` are excluded.

GitNexus 1.6.9 rebuilt the recovered tree. Both focused impacts returned LOW and zero callers, but source tests call the consent API and the HTTP router calls boundary. Rust graph edges are therefore incomplete, and FTS was unavailable. Treat authentication as security-critical regardless of the low graph label. Review all exact source callsites and run the complete identity suite.

## Architecture and transaction ordering

One explicitly provisioned owner per isolated connector database; no public signup or default password. Argon2id uses fixed bounded parameters (m=19456 KiB, t=2, p=1); password work runs off the async executor with at most two concurrent tasks. Lock owner before browser transaction, then registered client, consistently. Rate-limit failed logins in the owner record across connections/restarts: five failures trigger a 60-second cooldown. New preauth transactions are capped at 128 active per database and expire after 300 seconds. These are not a replacement for the future public ingress/IP limits.

GET authorize validates response_type/code, exact registered client and redirect, resource, mcp scope, S256 challenge and bounded state. It creates a five-minute browser transaction but never a code. The original request/state is encrypted at rest using domain-separated AEAD; browser cookie and form-CSRF secrets are stored only as keyed digests. Login requires the original cookie, separate CSRF field and owner password. Successful login replaces the preauth identity and rotates both secrets without extending the absolute deadline. Login alone does not issue a code. Consent POST explicitly allows or denies; row locks and one SQL transaction consume the browser flow with code/family creation. Denial creates no code/family. Unknown/lost responses are not replayed.

Credential rotation is an explicit trusted operator operation with an expected epoch. It invalidates pending/browser sessions and existing OAuth families. HTTP cannot supply subject/owner, rotate passwords, enroll devices or grant workspace permissions. Recheck owner epoch, flow expiry and client disabled/redirect state after awaited hashing and immediately before issuance.

## HTTP boundary

Secure, HttpOnly, SameSite=Lax, Path=/ `__Host-ctm-browser` cookie with no Domain. This origin is shared with an existing site: cookie prefixes/paths do not isolate untrusted same-origin applications. Production review must trust the existing site or move authorization to a dedicated hostname with explicit OAuth migration. No host change is made here.

POST requires exact Origin and CSRF, rejects duplicate cookies/form keys, unsupported keys/content types, malformed encoding and POST query strings. Present Fetch-Metadata must say same-origin. No third-party HTML resources/scripts, escape rendered values, no-store, no-referrer, nosniff, frame-ancestors none. Consent CSP form-action permits only self plus the prevalidated callback origin so a 303 redirect is not accidentally blocked. Real browser enforcement remains a separate test gate. Authorization `state` and all secrets stay out of logs and errors.

## Failure-first and regression acceptance

Unauthenticated authorize must never redirect with a code. Login CSRF/wrong cookie cannot mint a consent session. Login rotates session and invalidates preauth reuse. Consent CSRF/wrong phase/tampered form/expired transaction/rotated credential/disabled client must fail. Concurrent allow yields only one code. Deny yields access_denied plus unchanged state, not a code. Correct S256 exchange and refresh work with no Agent. Reopen the store and process to validate durable transaction continuation. Preserve all round2 and legacy protocol tests.

## Deliverables / budget

New `src/browser/{mod,credentials,envelope,flows,http,html}.rs`, additive `0002_browser.sql`, and separate `tests/browser_{store,http}.rs` (each <=500 lines); modify consent helper in oauth.rs, module exports, HTTP route composition and CI test selection only as required. Update issue/status/evidence docs. No root dependency changes, desktop changes, credentials, Nginx reload, VPS writes, release or merge.

## Sources

- https://www.rfc-editor.org/rfc/rfc9700.html
- https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html

These guide the design; passing in-process tests is not an independent security audit or real ChatGPT validation. Host remains UNCONFIRMED_ON_REAL_HOST.
