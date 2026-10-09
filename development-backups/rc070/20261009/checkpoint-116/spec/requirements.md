# Stage I genuine loader-context query — specification only

## 功能概述

The current prototype outer is explicitly CPython3.12.14/full3.12 ABI. Its actual DT_RPATH is $ORIGIN/../lib. StageI24 six parser controls passed but full input closure remains BLOCKED, and current877/source102 stays immutable. This proposal chooses an independently bounded genuine loader --list query for actual known executable contexts, instead of pretending a path-only visited set implements glibc ancestry/SONAME semantics. No execution or source implementation is authorized by this specification.

## 需求列表

### FR-1 — Immutable limited query admission
Before any actual process creation, admit only the actual source-sealed loader /usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 (438c546d8e8cc48496bf3a95f753051afd9db66a629a74e31a9ded71586b56e0) and individually declared canonical fixed executable targets from existing TOOLS; the first proposed target is the explicit outer3.12. Root artifacts, bridge modules, arbitrary user ELF and support DSOs SHALL never be queried as pretend executable roots. Literal/resolved aliases, full bytes/mode/identity, matching machine/interpreter and exact target role SHALL be sealed. Query ENV SHALL equal the existing future GCC job ENV (PATH=/usr/bin:/bin, LC_ALL=C, TZ=UTC), with no inherited LD_* or GLIBC_TUNABLES; the future outer launch must bind matching initial ENV rather than retroactively asserting it. DT_AUDIT, DT_DEPAUDIT, DT_FILTER/AUXILIARY, preload presence, unsupported token/relative/empty unsafe search entry, secure-mode/capability ambiguity, or any unsealed candidate/loader input SHALL BLOCK. Actual source/package version notes are not machine-code provenance.

### FR-2 — Genuine contextual fact, no altered resolution
The sole future actual vector is [sealed_loader, '--list', declared_canonical_target]. No --inhibit-cache, --library-path, hwcap override, ldd shell wrapper or interpreter substitution is permitted. The genuine loader shall supply each executable's actual dependency path set under its own first-loader/SONAME/RPATH/RUNPATH context. Query output SHALL be parsed fail-closed and bound to actual before/after native file identities, actual target and loader, cache/config/preload-absence and search-directory candidate facts. Unknown output, not-found dependency, unsealed selected path, changed identity or unsupported role SHALL not become closure success. Virtual kernel vDSO is declared as virtual, never fabricated as a disk file. Support/plugin DSO loadinghost, ancestry/namespace and actual planned load role SHALL be independently declared or remain BLOCKED; --list of a fake executable does not prove dlopen context. ROOT static/type2/no-interpreter/no-needed/no-PLT and ET_REL data rules stay unchanged.

### FR-3 — Ordinary owned process and separate qualification
Future query jobs SHALL use the already reviewed ordinary resource ownership pattern: prelinked actual process/PIPE/selector holders before constructors, protected post-creation observations, fixed120s total including retirement with preserved2+2 cleanup phases inside that total and no extension/restart, combined2MiB logs, independent once-close attempts, strongly retained UNKNOWN and all original primary/cancel objects. No PID/FD-number reconstruction or native-family authority follows. Actual tool exit/stdout/stderr and same-run fences SHALL be preserved. Primary glibc2.41 rtld source puts normal --list exit before target relocation/entry/init, but audit modules can initialize earlier and LD_DEBUG=unused selects relocation; required guards may not be omitted. Trusted loader's own execution is a separately authorized ordinary operation, not absence of native code. Specification/impact/peer direction and root manual-HIGH disclosure precede implementation; fresh source/control/runtime seal and independent startup ALLOW precede root-authorized actual query. Wholecompiler, ROOT execution, bridge import/factory, native14, original method/488, CI/install/publisher/release remain unauthorized.

## 非功能需求

Bound query admission/control files and dependency facts to4096 files/512MiB total/128MiB per file; no environment package, host/proc raw, ASLR addresses or process IDs in public source-only backups. Same current source and earlier failed raw remain immutable. A successful --list fact is not all later Python imports or plugin-runtime closure, compiler completion, native family/IO closure or release qualification.

## 依赖关系

Actual sealed loader/ELFs, official Debian2.41-12+deb13u3 selected primary source, strict output/admission parser, ordinary owned query controller, directory/negative-candidate and cache/native input fences, declared plugin host roles and future root authorization. Mechanism/query source absent; no queries executed.
