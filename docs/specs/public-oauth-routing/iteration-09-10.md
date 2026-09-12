# Iterations 9-10: confirmed BaoTa routing root cause

## Iteration 9 — inspect the supplied production vhost

The user supplied the complete `research-system.eswlnk.com` BaoTa Nginx server
block. The working general proxy is:

```nginx
location ^~ / {
    proxy_pass http://127.0.0.1:8080;
    ...
}
```

The same server also contains the panel-generated block:

```nginx
location /.well-known {
    allow all;
}
```

This resolves the previously bounded root-cause uncertainty. For each OAuth
metadata URI, `/.well-known` is a longer prefix than `/`; therefore Nginx
selects the `/.well-known` block rather than the general reverse proxy. With
`root /www/wwwroot/research-system.eswlnk.com`, a missing metadata file becomes
a Nginx HTML 404. `/mcp` and `/oauth/*` do not enter that longer prefix and
continue to reach `127.0.0.1:8080`.

That routing behavior exactly explains the independent public baseline:
`GET /mcp` reaches the application, unauthenticated `POST /mcp` returns the
application OAuth challenge, while all three metadata requests return the same
Nginx 404. This is a reverse-proxy path-selection defect, not evidence that the
Rust MCP listener lacks OAuth.

The supplied vhost also contains an extension include inside the server block:

```nginx
include /www/server/panel/vhost/nginx/extension/research-system.eswlnk.com/*.conf;
```

The preferred production change is therefore a separate English-named
`oauth-routing.conf` file in that directory, containing exact OAuth locations.
This avoids replacing the BaoTa-managed vhost and leaves the generic
`/.well-known`/ACME behavior intact.

## Iteration 10 — make the production config shape a regression contract

Added `scripts/nginx-panel-prefix-regression.sh`. It uses a real Nginx process
and a local fixture backend to prove, without external credentials:

1. the supplied plain `location /.well-known` shape leaves `/mcp` proxied but
   returns static 404 for all three OAuth discovery documents;
2. exact metadata locations restore proxying;
3. the existing ACME path still serves static content after the repair.

The branch CI now runs that failure-first contract on Ubuntu in addition to the
existing real Nginx + real Rust application PKCE/isolation suite. No retry loop
is used to turn a failed assertion green; the only bounded loops wait for local
process readiness.

Added `docs/deployment/nginx-research-system-oauth.conf.example`, pinned to the
actual working upstream `http://127.0.0.1:8080` and the supplied forwarded-header
shape. It also explicitly locks `/oauth/authorize` and `/oauth/token` so a later
panel-generated rule cannot split the OAuth control plane again.

## Remaining hard gate

Repository-side regression and diagnostics can now be validated independently,
but public readiness must stay failed until the production Nginx actually loads
the exact exceptions and an external probe verifies the three JSON metadata
endpoints. A successful `nginx -t` alone is not sufficient. Real ChatGPT account
OAuth remains a subsequent end-to-end validation and must not be replaced by CI
fixtures.
