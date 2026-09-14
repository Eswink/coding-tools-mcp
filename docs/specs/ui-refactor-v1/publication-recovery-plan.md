# UI v0.5.0 post-publication verification recovery

Status: IN PROGRESS. Continues the user's explicit instruction to complete the UI task through Windows/Ubuntu publication. This is read-only verification, not a new product release or a replacement UI implementation.

## Fixed identities

- Product/source/tag: `63261e0c9ae4b0c6befdbe5ae8caff7f5d32c076`; tree `01b11a1088d82501a1e579801ce6ac774ab5d43a`; merged PR #15.
- Original build/install/publish run: `34810770540`, attempt1. All sixteen non-publication jobs passed. Publication job `103873894785` failed AFTER the successful draft-to-public transition, at shared transport line189 GET `/git/ref/tags/v0.5.0`, HTTP404.
- The next live reads establish release `388174565` is public/prerelease with seven correct assets, and tag/main both equal the source. The 404 followed by successful resolution is consistent with a visibility delay; the service's internal cause is not proven. Do not claim the original run succeeded.
- Original delivery artifact `10334818036`, SHA256 `31c0a673cd4e1f8ecdb06bee67aad467febeb4582e351a0c2fe95ef6fb23db90`; original source artifact `10334108739`, SHA256 `475bf24e773bde010666c7fa2b0dcbeb875573f61cc710cd018f114e5caebda6`.

## Recovery and boundaries

1. Preserve the original failed run, public assets, release metadata and tag. Do not retry uploads/publication mutations, rebuild/install different source, move tags, or pretend a failed build passed. No product code, main, v0.4.0, Nginx or PR #11 changes.
2. Independently re-read and recompute source/native/route/UI/standard-user/package evidence from the original exact-source artifacts. Full local re-composition already passes every original gate and reproduces all seven delivered files byte-for-byte. This is evidence verification, not rerunning Rust or native GUI.
3. An isolated `verify/ui-v0.5.0` workflow with ONLY contents:read and actions:read checks out the exact product source separately from the verifier. Pin the original source/run/artifact IDs, digest/size and all seven asset digests. Check original run's exact jobs: all sixteen prerequisite jobs successful, solely the known publication job failed. A new source/native failure cannot be waived.
4. The recovery API refuses non-GET and uploads, independent of token permissions. Require already-public prerelease ID/tag/target/source and exact complete assets. Read tag/main/release branch before and after seven unauthenticated downloads using the existing download verifier. No TLS bypass, mutation retry or invented receipt. If any evidence/asset/identity differs, fail.
5. Save a separately named verification receipt identifying BOTH original build run and recovery run. Original overall conclusion remains failure. Complete delivery only after all seven public bytes, source and native evidence have independently verified. Add the receipt to PR #15 discussion; do not create a duplicate UI PR or overwrite published evidence.

## Impact and tests

Manual impact assessment: verification-only orchestration and new scripts on an isolated branch; existing source/protocol functions are imported unchanged at a fixed SHA. No production authorization or process symbol is edited. HIGH consequence for provenance if wrong, so hardcoded source/run/assets and read-only API are deliberate. Probe/GitNexus remain the previously recorded unavailable/offline channel; manual assessment is not graph validation.

Offline tests exercise write refusal, correct immutable identities, missing/draft/wrong-source releases, mismatched assets and any prerequisite job failure. Network-free unit tests are not public download proof. The new hosted run must provide actual anonymous download results.
