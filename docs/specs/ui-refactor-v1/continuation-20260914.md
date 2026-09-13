# UI refactor continuation — saved drafts and installed review

Status: IN PROGRESS; native candidate and user visual approval are outstanding.
Recovered source: 29b11a69767b89d5f10ff9d563e16328ee4a177c, tree bd44d99d5cb70b0d17ac45bdc7d66be68e66f02b. PR #15 is the only UI implementation PR. Main and v0.4.0 remain unchanged; do not merge independent PR #11.
Latest user direction: “继续循环迭代！直到任务完成”. This continues the approved plan, including its user visual review before merge/publication.

## Restoration and tool boundary

Downloaded source/UI/toolchain artifacts from run34777227213. SHA256s were checked and all source archive entries rebuilt into the exact Git tree. Read current AGENTS/Probe4.0.1, project context and graph guidance. Project resume launcher was missing; pinned installation timed out, offline resume/query/impact returned ENOTCACHED. Manual call-chain and diff review is the explicit fallback, not a successful graph or managed-plan check. Container Rust/native execution remains unavailable; exact-source CI provides those observations.

## Follow-up A — form-owned navigation state

The broad edited flag never became clean after successful child saves. Replace it with read-only boolean state exposed by the mounted port, tunnel, credential, policy and task-budget forms. No draft/credential values leave a form through this API. Parent mutation fencing remains separate. Unsaved changes still need a single local confirmation; disposal, changed draft generation or a newly busy operation rejects a stale confirmation. Hidden/unmounted panel states are not inspected.

During review the port component's inherited busy flag was found to include the leave dialog itself: reading it as a child operation would reject every accepted confirmation. Restrict its adapter to the owned port save; the parent guard separately checks real parent mutations. Keep disabled controls during confirmation. Added production adapter/function regressions and actual-built-route save/revert scenarios; core save/revoke/approve/credential handlers are unchanged.

Local frontend178 tests, zero failure/skip; Svelte/type zero errors/warnings and production build succeeded with the complete candidate. The new route scenarios still require CI. Invalid/blank numeric drafts remain dirty. Do not claim a generic cross-form save/draft reconciliation redesign; this change addresses navigation admission only.

## Follow-up B — installed UI review matrix

Add an allowlisted `ui-refactor` native scenario. It composes additional real-page review with, rather than replaces, all twelve existing exclusive/OAuth stages. Windows keeps the standard-user source-hash/logon/Job Object/cleanup gates; Ubuntu keeps isolated graphical session, encrypted storage and enabled sandbox. No mock transport, no synthetic clicks, no public grant endpoint.

Per installed combination: five actual pages, two themes and requested1280x800/960x640 native window sizes; save twenty PNGs, actual viewport dimensions, source-linked evidence, digest and zero measured horizontal container overflow. Then the unchanged twelve stages execute. A separate strict gate rejects old-only evidence, missing/duplicate screenshots, bad geometry, digests, mock transport and public-approval claims.

New workflow only builds review candidates with contents:read; it contains no publish job. Version moves to0.5.0 in the five standard files/six fields before any new installer. Exact-version verification guide is required: local release-readiness initially rejected its absence, then the guide was added. This is not a declaration that0.5.0 is released. Native contracts currently10 new +19 existing passed; native execution is pending.

## Next

Commit exact source to existing feature branch and run source/browser and new installed workflows. Read each failure and repair the smallest proven defect without lowering gates. Recompute artifacts and present same-source final gallery plus review installers. Preserve the explicit user visual signoff gate before merge or release. Continue recording follow-up failures/results here; never copy old-source PASS counts onto a new revision.

## Follow-up C — real saved-form browser failure and fixture wire contract

Source run34780311595 at22f6ed4 created40 screens with no measured horizontal container overflow and completed six prior interactions, but FAILED waiting for the saved Client ID. Preserve candidate artifact10324966839 SHA256cc3dc68aa618cff075b849259ca6f90ed0421e0cd5d1d60fc1e87d52ce808161. This is not a fully passing source candidate.

The synthetic invoke implementation structured-cloned raw arguments. Svelte nested reactive proxies cannot be structured-cloned; native Tauri's plain-object IPC uses JSON serialization (confirmed in tauri-v2.11.4/crates/tauri/scripts/process-ipc-message-fn.js). Thus the fixture threw before recording/persisting the actual form's update_workspace request. Two added contract tests fail against that fixture: nested-proxy save rejects, and cyclic arguments are wrongly accepted. Snapshot plain configuration arguments through JSON at the synthetic transport boundary; do not alter the product's AuthConfigForm save or native IPC logic. Both new tests plus the five original fixture contracts now pass. Complete local frontend180 passed, zero failed/skipped; type check0 errors/warnings. An accidental npm test invocation had no matching script; the repository's official node scripts/前端完整回归v4.mjs command produced the180 count.

Installed-workflow triggers now include UI browser/fixture contract changes so a final evidence revision can rebuild/verify the exact same source, not silently reuse previous-revision packages. No dependency, security check or user visual gate is relaxed. Pinned offline impact for the fixture again returned ENOTCACHED; manual scope is synthetic transport/test only. Browser and installed reruns must use a new documented candidate rather than retrying the failed SHA.


## D — Native Windows revoke readiness, exact failure retained

Source `d13385e` fixed the synthetic IPC boundary: actual built-route scenarios (including save/revert), 40 matrix screenshots plus eight state screenshots, Windows432/Ubuntu417 Rust and180 frontend tests per platform passed. Native run34780971822 nevertheless FAILED on Windows after20 UI captures and seven security stages. The local revoke readback remained active for30s. Artifact10325083219 SHA256b26917f30d3ef8461ec2edfe5964389d1547196eab026d1dd897f7fdcf56993e was downloaded/verified. Four Ubuntu combinations passed but cannot waive Windows. Earlier22f6ed4 native success is not substituted for this run.

The fixture navigated using headings only, then clicked a button existing before its async initial snapshot loaded. Production correctly disables that button while snapshot is null. W3C click delivery is not proof a disabled button handler ran. The failing artifact did not record pre-click enabled state, so this precise timing is a supported hypothesis, not a uniquely proved incident trace. A definite test contract defect was reproduced: four of six deterministic command-boundary cases fail on old code, including a click sent while permanently disabled.

The correction is test-only and narrow: revoke observes the original target's W3C GET /enabled until exact boolean true (bounded existing30s wait), sends ONE native click, then retains the existing authoritative completion readback. Disabled controls are never made enabled by script. Click errors are not swallowed or retried; still-active state fails; draining is never counted as free. Six new contracts plus the existing completion/draining assertions protect this. No product Svelte/Rust function, permission, timer, child deadline, native identity, or sandbox setting changes. Manual impact is confined to this installed fixture and tests; pinned offline GitNexus remains unavailable as recorded. All exact-source and five installed gates must run on the new candidate.

Protocol reference: https://www.w3.org/TR/webdriver/#is-element-enabled (read-only command); native click alone does not assert application state transition.
