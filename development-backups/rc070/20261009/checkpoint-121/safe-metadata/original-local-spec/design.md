# Design

## 概述

Corresponding requirements FR-1 through FR-5. Design only. Replace the previous remote branch entry with explicit fixed-native acquisition/owned payload staging, then invoke the original local branch once. There is no second full restoration and no new publication capability.

## 技术方案

### Ownership and IO

Prepare and strongly retain an explicit payload frame BEFORE each effectful constructor/read/write call, with immutable expected bytes/role and operation state. The actual returned object is linked to that frame immediately before any subsequent operation. If no return is observed or cancellation occurs before linkage, classify UNKNOWN, retain all already-known objects/frame/input and never fabricate the missing FD/object; this is not a claim Python assignment is atomic against signals. The writer uses exclusive unbuffered file creation, actual returned object and actual FD identity/noninherit readback; chunk<=65536 partial writes advance only actual count, zero/bool/oversize counts fail. Check size/hash/mode/file identity and known closure independently. Every readback/close/cancel failure records the actual original error, attempts other returned resource closures once, and retains UNKNOWN frames. No file object/HANDLE is reconstructed after no-return. Preserve actual created directory metadata separately; directory31 roles are snapshots under disposable-host assumptions, not parent pin capability.

Canonical payload root/source paths plus FULL43-FROM-EXACT73.patch exactly match the existing local branch convention. The Git/source mode for each73 is100644; data-input physical0600 intention is a distinct role. Windows ACLs are not derived from Unix mode. Actual whole inventory rejects extra/missing/symlink/reparse/hardlink data inputs; original Reader sees only genuinely prepared fixed regular bytes and remains byte/AST unchanged. Source before/after and input before/after compare real current identity/bytes, not a historical receipt.

### Exact native request vectors

| Stage | Actual code static path groups | No-error static count |
| --- | --- | ---: |
| management before | ownHEAD1 + originalHEAD1/7ls-tree + six/v12 ls-tree/show14 | 23 |
| new fixed acquisition | two immutable backupfetch2 + exact73show73 + patchshow1 | 76 |
| new owned payload creation/validation | 74files/31directory roles, fixed592919B; no Git request | 0 |
| original local branch validation | retained73 check_blob + patch bytes/SHA; no Git request | 0 |
| original local restore native body | clone/config/checkout/read-tree4 + hash/update146 + exact73 write-tree/tree_rows2 + applycheck/apply2 + final write-tree/checkout-index2 + original fullverifier4 | 160 |
| existing overlay/augmented before | fetch/show/hash/update/checkout5 + original augmented verifier4 | 9 |
| existing after | augmented4 + management23 | 27 |
| unchanged normal total | 23+76+160+9+27 | 295 |
| proposed source pool/ref before+after | each cat-file batch-all-objects/batch-check1 + for-each-ref1 | 4 |
| original negative badsource/badpatch/preexisting | rejection before native calls, not a claim if unexpected branch is reached | 0 |
| proposed total upper on expected path | 295+4 | 299 |

This vector has failure-path early lower0 per stage and planned upper as listed; it is not genuine executable WinAPI/Git process count. Mandatory after reservation29 (existing27+poolafter2) must remain available independently. Actual pending reservations/raw/elapsed budget is unknown until current native observations. There is no new automatic retry when319/320 capacity is insufficient. Unexpected control behavior fails before Go; original syscall latency and Reader read_bytes are not claimed forcibly bounded.

### Named positive and negatives

The named original-local-full-restore positive is the single actual source preparation in source300s, not a second restore in ordinary120s. Its current same-run original outcome/native raw/full1953 checksum/input frame closures must be consumed before Go. Ordinary120s receives fixed input snapshot and makes at most three owned negative copies under its own output prefix, validates each, then corrupts one source byte or patch byte or uses an existing destination. Instrument the bound delegate with an actual call journal so original negative must have zero native calls; a callback exception must not hide original or cancel errors. These are actual Windows-host IO negatives only after native execution, never POSIX qualification. Newly strict hardlink/reparse/collision/close controls are labeled separately from the original branch.

No original local-payload positive credit arises until it actually runs; static160 body requests are not a substitute for real current native vectors. No helper count320 positive/negative credit arises from arithmetic/mocks or lower-budget fixture. Sourcefull1953/sourcefull1954 and management/runtime/pool/ref admissions must all be independently attempted after, even on cancellation. Original function bindings restored exact objects.

## 文件结构

Current source04 production sources stay unchanged for this proposal. Future scoped changes may occur only in authorized native_ci.py/native_controls.py/native_manager_controls.py/inputs.json: explicit owned writer/acquirer/full inventory, original local argument plus same-run typed outcomes, negative worker bounded fixed argv/input vectors and ordinary JSON parser/error controls. Native_job.py immutable source04 reuse; workflow remains disabled. Any new need/API/workflow activation goes to root scope review.

## 未闭合项

No code/native/Go/officialZIP execution. Positive300s vs negative120s scope must be specifically accepted in direction review; do not claim an original ordinary120s local positive. Current native count-overflow320 method still not run. OfficialZIP strictercaps not verified; source-mode/FD/volume info are not all OS/VMowner/issuer authority. Parent b0 proves first genuine meaningfulpush event channel, not current newsource activation or tests. Oldsource03/cp88 STOP evidence stays immutable; source04 finiteSOURCE PASS is not startup.

### Exact source-pool window

The two native pool/ref command pairs refer only to the prepared1954 SUT repository AFTER authorized original restoration and overlay mutation finish. Baseline its actual .git/objects file identities/hashes and native all-object/ref raw, then compare after current ordinary controls/Go and mandatory final fences. The management repository legitimately receives two fixed backup fetches and overlay fetch; its object pool/FETCH_HEAD can change then. Do not call it whole-pool unchanged across preparation. Management HEAD/original7/new6/v12 bytes still have their existing before/after guards; a future additional management-pool after-fetch baseline requires a separately counted design. Source snapshots remain trusted-host observations and no new grants.

### Acquisition and overlay expected mutable records

Record management repository .git/objects, optional FETCH_HEAD, HEAD and refs/packed-refs actual FD/metadata before acquire76 and after its two fetches; then a separately labeled before/after record for the third overlay fetch. Preserve actual hash/identity changes as observed phase deltas under the disposable-host assumption. HEAD/refs/managed source must remain exact; only known fetch object/FETCH_HEAD mutation scope is allowed, and uncertain or unexplained states deny. This does not prove exclusive causal attribution or claim every byte in the pool unchanged while native fetch runs. Original local160 creates a separate SUT and legitimately adds blob/tree/index/working source; record that expected process rather than comparing an immutable nonexistent pre-SUT pool. After overlay1954 completes, start the actual SUT immutable pool/ref baseline described above. The new management snapshots are bounded chunked owned FD snapshots, with no added native Git command; actual file count/bytes/time compatibility is UNVERIFIED and late/UNKNOWN close denies rather than increasing budget. No constructor/resource is fabricated or double closed.

### Fixed new snapshot FS caps

Per snapshot hard upper32768 regular files /1073741824 actual bytes total /536870912 per actual file /65536 read chunk; actual lower0 only for optionalabsent fields, owned .git/objects must be present. Existing native raw16MiB/2MiB and320 requests stay unchanged. Reject file metadata sizes beyond cap before open; reserve actual remaining bytes, reject returned transfer beyond request, preserve terminal failure bytes as private evidence but no PASS, verify EOF/count/FD/path identity and deadline then independently onceclose. Source-phase snapshots use its existing300 deadline, final snapshots after60, both minoverall2700; late/unknown/closecancel exactgroup. All possible seven manager/source snapshot roles (five management phase records and two source immutable boundaries) share explicit finite role inventory, never arbitrary repeated loops. New FS caps may reject an actual checkout; do not increase them to force compatibility.

## Binding cancellation narrow repair

The initial binding assignment was outside try. Failure-first ordinary103 uses the actual already-loaded frozen original guard module, a ModuleType subclass with real setattr before cancellation, and explicitly mocked platform/loader. It shows bind then cancellation and no restore, without any native process. The repair moves only this assignment inside the existing try/finally; original guard/run_git bytes and original-negative semantics remain identical. A restored assignment or restoration failure is retained independently of original primary/cancel. This control does not prove atomic immunity from all Python bytecode signal windows; it covers the declared binding-effect boundary and known object restoration.

## Shared source binding cancellation repair

Retain original guard bytes, ownedhelper name and transparent Gitbinding contract. Set guard._nt_bound inside try, then bind realdeclareddelegate. In finally originalfunction restoration and flagclear run in two independent try blocks with exact readback; firstsetter cancel does not suppress second attempt. Strong diagnostic frame holds actualguard/original/delegate when any requiredrestore is UNKNOWN, including effectthenerror. Body error preserves originalidentity even if bothrestores succeed. The flag is a Python sequencing guard, not grant, VM capability or source authority. Actual loadedModuleType failure-first119 shows flag-effect-cancel and restorationerror leak trueflag on source07; future repaired ordinary must prove twoattempts/groupidentity. No forced syscall interruption or allsignalatomic guarantee is claimed. A source-restoration namedreceipt is a limited actualfunction-return record; original native_positive NOTRUN preserves originalNT status and must never be reinterpreted.

## Same actual guard UNKNOWN is terminal

Independent clearFalse does not prove originalrestore known. Source08 prior64 flags controls retained sourceframe UNKNOWN but entry checked only boolflag. New failure-first131 actualModuleType restore setter mutates then raises, clearFalse succeeds, and old second binding invokes one ordinary no-native delegate. Entry refusal must compare actualguard object identity in retained UNKNOWN frames before effect; do not clear the frame, retry setter or turn binding metadata into authorization. This new refusal is only same-process guard safety and cannot certify native owner/family. UNKNOWN prevents later afterchecks from using that guard; they still attempt at outer boundary and record denial.
