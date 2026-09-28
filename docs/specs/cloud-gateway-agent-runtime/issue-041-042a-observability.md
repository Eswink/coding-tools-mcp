# ISSUE-041/042A — Bounded Ingress and Redacted Observability

Status: **ENGINEERING_VERIFIED / AGGREGATE_ONLY / NO_EXTERNAL_TELEMETRY / HOST_DEFERRED**

Published source: `2934c5b534dd2d76e46dd700b96ce1a4eaf83a91`.

## Delivered

- shared in-memory gateway observer built only from fixed enums and integer counters;
- no arbitrary metric labels;
- HTTP accepted/rejected/rate-limited/status-class/timeout/body-limit/connection-capacity accounting;
- MCP request/tool-call/auth/permission/availability/workspace-offline/protocol-error counters;
- Agent ingress accounting limited to fixed transport categories;
- latency recorded only as aggregate bounded counters;
- graceful-stop aggregate snapshot only; no public metrics endpoint;
- live/ready/MCP/Agent response schemas remain unchanged;
- existing ingress limits remain unchanged.

The observer accepts no bearer token, refresh token, cookie, session, conversation binding, path, command, tool arguments, request body, source text, patch, key, signature or raw output as labels or stored payload.

## Verification

- One-shot exact-source run `35750849022`: Windows 2025 + Ubuntu 24.04 + actual PostgreSQL PASS.
- Permanent feature runs at `2934c5b534dd2d76e46dd700b96ce1a4eaf83a91`:
  - MCP business `35751729527` PASS;
  - identity `35751729626` PASS;
  - standalone service `35751729664` PASS;
  - authenticated Agent channel `35751729519` PASS;
  - outbound Agent client `35751729846` PASS;
  - request admission `35751729667` PASS;
  - grant projection `35751729512` PASS;
  - protocol laboratory `35751729515` PASS;
  - local Tool Runtime `35751729908` PASS;
  - release-candidate, secure-storage and fixed-entry regressions PASS.

One-shot artifacts:
- Ubuntu `10705156613`, SHA-256 `5252b7a6e122dc0cc38045ad5c05949a245864f94ae7b7a8c0edd35eb7ae3861`;
- Windows `10705022446`, SHA-256 `5f7fedaddeb45ca00bd47010f9582638b1a040afa61467659dfd5e497f6686d7`;
- PostgreSQL `10704547569`, SHA-256 `1438eadec3ec8a8c93cdf9b1cf6bb394165480f928c770aebcd2090c9bfefd07`.

## Retained iteration evidence

The development branch contains explicit fixes separating MCP outcome counters from transport ingress and explicit body-limit/timeout classification. The published feature source is the rustfmt/Clippy/PostgreSQL-verified exact source produced from that branch; development-branch formatting differences are not merged.

## Boundary

No persistent telemetry DB, external collector, analytics SDK, IP retention, per-user/per-chat labels, or public metrics endpoint was added. Physical VPS/workstation and real ChatGPT validation remain deferred and are not PASS.
