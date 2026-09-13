# Windows drain regression and release closure

Status: implementation in progress; no v0.4.0 publication claimed.
Recovered main: 1c0395da4225a68a588fd60e081c506580157f71.
Source tree: 6302a41112634302f22d3960d4af1b07702555ec.
User continuation: `继续任务`; existing explicit authorization includes finishing and publishing Windows/Ubuntu.

## Evidence and diagnosis

PR #12 is already merged. Do not reapply the old continuation patch. Failed release run 34759136823 stopped publication: Windows library tests report 346 passed / 1 failed at the real-child readiness assertion. All five installed combinations passed in that failed run, but none may be promoted into a later release. Downloaded failure artifact 10318890760 has SHA256 0b3d0950ad98e187e2a52dcf1968b55caaa41d5c4b227c2bff8daf5b07742783.

The test gives process startup eight seconds, starts a ten-second execution deadline, and then reuses the already-consumed startup deadline for draining. It checks only a marker's existence and omits the task status, exit reason, and stderr. The old log cannot distinguish slow scheduling/interpreter startup from a failed command. Do not assert an unobserved Windows root cause or change production execution limits on this evidence.

## Bounded continuation

1. Inspect the actual HTTP/task/lease call chain; retain the original failed log. Replace the ambiguous test oracle with independent finite startup (45s), drain (15s), and safety execution (120s) budgets. Require a child-written ready marker AND a live task, then successful natural child exit before successor admission. Inspect authoritative local task results after revocation; remote ownership gates stay intact. Add bounded cleanup and diagnostic stage timings without credentials.
2. Add deterministic negative checks (never started, early failure, late signal, premature free, timeout/cancel instead of natural exit) and a real nine-second delayed-start scenario. Run the same tests a fixed five times, stopping on the first failure, plus unfiltered complete Windows/Ubuntu regression. Never rerun an unchanged failure to obtain green.
3. Review exact diff and source identity; merge only after changed-source gates. Move the dedicated release branch forward without force. Rebuild and validate all five installed combinations in the SAME release run as source regression. Publish draft-first v0.4.0 pre-release only when every gate passes. Verify seven public assets by anonymous download, final tag/main, and retained receipt. Record any newly observed failure before a further change.

## Scope and tooling

Changes are test-only support, CI validation, and this evidence record; production authorization, refresh, executor, timeouts, dependencies and package version are unchanged. Manual upstream impact: the HTTP test entry calls real start_exec_task/exec_command, local read/cancel controls, ChatAuthorizer revoke/snapshot and remote successor authorization. The helper is reachable only from cfg(test). CI additionally records fixed-count evidence. No bypass of local approval or sandbox.

AGENTS.md, Probe 4.0.1 skill, project-context and GitNexus impact guidance were read. Native tools were not available in discovery; pinned resume installation timed out, offline resume and impact returned ENOTCACHED, and Git clone failed DNS. The source was obtained from a GitHub artifact and the complete tree recomputed. Continue with the existing written plan and manual call-chain/diff review as the declared fallback, NOT successful Probe/GitNexus execution.

Real ChatGPT account metadata/automatic refresh and visible OS notification banners remain explicit manual boundaries; synthetic installed tests do not establish them. Preserve PR #11, production Nginx, user secrets and all v0.3.2 tags/assets. No macOS.

## Initial local review

The patch has no production Rust/Svelte, dependency, or version changes. Existing Python release contracts 17/17, native evidence/navigation contracts 19/19, transport contracts 20/20 and six-field version preflight pass locally. The new Rust assertions and delayed child require real Windows/Ubuntu CI; no local Rust PASS is claimed because Cargo is unavailable here. Stage logs now separate readiness from release completion; early failure includes the bounded synthetic task snapshot/stderr. The fixed five-trial CI is in addition to, not a substitute for, the unfiltered suite.
