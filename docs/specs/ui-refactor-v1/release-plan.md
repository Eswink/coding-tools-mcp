# UI v0.5.0 release continuation

Status: IN PROGRESS; no new release is claimed by this document.
User instruction (verbatim): “继续任务执行，直到双端发布”. This explicitly authorizes completing the current UI implementation, merging after acceptance and publishing Windows/Ubuntu. It replaces the earlier planning-phase instruction to wait before publication; it is not a claim that the user personally inspected every final screenshot.

## Restored baseline and failures

- Sole UI implementation: PR #15, feat/ui-refactor-v1 @ acfa813b73b6f88065394546709854ea0e1c20eb, tree d89c4e81ad95489e012fc8f5f7a5e8f4161ac074. Independently reconstructed the complete source tree from artifact10325272117.
- Source run34781912679 succeeded. Native run34781912620 passed Windows and three Ubuntu combinations but FAILED Ubuntu22.04 AppImage; it is not a release candidate PASS.
- Failure artifact10324664914 SHA256 dd74190a3f3d600029dc309ad05fddf7888969250ef3e205064389b301094916: initial settings screenshot rejected as missing/invalid, after real local settings readback and before OAuth stages/UI matrix. Cleanup passed. The fallback screenshot is valid. Original raw screenshot size/header were not recorded, so the precise compositor/driver cause remains unproved.
- Preserve the earlier d13385e Windows failure and acfa813 native enabled-state fix. No retry of mutation clicks, extension of OAuth deadlines, disabled sandbox, fake PNG or promotion of previous-run packages.

## Bounded next rounds

1. Make presentation capture wait for fonts, visible nonzero viewport and two animation frames, with a bounded timeout and no approval/configuration mutation. Retain strict screenshot decoding, minimum-size and error rules. Add safe size/header/digest diagnostics and deterministic contracts. This fixes a missing render-readiness contract; it does not retroactively prove the historical invalid-image cause.
2. Review current production screenshots against the saved reference direction. Run complete source/browser and all five installed combinations at the exact changed SHA. Every new failure gets its own hypothesis, minimal correction and evidence; no rerun-until-green.
3. Add a UI-specific v0.5.0 publisher/workflow that composes existing strict source and native gates with 40 built-route screenshots, interaction/state checks and five sets of20 installed screenshots. Preserve the original v0.4.0 publisher's behavior and assets. Require same source/tree/version/run throughout; only the final publish job has contents:write.
4. Update PR #15 with exact evidence, review its actual diff/threads and merge with expected head. Do not create another UI PR or merge independent #11. No Rust business/authentication or dependency changes in this closure.
5. From the final main SHA rebuild/verify all packages and source in one explicit release/ui-v0.5.0 run. Draft-first prerelease; reject moved main, mismatched existing tags/assets and incomplete native evidence. Verify all public attachment bytes anonymously and cross-check downloaded evidence before reporting delivery.

## Tool and trust boundaries

Read AGENTS, Probe4.0.1 skill, project-context and GitNexus guidance. Native tool discovery found no corresponding integration. Missing project resume launcher returned127, pinned self-install timed out, offline resume/impact returnedENOTCACHED. Manual call-chain/diff review is the explicit fallback, not graph/managed-plan validation. This container has no Cargo; real Rust/installed GUI evidence must come from exact-source Actions. New release orchestration is HIGH impact for publication provenance; existing approval, credentials, process and sandbox contracts remain mandatory.

Real ChatGPT-account metadata/long-term refresh, OS toast visibility and all hardware/Wayland/FUSE variants remain separate unverified boundaries. The release is a pre-release. Keep v0.4.0 and every historical failure, and do not touch live Nginx or user secrets.

## Local preflight evidence

Seven deterministic capture-readiness contracts, eleven existing screenshot transport cases, twenty-five existing native contracts and ten UI evidence contracts passed. The old screenshot header/5000-byte cutoff remains unchanged; rejected PNGs are never retried. New diagnostics disclose byte count, signature boolean and digest only. Render readiness is observed before a single strict capture and is not a claim to reproduce the exact original compositor failure.

UI publisher's first contract run failed because its generic evidence loader requires an object while state-results.json is an array. Fixed a bounded duplicate-key/nonfinite-rejecting array read; all18 new UI publication contracts now pass, as do the17 unchanged v0.4.0 publication contracts. Checked the downloaded40-screen route evidence with the new inspection logic; source hashes match. Full local frontend180 passed, Svelte/type0 errors/warnings. Local production build exceeded the tool execution deadline while transforming; it is not a build PASS. The actual locked CI build is still required.
