# 需求文档：issue88-stage-retirement

## 功能概述

Retire only the publisher staging invocation's authenticated private artifacts after their known writers and retained handles close. Ordinary consumer outputs remain retained.
Baseline F is `f0fdfba5cd48b7cad477f1e2cb77bb70153ad657`, tree `84ff6fd8a0936f99d0b1267c78bd50ba52a70fa0`; this is an engineering prerequisite, not bundle/native or release admission.

## 需求列表

### FR-1: Register creation ownership and preserve descriptor lifetime

Priority: Must. WHEN each of six staging roots is constructed, the stage SHALL register its concrete owner before construction can fail and retain authenticated parent/root descriptors.
WHEN directories or exclusive files are created, the owner SHALL register their identities before subsequent fallible closes; unverified creations SHALL remain pending and retained.
WHEN a stage-owned buffered stream closes, the owner SHALL attempt buffered close once, retire its exact FileIO raw layer if necessary, and verify both `raw.closed` and `stream.closed` before one OS descriptor close.
IF raw/buffer quiescence cannot be established, the owner SHALL retain the Python object and raw descriptor without permitting descriptor reuse.

### FR-2: Remove only the complete authenticated owned inventory

Priority: Must. WHEN ordinary stage contexts have closed certainly, the stage SHALL preflight every owner before its first destructive operation.
The preflight SHALL verify parent/root identity, all registered file and directory membership including empty directories, nofollow type/owner/mode, regular-file single-link status, and duplicate identity rejection.
IF any object is unknown, missing, replaced, aliased or unauthenticated, the stage SHALL retain the artifacts and report retirement failure.
WHEN preflight succeeds, the stage SHALL remove registered files and then directories bottom-up through retained authenticated directory descriptors, immediately checking each target identity.
IF any removal or traversal close fails, the stage SHALL stop destruction, attempt each remaining certainly owned retained descriptor close once, and never retry deletion on repeated stage close.

### FR-3: Keep cleanup uncertainty and existing outcomes honest

Priority: Must. IF worker cleanup or an owned close is uncertain before destruction, the stage SHALL retain all staged entries and keep cleanup failure sticky; IF uncertainty arises after destruction starts, it SHALL stop and retain remaining entries without rollback or a no-residue claim.
IF buffered close fails, the stage SHALL poison deletion even if the raw layer is subsequently quiescent; exceptional raw retirement may discard pending bytes only on the failed operation.
The implementation SHALL preserve ordinary `PrivateRoot.close` byte-for-byte, default consumer buffering/retention, original byte/deadline/error contracts and executor/core effect semantics.
Independently owned read-only open_file/ZIP readers SHALL retain their existing close/error scopes; this feature SHALL NOT claim their physical closure or convert every read/parse error into cleanup uncertainty.

### FR-4: Bind source admission and real regression evidence

Priority: Must. The finite admission SHALL allow only D[F], ordered I[F,D] with D's tree, and J[R,I] with the four existing exact R document replacements.
It SHALL restore seven complete replacement baselines and twelve historical identities, preserve all original1445/strict303/consumer452 IDs, and validate each altered candidate freshly with terminal content failures.
Tests SHALL cover36 real filesystem/lifecycle/process/TLS cases plus12 composition cases, including real CPython3.12 late flush/GC after exact FD reuse, actual worker reaping, uncertainty retention and unchanged published/unknown effects.
All required source-bound focused, hosted and D1493/I1154/J1154 contexts SHALL pass without skips or repeated failed-evidence credit before integration.

## 非功能需求

- Fifteen paths, seven replacements and eight additions;1803 entries; aggregate added/deleted cap2250, individual delta caps sum2220; every source file at most500 lines.
- No recursive delete-by-discovered-name, rmtree, glob authority, generic cleanup framework, elevated permission, retry or destructor cleanup.
- Existing no-concurrent-writers/no-delegation assumption applies. Separate inode checks and unlink/rmdir are not atomic against a hostile concurrent replacement; no global alias or hard cleanup deadline guarantee.
- Live publication and missing bundle/native/security gates remain blocked; held PR98/snapshot and Windows work remain separate.

## 依赖关系

Existing PrivateRoot/ExitStack ownership, supervisor worker cleanup, publication stage/executor/core and historical pretag adapters are reused. Supported staging requires dirfd unlink/rmdir and fd scandir before artifact creation.
