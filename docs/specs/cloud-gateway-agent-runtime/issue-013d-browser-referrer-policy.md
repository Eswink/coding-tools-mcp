# ISSUE-013D — Strict Origin and browser form Referrer-Policy

Tracking: GitHub #45, parent #42/#41. Status: IMPLEMENTED; CI_BROWSER_VERIFICATION_PENDING.
Date: 2026-09-21. Physical workstation/live VPS/real ChatGPT tests remain DEFERRED.

## Failure and diagnosis

Automated service run 35619527365 passed all 30 standalone process/HTTP cases but failed Chromium. Diagnostics-only commit 8d2a621cd58943e1c2edb71e9c612b96a01e50ad preserved assertions and exit codes; run 35620780199 reported the allowlisted failure `browser_login`. No credential-bearing headers, exception text or callback URLs were exported.

The form HTML and outer identity middleware both forced `Referrer-Policy: no-referrer`. Under [WHATWG Fetch, append-Origin](https://fetch.spec.whatwg.org/#append-a-request-origin-header), a non-CORS POST under this policy uses `Origin: null`. This conflicts with the intentionally strict non-null same-origin login/consent checks. The pre-fix CI artifact proves login failure, not a captured null header; the cause is supported by the normative algorithm and source, with explicit post-fix header comparisons in the browser test.

## Bounded change

Only trusted login/consent HTML pages use `strict-origin`: real same-origin form Origin, origin-only Referer without path/query. The outer middleware preserves that explicit response policy. Redirects, errors and API responses retain `no-referrer`. Request Origin checks, CSRF, cookies, local authority and callback allowlists are unchanged. The browser test privately compares form Origin and origin-only Referer and requires a referrer-free cross-origin callback; only fixed case names are output.

## Evidence before publication

- Fresh GitNexus: page LOW (two callers), identity boundary LOW (router registration checked manually), existing header/browser test entry LOW. Rust graph coverage is not a substitute for manual callsite review.
- Three new HTTP tests run before production edits: form-page policy FAIL, two negative/default-policy tests PASS.
- After fix: new three tests PASS; all 13 prior browser HTTP tests PASS; full 142 Rust tests PASS, 0 failed/ignored; fmt and all-target Clippy PASS.
- Actual disposable binary/process/HTTP suite: 30 PASS, no Agent.
- Eight diagnostics redaction/exit-code tests PASS. No physical-host or production system was contacted.
- Automated CI Chromium outcome is pending at this source commit; do not call #42/#45 or reconnect acceptance complete yet.

Rollback is limited to these policy/test changes. Do not loosen null/missing/foreign Origin rejection to repair UX. Existing desktop/runtime, credentials, DNS/Nginx/WAF, main and releases are untouched.
