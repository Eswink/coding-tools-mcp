# 需求文档：issue88-owned-debian-msgfmt-preparation

## 功能概述

Separate workspace-only genuine Debian GNU msgfmt acquisition proposal. Official GNUgettext1.0 configure120 actual TIMEOUT, OWNED_INSTALL=false and prior GitV1/V2 defaultmake FAIL remain immutable. Read-only official Debian bookworm signed metadata selects gettext0.21-12 amd64; no package execution, extraction, APT, system installation or GitV3 has occurred.

## 历史经验与坑（来自记忆库）

GPGexit0 does not alone authorize bytes; reject expired/revoked/bad/unknown signing status. Preserve TRUST_UNDEFINED, exact official source anchors, every old failure and partial binary unqualified. GNU configure timeout cannot justify feature disabling. Debian maintainer scripts, APT and global PATH/LD_LIBRARY_PATH are excluded.

## 术语定义

Authenticated package: compressed .deb bytes with exact Size/SHA256 from exact Packages.xz hashed in verified official InRelease. Owned extraction: data only under one fresh task root, no dpkg install/maintainer script invocation. Native msgfmt: exact actual ELF, genuine GNU behavior and every resolved runtime dependency identity, not a wrapper/alias or path-only receipt.

## 范围边界

In Scope now: legal read-only official signed metadata/key identity, limited new spec/impact, ordinary preparation source controls and independent peer. Future root-reviewed scope: genuine package data download/extraction and one bounded literal msgfmt usability vector, then separately one original wholeGit makeall480s.
Out of Scope: downloaded binary execution before root review, APT/dpkg install/sudo/systemdirs/customer/CIhost installation; replacing loader/libc/compiler/systemGit; PATH shims/aliases, global loader env; original Git flags/Rust/NLS/Reader/runtime pin/test vectors or budgets changes; GitHub push/grants/release/RC authority. No claim trusted complete host sandbox or hostile same-UID race protection.

## 需求列表

### FR-1 Exact official Debian authorization chain
**优先级:** Must
**用户故事:** 作为维护者，我要按真实官方签名链校验工具字节。
#### 验收标准（EARS）
1. WHEN processing source THEN system SHALL require captured official bookworm InRelease151075B SHA77737fa4b34f2693e982cc9ee35736816c35a7778fc2d326cc1bbf5b301fe1aa; OriginDebian/Codenamebookworm/amd64 and realGPGexit0 GOODSIG/VALIDSIG from exact official bookworm archive primary B8B80B5B623EAB6AD8775C45B7C5D7D6350947F8 and stable primary4D64FEC119C2029067D6E791F8D2585B8783D481. Reject ANY expired/revoked/bad/unknown signature. Extra trixie signature does not replace two selected anchors. Official ftp-master keys.html and key12/release12 .asc match primaries; legal existing public keyring resolved .pgp55918B SHA506b815cbb32d9b6066b4a2aa524071e071761e7e7f68c3ac74f3061ba852017 remains leased.
2. WHEN checking metadata age THEN system SHALL preserve signed Date2026-07-11 and actual captured time2026-10-09; no Valid-Until is provided by this main point-release metadata. Reject future dates; do not invent expiration waiver or claim strict freshness/anti-replay. If strict freshness is needed, BLOCKED until separately reviewed official timely source. TRUST_UNDEFINED/source policy is not publisher authorization.
3. WHEN selecting packages THEN system SHALL require exact signed SHA256 Packages.xz8790396B SHA9e0b5aabb2465b3d2e7a7fe27f9913846277833f7a2826e7767acccff5b588c5; bounded decode50060337B SHA515e692f2c4121c6fcec444ef100cc18f79a991910615f3a88c8b7becfc94d2f; strict unique package/version/architecture/filename/size/hash/dependency fields. gettext0.21-12 amd641300056B SHA8c1f9d43575373ce311f51d00a13afbb4888d63aa559a93a3472f5d77513b60c is pinned. No arbitrary mirror/source fallback.

### FR-2 Bounded owned package data and truthful dependency gate
**优先级:** Must
**用户故事:** 作为维护者，我要真正可执行的工具及对应依赖而不替换系统。
#### 验收标准（EARS）
1. BEFORE extraction THEN system SHALL verify exact selected .deb size/hash, ar member structure/debian-binary2.0 and bounded control/data tar. Fresh nofollow/exclusive root only; reject duplicate/absolute/traversal/special/hardlink/escaped link entries, oversized expansion and unsafe modes; preserve package regular bytes/modes and vetted in-root relative library symlinks; exactly observed authenticated libgomp1 usr/share/doc/libgomp1 -> gcc-12-base may be retained as dangling non-native documentation DATA only, with lexical inode/mode/time/linkstring/canonical owned target manifest. It is outside all literal loader library dirs and cannot admit missing library links. All other dangling/directory/escaped links remain denied. Never execute control/preinst/postinst/triggers or dpkg/APT. Complete selected data extraction and manifests required; not selective copy of host binary.
2. WHEN dependency selection runs THEN system SHALL distinguish package dependency metadata from native ELF NEEDED runtime closure. Candidate owned packages are gettext/gettext-base/libgomp1/libunistring2/libxml2/libicu72/liblzma5/zlib1g, exact signed records. Existing host libc/loader/libstdc++/libgcc native ABI must be explicitly measured by actual ELF version-needed inventory and real loader version resolution; lease four original host libraries before first load, reject any host dependency outside that set, and keep selected package dependency/version records. Package database installation/status is not claimed by data extraction; absent/incompatible native ABI is BLOCKED, no replacement/install or waived native dependency. Do not assert all failures have one cause.
3. WHEN root approves genuine execution THEN system SHALL require literal owned usr/bin/msgfmt native x86_64 ELF with leased real interpreter/all resolved libraries/selected paths/modes/hash before every command and after final command; approved genuine host ELF loader --library-path <exactownedlibdirs> <literalownedmsgfmt> may select real authenticated libs; no LD_LIBRARY_PATH assignment or global env/PATH shim/alias. Record actual GNUgettext0.21 --version, UTF8 knownPO→actualMO translation and malformedPO nonzero rejection, no synthetic semantics receipt. HOST_INSTALL=false/OWNED_EXTRACTION=true only after actual data success; product INSTALL remainsNOTRUN.

### FR-3 Finite phases and original Git/SUT boundaries
**优先级:** Must
**用户故事:** 作为维护者，我要保持原门禁而得到新的实际工具。
#### 验收标准（EARS）
1. WHEN preparation executes THEN network phase SHALL be <=120s total/<=30s request, max512KiB InRelease, max16MiB Packages.xz/max128MiB decode, <=8data packages <=32MiB compressedtotal, <=128MiB expanded data total/maxmember64MiB/max10000entries, owned extraction<=60s, native/static dependency inspection<=30s total and genuine version/positive/negative vector<=30s total; eachprocesslog<=2MiB, finite ordinary owned-process cleanup. Unknown nativefamily/IO cancellation closure is not inferred. Failures stop, no automatic budget expansion/retry.
2. WHEN future separately approved GitV3 runs THEN supported originalMakefile MSGFMT=<genuine loader + exact literal argv and ownedELF> (future new limited integration review required) and explicit reviewed genuine loader argv SHALL retain all original source/defaultcomponents/flags/Rust/NLS, original build480s. Existing cargo/rustc genuine payload env from V2 remains distinct. Original systemGit and literal publisher /usr/local/bin/git pin not satisfied by owned tool/setup; no fake target path. Before/after original source/runtime leases include last native checks.
3. IF any auth/data/dependency/tool/Git gate fails THEN system SHALL retain genuine FAIL/BLOCKED/NOTRUN, old GNU/V1/V2 receipts and backups unchanged; no original85/300/Windows/native/install/release qualification from preparation. Current research downloaded executable launches0 and SUT0.

### FR-4 Fresh source review and safe persistence
**优先级:** Must
**用户故事:** 作为维护者，我要小范围真实可审查的结果。
#### 验收标准（EARS）
1. BEFORE helper symbols are edited THEN fresh impact calls SHALL actually run and nested UNKNOWN/degraded be disclosed manualHIGH; no sourcegraph or zero impact inferred from topok. New source authorization/extraction/runtime inventory risk must be disclosed before implementation.
2. WHEN preparation source is frozen THEN new ordinary signature/age/hash/record/ar/tar/path/link/budget/dependency/default-executeFalse/final-runtime controls and independent peer SHALL precede root-only one real tool launch. Mocked native metadata/MO are ordinary controls, not genuine Debian executable proof.
3. WHEN backing up THEN public payload SHALL be only safe source/patch/spec/mode/hash/status, excluding binaries/debs/keys/rawhost/runtime/env/logs/Gitobjects; keep old immutable bundles and failure evidence. No new remote/system/CI authority from source-only backup.

## 非功能需求

- NFR-1: Finite budgets above do not expand GNU120/480/60 or originalGit480/publisher envelopes. Actual host ABI/dependencies UNKNOWN until measured.
- NFR-2: Workspace data-only extraction, no installer/system/compiler/libc/loader replacement. Scope-owned child libs via genuine loader --library-path only with concrete reviewed identities; never LD_LIBRARY_PATH/global env. Existing carrier unconditional no-install markers remain untouched, future setup must truthful distinct receipts.
- NFR-3: Public archive signing keys are source trust anchors only; no tokens/session/credential inspection, issuer/grant mint or GitHub permission changes.

## 依赖关系

Official Debian ftp-master fingerprints/publickeyring and signed captured bookworm metadata; root source-only review and specific future launch; existing host ABI and dependency identity; original Git supported MSGFMT variable. Whole RC gates remain outside scope.

## 检查清单

- [x] Read-only actual metadata chain captured, no downloaded tool executed or extracted.
- [ ] Fresh impacts/manualHIGH/source implementation/ordinary controls/peer.
- [ ] Root-only actual data/executable vector, later separately GitV3.

### FR-5 V2 real resource closure preserving original objects
**优先级:** Must
**用户故事:** 作为维护者，我要关闭异常不遮蔽原读写或取消对象，且不靠不明FD转交造安全证明。
#### 验收标准（EARS）
1. WHEN a critical reader/writer/log/MO/metadata/result/snapshot/tar operation fails THEN source SHALL perform actual once-close and explicitly propagate originalprimary/KeyboardInterrupt/SystemExit/pre-existinggroup objects together with any distinct close errors; Python__context__alone is not admission. Each stdout/selector/output cleanup MUST still be attempted independently, no cleanup skipped dueanotherclosefailure.
2. WHEN native datafile is opened THEN source SHALL own only the actual returned os.open FD in a private lexicalledger, use os.read/os.write directly and onceos.close, avoiding fdopen's ambiguous transfer. Closeexception retains UNKNOWN diagnostic, no retry, no ownership/admission minted from FDnumber/F_GETFD/path/inode. All constructors that fail afteropen still attempt realclose; missing/existing/unsafe paths remain denied by actual validatedcallers. This is workspace tool DATA, not Windows owner/nativeallIO authority.
3. BEFORE V2 rootlaunch THEN actual ordinary realowned FD/readwrite/logoutput EBADF closure controls, KBI/SystemExit/group same-object checks, no-fdopen negative and stdout/selector/output allattempt controls SHALL pass with newcount/rawlogs. Old23 baseline notwholehelperIOproof; oldd696/cp55+failureevidence preserved, V2newfreeze/peer/cp65 required. No realDebian filesystem extraction/ELF by author.
