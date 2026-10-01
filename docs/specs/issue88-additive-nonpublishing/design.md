# Design: authenticated FINAL artifact consumer

## 概述

This specification covers FR-1 through FR-6 for [Issue #88](https://github.com/Eswink/coding-tools-mcp/issues/88). The [full-scope RC ledger](../../releases/next-rc-ledger.md) tracks release eligibility and remaining cross-project gates.

The additive implementation was developed against commit `1281915b38c2364c4476ca94aabae3043423ed5f` (tree `a0e84eb7e7f237b64908058e5a5ee1f306752ca4`). Local code review and fixture/regression checks have passed. Exact-source hosted fixture CI, authenticated real storage/ZIP transport evidence, and a genuine eligible first-attempt FINAL DAG remain separate unestablished gates. The production storage-host allowlist is empty, so live artifact downloads fail closed. Local review does not establish release acceptance.

## Decision

Add a separate, read-only cross-run consumer. Authenticate an existing FINAL Actions artifact, validate its bounded data and producer identities, and emit an exact six-file prospective release asset plan: four required payloads and two newly generated sanitized evidence files. Both `release_approved` and `publish_approved` remain literal `false` everywhere.

Leave `release.yml`, `release_tag_gate.py`, `final_rc_evidence.py`, `release_dependency_contract.py`, `cloud_release_bundle.py`, their producer allowlists, and every stable publisher unchanged. Do not call a producer CLI under invented `GITHUB_*` variables. No tag, Release, upload to a Release, installer execution, production operation, version selection or credential provisioning is part of this increment.

The local implementation can be validated with fixtures before release blockers are solved. It does not make current canonical artifacts eligible: the exact canonical integration still fails Windows, source/gateway versions are not aligned to a newly selected RC, the final reviewed manifest/version decision remains pending, and a genuine full FINAL artifact is not established.

## Why a new boundary is necessary

1. `release_tag_gate.successful_run` already implements the right latest-all-status selection, bounded complete pagination, strict 13 FINAL / seven integration jobs and exact attempt checks. `bundle_metadata` deliberately permits a missing digest and returns `artifact_bytes_verified=false`.
2. `release_dependency_contract.verify_archive` intentionally requires `expected_producer == current_producer()` for release archives. `verify_noncloud_audits` likewise reads the current run attempt/workflow from the environment. `final_rc_evidence.main` derives the current run ID. A later workflow is not that producer.
3. Internal checksum files prove consistency only after the outer ZIP is authenticated. An attacker who changes a package can also change its internal checksum and receipt.
4. Some existing package inspectors execute an AppImage (`exclusive_packages.inspect_linux`), and `cloud_release_bundle.probe` executes binaries. Neither may be called by the consumer. Installed acceptance is authenticated producer evidence; the consumer must not pretend it reran native installation.

## Authority and runtime inputs

New `rc-artifact-consumer.yml`: `workflow_dispatch` only, with required `rc_version`, `release_tag`, `source_sha`, `final_run_id`, `final_run_attempt`, `integration_run_id`, `integration_run_attempt`, and `artifact_id`. These inputs are expectations to match, never trust roots. No `publish`, bypass, engineering, ignore, digest-override or force input.

The dispatched workflow itself must be on exactly `source_sha`; require actual `GITHUB_SHA == source_sha`, checkout that immutable SHA with full history and `persist-credentials: false`, and require its checked-out consumer workflow to be the expected path. Record actual consumer run/attempt/workflow separately from the producer. Never replace those environment values.

Require a clean checkout including untracked files, six RC version fields through `rc.verify_source`, gateway product/component alignment through `cloud.versions`, and the pre-existing reviewed manifest through `reviewed.verify`. Do not create a manifest or adjust versions. Require `release_tag == 'v' + rc_version`, an existing local lightweight tag at that source, and a live API tag object of type `commit` with that exact SHA. A missing, annotated or moved tag fails closed. This preserves the current operational restriction until real annotated push behavior is independently verified.

The first consumer supports FINAL producers only at **run_attempt1** (explicit input must be1 and the authenticated latest run must still be1), from authenticated `push` runs on `release/full-rc-candidate-*` branches. This intentionally excludes standalone cloud workflows and ambiguous workflow-dispatch producer refs. Supporting FINAL reruns requires independently authenticated intermediate artifact ZIPs and per-job attempt binding; it is not implemented in this increment. Supporting a FINAL dispatch producer later requires an independently authenticated workflow-ref derivation and separate review; do not infer a producer ref from bundle content. The consumer's own invocation is manual and does not share this restriction.

## 技术方案

## Trust chain and fail-closed sequence

### 1. Authenticate the selected source and latest full CI

Reuse unchanged `release_tag_gate.GitHub`, `paginate`, `successful_run`, `same_snapshot`, `latest_run`, `timestamp`, `live_tag` and the committed `FINAL_JOBS`/integration job constants. Do not use the weaker successful-only `final_rc_evidence.select_run` or its CLI.

- Fetch authenticated repository metadata and bind the numeric repository ID as well as exact repository name; head repository must be this repository
- Run `successful_run` independently for integration and FINAL at the exact source; require the selected positive IDs and attempts equal every explicit input
- Require every job's selected run/attempt/head SHA/completion/success, not a success subset; duplicates, skipped jobs, incomplete pagination, search-cap hits, newer pending/cancelled/failed runs all block
- Retain full attempt-specific job IDs and times; additionally validate `started_at <= completed_at` and that the bundle artifact's creation falls inside the selected FINAL bundle job's observed successful execution window
- Require producer FINAL event `push`, authenticated head branch with the candidate prefix, and derive its workflow ref as `Eswink/coding-tools-mcp/.github/workflows/final-rc-packages.yml@refs/heads/<head_branch>`
- Pin source tree through local Git; FINAL/integration run metadata provides commit identity, not an independently attested tree

### 2. Authenticate artifact metadata and downloaded bytes

Call `bundle_metadata` as a baseline, then strictly strengthen it in the new consumer without modifying the original:

- Exactly one `rc-structural-bundle` for the selected FINAL run; require it is exactly `artifact_id`
- Fetch `/actions/artifacts/{id}` independently and compare ID, name, workflow run/source/repository IDs, creation/expiry/update fields, size and digest to the run artifact listing
- Digest is mandatory: exactly lowercase `sha256:<64 hex>`; absent or malformed digest blocks. Require unexpired/nonempty metadata and selected bundle-job time window
- Never accept a local checksum, input hash, receipt, artifact name or download URL as the external digest authority
- Download only `/repos/Eswink/coding-tools-mcp/actions/artifacts/{id}/zip` on fixed `https://api.github.com`, using Actions-read token only on that origin
- Accept one authenticated API 302 with a reviewed HTTPS storage Location; create a fresh token-free request. No forwarded Authorization/cookies, user-info, non-443 port, IP literal, fragment, arbitrary host, or second redirect. Enable only a narrowly reviewed storage-host contract established by a harmless authenticated Actions artifact transport proof; the current exact-host allowlist is empty. Observation alone does not authorize a host or prove its downloaded byte/ZIP shape. Do not log the signed URL/query
- Bound network time and compressed byte count, require expected actual byte length and SHA256 equal API metadata before opening any archive parser. Stream into a newly created private nofollow file, hash while streaming, then fsync/close; a failed download has no success plan
- Re-read the artifact metadata and selected run after download; deletion, expiration, replacement ID, changed digest/size/attempt or status blocks

Official GitHub documentation exposes artifact `workflow_run`, digest and a temporary download redirect, but no artifact `run_attempt` field: https://docs.github.com/en/rest/actions/artifacts. The pinned upload-artifact v4 producer creates an immutable ZIP with a digest; the consumer must fail on a digest mismatch rather than accept a download action's warning: https://github.com/actions/upload-artifact/tree/ea165f8d65b6e75b540449e92b4886f43607fa02.

### 3. Attempt binding and its limit

**Security-review restriction:** Reject every FINAL run whose latest `run_attempt != 1` with `unsupported_rerun_provenance`; never fall back to an older successful FINAL run. The producer’s mutable `actions/download-artifact@v4` implementation selects the greatest artifact ID per name, not per attempt. A deleted current-attempt desktop artifact could expose retained prior-attempt bytes even when all current jobs succeeded; the producer desktop receipts cannot disambiguate this because they have no attempt field. Requiring first-attempt FINAL evidence excludes that retained-prior-attempt ambiguity without changing the producer. This scenario is a source-derived possibility, not an assertion that it occurred. The download action is a mutable tag, whereas upload-artifact is SHA-pinned; no existing producer action reference is changed here. Reviewed upstream sources: https://raw.githubusercontent.com/actions/download-artifact/v4/src/download-artifact.ts and https://raw.githubusercontent.com/actions/toolkit/main/packages/artifact/src/internal/find/list-artifacts.ts.

A later attempt-capable consumer would have to authenticate each required intermediate package/installed/source artifact ZIP by API digest, require its creation inside the matching current-attempt job window, and compare authenticated members to the FINAL evidence subtree. Metadata-only checks of those intermediate artifacts are not sufficient. Do not silently enable reruns after a fixture succeeds.

The consumer derives an explicit immutable trusted producer context from the authenticated selected FINAL API run, workflow and exact jobs, never from downloaded JSON:

`repository, repository_id, source_sha, source_tree, run_id, run_attempt, workflow_ref, workflow_id, bundle_job_id, bundle_job_started_at, bundle_job_completed_at, artifact_id, artifact_sha256, artifact_size`.

GitHub documents that reusable workflows inherit the caller GitHub context, and local `./.github/workflows/...` reuse is from the caller commit. Thus the current producer environment uses the FINAL caller workflow ref, not a ref inferred from the cloud receipt. Sources: https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations and https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows.

The cloud expected build producer is this context with the existing exact `provider=github-actions`, `job=build`, `runner_os=Linux` contract. Noncloud capture must identify the same source/tree/version/run/attempt/workflow and `job=contracts`. Producer artifacts/receipts that lack attempt fields are bound transitively through the authenticated first-attempt final ZIP and the full successful first-attempt DAG; internal cloud and noncloud attempts must agree explicitly.

Integration evidence can still have an explicit positive attempt greater than1, subject to the unchanged strict current-attempt seven-job inventory and recorded selected receipt IDs. The FINAL producer is first-attempt only.

This is an authenticated CI provenance observation, not a cryptographic job attestation. GitHub's artifact API does not independently assert job or attempt. Therefore require all of: FINAL attempt exactly1, exact all-job attempt inventory, artifact timestamp inside the selected bundle job window, matching nested build/capture attempts, and stable repeated reads. If the hosted API does not expose usable timestamps or full current-attempt job inventory, block with `attempt_binding_unproven`; never weaken the contract. A future signed attestation would be a separate capability, not invented here.

### 4. Bounded archive and data-only validation

Use Python standard ZIP/TAR/gzip parsers behind narrowly scoped preallocation and streamed-output guards; do not invent a general replacement archive format parser. Implement new bounded ZIP/TAR reader wrappers. Never call `extractall`, execute or import an extracted file, run a shell against archive paths, invoke installers, use `ldd` on payloads, or call existing helpers that execute payloads. Only the reviewed checked-out Python modules and fixed Git commands run. Extraction roots must be outside source, new, private and unreachable through symlinks; files are opened nofollow/exclusive and materialized nonexecutable.

Implemented outer archive limits (constants, no user override): outer ZIP 2 GiB compressed; central directory 8 MiB; <=4096 entries; <=4 GiB expanded total; <=512 MiB per regular file; <=1024-byte normalized path; JSON/checksum input <16,000,000 bytes; decompression ratio <=1000 plus absolute streamed output limits. Inspect bounded EOCD/ZIP64 metadata before letting the ZIP library load the central directory. ZIP64 support must remain inside these limits; don't allocate from untrusted lengths.

Reject absolute/drive/UNC paths, `.`/`..`/empty components, backslashes, NUL/control characters, alternate-stream colons, invalid Unicode, duplicate names including Unicode-normalized and case-fold collisions, file/dir collisions, symlink/special/link attributes, encrypted entries, unsupported compression, contradictory sizes, CRC errors, extra data hiding another archive, and over-limit expansion. Standard parser metadata types/lengths must be guarded before allocation, not only checked afterward. ZIP archive comments and unrecognized extra fields fail closed; real producer compatibility must be verified separately. Allow only root fixed public payload paths, `packaging-report.json`, `SHA256SUMS.txt`, and safe paths below `evidence/`. Evidence may contain diagnostics; it is never itself the public asset allowlist.

Parse `SHA256SUMS.txt` with an exact grammar, unique safe paths, lowercase 64-hex values and exact coverage of every regular file except that checksum file itself. Compare every computed digest. No comments, escaped filenames, extra file, omitted file, duplicate or checksum outside the extraction root is accepted. Parse JSON with duplicate-key and nonfinite-number rejection, including `parse_float` overflow (`1e999`) as well as NaN/Infinity constants. IDs/counts/sizes/schema fields must be exact integers, not booleans. Do not impose an integer-only rule on durations: the real installed-native `pending_elapsed_seconds` is a finite non-bool integer or float >=90 and may be90.5.

Cloud TAR member bytes are capped below 256 MiB, with total output bounded to four such members plus 2 MiB and 20 KiB framing allowance. Nested cloud TAR must have exactly the six existing `cloud.MEMBERS` entries: four fixed `bin/*` executables, `manifest.json`, and `README.md`. Use streaming gzip/TAR bounds, exact membership, duplicate rejection, regular-file-only checks, fixed expected archive modes, bounded total/member bytes, and no links, PAX/GNU path rewriting, sparse entries or trailing concatenated archive. Before `tarfile` processes a member body, a narrowly scoped standard-library `TarInfo` header guard must reject extension and sparse type flags; checking only yielded logical members is too late for PAX/GNU allocation/path rewriting. Bound individual parser read requests and cumulative decompressed output; reject unbounded `read()` requests. Drive the standard gzip/zlib parser through its complete trailer/EOF, rejecting a second gzip member or trailing non-padding TAR data rather than stopping after six files. Use a declared-huge-PAX fixture to prove rejection before extension-body allocation. Write data nonexecutable in a separate new nofollow root. Verify manifest source/tree/run/product/component versions/target/build OS/schema/approval flags and all four byte sizes/hashes; inspect ELF64 little-endian amd64 headers as data.

### 5. Recompute bundle contracts with explicit producer

Do not call `final_rc_evidence.bundle` as a consumer, because it eventually re-enters current-producer validators. New functions validate the same mandatory evidence against the trusted context:

- Root packaging report: exact source/tree/version/producer run, `passed=true`, both approval flags false, supported schema/scope/blocker semantics; retain existing release blockers verbatim. Never turn packaging success into security acceptance
- Contract `identity.json`: exact source/tree/version/run/passed; rehash and compare its complete `evidence_inventory` using unchanged `final.evidence_inventory`. Its digest is now authenticated transitively by the outer API ZIP digest, not falsely described as an independently fetched job output
- Cloud: exact archive copy at root equals nested `evidence/rc-cloud-linux-amd64/cloud-linux-amd64.tar.gz`; nested receipt/envelope/manifest must agree. Hash envelope/archive from authenticated bytes, then call unchanged `dependency.verify_build` with the explicit canonical producer and data-only extracted binaries. This retains all exact build/lock/stream/audit/advisory/source checks and the existing narrow producer allowlist; add the stricter FINAL-only producer check before it
- Noncloud: new `verify_consumed_noncloud_audits` mirrors the current capture binding and report/hash/command/advisory checks but takes the authenticated producer explicitly. Reuse unchanged `dependency.raw_audit` and `desktop_source_proof`; the latter is data-only with respect to artifacts but is not a pure function: it imports the reviewed checkout verifier and checks the real consumer environment and ancestor/CARGO_HOME config. Keep that real environment unchanged, fail on unexpected overrides, and never claim this re-proves the producer’s historical environment. Preserve desktop official-source/paired-audit evidence, unsound-warning rejection, all raw findings and warnings, exact locks, no filters, and `raw_zero_claim=false`. Add parity tests so every existing noncloud negative still fails the new entrypoint
- Keep cloud raw audit byte equality with the canonical contract copy; require strict integer zero for npm findings and no npm error. No new vulnerability waiver
- Integration receipts in contracts and cloud evidence must identify the selected newest integration run and source, not merely any old passed same-source run; require their recorded job ID/name set to match that selected run. This rejects a FINAL bundle built against an older integration proof when a newer run exists
- Linux manifest: exact `release-candidate`, Ubuntu22.04 build platform, exactly DEB/AppImage, exact generated names, amd64, package-record positive size/digest. DEB package version must equal `rc_packages.debian_version(version)` and AppImage package version equal the RC SemVer. Root and nested package copies must be byte-identical
- Linux installed receipts: exactly Ubuntu22/24 x DEB/AppImage, platform/source/tree/version/run/kind/package record/payload identity equality. For DEB native executable digest must equal payload SHA; for AppImage native executable digest must equal the outer AppImage SHA. Validate all four unchanged 12-stage `rc_native_gate.verify` contracts and explicit no-real-ChatGPT boundaries
- Windows: exact generated NSIS name, record/kind/source/tree/version/run/booleans, `payload_sha256 == native_executable_sha256`, retained payload verification JSON consistent with the package receipt, unchanged 12-stage native gate, and honest `signed`/external acceptance status. A passing receipt is not a new signing or Windows isolation claim
- Required payloads are exactly four families: NSIS, DEB, AppImage, four-binary cloud TAR. Missing one, an extra root executable, a version-renamed predecessor, mismatched receipt or altered package is fatal

The consumer rehashes exact installer bytes and verifies producer-installed payload assertions; it does not independently extract or rerun NSIS/AppImage. An altered payload inside an installer necessarily changes its authenticated outer hash. If all API provenance and the producer itself are malicious, this checker cannot establish independent reproducibility or replace the producer's trust. State that limit explicitly.

### 6. Final freshness fence and exact outputs

After bounded content validation, asset preparation, hashing, fsync and nonessential descriptor cleanup, and immediately before committing the success filename, redo both strict latest-source selections, selected run reads, full job inventories, final artifact listing/direct metadata, and live tag verification. Compare source/tree/version/reviewed manifest and actual checkout again. Require stable selected IDs/attempts/job records/artifact metadata. The new context adds immutable event/head-branch and timestamp comparisons beyond the old helper's fields.

Prepare sanitized `RC_PROVENANCE.json`, `SHA256SUMS_<version>.txt` and the four payload copies in a fresh private output directory before that final fence. Stage the internal plan under `rc-asset-plan.pending` in a separate receipt-only root. Only after the fence succeeds may the anchored terminal rename expose `rc-asset-plan.json`, subject to the failure boundary below. Checksum lists the four payloads and provenance, excluding itself; the plan then hashes all six final files. Publish candidates are exactly:

1. `MCP_<version>_x64-setup.exe`
2. `MCP_<version>_amd64.deb`
3. `MCP_<version>_amd64.AppImage`
4. `cloud-linux-amd64.tar.gz`
5. `RC_PROVENANCE.json`
6. `SHA256SUMS_<version>.txt`

The plan includes exact filename, media type, size, SHA256 and family for each; exact source/tree/version/tag object; authenticated API producer/integration run+attempt IDs and artifact ID+digest; separately labelled consumer run/attempt; verification timestamp; full installed platform matrix; raw-vs-active audit counts and warning summary; signing/real-host limitations; original blockers; `release_approved=false`, `publish_approved=false`, `scope=authenticated-final-artifact-validation-only` and `snapshot_atomic=false`.

Do not include raw logs, absolute runner paths, signed download URLs, source-root paths, screenshots, arbitrary metadata strings, credentials, the broad internal checksum file, every nested evidence file, or source code in prospective public assets. Use explicit field-by-field allowlisting, not removal by secret regex. No raw error/API body in the sanitized output. A failure emits bounded fixed-code diagnostics and fails the job; the success-only upload cannot run, and no publication authority is granted. After a terminal rename or cleanup failure, success-filename absence is claimed only after confirmed absence or exact-owned-file withdrawal. Failed withdrawal is reported as `uncertain_plan_outcome`; a plan may remain on disk and must not be treated as success. See the terminal-failure contract below.

A future publisher must rerun live validation and rehash exact staged bytes; this plan is not a transferable authorization, lease, or guarantee against a later tag/run change. Current API reads cannot be an atomic transaction. Publication, existing Release collision/no-clobber handling, draft/resume behavior and anonymous post-upload verification require a separate design and approval.

## 文件结构

## Exact implementation surface

All new files are at most 500 lines. The runtime modules have these responsibilities:

- `scripts/rc_consumer_snapshot.py`: immutable `TrustedProducer`, selected source/run/artifact authentication and repeated full snapshot fence
- `scripts/rc_consumer_io.py`: bounded data readers, private nofollow roots, exact-owned file operations and one-attempt descriptor disposal
- `scripts/rc_consumer_transport.py`: fixed-origin authenticated API download, reviewed token-free storage request, outer size/hash verification
- `scripts/rc_consumer_archive.py`: bounded ZIP/ZIP64 and cloud TAR inspection/extraction, checksum inventory validation
- `scripts/rc_consumer_noncloud.py` and `scripts/rc_consumer_contracts.py`: explicit trusted-producer audit, build, package and installed-native evidence validation
- `scripts/rc_consumer_finalize.py`: pending-plan identity capture, anchored commit and conditional exact-file withdrawal
- `scripts/rc_artifact_consumer.py`: orchestration, sanitized provenance, six-asset staging and fixed-code failure reporting; the CLI takes the ephemeral token only through environment and accepts no offline snapshot
- `scripts/rc_consumer_test_runner.py` and matching fixture/test modules: mandatory checksum-pinned source-data fixture, zero-skip aggregate tests, adversarial contracts and static workflow checks
- `.github/workflows/rc-artifact-consumer.yml`: manual read-only consumer
- `.github/workflows/rc-artifact-consumer-checks.yml`: path-filtered hermetic tests on Ubuntu 24.04 for pull requests and engineering branches; no `workflow_run` or `pull_request_target` trigger

Existing functions and producer contracts are unchanged. Any future change to those boundaries requires its own impact analysis, review and regression evidence.

Workflow token: explicit `permissions: {contents: read, actions: read}` only, no `id-token`, attestations, packages, deployments or contents write. Pin checkout, setup-python and artifact-upload actions to independently verified commits; no marketplace publishing action. Use a fresh Ubuntu24 hosted runner, fixed Python3.12, isolated temp directories, `PYTHONDONTWRITEBYTECODE=1`, no restored cache, no secrets besides ephemeral repository token. Network access happens only in the snapshot/download layer. Upload only sanitized consumer receipt/asset plan as Actions artifacts after success, not payloads or private diagnostics. Uploading an Actions artifact does not grant Release authority and needs no broad GitHub repository write token.

## Reused-helper execution and environment audit

- `release_tag_gate.GitHub.get`, `paginate`, `successful_run`, `same_snapshot`, `latest_run`, `timestamp`, `live_tag`: fixed-origin GETs and data checks only. `successful_run` calls `final.integration`, which is pure; none derives a current producer. `route`/`verify` are intentionally not used because their push-event contract is different
- `rc.verify_source` and `reviewed.verify`: parse committed source and use fixed read-only Git commands; no artifact execution and no current-run producer expectation. Add an explicit untracked-clean check because the RC helper checks tracked cleanliness only
- `cloud.versions`: source Cargo/TOML parsing only, no environment identity or payload execution
- `dependency.verify_build`: explicit producer canonicalization then `exact.verify`; reads source, fixed Git metadata, retained build/audit streams and explicit extracted binary hashes. `binary_dir` is mandatory to prevent using recorded producer absolute paths. Never call `exact.collect`, `execute` on artifact commands, or any caller CLI
- `dependency.raw_audit`: pure dictionary/lock invariant checks; no subprocess or environment use
- `dependency.desktop_source_proof`: imports only `root/scripts/verify_glib_backport.py` from clean authenticated source. Its source/metadata/audit verification is data-only, and the upstream crate digest is hardcoded and checked before TAR parsing. Its `verify_configuration(root, os.environ)` inspects the *actual consumer* CARGO_HOME, ancestor config and override environment. This is an extra fail-closed consumer-environment precondition, not authentication of producer configuration; do not spoof, clear or synthesize it
- `final.evidence_inventory`: bounded, newly extracted private tree hashing only; no environment producer expectation. It does not itself protect parent symlinks, so the secure reader wrapper's directory ownership/nofollow invariant remains necessary
- `rc_native_gate.verify`: pure receipt checks with explicit expected run/source/version/kind/hash; no installer launch or current environment identity
- `rc_packages.debian_version`: pure SemVer-to-Debian mapping only. Never call `rc_packages.identity/load_manifest/prepare/installed`, `exclusive_packages.inspect_linux`, cloud `identity/build/probe/main`, `final.main/bundle/dependency_contract`, or dependency `verify_archive/verify_noncloud_audits/current_producer` as consumer entrypoints

Tests should instrument all subprocess calls and imports during content validation: permit only fixed Git reads and the reviewed checkout verifier, never an executable/command/module selected by artifact content. Artifact paths never enter `sys.path` or working directory.

## Change-control and review requirements

Review must bind the exact source tree, workflow bytes and file hashes tested. Record upstream impact before modifying symbols and inspect the staged change graph for unexpected callers, workflows or producer edits. Review helper reuse against the explicit data-only and real-environment contracts above; unindexed callers are not proven safe by an empty graph result. Existing producer and stable-release paths remain unchanged.

## Required tests and evidence

Hermetic tests must never depend on real tokens, live artifacts or downloaded executable execution. Fake API/download transport is injected only into library functions; production CLI has no offline-trust shortcut. Assertions inspect request method/origin/headers, byte access order, final files and unchanged environment.

1. Positive synthetic FINAL+integration snapshot with exact inventories, frozen source/version/manifest/tag, current-attempt final bundle, all four payload families, five native installed cases, cloud exact-build and noncloud paired audits; both approval flags stay false
2. Wrong/missing source/tree/version/gateway/sixth field/reviewed manifest; dirty/untracked source; stable or malformed tag; missing/moved/annotated tag; wrong consumer source or workflow; never mutate/fetch-create a tag
3. Wrong repository numeric/name/head identity, workflow/event/ref, run/attempt/job ID/name/source/status; missing/skipped/duplicate or extra jobs; latest failed/pending/cancelled/incomplete run; changed attempt/run/job/list/tag on each fence
4. Pagination >bound, count mismatch, duplicate records, short page, 1000-search-cap uncertainty; mandatory newest selection must not consult only successes
5. Wrong artifact ID/run/source/attempt time window, FINAL attempt2 with otherwise perfect current receipts, deleted attempt2 desktop artifact exposing attempt1 input, expired/empty/missing/double artifact, absent/malformed/wrong API digest, mismatched direct metadata, truncated/oversize/wrong download size/hash, deletion during download
6. Signed redirect token never forwarded; insecure URL/arbitrary host/IP/port/userinfo/second redirect blocked; streaming timeout/error produces no success output or archive parse. Mock archive parser proves it is never called before outer digest success
7. ZIP/TAR duplicate/case/Unicode aliases, traversal, drives/UNC/ADS/control paths, file-dir collisions, symlink/device/link/sparse/PAX rewrites, encrypted/unsupported format, declared-huge PAX/GNU body rejected before allocation, oversized headers/count/entry/total/ratio, individual unbounded parser reads, CRC/gzip trailer failure, trailing/concatenated data; extraction root symlink/race/preexisting file; no source writes
8. Self-updated internal checksum after altered installer still fails against API digest; wrong checksum coverage/duplicates, package root vs nested mismatch, receipt or payload-hash mismatch, swapped old-version package, missing one family or missing any of the four cloud binaries, missing any platform/native receipt
9. Noncloud parity with every existing raw-audit negative; wrong cloud envelope/streams/lock/advisory/provenance/current attempt, engineering/standalone producer, incomplete sources/audits, active vulnerability, filtered audit, unsound warning, changed upstream proof, older integration receipt, npm bool-zero, float/nonfinite IDs/sizes, accepted finite90.5s native duration and rejected bool/NaN/Infinity/1e999 duration
10. No subprocess payload execution, import from extracted root, environment spoofing, producer-token reuse, implicit tag creation, release API writes or publication path. Snapshot remains API-authenticated even if receipt asserts a different run/attempt
11. Sanitization and exact six-file output: no arbitrary raw strings/paths/logs/extra files, truthful raw findings/warnings/security/signing/real-host boundaries, `publish_approved=false` and no publisher invocation on all successful paths
12. Old producer regression suites unchanged and green: release tag, RC version/source/reviewed manifest, cloud bundle, final evidence, dependency capture/contract, exact build audit, native/package contracts, and original stable version regression. Existing producer rejection of foreign current run/attempt/workflow must remain exactly tested

Run fixture suite locally, py_compile, diff/line-count/static workflow checks, independent code review, then exact-source hosted fixture CI. Separately perform a harmless read-only real artifact metadata/download proof to establish API digest/ZIP and redirect shape; it is transport evidence only. A genuine successful exact-source FINAL DAG must later confirm all13 actual job display names and attempt timestamp shape before accepting a real candidate. Tag creation belongs to a separate release procedure. Never fabricate such a run or call fixture/transport proof final acceptance.

## Independent security-review checklist

Independent review must challenge:

- First-attempt-only provenance, complete job windows and retained-artifact/rerun ambiguity where the API lacks an artifact attempt field
- Workflow-ref derivation from the restricted authenticated push producer and reusable-workflow caller context
- Outer API digest authentication versus transitive internal checksums, without an independent producer-signature claim
- Archive preallocation/decompression limits, extension records, nofollow ordering and private-root assumptions
- Every reused helper's execution and current-environment behavior
- Negative parity with original producer contracts, installed-payload semantics, exact six-asset sanitization and stable-path noninterference
- Token confinement, freshness races, terminal withdrawal and uncertain-plan reporting

Code review and fixture CI do not authorize publishing. A future publisher must satisfy separately reviewed authorization, live revalidation and post-upload integrity requirements.

## Terminal-failure contract

Asset preparation, hashing, fsync and nonessential descriptor disposal precede the final complete API/source/tag fence. The receipt root and pending file remain bound to identities recorded at exclusive creation. The terminal rename is anchored to the owned private directory.

Any rename or postcommit cleanup failure remains a job failure. One withdrawal attempt may touch only this invocation's exact `rc-asset-plan.json`, after all-parent nofollow reopening, original root/inode/owner/mode checks and bounded exact expected plan content verification. Successful unlink is followed by observed absence confirmation. An already absent target is reported as confirmed absence, not a deletion. A changed root/file/content, failed verification, unlink or descriptor disposal yields `uncertain_plan_outcome`, never claimed absence or success. There is no alternate path, broad cleanup, automatic replay or suppression of the original failure. Descriptor ownership is cleared before a potentially failing close and that descriptor is never retried.

Thus absence of a success filename after failure is conditional on confirmed absence/withdrawal, not a guarantee under arbitrary filesystem failure. Both approval flags remain false; failed steps cannot reach the success-only Actions upload. Future publication still requires new live validation. The private-root model assumes no concurrent writers sharing this invocation's UID; check-then-unlink does not claim atomic protection against such a writer.

The fixture workflow uses `runner.temp` only in supported step-level env contexts and is checked with actionlint, in addition to static tests. Fixed checksum-pinned GLib source data is mandatory in hosted fixture setup; zero skips are required.
