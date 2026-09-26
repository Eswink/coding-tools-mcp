# Round 2 — durable identity primitives and deployment boundary

Status: LOCAL_VERIFIED / LIBRARY_INCREMENT / NOT_PUSHED. Parent: Epic #32, PR #36. Base: ba9c379f08da37f2a05bb96c377a95f432da969e.

## Bounded scope and evidence

M1 wire laboratory remains unchanged. Add an independent Rust library at services/cloud-gateway for the production identity boundary. It is not yet a public service: no owner login/consent UI, agent socket, MCP dispatch or local execution is exposed by this increment. OAuth code issuance and device invitation creation are trusted-operator library APIs only, never remote routes. Complete ISSUE-013/014/016 remains OPEN until their integration gates pass.

## Contracts before implementation

1. An explicit HTTPS PublicIdentity pins issuer, connector resource and path-prefix; no Host/Forwarded header can select them. Preserve the existing website and Nginx 443 listener. Use a separate /coding-tools/ prefix and loopback upstream.
2. Authorization codes are bound to preregistered client, exact redirect, resource, subject and S256 PKCE. They are single-use, short-lived and stored only as keyed digests. Owner consent must precede the trusted issuance API; callers cannot submit a subject through the token HTTP route.
3. Public clients use PKCE; confidential clients additionally prove their secret. Token values are random 256-bit opaque credentials, domain-separated in the database. No password grant, dynamic redirect registration or token passthrough.
4. Refresh uses a PostgreSQL family row lock. Concurrent use has one successful rotation; reuse revokes the family, including issued access tokens. Lost refresh responses require authentication recovery; no reusable grace token is silently added. Agent state is not a refresh prerequisite.
5. Expiry uses database time and absolute family limits; restart cannot renew them. Bind store initialization to issuer/resource and a key fingerprint so accidental config/key changes fail closed. Backup rollback protection remains a deployment gate, not claimed solved by persistence alone.
6. A device invitation is short-lived, one-use and route-bound. Redemption additionally proves possession of its Ed25519 private key. Verification occurs before consuming an invitation. Enrollment does not create a chat grant or allow file access.
7. Device signed grant verification binds device, connector, issuer, conversation, scopes, expiry and epoch. A cloud ticket cannot expand these values. This is a verification primitive, not an implemented cloud/local projection or device channel.
8. HTTP identity adapter has bounded form input, no duplicate fields, credential redaction, strict Host/Origin and no-store responses. Invalid credentials remain OAuth errors, not offline results. No payload logging.
9. Unit, actual PostgreSQL transaction/restart/concurrency tests and HTTP adapter tests are separate evidence. Ubuntu-container results are not Windows installed results. Future CI must run both; unavailable remote write/CI is recorded honestly.
10. Supplied CentOS Stream 8 host is out of updates (CentOS official end date 2024-05-31). Docker does not patch its host kernel. Production-ready status requires a maintained host/security resolution; no automatic OS, firewall, WAF or Nginx changes.

## Delivery and rollback

Issue files: issue-013-cloud-oauth.md, issue-014-local-grant.md, issue-016-device-enrollment.md. Existing issue numbering is preserved; no fictitious GitHub issue numbers are assigned when write tools are absent. Additive SQL schema is namespaced ctm_ and only applied to an explicitly chosen isolated database. Never point tests at production. Rollback removes this new library/deployment templates, without changing desktop credentials, grants or history.

## Gates that remain open

Trusted owner login and CSRF-safe consent flow; revocation/restore anti-rollback; abuse controls; authenticated outbound channel; distributed request journal; local approval projection; worker/TTY/sandbox; real VPS deployment; real ChatGPT reconnect acceptance. No indefinite tokens and no insecure public fallback.
