# Design: Linux package provenance and scoped RELRO preservation

## 概述
This design covers FR-1 through FR-8. M is fd7b303839aa648d33456f7aaeec6388bfb696c4, tree e4ab19e2fe4bfbb1fef9e0cd713a6fbb18d03995. It combines one production packaging correction with the existing compiler collector and installed harnesses in one necessary build. Existing current-D evidence informs the design but is not new-candidate proof.

No Rust application/link change or DEB search-path change is needed. The evidenced AppImage contract already launches through AppRun. A narrow PATCHELF wrapper preserves exact authenticated inputs rather than adding RUNPATH to them; dependency discovery/copying and all other legitimate original-tool operations remain.

## 技术方案
- SourceRoot: authenticated checkout
- BuildEvidence: RUNNER_TEMP/linux-rc-evidence, outside source
- CompilerEvidence: BuildEvidence/compiler, fresh and collector-owned
- TargetRoot: RUNNER_TEMP/linux-rc-provenance-target, fresh external Cargo target
- OriginalsRoot: RUNNER_TEMP/appimage-originals, existing five original tools
- PackagesRoot: RUNNER_TEMP/linux-rc-packages
- GuardRoot: CompilerEvidence/appimage-relro
- AppDir: TargetRoot/x86_64-unknown-linux-gnu/release/bundle/appimage/Coding Tools MCP.AppDir

Profile is exactly linux-engineering-packages-v1. The existing executable collector adds collect-linux and verify-linux dispatch; engineering-only code lives in linux_package_provenance.py and linux_package_provenance_contract.py. Historical collect/build_environment/tool resolution, Cargo argv, source defaults, link/probe/DEB algorithms remain unchanged. One existing verification tail is shared within the old contract without copying its algorithm.

The single engineering command is:

    npm run tauri -- --verbose build --config src-tauri/Ubuntu桌面v1.json --bundles deb,appimage --target x86_64-unknown-linux-gnu --runner SourceRoot/scripts/desktop_glib_build_evidence.py -- --locked --message-format=json

Global --verbose retains pinned linuxdeploy diagnostics; Cargo JSON is captured separately. The strict child environment adds only APPIMAGE_EXTRACT_AND_RUN=1, exact LDAI_RUNTIME_FILE, PATCHELF=SourceRoot/scripts/appimage_relro_guard.py, APPIMAGE_RELRO_CONFIG=GuardRoot/config.json and its actual SHA256. Reject inherited guard/compiler/target/profile and unknown loader overrides; recognize only the authenticated setup-Python input described below, without forwarding it into compiler children; do not forward the CI environment or add a PATH shim, LD_LIBRARY_PATH or NO_STRIP override.

## Single-build state flow (FR-1, FR-3, FR-4, FR-5)
1. Existing prerequisites/full regression keep their semantics; logs move to BuildEvidence. Regression failure remains failure even when diagnostic packaging runs.
2. Create fresh target/evidence, acquire existing fixed GLib/audit inputs, resolve real tool identities and prepare unchanged AppImage pins/cache under the controlled environment.
3. Stage original patchelf and initialize the immutable guard config/lock/journal. Authenticate fixed host GLib inputs before the expensive build.
4. Existing cargo_runner captures events/traces and copies desktop.elf/glib.rlib. The sole bind_compiler writer then seals compiler-binding.json before returning to Tauri.
5. Original beforeBundleCommand and packaging run once. The scoped wrapper handles original-tool calls. No product rebuild, alternate dependency resolver or launcher replacement occurs.
6. Verify original tool pins, restored target executable, raw-DEB marker binding and actual AppDir/final-image ELF inventory. Prepare final packages from the authenticated external target/triple; retain raw-DEB and repacked-RC-DEB identities with identical payloads.
7. Verify guard state/journal, final protected bytes and RELRO before successful package upload/readiness. Failure evidence remains uploadable separately.
8. Write PackagesRoot/provenance-inputs.json with package/member/guard identities; CompilerEvidence/envelope.json binds it and compiler evidence. Copy that exact envelope to PackagesRoot/compiler-envelope.json after sealing, avoiding a digest cycle.
9. Existing installed jobs consume exact artifact ID/attempt and trusted envelope digest. The existing Ubuntu24 DEB row performs independent data-only compiler/guard replay after its original behavior checks; no extra product-build job.

## Protected inputs and original tool (FR-2, FR-3)
Exact protected paths are main usr/bin/coding-tools-mcp-desktop plus these eight regular files:
- usr/lib/libglib-2.0.so.0
- usr/lib/libgmodule-2.0.so.0
- usr/lib/libgio-2.0.so, .so.0 and .so.0.7200.4
- usr/lib/libgobject-2.0.so, .so.0 and .so.0.7200.4

Signed Ubuntu input is libglib2.0-0_2.72.4-0ubuntu2.10_amd64.deb,1468764 bytes,SHA256 b82973c5d9698e48297000e74d2dc7431e726db8f0f948ea56be7f9e4c9e66fb. Original library identities:
- glib1281808 bytes:86acf2c843bcfaf5e8c24ab959737960c797da53b41658dc8ec6f257c786048c
- gio1932688 bytes:b63a477916c1f95de4b2c80bb4f5940a59ebc5860793d93b271448e90edbfe52
- gobject387464 bytes:05a94d6be0a50dba15a579f3ad1f5c6ec12c8d303f3b715a665fd27824ca523e
- gmodule22736 bytes:1019fc28ced6829f22b446a091ecb5b76b9fa3b3c458bc6ea936c1d328302cb5

Main expected bytes are the same-run retained compiler ELF with its unique __TAURI_BUNDLE_TYPE_VAR_UNK changed only to __TAURI_BUNDLE_TYPE_VAR_APP. Reuse unchanged DEB marker/range controls on an in-memory DEB-marker view, then require direct exact APP equality. Do not use current-D hashes or section-only equality for new acceptance.

Add only official Ubuntu squashfs-tools to existing apt prerequisites. /usr/bin/unsquashfs reads the already fixed original linuxdeploy through its authenticated descriptor at offset193728. Bounded numeric listing must establish one regular usr/bin/patchelf, directory parents, no ambiguous paths. Fixed single-file cat stages1029016 bytes,SHA256 c15c1282d9dadcaaf5e492c0ee5f929d34453f8af759cc4aadad03b5b65df879. Authenticate before making the owned derivative executable; no new downloaded backend, system-tool replacement, archive self-execution or full-tree extraction.

Run bounded original-tool read-only and disposable setter compatibility probes inside the next authorized build; mocks do not replace them. Keep originals and .tauri inventory unchanged. The staged backend is static amd64 ET_EXEC without PT_INTERP and is executed through its authenticated descriptor, preserving original argv.

## Scoped operation and failure contract
The only success without delegation is exactly three argv elements: --set-rpath, $ORIGIN/../lib for main or $ORIGIN for a protected DSO, and its exact authenticated canonical AppDir destination. Authenticate ownership, mode, one-link regular file, held parent/leaf descriptors, stable bytes and current named identity. A protected-looking wrong target/hash/request/mutation fails before touching bytes. Extra family aliases reject scope; they never broaden suppression.

Queries and legitimate unprotected calls preserve original argv, cwd, environment, streams and exit/signal. Parse original0.8's first-nonoption operand semantics, including recognized value-taking options; do not assume the last argument is the filename. Unprotected mutations stay in the owned AppDir and cannot alias protected inodes. Reject preexisting filename_patchelf_tmp; original0.8's writer renames its temporary file, so a verified new inode after successful delegation is legitimate. Queries must not change identity. This is owned CI state with race checks, not isolation against a hostile same-UID actor.

Guard state is prepared -> active -> sealed, or sticky failed. Config is immutable; compiler binding is exclusively written after verified compiler copies. State/journal use exact schemas, keys/types and strict JSON; self-declared pass flags grant no authority. Each whole invocation holds the owned flock and records fsynced begin/end with one sequence, config/binding hashes, process identity, exact argv/decision, file/tool records, stream identities and actual exit/signal/error. Failed/pending calls cannot be erased by later successes. A create-once failed.json and exact guard failure prefix supplement journal replay. Atomic state-summary replacement is only a convenience; replay is authoritative.

Pinned linuxdeploy may swallow setter/query failures. Finalization requires exact INFO-setter/journal bijection, reconciles DEBUG selectors only when emitted, replays every recorded query and rejects every recorded failure, pending event, sticky marker and visible error diagnostic. Recursive INFO-only calls remain valid. All nine AppDir/final-image byte and RELRO checks and the dependency-inventory comparison remain mandatory. independent_all_query_attempts_verified is always false: a pre-wrapper recursive query-launch exception may be unobserved. Original recorded nonzero, timeout, missing log, changed bytes or incomplete state cannot become a successful package.

Fixed caps: parser30s wall/20s CPU/256MiB memory per call,1MiB listing/64KiB stderr and exact extracted-file bytes; config/binding32KiB each,state16KiB,failure4KiB,final1MiB; journal32MiB,4096 calls/8192 events,32KiB/event;64 argv strings/16KiB total,4096-byte paths;256MiB/ELF,16GiB total guard hashing;30s/call/lock and900s cumulative guard duration. Child streams≤1MiB each. No option raises these bounds.

RELRO verification checks bounded ELF64 little-endian amd64 headers, one PT_DYNAMIC in valid LOAD mapping, declared/effective4096-byte GNU_RELRO coverage, no writable alias escaping protection, and retained BIND_NOW/NX/PIE appropriate to the original. Preserve exact original headers through whole-file equality. A GNU_RELRO header's mere presence is insufficient.

## Installed runtime observations (FR-6, FR-7)
One directly used linux_runtime_provenance.py supplies attach/checkpoint/finish plus data-only verification. A private spawned observer owns only its own worker/query processes, with bounded control messages, cancellation-safe shutdown and exact signal propagation; original product cleanup remains protected by its own finally paths. Existing startup Popen and Linux NativeSession driver Popen are the anchors. Discover actual desktop/WebKit descendants using PID/start-time/ancestry; driver PID or process name is not product identity. Separate both native sessions and finalize every constructor/error/restart/close path without masking existing cleanup failures. Windows receives no new behavior or observer keyword.

Capture bounded raw maps plus executable/library backing-file identity at checkpoints while mount/extraction exists. Open a file in the observed process's filesystem view, require device/inode match and stable descriptor/process/mapping rechecks. Record inaccessible/deleted/ambiguous/transient mappings honestly; do not add capabilities, ptrace settings, sudo observation or sandbox bypass. Sampling is not an atomic snapshot or complete lifetime closure, and file identity is not relocated-memory hashing.

Keep an explicit loader/GIO/GTK/AppImage environment projection only, never complete environ/cmdline/credentials. Preserve original inherited behavior; relevant unexpected overrides block a baseline-resolution claim. Dpkg ownership/version is separate from official archive-byte correspondence. Record host ownership before and after WebDriver installation. Successful ldd output remains diagnostic. An unobserved TLS module remains unobserved under the existing local-HTTP fixture.

Observation caps:250ms discovery,1Hz mappings plus checkpoints; existing20s startup windows/native≤900s;128 owned process identities,512 unique ELF files;1MiB/8192 maps rows per process,4096-byte paths;256MiB/file,8GiB total unique hashing;128MiB raw maps/256MiB complete evidence per job. Limits latch incomplete/failure, never truncate into success. Required desktop/helper mappings cannot pass as an empty result.

## Compatibility and remaining claims
The original four installed rows retain all startup scenarios before driver installation, twelve native stages,100 foreign requests, real pending expiry, permission clicks, screenshots, restart/drain, secret scans and cleanup. No tests/actions are replaced or replayed by observation.

GTK recursion inherits PATCHELF. Its copies/symlinks/WebKit substitutions continue. Optional GStreamer remains disabled and absent from the reviewed hook/helper contract; no PATH shim silently covers its direct calls. Unknown dependency-copy differences require review: preserve full verbose diagnostics and compare final inventory to current-D evidence without pretending it is an atomic copy trace.

Protected byte/RELRO flags may become true only after exact verification. Other-DSO protection, full closure, native-linker consumption, retained GLib code, security, release and publish approval remain false/unproved. Current-D and historical PR113 proof never certify the new source.

## 文件结构 (FR-8)
34 paths:19 additions and15 replacements; final1724 entries. Aggregate added+deleted cap8500, with per-path sum8851. Modes below are exact; all existing modes stay unchanged.

| Path | Mode | Final lines | Added+deleted |
|---|---|---:|---:|
| .github/workflows/linux-rc-packages.yml | 100644 | 400 | 260 |
| scripts/desktop_glib_build_evidence.py | 100755 | 350 | 65 |
| scripts/desktop_glib_build_contract.py | 100644 | 500 | 140 |
| scripts/exact_build_audit.py | 100644 | 430 | 5 |
| scripts/linux_package_provenance.py | 100644 | 450 | 450 |
| scripts/linux_package_provenance_contract.py | 100644 | 460 | 460 |
| scripts/rc_packages.py | 100644 | 270 | 110 |
| scripts/AppImage入口配置v3.py | 100644 | 500 | 330 |
| scripts/AppImage入口回归v3.py | 100644 | 180 | 12 |
| scripts/linux_startup_candidate.py | 100644 | 300 | 90 |
| scripts/Ubuntu原生验收v1.py | 100644 | 400 | 90 |
| scripts/跨平台原生驱动v8.py | 100644 | 310 | 55 |
| scripts/exclusive_native_acceptance.py | 100644 | 440 | 115 |
| scripts/preliminary_package_contract_tests.py | 100644 | 100 | 35 |
| scripts/linux_runtime_provenance.py | 100644 | 500 | 500 |
| scripts/linux_package_provenance_tests.py | 100644 | 460 | 460 |
| scripts/linux_package_binding_tests.py | 100644 | 400 | 400 |
| scripts/linux_runtime_provenance_tests.py | 100644 | 500 | 500 |
| scripts/linux_runtime_workflow_tests.py | 100644 | 300 | 300 |
| scripts/appimage_relro_tool.py | 100644 | 370 | 370 |
| scripts/appimage_relro_guard.py | 100755 | 440 | 440 |
| scripts/appimage_relro_contract.py | 100644 | 495 | 495 |
| scripts/appimage_relro_tool_tests.py | 100644 | 360 | 360 |
| scripts/appimage_relro_guard_tests.py | 100644 | 480 | 480 |
| scripts/appimage_relro_contract_tests.py | 100644 | 480 | 480 |
| docs/specs/linux-package-provenance-relro/requirements.md | 100644 | 150 | 150 |
| docs/specs/linux-package-provenance-relro/design.md | 100644 | 260 | 260 |
| docs/specs/linux-package-provenance-relro/tasks.md | 100644 | 200 | 200 |
| scripts/rc_pretag_linux_package_profile.py | 100644 | 360 | 360 |
| scripts/rc_pretag_linux_package_inverse.py | 100644 | 320 | 320 |
| scripts/rc_pretag_linux_package_cases.py | 100644 | 500 | 500 |
| scripts/rc_pretag_publication_profile.py | 100644 | 500 | 5 |
| scripts/rc_pretag_appimage_profile.py | 100644 | 180 | 4 |
| scripts/rc_pretag_appimage_cases.py | 100644 | 440 | 50 |

## Finite source admission
Use D[M], ordered I[M,D] with complete identical D tree, and ordered J[R,I] with exactly four pinned R documents. R=e2e011f7f2a3a1df838bbd588106205b999db610, treec0dfe00fdcc7ebc8e26acaad5d18ff3f94df9ba3. No arbitrary ancestors, correction chain or same-tree impostor anchor is accepted.

A five-line dispatcher keeps publication_profile at500 lines. Only topology mismatch permits fallback; selected content errors remain terminal. A two-line prefix in inverse_appimage_adapter handles the new exact inverse; publication_adapters remains byte-identical. Historical AppImage cases receive only eight approved source-read normalizations, with full inverse/assertion preservation. Fixed source mode/blob/SHA256/size/line pins are frozen after implementation, not derived during admission. External exact-source review binds the profile itself. No production cache; fixture-only immutable-M reuse is exact-root/ref/callback/argument-bound, defensive and excludes altered candidates.

## Validation
- Unique intended inventory1174: original815 + mandatory affected223 + provenance68 + RELRO48 + composition20; sorted-ID SHA256 a40dee60873940221d23eca3b5e8af13e260f57bcbbbd72c7a77de72c93fa90a
- New groups: CompilerIntegrationTests20, PackageBindingTests12, RuntimeMappingTests16, RuntimeLifecycleTests12, InstalledWorkflowTests8, RelroToolTests12, RelroGuardTests20, RelroContractTests16, LinuxPackageCompositionTests20
- Actual D runs all1174 once after focused implementation checks. Faithful I/J run835 original/structural cases each; unchanged supplemental/functional evidence stays explicitly D-scoped, rerun only when impact or failure warrants it
- Existing hosted strict303/consumer452/contracts755 remain unchanged. The single necessary native build retains original Rust/frontend/native behavior, genuine compiler observations, original three real-byte mutation controls and all four installed results
- Fresh source/impact/spec/security review, staged scope detection, gencommit, exact source/test inventories and authenticated final artifacts precede normal feature integration. No main/release/final approval follows

## Actual runner compatibility correction
The shared preliminary command check remains importable on Windows: resource is loaded only by the Linux parser-limit entry, which fails explicitly on unsupported platforms. Existing Linux resource bounds stay exact. An explicit empty observer environment remains empty instead of inheriting runner values.

The measured hosted setup-Python lib directory is world-writable (full mode0o40777), so it cannot be admitted as a safe inherited loader path. setup_python_library and its0o7022 rule remain byte-identical. Only explicit engineering omission call sites may identify the exact selected CPython3.12 input to remove it: canonical installation/version/interpreter bytes and held no-follow directory identity remain required. Unknown/alias/multiple/present-empty LD values and preload/audit/debug/GIO/GTK overrides fail. Neither the original record nor the omission record authorizes loading or claims immutable hosted-toolchain closure.

Bindings/envelopes require python_loader=null and python_loader_omission={schema:"setup-python-omission-v1",input:<the existing five-field loader record or null>,original_ld_library_path:<exact input path or null>,child_ld_library_path:null,loading_authorized:false}. The outer object is always present; null input denotes an absent original key. setup_python_omitted validates this closed removal evidence; omit_setup_python_input copies a bounded projection and removes only the exactly matching LD key. Default capture_setup_python_loader remains strict; omission=True is selected only by reviewed call sites. The build's original executable still matches tools.python; installed evidence records its own current job.

Every existing startup and native harness invocation uses a subshell: builtin variables save original LD presence/value, builtin unset removes it before the Python checker starts, and successful project-harness-input is followed by exec of the unchanged harness command. The parent environment, AppRun bytes/general inheritance, arguments, cases, native PATH choice, signals, pipefail and cleanup remain unchanged. The checker requires its real current environment LD-free, reconstructs supplied original presence/value only as data, re-observes the selected Python and binds the exact original record. No arbitrary command is launched by the checker and no path is added. Its own successful execution is actual selected-Python LD-free startup evidence.

Each EVIDENCE_DIRECTORY/<phase>-launch-projection.json has exactly schema="linux-harness-projection-v1", phase, binding_sha256, omission, original and projected. Phase is startup-<one of the four existing cases> or native (shared by sessions1/2). The binding digest is SHA256 of json.dumps(binding,sort_keys=True,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode('ascii'). Original/projected use existing ENV_KEYS/value/total bounds; the proof is at most64KiB. Runtime construction and data-only replay join phase/digest/omission and actual harness projection; product launch remains LD/GIO-free except AppRun's existing bundled prefixes. Required binding/projection errors stop before product launch, without fallback to original inherited input. Pure helpers stay in the Python3.10-compatible entry module; no compiler/tomllib import is added to the observer. Same34 paths/caps/1174 IDs remain; security/release/publish/closure claims remain false.

The existing mandatory12 package-binding cases still run once immediately after setup-python, using only selected Python and Ubuntu dpkg-deb. Existing bounded failure-only capture diagnostics and original strict rejection remain for unrecognized inputs. Official-image preparation is not substituted for measured metadata. The shared command fixture uses native pathlib formatting and its system-Python assertion binds the same PATH prefix with explicit exec; all original case IDs/assertions retain their intent.

## Guard interpreter correction
The guard alone executes fixed /usr/bin/python3 -BES, resolving exactly to root-owned mode0755 /usr/bin/python3.10. tools.guard_python has exactly path,version,sha256,size,mode,uid; capture observes stable executable bytes/metadata before and after a bounded LD-free version query, and pure replay binds this independent identity to config. Compiler tools.python and selected PATH remain CPython3.12; no hosted executable permission rule is relaxed. The guard import closure loads TOML only inside existing audit/configuration functions, preserving all audit decisions.

The existing20 guard cases run once in an early required step: a scoped subshell retains original LD presence/value as data, builtin-unsets it before selected-Python exact-input omission validation, then execs /usr/bin/python3 -BES with the original test script. Unknown/empty/alias/multiple input fails before execution. Actual Ubuntu3.10 executes the import/guard cases in focused validation; syntax checks alone do not establish compatibility. The only scope addition is exact_build_audit.py (final430,delta5);34 paths and the1174 test inventory retain all other caps and held paths.

## Actual Ubuntu SquashFS parser preflight
The measured official Ubuntu22.04 squashfs-tools1:4.5-3build1 help renders some supported full flags with bracket abbreviations. Capability validation accepts only the finite anchored literal/full and observed bracket tokens; every capability, fixed executable/package identity and all parser argv/resource bounds remain required. The real official binary must pass the unchanged full list/cat commands on the authenticated AppImage before this correction is frozen. Immediately after the existing apt install and before long prerequisites/Rust, the workflow calls the same parser_identity inside the existing environment context with exactly PATH=/usr/bin:/bin, LANG=C and LC_ALL=C, so parser/dpkg children receive no setup-Python loader input. Parent environment and selected compiler3.12 remain unchanged; no job/helper/test ID is added.

### Exact original-backend mutation diagnostic
The pinned patchelf0.8 succeeds on the owned mutation probe but emits its exact4096-byte Linux-kernel-hole warning. The producer and data-only replay share one closed predicate: only call index2, exact --set-rpath/$ORIGIN/canonical owned mutation path, exit0, empty stdout, and the full expected stderr bytes are eligible. Before bytes must be26936 with SHA25694f5d1c6ad51bbd532bf2e702b3d28cb57ba8887435b4514a06e4ba0cd7fedba; after bytes must be34680 with SHA2560368ae5de963c8931adc05c65d4222434321314a4c0e2e1e25053fab2e039b19. The subsequent readback must return exactly $ORIGIN plus newline, empty stderr and unchanged after identity. A general warning family, growth threshold or other hole size is insufficient.
All other stderr and every nonzero/error remain fatal; the existing empty-stderr behavior remains. Keep the exact raw bounded diagnostics so an unexpected outcome remains inspectable. This classification concerns only disposable compatibility-probe copies, and makes no production RELRO acceptance inference or change to normal backend delegation, protected files, archive flags, byte pins or resource limits. Existing12 case IDs cover the exact positive pair and forged operation/path/stream/hash/size/exit negatives; the real four-command replay is retained as source-specific evidence.

### Exact core-library media classification
D7's actual AppDir and final-image dictionaries contain the existing usr/lib/libgstreamer-1.0.so.0 core DSO, not the optional GStreamer plugin route. Admit only that exact path as file mode0644, integer nlink1, size1430064 and SHA256578881fac71165c3cc61a24e71f41f5c9d40da432284ca39e8ca550cff8c8fb7, with strict field types. No family/prefix/version allowance is added. Actual pinned Tauri enabled only the GTK plugin and the identity matches the retained baseline.
The existing tree walk must enforce the shared media policy before skipping directories or non-ELF files: reject optional plugin/helper/hook paths, empty optional directories, non-ELF core-name impostors, media-named symlinks, and lexical or fully resolved media alias targets. The final pure replay repeats the same policy, including normalized link targets. Keep the original inventory schema, all path/byte/count caps and nine protected-file rules. Existing contract case IDs cover exact-core success plus changed identity/type/mode/link/path and real walker/alias negatives; no media feature or runtime-library acceptance claim is enabled.
After the reviewed correction, offline D7 remaining-gate checks are diagnostics against retained actual data. Missing envelope/provenance/final receipts stay missing; no reconstructed context is original CI proof. Final fresh candidate checks and installed lanes remain mandatory, and the PR/strict cancellation hold remains unchanged.

### Stable-product runtime observations
The positive runtime claim is limited to a mandatory stable-product epoch opened by the existing first-window or native-ready checkpoint. Retain every bootstrap PID/start/executable version and unknown fact; no basename authenticates a transient process. Real desktop, WebKitWebProcess, WebKitNetworkProcess and native-driver observations remain mandatory. Missing required roles, exhausted retries, unresolved executable/file-backed mappings and empty observations stay failed. An EGL-aborted WebProcess cannot become an accepted bootstrap gap.
Recognize only the measured non-executable shared 00:01 /SYSV00000000 (deleted) and /memfd:WebKitSharedMemory (deleted) tuples as shared-memory observations; retain raw rows and explicitly unobserved bytes. Accept only the existing pinned AppRun hook's exact GTK_PATH=<bound APPDIR>//usr/lib/gtk-3.0 projection; inherited GTK, DEB GTK, alternate spellings and other loader overrides still reject. AppRun and parent environment are unchanged.
Keep descriptor/maps/process identity rechecks short. Move bounded exact-path same-phase dpkg ownership enrichment outside that interval, with full identity checks and finite query/argv/output/time budgets. Retry transient capture churn finitely and transactionally, retaining failed attempts, raw/hash work and file references. No pending ownership result, abandoned verified-file claim or hidden uncertainty may pass.
The observer control loop must retain stage history and remain responsive to final capture. Only its own SIGTERM path uses the existing handler so finally can retain bounded partial progress; nonzero/timeout errors, the ten-second stop bound, TERM/KILL escalation and original product cleanup remain. Capturing a failure does not establish its slow operation.
Move pure same_process, maps parsing, package origin and receipt replay plus needed constants into the existing Python3.10-compatible entry module, preserving runtime reexports without circular or compiler/audit imports. Runtime remains500 lines; entry500/delta330, runtime tests500 and workflow tests300. Preserve all1174 IDs and the8500 aggregate ceiling.

### Pre-driver Mesa EGL prerequisite
Add only official Ubuntu libegl-mesa0 to the existing pre-driver runtime apt list. The AppImage supplies an EGL dispatcher but needs the host Mesa vendor implementation; the observed Ubuntu22 job received it only during later WebDriver installation. Keep WebDriver installation after all four raw startup scenarios, all actual native stages and mandatory WebProcess runtime evidence. This does not relabel the failed D8 EGL startups or change the project launcher, graphics environment or security settings; a fresh installed run must establish the fix.
