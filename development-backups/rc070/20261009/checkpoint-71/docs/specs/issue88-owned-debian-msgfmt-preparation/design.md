# 设计文档：issue88-owned-debian-msgfmt-preparation

## 概述

FR-1 authenticates official signed bytes. FR-2 bounds owned extraction and genuine dependency usability. FR-3 preserves original budgets/SUT. FR-4 preserves source review and evidence. This separate proposal follows actual GNU1.0 configure timeout, not an upgrade of its partial output.

## 技术方案

### 架构设计

Captured InRelease + official fingerprint anchors + legal keyring lease → full real GPG status gate → exact SHA256 Packages.xz → bounded RFC822 unique records → exact .deb data-only ar/tar validation → fresh owned full data trees → explicit native ELF interpreter/NEEDED closure/current host ABI identities → separately root-approved real version/UTF8 PO/MO/malformedPO → separately original makeall480 with genuine loader literal argv in MSGFMT, only after separate integration review. Default helper execute=False does not launch downloaded ELF. No APT/dpkg/maintainer scripts or host binary copying.

### 技术选型

Python standard library byte parsers; genuine existing GPG with owned homedir/no-options/no-auto-keyretrieve/no-agent, existing archivekeyring public data. .deb ar control/data .xz/.gz may be supported; other codecs fail clearly until reviewed, never call package installer as fallback. Record complete extracted package file/directory manifests and link inode/target topology. Native metadata may use genuine existing readelf after source review, not downloaded wrapper. Actual ldd/loader resolves target and may invoke its interpreter: root-only execution gate applies, not assumed read-only safety.

## 文件结构

Separate publisher-debian-msgfmt-research with proposed owned_debian_msgfmt_prepare.py and owned_debian_msgfmt_prepare_tests.py plus three specs. Private metadata/debs/native payloads/runtime/logs are excluded from safe public backup. Original repository/SUT and previous GNU frozen fivepaths unchanged.

## 设计决策

### 决策1：Exact signed release with explicit age limitation (FR-1)

Bookworm official main point-release dated2026-07-11 has no Valid-Until. Actual download2026-10-09 and three valid signatures show authentic captured bytes, not strict replay protection. Require both bookworm anchors independently matched official fingerprint page and public .asc, reject all bad status even if another valid signature exists. TRUST_UNDEFINED preserved. If future gate requires strict freshness, this proposal cannot silently waive it.

### 决策2：Package deps versus executable closure (FR-2)

getText package dependsgettext-base/libc>=2.34/libgomp/libunistring2/libxml2; libxml2 adds ICU72/lzma/zlib and ICU72 hostlibstdc++/libgcc. Proposed eight data packages total remains<=32MiB; captured exact records cover dependency requirements. Host libc/loader/ABI are never extracted/replaced. Native actual msgfmt may load fewer libs than package dependency metadata; actual-needed inventory and signed package dependency constraints must be accurately declared; host native ABI is checked with ELF version requirements and actual loader resolution, no package database installation/status claimed; missing native dependency blocks. Relative package library symlinks may be needed; validate resolved in-root regular target, reject externally resolved/cycles/duplicates, do not replace system aliases. Explicit genuine loader --library-path argument is new risk; no LD_LIBRARY_PATH env assignment/PATH shim/global env.

### 决策3：Truthful finite preparation (FR-3)

Network120/request30/dataextract60/nativeinspection30/usability30 are new fixed proposal budgets, not inherited old proof. Total expansion128MiB/maxmember64MiB and unique10000entries bound real data. Tool execution only literal authenticated ELF and exact real runtime paths leased beforeeach/final. Installation is false: data extraction is neither dpkg installation nor user product installation. Existing runtime pin /usr/local/bin/git is still unsatisfied by workspace msgfmt/Git. No sourceflag/feature disable can hide prior make failures.

### 决策4：Independent gate before launch (FR-4)

Freshnewsymbols UNKNOWN/manualHIGH until indexed. Ordinary controls can exercise mocked metadata and owned process stop limits, but cannot prove genuine binaries/native family closure. Source freeze/negative controls/independent peer/root exact launch required; root uniquely launches realtool. Preserve every old timeout/cancel/failure and immutable sourcebackup.

## 测试策略

New ordinary controls reject GPGexit0 plusexpired/revoked, wrong/missingbookwormsignatures, changedmetadata/packages/deb/keybytes, futureDate/declaredValidUntilexpired, duplicate/mismatchedpackageversion/arch/filename, truncatedar/specialmembers/sizecaps, unsafe tar paths/links/hardlinks/specialmodes, missing dependency/currentpathdrift/default executionFalse, broad/globalenv mutation and finalcommandlease omissions. Real success vector later requires msgfmtGNU0.21 version, independent knownMO parse and malformedPO true failure with genuine complete dependencies, newbytebeforeafter. Original GNU and Git tests not borrowed as this family proof.

## 风险评估

ManualHIGH: newgraph coverage UNKNOWN; public source-key authorization/extraction/ABI and native runtime closure; explicit real loader --library-path argv proposed only inside root-approved process. Signed oldstable main has no expiration field; no strict freshness claim. Existinghostlibs/dynamicloader tool semantics not yet measured. Complete selected manifests do not prove global host immutability, hostile sameUID race or OS filesystem sandbox. New budgets must be enforced, not summaries. Downloaded .deb native execution never automatic.

## 检查清单

- [x] All four FRs mapped, authentic captured metadata and age limitation explicit.
- [ ] Implement ordinary controls after check_spec/manualHIGH; independentpeer/root launch.

Actual control declarations: controls02 seventeen ordinary methods PASS included primary/cancellation object preservation after failure-first01; controls03 twenty PASS, controls05 twenty-one PASS after preserved pre-native failure-first02. Final vector adds existing host Python exact byte-copy ELF readelf/loader --list dependency-denial control, not Debian/GNU usability. Controlled cancellation/readerclose signals are ordinary delegates, not native IO close/interrupt proof. Four host ABI libraries are leased before first load; no host library outside them may be admitted. All owned file/link/directory leases are checked before first native delegate and again finally. Partial native lease state is retained across failed static/loader observations.

Actual signed package topology research (FR-2): exact eight .deb downloads12370000B,3.327963s within120s/32MiB; stdlib headers only, zero filesystem extraction/native/controlscript launch.495entries/47707775regularpayload/20symlinks; sole missing-target documentation link is signed libgomp1 usr/share/doc/libgomp1 -> gcc-12-base. Proposed exact literal non-native doc DATA preservation is confined to that package/path/target; lexicalmode/devino/mtime/ctime/linkstring/canonicaltarget lease, no target dereference and no arbitrary dangling links. Loader dirs are only real pkg usr/lib/x86_64-linux-gnu and lib/x86_64-linux-gnu; documentation is not executable/dependency authority. All other library/java/man links require actual same-package regular targets. This avoids installing gccbase or widening eightpackages. Actual data extraction/genuine msgfmt remainsNOTRUN.

Own exactfivefile standalone graph actualindex0: initialgraph122nodes275edges20flows, extractCRITICAL9/direct5/process7, prepareHIGH4, runtimeHIGH7 disclosed before exactdoc DATA sourceedit; currentindex02actual0/124nodes285edges20flows, MO reader freshLOW6/direct2/process2 before bounded2MiB+1 read hardening. Initial11preimplementation failedtempgraph calls remain failed/UNKNOWN; standalonehelper graph does not establish originalrepo/native coverage.

V2 FR-5 decision: independentd696 peerSTOP authentic/datachain otherwiseverified. Outerlogfile and fdopenwriter with-exit could mask original/cancel; snapshot/auth/MO streams have sameform. Replace all critical actual filesystemIO with one explicit resource-close adapter and bounded fileIO using rawnative os.open/read/write onceclose ledger. Avoid fdopen entirely so no uncertain transfer inference; ctorfault-after-open realclose required, closeUNKNOWN notretry. Generic actualclose resource covers tar objects; stdout/selector/output independentfinally attempts remain. Explicit BaseExceptionGroup keeps primary orpre-existinggroup exactly, plus distinct closeerror. fdnumber/devino notcallergrants. OrdinaryrealEBADF close and controlledreadwrite/KBI/SystemExit failures are newcontrols, no nativecancel/allIO proof. Full old15tools/fourABI/loader/8datafirstmanifest/auth/defaultbudget structure staysunchanged.

### V2 concrete source and ordinary coverage

The adapter uses actual returned `os.open` descriptors, direct bounded `os.read`/partial `os.write`, and a state recorded UNKNOWN before each once-only `os.close`. It does not call fdopen or infer ownership from descriptor numbers. Critical file reads/writes and returned tar/member resources share explicit `owned_debian_resource`: a distinct close exception groups the exact original primary object, including a pre-existing BaseExceptionGroup. Output closes after independent stdout/selector cleanup, retaining an already formed cleanup group. Native package/library leases remain original captured fields; public keyring reads resolve its known public symlink without claiming additional authority. Exclusive evidence/result writes refuse existing paths.

Actual V2 ordinary controls are 23 baseline plus 8 new methods (31 total), including real owned FD output EBADF; read/write primary plus close KeyboardInterrupt/SystemExit; returned-FD constructor failure; close-only UNKNOWN/no retry; snapshot/metadata/MO reader routes; real ordinary process stdout/selector/output all attempted; tar member primary preservation; and a negative fdopen assertion with actual writer FD closed. Mocked cancellation objects are ordinary signals, not native allIO cancellation/FD retirement proof. Native F_GETFD in tests is only a diagnostic on the actual owned serial test FD, never admission. Authenticated downloaded Debians remain read-only, with no real filesystem extraction or downloaded ELF executed by these controls.

### V3 constructor cancellation boundary

Independent V2 peer STOP identified os.open/state before try. V2 freeze/31controlraw remains immutable. V3 moves real returned-FD assignment/state/fstat into one try. The exception branch closes only if self._fd is non-None, restores local OPEN state for that known actual returned FD, and retains all primary/close objects. New ordinary tracing interrupts this actual source constructor after its real FD is recorded (not an adapter opening an unreturned FD), with actual once-close/EBADF diagnostics. This is ordinary controlled cancellation, not OS native cancellation retirement proof. FreshV2graph classLOW4, constructorLOW0; overall authentication/data/ABI manualHIGH remains.

V3 final ordinary result: 33 methods actualPASS7.774s, with two new constructor methods. Valid negative executed the immutable original V2 constructor and observed recorded/injected returned FD and zero helper close attempts. First trace attempt failed from an absent preinitialization attribute and is explicitly invalid as FD evidence. Corrected trace waits for actual self._fd recorded, and V3 closes once with exact original cancellation/cleanup objects. No global native asynchronous cancellation guarantee is claimed.
