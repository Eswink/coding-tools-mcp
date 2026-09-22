# ISSUE-058: exact migration-workflow scope guard

## Scope and source

Base: `08a4e57d8e9d3959a8f9805d0b750c468a442cd7` (tree
`dbb702473fd7f135b996cb0298e3dd77bd289391`). Continue #58/#57 on Draft PR #36.
Recovered the CI Git bundle from artifact 10709115489; its ZIP SHA-256 is
`4cc459f7f26455bbac10c61411f78e2e84bef9443d73c8db96428581d901986a`.

The only existing-source edit adds `.github/workflows/origin-migration.yml`
to `allowed_exact`. It does not widen any prefix or alter a production function,
dependency, credential, desktop authorization, execution gate or release rule.

## Failure-first and automated tests

The new test executes the actual inline Python guard extracted from the workflow,
with temporary files and an explicit Git-output fixture. No duplicate production
allowlist is implemented in the test. On the unchanged workflow, 14/16 cases pass
and 2 fail: migration inclusion and its subsequent deletion guard. After the
one-line fix all 16 pass. Existing unknown-workflow, suffix-lookalike, desktop,
rules, deletion, mixed-path, source-length and SHA-256 evidence boundaries remain.

Local Linux / Node 22.16.0 / Python 3.13: 48 protocol/scope tests, 23 deployment
planner/renderer tests, 25 scheduler tests and 18 metadata tests pass. These local
results are not Windows, PostgreSQL, installed-host or real ChatGPT evidence.
Native Windows/Ubuntu CI must be checked on the published candidate before closing.

## Impact and limitations

Manual diff review: one existing inline configuration set, plus a new test file
and this record. No existing function/class/method is changed. The inherited
whole-branch graph reports CRITICAL / 44 flows; it is not a fresh narrow-change
risk assessment and is not waived. The local pinned probe launcher is absent;
`resume_plan` cannot run. Pinned offline probe installation and GitNexus
`detect-changes` were attempted but unavailable from the package cache. Do not
claim those gates passed. The existing CI graph/spec job remains enabled and
must provide the fresh candidate result; no check or permission was disabled.

## Rollback and release boundary

Revert these three additive/configuration files to undo this increment. No DB,
OAuth, device, routing, production site or runtime state is touched. Reverting
only the allowlist line reintroduces the known CI failure. This work does not
satisfy the supported-host, installed Windows/Ubuntu, security-review, package
or real-ChatGPT release gates. No main merge or release is authorized by test green.
