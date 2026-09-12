# Iteration 15: fail closed on incomplete release inputs

Base: `e629875b80f1a944f69ca5fc39ff50f67538d0a9`, tree `aa725ead78be1af3b9d690e1e6d62429cbf1f7ec`.

## Demonstrated defects

The publisher looked for a version-specific installation guide only at the final compose stage, but the newly prepared 0.3.2 version had no guide. Separately, frontend baseline validation accepted any report containing `# fail 0` without requiring actual test results, a nonzero count, completion, or zero skipped/cancelled tests. This could promote incomplete evidence to a release gate.

Twelve characterization tests failed or errored before the repair, including real acceptance of a lone zero-failure line, zero tests, missing summaries and skipped/cancelled reports. New-guide interface cases fail before implementation; they are not presented as pre-existing function failures.

## Repair and impact

Require a full Node TAP summary with unique counters, nonzero all-passed tests, zero failure/cancel/skip/todo, consistent actual result lines, exact top-level plan and a completion duration. Preserve nested suites, and reject huge claimed plans without allocating their reported size. Publish the frontend test count in the release summary. Existing synthetic release fixtures now produce complete TAP reports; none of their assertions are removed.

Select the exact version's English-named `verification-v<version>.md`, with compatibility only for that same version's historical filename. Never fall back to an older version. Reject invalid versions, symlinked or empty guides. Add a 0.3.2 installation/verification guide which explicitly does not claim a package or release already exists. Run this preflight plus its regression tests before native/package builds and before the final release workflow starts its matrix.

Manual impact: publisher baseline -> compose -> publication gate; versioned guide -> release notes and evidence ZIP; both read-only workflow preparation jobs. Risk HIGH for release evidence interpretation. No application code, native assertions, permission scope, tag mutation, main-source guard or Windows waiver is changed. MCP/GitNexus remain unavailable as documented earlier; no graph-tool success is claimed.

## Verification and self-review

After repair: **13/13** release-readiness tests, **19/19** existing release-gate tests, **99/99** authorization helper tests, **5/5** native-entry tests and **124/124** full frontend regressions pass. The actual current frontend TAP log is accepted with count 124. The preflight resolves six consistent 0.3.2 fields and its exact-version guide. Workflow YAML and diff checks pass.

At this iteration's local review the native run `34684664507` had entered real compilation; its subsequent failure and repair are recorded in iteration 16. Neither that old run nor these source checks approve this new tree. The exact new head must pass the strict native matrix before merge. Source-test success does not establish installer, real-user or public-release acceptance.

Scoped self-review: **94/100**, candidate only. The stricter evidence parser is intentionally fail-closed; unsupported future TAP format changes require an explicit regression-backed update.
