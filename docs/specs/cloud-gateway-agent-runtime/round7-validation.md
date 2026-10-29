# Round 7 — native outbound control client and delivery queue

Date: 2026-09-22. Baseline: `99ed3d061b8c72bde36fcb64b9a29aca6c703a6d`.
Issues: #47 / ISSUE-017B, #48 / DELIVERY-001; next packet #49 / ISSUE-019A.
Status at source commit: **LOCAL_ENGINEERING_VERIFIED / REMOTE_CI_PENDING**.

## Implemented scope

Two independent binaries now exist: `coding-tools-agent` and
`coding-tools-control-gateway`. The existing `coding-tools-gateway` remains
identity-only. Control service requires explicit, transactional, idempotent
local selection of an enrolled device. Selection and failed bind do not restart
or fence another live controller. The same bounded HTTP server hosts the
opt-in upgrade route; upgraded sockets have their own shutdown ownership and
connection budget. Stale controller shutdown cannot invalidate a newer boot.

The local client uses WSS with real chain/name/date validation, no redirects,
strict fixed wire/identity validation, bounded retry/cancellation and typed
recovery-only signing. An optional DER CA is an explicit local trust store,
not a certificate-verification bypass. Key input is bounded non-terminal stdin
or existing protected Unix files; Windows private-file mode is refused until
ACL support exists. OS journal locks release after process death. Signed,
identity-bound revisions are appended and synchronized before transmission.
Corruption, rollback, duplicate records, concurrent writers or configuration
mismatch fail closed. Same-UID attacks, hostile filesystem stalls and rollback
of all authorities are not claimed solved by the journal.

A heartbeat never extends a local grant. Recovery snapshots independently
refresh every 16s under the connection lease ceiling and cannot contain grants,
scopes, conversation ownership or drain acknowledgements from the server.
This client cannot execute files, shell commands or sign arbitrary peer bytes.
Actual locally approved execution is a later provider/admission integration.

## Tests actually executed locally

- Final full Rust rerun: **223 passed**, zero failures/ignored; all prior 194,
  26 new pure client/journal/classification tests and 3 new lifecycle tests
  are included, not added again. Lifecycle coverage includes stale controller
  shutdown, owner retention and actual pre-authentication WebSocket shutdown.
- 25 actual independent gateway/Agent/WSS/PostgreSQL process cases passed.
  Test CA and leaf are distinct; untrusted CA, wrong name, expired leaf and
  HTTP redirect fail before proof. The suite also observes independent snapshot
  refresh, crash lock release, restart/new boot, revocation, old default route
  isolation, failed bind/selection, resource ownership and log redaction.
- Existing standalone process/HTTP suite: 30 passed; no Agent required.
- Existing protocol lab 32, UI source contracts 8, fault-proxy 8 and deployment
  renderer 13 passed. These are different scopes, not installed-host tests.
- Scheduler 25 Python/Git tests and metadata script 18 actual-script mock tests
  passed. Metadata mocks never use a token or real network and are not receipts
  that the real workflow has posted an issue comment.
- Formatting, all-target Clippy, Python syntax and workflow YAML checks pass.

## Retained failures and fixes

1. First full WSS client failed with MissingConnectionUpgradeHeader. Hyper with
   keep_alive(false) overwrote the Upgrade connection header. Opt-in control
   connections now enable keep-alive and with_upgrades while retaining the 10s
   HTTP lifetime, 5s header timeout and independent WebSocket limits; the old
   identity-only default remains unchanged. Real process regression crosses the
   old 10s boundary and observes the channel still working.
2. Certificate errors from tokio-rustls surfaced as io::InvalidData and were
   incorrectly classified retryable. The actual untrusted-CA timeout and a
   failure-first unit case reproduced this. Invalid TLS data is now terminal,
   verified with actual trusted/untrusted/wrong-name/expired-certificate cases.
3. A failed or idempotent select-device used to activate projection first and
   fence a live connection. The failing process case is retained. Selection
   now locks the registered device and projection in a bounded transaction,
   inserts only an absent row, never replaces a different device, and preserves
   an existing boot. The process regression passes.
4. Issue metadata validation initially ran during the mutation loop. A test
   demonstrated a first write before a later malformed packet was rejected.
   The entire packet batch is now validated before issue mutations; the
   failure-first actual-script mock test passes. API mutations themselves are
   not a cross-issue transaction; idempotent markers support retry recovery.
5. Initial Rust Read/Write by_ref ambiguity and Clippy constant chunk advice
   were corrected. Expired-cert fixture initially used unsupported negative
   x509 days; an explicit past validity interval via openssl ca replaced it.
6. Container tooling initially mixed an older libc library directory with the
   current loader. It was removed; PostgreSQL received only the missing ICU74
   libraries and its own share path. This changed the development container
   only, never the user's host or repository runtime dependencies.

## Delivery automation

`tools/delivery` is a typed dependency/resource scheduler with exact Git/file
fingerprints. Source changes invalidate evidence and propagate through
prerequisites; independent CI run references still require verification. It
emits at most three packets by default, not imaginary coding-worker receipts.
`cloud-delivery.yml` computes/tests with read-only permissions; the isolated
metadata job has no checkout/cache/artifact execution, checks the current
feature head, validates bounded fields, and deduplicates issue queue markers.
Only trusted feature pushes can write issue metadata. It cannot publish a
release, execute an issue body, waive deferred Host gates or close unverified
issues. Closed issues are not treated as code implementation evidence.

The manifest is a component dependency view of the existing roadmap, not a
claim that all 36 tasks or their broader parent issues are complete. Current
in-progress #47/#48 deliberately do not yet unblock #49 in the checked-in
source-stage manifest. After exact-source CI passes, publish a separate
verification-state update and the workflow can queue the next ready task.

## Impact / rollback / remaining gates

Fresh graph review was performed before edits. The existing service entry
returned HIGH with known unrelated axum::serve links; this was reported before
editing and supplemented by manual callsite review. Before commit a freshly rebuilt graph returned **CRITICAL** (57 inferred
impacts/37 direct) for multiple distinct new Rust targets. This was reported
before publication and is retained, not relabeled LOW. Manual review found
`serve_managed` is crate-private with exactly two callers, both inside the new
cloud crate. That crate declares its own Cargo workspace; existing Tauri and
root frontend have no dependency on it. Several graph-inferred old desktop
callers therefore cannot call this private function. New graph nodes lacked
exact UIDs, and the same aggregate was returned for unrelated targets. The
structural source evidence resolves that particular cross-crate blast-radius
claim, but does not remove the security sensitivity of this HTTP entrypoint.
Actual shared HTTP/Upgrade/cleanup paths were reviewed and tested explicitly.
Rust symbol resolution and unavailable FTS remain recorded limitations. New client/selection/delivery code is
isolated; existing desktop/rules/root dependency objects remain unchanged.
The lab workflow scope allowlist was expanded only for the explicit new delivery
paths. No blanket acceptance of arbitrary paths was added.

Remote Windows/Ubuntu and PostgreSQL/WSS evidence is pending at this source
commit; update the publication addendum after reading exact-source CI results.
There is no MCP business dispatch, local authority provider, request ledger or
local tool execution in this increment. #49 owns admission/no-replay next.
Physical-machine/VPS/ChatGPT gates stay deferred by user, not PASS. Source
rollback retains identity/projection data and revocation tombstones; stop the
opt-in control service before rollback and never delete migration history.
No main merge, production tag/release, installation, DNS, Nginx/WAF or VPS change.
