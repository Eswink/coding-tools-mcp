# Design: cooperative FINAL archive budget
## 概述
Actual F=e90e15fa8b6d527006b6c62a75eb2fcab6629f0f, tree73bf80abd94a0ec8db241453c225b6bf62652b1b; prior provisional D=73e4fdb7ea077392a93105652374eba8bf0a605f.
F ordered parents[39a9ae7e2761f419db5cace712368e5671042b5e,D] and complete tree equality are verified in F-BINDING.json; D and F remain distinct identities.
## 技术方案
### FR-1: Original controls
_verify_bundle_bytes forwards its existing budget to extract_bounded_zip and extract_bounded_cloud_tar; other phase order stays fixed.
Only seven archive symbols change: _directory_guard, _local_records, _deflate_integrity, extract_bounded_zip, _GzipReader.__init__/read and extract_bounded_cloud_tar.
Use optional keyword-only deadline/check_active and empty kwargs when both are omitted. The reader retains the identical controls on its existing instance; read(size) keeps its call shape.
Reuse unchanged IO _check_budget and hash_file. Do not create another duration, cancellation state, helper framework or callback identity.
Central/local records poll at bounded record boundaries. Deflate integrity polls both raw-input and bounded-output loops, retaining terminal size/EOF/trailing checks before success polls.
ZIP extraction polls member read/write/EOF, directory/mkdir, close and final inventory boundaries. Requests use64KiB, but stdlib ZipExtFile may internally read/decompress repeatedly and flush before returning.
Thus only the separate integrity pass polls each compressed/raw/output slice; the ZIP second pass is cooperative around stdlib read calls, not inside them.
The gzip reader polls raw/decompress/trailer work and all successful returns including read(0)/finished EOF, preserving CRC, ratio, size and single-member rules.
Tar iteration uses the existing r| reader/512 buffer, whose raw/decompress work passes through _GzipReader; already-buffered stdlib parsing remains synchronous.
Tar copies, padding drain and EOF poll after local validation. Manifest parse, ELF header/close and the four cloud hashes reject late success before contracts.
### FR-2: Ownership and error precedence
Enter every acquired source/output context before a newly added callback, including extractfile(member). Preserve existing close ordering.
Validate facts established by each operation before that operation's post-success poll: size mismatches at EOF, decoder trailing/terminal state, zero padding and ELF bytes.
Retain close-error precedence where baseline validates after close. Later schema/digest phases remain separate; earlier cancellation need not run later phases.
Do not poll after known errors or from finally. Archive catch lists preserve ConsumerError from the shared helper and retain sanitized interruption behavior.
Original stage/session mapping yields cancelled/none or timeout/none only after reliable disposal; existing sticky cleanup failures remain adapter_error/none.
IO helpers, six roots, retained assets, receipt bytes, stage/executor and transport lifetime remain unchanged. No deletion is added.
### FR-3: Finite history and baseline
Reviewed runtime/tests may be implemented locally on isolated D with no refs/CI/publication. Before final admission, obtain actual F/raw parents/tree and prove full-tree equality; never claim D/F equivalence or provisional tests as final proof.
Use actual F as the new profile M. No placeholder commit may be written into production source.
Exactly five modified paths reverse to complete F bytes. Three prior paths admit only eight exact historical identities; all other source is rejected.
The old checksum profile gains only select/normalize delegation. Four old checksum methods gain five source-operand wrappers plus one import, preserving IDs/assertions.
D2[F], I2[F,D2] with tree(D2), and J2[R,I2] with exact four R documents are the entire grammar. Selected-content failures never delegate.
Candidate source pins cover all scoped files except the independently reviewed profile itself; complete outside-CAPS entries stay F. No production cache.
Within the new inverse-negative case, authenticate complete F consumer bytes to both baseline and checksum pins; mutate one checksum fragment, then isolate the outer delegate only for a direct lower-layer diagnostic assertion.
Require exact checksum fragment failure and one exact delegate call, restore patches, and separately require unpatched outer rejection of that mutation. No production allowance changes.
### FR-4: Verification
Fifteen new parameterized runtime tests use real ZIP/gzip/tar bytes, real reads/decompression/writes, EOF/close and diagnostic-collision cases; no parser/hash success stubs.
Reuse existing helper methods by alias, not inherited TestCase classes. Two real TLS workers must be retired before parser cancellation cases; original receipts/handles stay bound.
Twelve composition cases preserve old1376/strict303/consumer452, five inverses and eight prior pins. Proposed D2 total1403, I2/J2 each1064, publisher219.
The archive sketch is statically measured444 lines/delta164. A measured observation-support split preserves15 cases under500 lines and a support module under200; no parser success stubs or inherited tests.
Fresh exact-source tests, review, staged detect_changes, gencommit, hosted and independent local evidence precede engineering integration; use no PR137 outcomes as proof for changed bytes.
## 文件结构
Tasks lists12 exact paths and final/delta ceilings. No receipt/snapshot/executor/IO/shared fixture edit is authorized.
## Security and limits
Synchronous OS calls, sorts, callbacks, stdlib/zlib/JSON calls, root walks and close operations cannot be interrupted mid-call. Their late success is rejected only at the documented checkpoint.
Receipt ZIP, source/Git descendants, metadata, later contracts/copies/hashes and scratch removal remain gaps. No full-bundle deadline or authentic bundle/native/security admission follows.
Global eligibility, live writes, main/tag/release, credentials/protection settings, Windows work and held PR98/snapshot operations remain outside scope.
