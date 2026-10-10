# Design: shared publisher staging budget
## 概述
M=981d7b23af1c5c8174352c4564aa65b1557cc546, tree=c3d7780ce761dac4da71d97a010381ec5074f69f.
M ordered parents are 7de3244adc367fa60463d1e3b64c92f211d2fda8 and d52937c98d441f3ee49eb9decd9101cade654748.
This adds a missing production connection; it does not produce authentic bundle or publication admission.
## 技术方案
### FR-1: Control flow
PublisherSession._prepare keeps _authenticate and _remote_constraint before staging, then supplies its existing _deadline and bound _check_active.
stage_selected and StagedAssets accept optional keyword-only deadline=None/check_active=None and retain those exact controls.
Receipt download and consumer._verify_bundle_bytes receive the same original values, including elapsed authentication/receipt time.
_verify_bundle_bytes forwards controls only to the existing download_artifact_zip; metadata reobservation, archive/checksum/cloud verification and inventories keep their current ordering.
Omitted controls preserve legacy defaults and fixture call compatibility; no new public activation argument is introduced.
Later operation fences continue using the existing per-operation budgets; an expired activation budget is not reused after a pause.
## FR-2: Failure precedence and ownership
StagedAssets retains a private sticky cleanup-failed flag. Set it on original transport_cleanup_uncertain or ExitStack.close failure before unwinding.
Preserve original transport_cleanup_uncertain if stage close also fails. Otherwise propagate the ordinary primary failure after reliable close.
Repeated stage close remains idempotent and never re-closes uncertain descriptors.
PublisherSession._dispose transfers the stage flag into its existing _cleanup_failed before detaching owners; stage/API close failures remain sticky.
_prepare prioritizes original transport uncertainty or failed disposal as adapter_error/none. Reliable cleanup permits exact ConsumerError transport_deadline_exceeded→timeout and transport_cancelled→cancelled.
Existing WireFailure mapping remains; other ConsumerError/exception codes map to adapter_error. No core code-enum expansion.
Every failed activation remains blocked_no_effect with transition None and zero mutations. A later successful close cannot clear cleanup uncertainty.
The six existing PrivateRoots, ExitStack, original plan/provenance bytes and opened asset handles stay the only owners.
Close retires handles; it does not promise file deletion. Do not delete files beneath an uncertain child.
## FR-3: Finite source admission
Exactly seven modified existing files are normalized to complete M bytes, with pinned mode/blob/SHA256 and unique exact fragments.
Only finite pinned historical passthrough pairs are admitted; invalid selected content terminates.
D has sole M parent; I has ordered parents[M,D] and tree(D); J has ordered parents[R,I] and exactly four pinned R documents over tree(I).
The new profile is independently bound by the complete reviewed tree and excludes its own source pin; all other scoped sources are pinned.
Dispatch precedes historical validation but cannot catch and suppress content errors. No ancestry-wide exemption, mutable candidate cache or test skip.
Two strict consumer inverse operands and eleven download-budget case reads receive exact reversible wrappers. Original IDs, assertions and complete historical bodies remain.
The seven inverses, finite prior pins and historical adapters must roundtrip exact bytes under independent review.
## FR-4: Verification
Add exactly12 StagingBudgetCases and12 composition cases. Reuse publisher_fixture, artifact_worker/artifact_route and HTTPSFixture; do not inherit an old TestCase.
Exercise both real worker launches, same deadline/callback identity, reduced FINAL allowance, cancellation/expiry between downloads, child reaping, owned descriptor retirement and sticky uncertainty.
Real cancellation/timeout tests preserve worker/IPC semantics. Explicit cleanup-failure injections prove failure precedence, not real OS cleanup uncertainty.
Existing authentic entry/direct sink negatives remain intact; fixture authorities prove mechanics only.
Keep every old1328 ID, strict303 and consumer452 inventory. Candidate total1352; actual I and local overlay J each1013; publisher workflow144→168.
Publish reviewed draft/start hosted CI alongside required independent local coverage after focused/source gates; all necessary gates must pass before integration.
Preserve source-specific failures, interrupted evidence and composed-vs-monolithic distinctions.
## 文件结构
Three existing runtime modules carry controls; the existing download-budget dispatcher and case operands delegate to one finite staging profile. Tasks lists all13 exact paths.
## Security and limits
Core, policy, eligibility, admission, downloader worker/transport, PrivateRoot, source/tag fences, credentials and workflow permissions/events remain unchanged.
Source-helper subprocesses, metadata calls, archive parsing, copies and hashes are not all interruptible by this increment.
Global eligibility, genuine FINAL/native/security, Windows/snapshot, held PR98 operations and final publication safeguards remain blocked.
No main/tag/release mutations or test seam becomes caller-supplied authority.
