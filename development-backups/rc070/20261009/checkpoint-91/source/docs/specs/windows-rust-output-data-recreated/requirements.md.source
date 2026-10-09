# Requirements: windows-rust-output-data-recreated

## 功能概述
Rebuild missing old Rust output DATA draft on exact19bb/1953, not restored old8path source. Existing pure Go direction2 output semantics are the reference. Exactly3Rust source paths and3spec paths; no native permission, handle/IOclose or publication bridge.

## 历史经验与坑（来自记忆库）
Old Rustdraft MISSING; Go value copies originally allowed repeated consumption and actual failure-first led to shared pointer once-state. Here ArcMutex shares entire private output state. Existing RunBinding is nominally reused via original public input::owned_run re-export; original validator/path/chunks byte exact. Source recovery or isolated compiler success is not RC or wholeWindows/native owner proof.

## 范围边界
Only output_stage/data.rs,data_tests.rs,mod.rs plus thisspec3files. No gate/nt/owner/input validator/body or protectedoriginalwsspositive change. No native boot grant/IO-close/writeback/publisher/snapshot/authorization; default request_publication denial preserved.

## 需求列表
### FR-1 Exact output framing and binding
WHEN receiving output data THEN consumer SHALL use CTMWIO02 direction2 and original valid ninefield RunBinding digest: CTM-DATA-BINDING-1 + each UTF8 byte length uint32LE + bytes in host/profile/caller/source/session/operation/input_relative/output_parent/output_leaf order. Header72 bytes, reserved10/11/36..39 zero, exact binding32, sequence uint32LE starting0, offset/total uint64LE and bodylength uint32LE must match. Body≤32768, total≤1048576, atmost32nonemptydataframes+onefinalemptyframe, framed≤1048576+33*72. All malformed/foreign/mutated/incomplete/replayed/trailing data SHALL reject, no data hash interpreted as authority.
### FR-2 Actual Reader EOF and finite cancellation boundary
WHEN finalzero-length frame arrives THEN offset SHALL equal manifesttotal and actual SHA256 data match before an actual Reader read returns Ok(0) EOF. Missing EOF/trailingbyte/readerror denies. Cancellation SHALL be checked before/after each physical read, after finalEOF and around detach/take. Cancellation token is shared monotonic stop-only privateAtomicBool, cannot reset through API. Synchronous Read cannot interrupt a blocking native pipe; controlled blocked-reader test SHALL declare that limitation and release its own ordinary reader, never spawn abandonedwaiters or claim native IOclosure/timeout.
### FR-3 Shared terminal single consumption
WHEN data owner is cloned THEN all clones SHALL share same ArcMutex private binding/data/hash/cancellation/consumedstate. Each take attempt SHALL set consumed before validating caller binding/cancel/hash and never reopen, including foreignattempt, cancellation, corruptdata or poisonedmutex. Correct concurrent32consumers yield exactlyone success; returned Vec is detached, modifications do not alter retained bytes. This data owner SHALL mint no resource/owner/retirement/publication capability.
### FR-4 Actual isolated tools, source identity and review
WHEN verifying THEN actual originalGo encoder/digest and direction2 consumer SHALL emit current crosslanguage golden vectors, while exact actual Rust1.98.1 compiler uses minimalcrate with original byte-exact transfer.rs/path.rs/chunks.rs. Facade reproduces only original owned_run RunBinding re-export; omits native gate/nt/owner/root/Tauri and must be named accurately. Wholecrate/Windowscompile/nativeVM/install remains NOTRUN. Freshsource-specific graphimpact, manualHIGH disclosure, necessary actualtests, independentpeer/freeze/safebackup precede rootonlypush; original1953base paths except mod.rs preserved and originalwss SHA c9fcdba432c239cc08a090c6cb4256f51b54368cbefb3afac553c1a6c719b9b8 remains16assert/9unwrap/3scope.

## 非功能需求
Each data file≤500lines; bounded parser allocation1MiB; immutable safe sourcebackup only—no keys/rawruntime/host/env/binaries/Gitobjects. Rustdata compile invocation bounded480s; each ordinary blockedread case has controlled3second channel boundary, no existing RCgate budgets expanded. ManualHIGH: existingbinding9impacts, new UNKNOWN not0.

## 验收标准
FR1 originalGo golden interoperability and max/boundary/empty/error vectors; FR2 EOF/cancellation/readfail/declaredblockedRead; FR3 clone/concurrent/terminal/mutation/poison; FR4 exactnative tool/source leases and limitedfacade/sourcepeer qualification.

## 依赖关系
Original pub(crate) input::owned_run::RunBinding and sha2/uuid; true existing pinnedRust/Go; rootisolated19bb source/index and currentGo output frozen source; no old missingRust draft restoration.
