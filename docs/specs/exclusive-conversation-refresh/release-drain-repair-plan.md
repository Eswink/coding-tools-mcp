# Release drain-startup repair plan

Status: IN PROGRESS. This continues the approved plan and explicit Windows/Ubuntu publication authorization. No failed-run asset may be released.

## Recovered source and failure

- Reviewed/merged main: `1c0395da4225a68a588fd60e081c506580157f71`, tree `6302a41112634302f22d3960d4af1b07702555ec`, version 0.4.0.
- PR #12 is merged. Do not reapply the old ecf5ca9 continuation or overwrite main with a stale feature branch.
- Final release run `34759136823` failed its Windows Rust regression: 346 passed / 1 failed / 0 ignored, at `http_revoked_owner_drains_actual_background_process_before_successor`, `worker must really start`.
- All five installed-package jobs succeeded, but publish was correctly skipped. Those successes do not waive source regression.
- Downloaded source and failing Windows artifacts were SHA256-checked and the entire source Git tree was independently recomputed.

## Investigation and impact

The current HTTP test observes only a filesystem marker for eight seconds and shares that deadline with draining. It does not distinguish queued, running, failed, timed-out or interrupted tasks. Add bounded diagnostics without changing its original pass/fail criterion first.

Manual inspection also found that Windows `resume_primary_thread` accepts any non-error ResumeThread result from the first matching thread. Windows documents return 0 as a thread that was not suspended, not proof that the suspended primary thread ran. Capture actual return counts before assigning this as the reported failure's root cause. Preserve job assignment before resume and fail-closed child cleanup.

Impact: HTTP fixture changes are test-only. Any subsequent Windows process-tree change affects managed background command spawning, cancellation and shared-workspace draining; treat this as HIGH security-sensitive risk. No OAuth scopes, local approval, lease, timeout enforcement, credential storage, hidden-window flags or sandbox settings may be weakened.

AGENTS.md, Probe 4.0.1 skill, project-context documents, graph summary, GitNexus impact/guide/CLI skills, current code and release records were read. Native Probe/GitNexus discovery found no applicable tool. Pinned offline resume and impact commands returned ENOTCACHED; container DNS and Cargo are unavailable. Continue with explicitly declared manual call-chain/diff review and real GitHub Actions, not a graph-validation PASS.

## Bounded rounds

1. Diagnostic-only candidate: preserve eight-second readiness gate, record authoritative task result and actual Windows thread-resume counts. Run full Windows/Ubuntu source regression and a fixed diagnostic sample; retain all failures.
2. Apply the smallest evidence-supported correction. Add deterministic negative regressions for the identified defect, bounded readiness/terminal diagnostics and failure cleanup. Never replace an actual child with a mocked readiness marker or rerun until green.
3. Run exact-candidate full source, browser and publisher contracts. Exercise real child start, revoke/drain, successor exclusion, timeout and cancellation on both platforms. Review every changed symbol and file.
4. Open a focused fix PR, merge only after applicable candidate gates. Fast-forward the dedicated release branch to reviewed main without force.
5. Rebuild the same main SHA in one final release workflow; require all source gates and Windows NSIS plus Ubuntu22.04/24.04 DEB/AppImage twelve-stage installed gates. Publish v0.4.0 as pre-release only, retaining genuine ChatGPT-account and OS-toast limitations.
6. Anonymously download and digest-check all release attachments, verify tag/source/main/run provenance, update completion/PR records and provide both-platform packages.

Stop publication on any new failure; continue a specifically documented fix round instead of downgrading a gate. Preserve v0.3.2, PR #11, live Nginx and user credentials. No macOS or unrelated changes. New files use English names.
