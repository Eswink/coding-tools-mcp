# ISSUE-015A — Real-Channel Offline Authorization Suppression

Status: **ENGINEERING_VERIFIED / VERIFICATION_ONLY / NO_PRODUCT_CODE_CHANGE / HOST_DEFERRED**

Published regression source: `c6f746533d9fb4c81cf5c2d5f1b2c55acc3b3fc4`.

## Result

The production cloud MCP adapter already satisfied the intended offline authorization-noise invariant. This issue added failure-first PostgreSQL/channel coverage and found no product-code defect after formatting was corrected.

Verified behavior:

- a foreign/unapproved conversation asking for `request_chat_authorization` while the Agent channel is offline receives HTTP-success MCP `CHAT_AUTHORIZATION_UNAVAILABLE`;
- the response remains a permission error with `retryable=false` and `requires_local_action=false`, without `WWW-Authenticate`;
- the foreign response does not disclose offline/paused/workspace/owner/grant/request metadata;
- repeated suppressed requests do not mutate channel generation/session/sequence/lease state;
- suppressed requests do not allocate request-ledger rows or per-conversation projection rows;
- an already-approved owner remains locally authorized while execution is reported offline;
- invalid/missing OAuth remains a transport authentication failure and is not converted to workspace-offline;
- discovery/catalog remain independent from Agent presence.

No cloud pending-approval table, notification queue, server-to-Agent approval message, Tauri change, or remote approval path was introduced.

## Verification

- One-shot run `35735681618`: Windows 2025 portable, Ubuntu 24.04 portable and actual Ubuntu/PostgreSQL channel/projection/admission/MCP suites all PASS.
- First run `35735522049` failed before product tests at `cargo fmt --check`; retained as failure-first formatting evidence.
- Permanent feature run `35736626909`: Windows 2025 portable, Ubuntu 24.04 portable and actual PostgreSQL MCP/admission jobs PASS.

Artifacts:
- one-shot PostgreSQL `10697951040`, SHA-256 `2c2daf5be6b24c09d007d98a78edd29c89acb4ca4f921cd711db7e7f57a07c24`;
- one-shot Ubuntu `10697821129`, SHA-256 `58b7ff8bbd0eb920e0a143b8e1ef82f61790cb496ea84db4bcb4805f1214e487`;
- one-shot Windows `10697176909`, SHA-256 `0c913dc0817829577e6465fbef1fbee0208435f8ef5f58054a04e730dadc5088`;
- feature PostgreSQL `10697193030`, SHA-256 `0f09e424e96d87b3c40d37892b91edae82150096a9bef370cd7bb56982811f98`;
- feature Ubuntu `10698172149`, SHA-256 `131f1ea7c1b0d9becb9b9d4707180b22c9a993672a637d9110a0954f4d79040d`;
- feature Windows `10697318098`, SHA-256 `d97658545d2ad4ebb980083731ac594d89de934315c0301e7eb18c1ab0f91d90`.

Physical VPS/workstation and real ChatGPT UI behavior remain deferred and are not PASS.
