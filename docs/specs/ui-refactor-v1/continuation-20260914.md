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
