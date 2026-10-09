# Genuine loader context boundary

## 概述

对应需求：FR-1、FR-2、FR-3。The mechanism remains specification-only and requires explicit root implementation/query authorization.

## 技术方案

Choose two independent external ordinary modules later: loader_query_context.py (fixed admission, exact loader/target/ENV vector, contextual fact parser and before/after fences) and loader_query_controls.py (bounded controls and one sealed root-owned launch entry). Reuse the tested ordinary process/file holder mechanism under an explicit new whitelist, never monkeypatch the current run_job guard or call the whole compiler. Current eight source files, original SUT/runner/tests/worker/deadlines and source102 stay unchanged during this proposal. Integration into build_source_owner.py is a later separately reviewed change; current DT_RPATH block stays.

Full static modeling is not an honest two-function shortcut: per-execroot loaded alias/SONAME map and first l_loader ancestry, RUNPATH tag presence suppressing ancestor RPATH, main RPATH fallback, dynamic origin, cache/hwcaps/default flags and dlopen host must all be carried. The loader query uses the system's actual implementation for each known executable; plugin contexts remain separate OPEN inputs. Main ORIGIN uses actual executable resolution; DSO ORIGIN binds the loader's actual loaded filename parent, not blindly Path.resolve().parent. Never use the requester's ORIGIN to expand an ancestor's RPATH.

## 文件结构

Proposed external loader_query_context.py and loader_query_controls.py are absent. Current changes are the three specification files only. Source102/current877 is unchanged.

## Primary source and actual observations

Official Debian dsc archives were SHA256 verified and relevant selected loader sources reconstructed with ordered zero-fuzz patches. This is version-corresponding primary research, not binary-source build proof. rtld audit load precedes its nonnormal listing/exit branch. dl-load path search first reuses loaded aliases/SONAME, then (if the immediate requester has no RUNPATH tag) traverses eligible requester/ancestor/main RPATH, then environment, immediate RUNPATH, cache and defaults. Needed context and origin must remain explicit.

Actual candidate catalogue has63 ELF objects, only outer3.12 RPATH and no RUNPATH. Outer candidate DAG has8 objects/13 edges; prefixlib contains none of the inherited-name candidates. These are readonly current candidate observations, not genuine runtime selected context, absence facts for a future build, or permission to ignore inheritance. Current LD variables examined were absent; prior runs' initial LD environment was not independently sealed retroactively. GCC future ENV already excludes LD variables by complete replacement.

## Process and threat limits

First actual query, if later authorized, is one canonical real outer3.12 target. No target main/init execution claim without audit/preload/debug/unsafe tag rejection and trusted matching loader-source semantics; loader itself executes trusted platform code and maps actual libraries. Known dynamic query callbacks are prohibited; unsupported primary/binary binding stays BLOCKED. Files/cache/search directories require before/after identity and negative-candidate observations; privileged transient code injection remains outside this finite build model and is not hidden by hash equality. Unknown ordinary IO retirement cannot be recast as native family empty or native_closed.

## Meaningful finite controls to review before launch

Ordinary source-only admission negatives reject arbitrary ROOT/DSO targets, unsafe flags/LD environment, audit/filter tags, unsealed paths, malformed/not-found output and changed native identities. After distinct startup permission, meaningful actual owned-query controls must cover first process observation failure, real selector/PIPE close cancellation aggregation and original primary preservation, with exact official loader --list target and budgets. These are not native14 or C01 support. Root controls first actual query launch; no auto retries, and complete compiler launch remains separate.
