# Issue register

Parent [#32](https://github.com/Eswink/coding-tools-mcp/issues/32). Legacy spec IDs ISSUE-010..045 are **36 tasks**; these are not GitHub issue numbers. Only #33/#34/#35 have been opened for this first batch. Remaining rows are planned work, not created GitHub issues. The repository accepted real issue creation on 2026-09-21; the old "Issues disabled" statement no longer describes this execution.

| Spec ID | Scope | Milestone | GitHub | Status | Dependencies |
|---|---|---|---|---|---|
| ISSUE-010 | Architecture and threat model | M1 | #33 | IN_PROGRESS | none |
| ISSUE-011 | Modern/legacy MCP contracts | M1 | #34 | IN_PROGRESS | 010 |
| ISSUE-012 | Cloud MCP gateway: lab then production | M1/M2 | #35 | IN_PROGRESS | 010,011; production:013-021 |
| ISSUE-013 | Cloud OAuth | M2 | - | PLANNED | 010,011 |
| ISSUE-014 | Cloud/local chat authorization projection | M2 | - | PLANNED | 010,013 |
| ISSUE-015 | Offline authorization suppression | M2 | - | PLANNED | 014,018 |
| ISSUE-016 | Device identity and enrollment | M2 | - | PLANNED | 010,013 |
| ISSUE-017 | Authenticated outbound transport | M2 | - | PLANNED | 016 |
| ISSUE-018 | Presence and generation fencing | M2 | - | PLANNED | 017 |
| ISSUE-019 | Multiplexing and bounded request admission | M2 | - | PLANNED | 017,018 |
| ISSUE-020 | Disconnect and uncertain outcome reconciliation | M2 | - | PLANNED | 019 |
| ISSUE-021 | Local execution ticket and grant verification | M2 | - | PLANNED | 014,016,019,020 |
| ISSUE-022 | Tool runtime abstraction | M4 | - | PLANNED | 021 |
| ISSUE-023 | Unified bounded execution runtime | M4 | - | PLANNED | 022 |
| ISSUE-024 | Windows ConPTY / Ubuntu PTY | M4 | - | PLANNED | 023 |
| ISSUE-025 | Exec policy and approval engine | M4 | - | PLANNED | 022 |
| ISSUE-026 | Ubuntu native sandbox | M4 | - | PLANNED | 025 |
| ISSUE-027 | Windows native sandbox | M4 | - | PLANNED | 025 |
| ISSUE-028 | Safe patch transactions | M4 | - | PLANNED | 022,025 |
| ISSUE-029 | Hierarchical project guidance | M4 | - | PLANNED | 022 |
| ISSUE-030 | Bounded local Skills | M4 | - | PLANNED | 029,025 |
| ISSUE-031 | Hooks under common policy | M4 | - | PLANNED | 025,026,027 |
| ISSUE-032 | Local trace and replayable state views | M4 | - | PLANNED | 023 |
| ISSUE-033 | Worktree management | M4 | - | PLANNED | 025,028 |
| ISSUE-034 | Snapshot and explicit rollback | M4 | - | PLANNED | 028,033 |
| ISSUE-035 | Structured verification evidence | M4 | - | PLANNED | 023,032 |
| ISSUE-036 | Tool discovery scaling evaluation | M4 | - | PLANNED | 022; real Host support |
| ISSUE-037 | Public-origin migration | M5 | - | PLANNED | 012-021,039 |
| ISSUE-038 | OAuth continuity migration | M5 | - | PLANNED | 013,014,037 |
| ISSUE-039 | VPS deployment and restore package | M3/M5 | - | PLANNED | 012-021,040,041,042 |
| ISSUE-040 | Secret/database protection | M2/M5 | - | PLANNED | 010,013 |
| ISSUE-041 | Rate limits and abuse bounds | M2/M5 | - | PLANNED | 012,019 |
| ISSUE-042 | Redacted observability | M2/M5 | - | PLANNED | 010,012 |
| ISSUE-043 | Windows installed acceptance | M5 | - | PLANNED | 022-035,037-042 |
| ISSUE-044 | Ubuntu installed acceptance | M5 | - | PLANNED | 022-035,037-042 |
| ISSUE-045 | Real ChatGPT reconnect acceptance | M3/M5 | - | UNCONFIRMED_ON_REAL_HOST | early:012-021,039-042; final:043,044 |

## Issue exit rule

OPEN -> DESIGN_REVIEW -> IMPLEMENTING -> ENGINEERING_VERIFIED -> HOST_VALIDATED (when relevant) -> DONE.

An issue spanning laboratory and production stays open after laboratory tests. Each PR must state exact commit, scope, tests, failures, remaining gates and rollback. Failed evidence is retained; CI retry alone is not diagnosis. A controlled one-time OAuth reconnect during origin migration is distinct from unwanted reconnect caused by routine local offline.
