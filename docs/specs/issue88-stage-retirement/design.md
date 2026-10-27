# 设计文档：issue88-stage-retirement

## 概述

FR-1 through FR-4 add one internal stage-only creation ledger and deterministic retirement pass. Ordinary consumer roots continue retaining their outputs.
The baseline is F `f0fdfba5cd48b7cad477f1e2cb77bb70153ad657`, with exact tree `84ff6fd8a0936f99d0b1267c78bd50ba52a70fa0` and1795 entries.

## 技术方案

### Creation and lifetime (FR-1)

StagedAssets appends each StageRootOwner before entering its PrivateRoot constructor. Exact owner type is an internal trusted-code contract, not protection against arbitrary Python mutation.
Retained parent/root dirfds bind names to authenticated invocation-created objects. Reserve first, register only after nofollow opened/name identities agree, and reject duplicate names or identities.
Register directories and exclusive files before later closes; a successful creation that cannot be authenticated remains pending and is never inferred from its basename or prefix.
Stage-only IO close accounting covers six existing PrivateRoot methods and the stage handle-check temporary dirfd. A close attempt consumes descriptor ownership before the OS call; ambiguous closes are not retried.
Default PrivateRoot.close and `_directory` remain exact baseline bytes. Partial constructors not registered in ExitStack remain reachable through their already appended owner.
Existing stack order closes retained handles before ordinary roots; the retirement pass runs afterward.

### Buffered stream ownership (FR-1, FR-3)

Stage-only fdopen uses closefd=False; default fdopen is unchanged. Accept only exact standard BufferedReader/BufferedWriter and FileIO instances with the expected original raw descriptor.
Attempt buffered close once. If the raw layer remains open, invoke builtin FileIO.close to invalidate its internal descriptor without an OS close.
Verify both raw.closed and stream.closed before releasing the owned OS descriptor once. If either state is false or unobservable, retain the stream and descriptor and mark uncertainty.
A buffered-close error remains an error and blocks deletion. The exceptional raw fallback may discard pending bytes only after failure; normal buffering and flush/fsync order remain unchanged.
Test real before-close, during-flush and after-close faults, pending buffered bytes, exact descriptor-number reuse, late flush and GC against an outside sentinel on CPython3.12.

### Complete preflight and removal (FR-2)

Before the first unlink, preflight every root's authenticated parent/root, pending/active/uncertain state, and exact file/directory ledger equality with PrivateRoot's records.
Construct expected immediate-child membership once; include empty directories. Traverse only registered directories and reject every unknown, missing, symlinked, aliased, owner/mode/type-drifted object.
Require regular-file nlink1 and unique registered identities across all stage roots. This does not prove absence of mount aliases or hostile concurrent writers.
Remove only recorded files, then recorded directories bottom-up, checking each target immediately through a retained checked parent dirfd. Stop the first destructive or traversal-close failure.
Regardless of failure, independently attempt remaining certainly owned retained dirfd closes once. Repeated stage.close performs no further deletion or close attempt.
No ambient pathname cleanup, discovery-derived authority, rmtree, rollback or removal retry is introduced. Python unlink/rmdir lack expected-inode atomic removal; retain the existing no-concurrent-writer assumption.

### Error and evidence boundaries (FR-3)

Worker cleanup uncertainty or an owned close failure known before destruction sets the existing sticky cleanup flag and retains all private entries. A failure after destruction starts stops further removal and retains remaining entries without rollback or a no-residue claim; original core/executor outcomes and prior mutation effects remain unchanged.
Independently owned read-only open_file/ZIP readers keep prior error/close behavior. This guarantee covers known writers, retained handles and owned directory descriptors, not every read-only inner descriptor.
Synchronous traversal, metadata, OS close and filesystem operations have no new hard wall-clock guarantee. Existing byte budgets and original operation deadlines are unchanged.
Two existing adversarial tests explicitly assert first-close failure after their original ownership-drift assertions. Their original test IDs and assertion-call ASTs remain present.

### Finite composition and validation (FR-4)

The latest readiness profile first calls the new exact normalizer/selector; only the new selector's topology nonmatch returns control to the prior profile. Selected historical/source errors remain terminal and candidate validation stays fresh.
Seven replacements invert to full F bytes, including the two intentional test adapters; twelve historical blob/SHA256 identities remain exact. All outside-scope bytes/modes stay F.
Only D[F], I[F,D] and J[R,I] are admitted. I has D's complete tree; J differs only at the four exact retained R documents. No broad ancestry or mutable-candidate cache is added.
Preserve1445 old IDs and add36 real cases plus12 composition cases: D1493, I1154, J1154 and publisher309. Source-bound hosted reuse must prove identical commands/setup/IDs and retain inferred-ID limits.
Use two independent implementation partitions after fresh impacts, exact review and spec gate. Focused review/tests precede draft CI; full local contexts run alongside hosted checks, with at most two local test workers.

## 文件结构

- Existing runtime: `scripts/rc_consumer_io.py`, `scripts/rc_publication_stage.py`
- New owner and tests: `scripts/rc_publication_retirement.py`, `scripts/rc_publication_retirement_cases.py`, `scripts/rc_publication_retirement_lifetime_cases.py`
- Existing test adapters: `scripts/rc_publication_stage_cases.py`, `scripts/rc_publication_staged_bytes_cases.py`
- Existing dispatch adapters: `scripts/rc_pretag_supervisor_readiness_profile.py`, `scripts/rc_pretag_supervisor_readiness_cases.py`
- New admission: `scripts/rc_pretag_stage_retirement_profile.py`, `scripts/rc_pretag_stage_retirement_cases.py`
- Existing workflow: `.github/workflows/issue88-publication-executor.yml`; add only exact source/workflow inventory and309-case wiring, preserving permissions/events/limits
- Three current spec documents; total15 paths,7 replacements/8 additions and1803 entries. Aggregate cap2250; sum of individual delta caps2220; source modules at most500 lines
