# Round 4 — Issue #42 standalone identity service

Date: 2026-09-21. Base `5ad89711e67eeb907d496a32a1b54a3f82500c55`.
Classification: **LOCAL_RUNNABLE_IDENTITY_VERIFIED / BROWSER_BLOCKED / PUBLICATION_PENDING**.
Issue #42 remains OPEN. This is not a production Gateway, Agent channel or ChatGPT validation.

## Implemented

An isolated `coding-tools-gateway` Rust binary now wraps the previously verified
identity/browser library. Explicit check-config/migrate/provision-owner/register-client/
rotate-owner/serve operations use strict configuration and bounded protected secret
inputs. Serve checks migration ledger, store identity, owner and client before a
loopback listener is opened. No automatic schema migration/provisioning, no HTTP
administrator, and no local workspace tool execution are added.

The HTTP/1 profile caps concurrent connections, headers, bodies, request rate,
connection lifetime, database waits and shutdown grace. Health distinguishes process
liveness from database/provisioning readiness. All HTTP routes, including health,
validate configured Host and optional serialized Origin. Unix secret files enforce
ownership/mode/link/type checks; Windows rejects secret-file mode until ACL verification
exists, while explicit pipe input is supported. See `services/cloud-gateway/SERVICE.md`.

## Actual tests (development container, not native Windows or CentOS)

| Gate | Result | Scope |
|---|---|---|
| Rust tests | 91 PASS, 0 failed/ignored | Existing 68 identity/DB/browser tests plus 23 new config/secret/CLI contracts |
| Separate-process HTTP | 30 PASS | Fresh private PostgreSQL, actual binary/TCP, provisioning, login/consent/PKCE, refresh after process restart, real DB stop/start, rate/cap/slow-header/graceful-stop |
| Existing protocol lab | 32 PASS | Node loopback synthetic protocol regression only |
| Existing UI source contracts | 8 PASS | Source contracts, not graphical desktop acceptance |
| Existing fault proxy | 8 PASS | Existing Python fault proxy tests |
| Deployment renderer | 13 PASS | Existing offline render contracts; no live Nginx or Docker changes |
| Rust formatting / all-target Clippy | PASS | No final warnings |
| Chromium browser gate | BLOCKED, exit 78 | Chromium 144.0.7559.96 starts, navigation rejected with ERR_BLOCKED_BY_ADMINISTRATOR; managed URLBlocklist contains `*` |
| Remote Windows/Ubuntu CI | NOT_EXECUTED | Workflow prepared; no remote write action in this session's connector catalog |
| VPS/BaoTa/WAF/ChatGPT | NOT_EXECUTED | No deployment or production credentials used |

The browser gate is not replaced by the passing HTTP client fixture. Chromium
policies were not changed and no alternative browser was used to evade them. Browser
redirect/CSP/cookie behavior beyond the blocked navigation remains unconfirmed.
The prepared CI workflow treats a blocked or failed browser gate as non-success.

## Failure-first review and fixes

1. The new generic health routes initially inherited only Host checking, unlike the
   identity routes which also checked Origin. Actual TCP regression returned HTTP 200
   for an alien Origin; the new test failed. Graph impact and manual wrapper review
   preceded the targeted shared-ingress check. The same 30-case process suite then
   passed. No OAuth or desktop transaction method was changed.
2. First patch application expected a differently formatted source fragment and
   stopped on an assertion; no fix was applied. The repeated failure is retained;
   the exact source was reread and the successful fix/build/test recorded separately.
3. Restored PostgreSQL binaries initially could not find their distribution shared
   data directory. The developer container's isolated public-tool installation paths
   were corrected; no user's server/service was touched. A fresh test cluster then
   initialized and all DB/process suites passed.
4. Real browser navigation is policy-blocked, not an application PASS or an OAuth
   failure. The safe test reporter records a fixed BLOCKED reason without dumping
   credential-bearing URLs or Playwright traces.

## Impact, scope and provenance

Pinned resume_plan 4.0.1 recovered the exported active checkpoint and continued its
implementation step. A fresh parent/child check_spec passed with 0 errors/0 warnings.
Graph impact was invoked before wrapper edits; initial repository name mismatch was
corrected. FTS unavailable and incomplete Rust caller coverage were explicitly noted:
zero graph callers is not evidence of zero source impact. Manual review covered the
identity_routes and trusted provisioning callsites. Existing targets were reused,
not rewritten. Automatically generated rule/index edits were restored, not committed.

Input tool/source archives matched their previously published SHA-256 values. The
local clone contains the exact remote base. New dependency declarations reuse pinned
versions already in the existing lockfile/cache; unrelated dependency versions are
unchanged. New source files remain below the repository's 500-line limit.

## Final staged review addendum

The staged graph review reported **HIGH**, with 146 touched graph nodes across 20
files and 12 affected processes. This was surfaced before committing. Manual review
found that the listed existing desktop health fixtures call `axum::serve`; they do
not call the new, separate-workspace `service::runtime::serve`. The graph name-resolution
collision does not establish a cross-crate dependency. All changed symbol paths are
inside the declared new service/spec scope; existing desktop Git objects are unchanged.
The HIGH aggregate result is retained, not relabeled as a reliable LOW-risk proof.

The first ARC-8 validation submission had four missing structured design fields and
failed. Recorded alternatives (isolated wrapper, desktop embedding, synthetic lab),
selection rationale, module boundaries and rollback evidence were then supplied from
the actual design; final bounded validate/drift checks have no gaps or drift findings.
These tools check supplied evidence structure and offer review guidance; they are not
an independent security audit and do not clear the blocked browser/production gates.
The review helper also listed eight unstaged generated-tool/cache files; the explicit
20-file staged publication set excludes them and contains no tool runtime or local env.

## Remaining gates and continuation

- Publish the exact local commit/tree and append the prepared progress comment to
  existing Issue #42. Re-read the current branch and issue before writing; never
  force-push, overwrite concurrent work, or claim a queued update is already online.
- Run the prepared native portable and process/browser CI jobs. Do not close #41/#42
  or mark Chromium acceptance passed based on HTTP tests.
- Complete #38 local authority projection and #39/017-021 authenticated outbound
  channel and durable reconciliation before any local tool dispatch.
- Host-loopback validation is not Docker bridge validation. The old Compose renderer
  remains a blueprint; container listener/image, actual Engine isolation, unsupported
  host OS, live TLS/WAF routing and restore remain #40 deployment gates.
- A path prefix is not same-origin browser isolation; dedicated-origin/shared-origin
  trust review remains mandatory before deployment.

No existing desktop source/installer/rules, root package/lock, main, DNS, Nginx/WAF,
VPS configuration or production secrets changed. Real Host remains
`UNCONFIRMED_ON_REAL_HOST`. No claim of reconnect-card elimination.
