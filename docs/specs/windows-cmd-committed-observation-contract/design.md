# 设计文档：windows-cmd-committed-observation-contract

## 概述
Covers FR-1..FR-6 and NFR-1..NFR-4. Rebuilt from exact e5b4d806/tree4849505c source and accepted-in-principle late-failure clarification. Existing Plan was resumed and expanded with full-spec/check/impact/root-review prerequisites before implement. Root approved exact preparation hashes and local implementation on2026-10-03 at02:54 after the HIGH warning; the original sealed preparation packet remains retained. Durable evidence includes current immutable-spans.json, source integrity and graph report. Earlier lost packet/index is not called verified.

## 技术方案
### 技术选型
Keep existing C# partial BrokerDirectLauncher, PowerShell5.1 and Python source audits. Reuse unchanged PilotCmdCaptureOperations, PilotCmdMinimalBatchBytes, CapturePilotCmdBatchCore, ReadPilotCmdCapture, PilotCmdNativeCaptureOperations, raw equality/hash and close/metadata helpers. New C# file adds no type or native import; new managed test file may add only one named injected trace class. New Python audit includes a pure artifact evaluator and synthetic fixtures, not a Windows lifecycle abstraction.

### Finite integration and immutable boundaries
1. Append cmd-cwd/cmd-read-direct to both ordered case lists; map only these exact cases to runtime cmd and apply the existing same-original-cmd byte check before actual-target verification. Required count becomes10; retain original6/sentinel1/batch1 and add cwd1/read1.
2. Extend only ValidatePilotPreparation's finite kind whitelist and PreparePilotSubject's runtime-copy/command/fixture prelude. Record exact command/cwd schema before allocation. Both use private code/cmd.exe, unchanged copy/hash process. New TYPE branch writes PilotCmdMinimalBatchBytes into workspace/direct.cmd and calls new exact-case pre-allocation capture adapter. Existing original/minimal adapters/commands remain unmodified.
3. Leave PilotSubjects.cs99-end verbatim: profile creation/checkpoint, ACLs, stdio rights/exact HANDLE_LIST, job, EnvironmentBlock, explicit CreateProcess(exe,...,environment,s.Workspace,...), all setup cleanup. No alternate launch route.
4. Leave PilotRunner.cs81-129 verbatim: actual-target query/duplicate/signature, ordinary witness, may-resume/assignment/resume, wait/queried exit, stop/drain/guard and original CaptureOwnedFile calls. Insert only `if(PilotCmdObservationKind(kind)) ReadPilotCmdObservation(s,evidence);` immediately after that frozen sequence and before unchanged ClassifyPilotCase.
5. The new raw adapter requires exact case/protocol/cmd/cwd identity, ownership certain, created/resumed target, confirmed ProcessStopped/JobDrained/individual stop-drain-close evidence and completed original mandatory captures. Read workspace stdout with original stdio identity, artifact stdout via its own measured identity, then similarly stderr. Compare exact arrays and require every read and close. All new handles are non-inherited readonly and acquired after inherited/process/job handles are closed; reuse existing same-handle1MiB/no-follow metadata guards. Set raw_complete only after all4 reads close and both source/copy comparisons agree.
6. Artifact-copy identities are independently measured/rechecked, not claimed pinned by the old writer. Original workspace reads remain bound to original stdio IDs. Missing mandatory files/uncertainty throw into existing fatal recovery path; actual output mismatch does not throw. No new raw file is written; existing stdout.txt/stderr.txt remain the byte artifacts.
7. Keep ClassifyPilotCase unchanged. Add a separate new reset line for the2 case raw flags in ClassifyPilotFacts, preserving old reset text. Route the2 new identities after unchanged outside-canary checks/old cmd routes and before ordinary/runtime generic path. New helper compares raw receipt facts, never normalized dictionary text. No old helper/reducer edit.
8. Leave existing case cleanup/journal/case.json code verbatim. Raw matched fields may stay factual after later case.json failure; Fatal/Status retain failure and accepted artifact results remain unavailable. This replaces the old proposal for a new fatal clear after case persistence.
9. New run raw reducers validate exact slots8/9 and raw contracts only; the raw-evidence predicate and reducers must not add late row.Fatal/scoped-cleanup/run-success requirements (those belong exclusively to acceptance). Initial classification still resets both new flags and returns on a fatal row; later failure does not rerun classification or erase measured raw facts. update them after every row and in catch alongside, without changing, all3 existing reducer assignments. No new accepted Passed field anywhere in producer receipts. Full cleanup count becomes10 and scope wording stays bounded. PilotMayAdvance governs continuation unchanged.
10. Leave run-root/final scan/pin-close/final write/bind/verify/Resolve/return sequence verbatim (published216-228), including no new statement after Resolve. Wrapper's old3 checks remain verbatim; append2 raw-match checks with messages explicitly referring to raw observation failure, no accepted-result persistence.
11. Existing diagnostic workflow only adds new source-audit invocation, managed test entry and truthful10-case label. Keep one pilot invocation, all7 old portable audits,6 old managed entries, metadata tests, Rust fmt/clippy/build, native foundation,20nested rows, always-capture/upload and failure semantics. No continue-on-error, new capability, setup action or host probe.

## 数据模型：exact producer schema

All new dictionary keys below are optional only on old/blocked/unprepared rows. Allocated new rows require every applicable key; absence never defaults to passing. Numbers are actual Int64 JSON integers, booleans actual JSON booleans, hashes lowercase64hex; no string/float/bool-as-int coercion. New fields default false/zero and are assigned only at their stated stage.

### Receipt members
- PilotCaseReceipt adds exactly `bool CmdCwdObserved, CmdReadObserved` (raw only)
- PilotRunReceipt adds exactly `bool CmdCwdRawObservationMatched, CmdReadRawObservationMatched`
- PilotRunReceipt RequiredCaseCount=10; existing OriginalPilotRequiredCaseCount=6, AdditiveSentinelRequiredCaseCount=1, AdditiveBatchRequiredCaseCount=1, OriginalNestedRequiredRows=20 remain; add `int AdditiveCwdRequiredCaseCount=1, AdditiveReadRequiredCaseCount=1`
- Existing phase/protocol fields remain. No CmdCwdObservationPassed, CmdReadObservationPassed or computed equivalent exists on any producer type

### New preparation Identities keys
- pilot_cmd_observation_protocol = `cmd-cwd-read-raw-v1`
- pilot_cmd_observation_case = exact cmd-cwd or cmd-read-direct, equal to row.Case and existing pilot_case_id
- pilot_cmd_observation_command = exact r.CommandLine, derived only by that case's fixed builder from r.Executable
- pilot_cmd_observation_cwd = exact coordinator s.Workspace; validate unchanged PilotOwnedPath syntax and ordinal equality with Path.GetFullPath(s.Workspace), require terminal workspace leaf/layout; never normalize stdout to fit
- Existing pilot_original_cmd_sha256 and pilot_cmd_same_binary_verified are reused for same-run executable equality, not new fields
- TYPE reuses existing minimal source/destination/readback receipt keys solely after its new exact-case adapter succeeds; old adapters still reject the new case ID

### New raw-stage keys
Identities:
- pilot_cmd_observation_stage = `after_target_stop_and_job_drain`
- pilot_cmd_observation_expected_sha256 = hash of exact expected bytes only when expectation supported; absent for unsupported non-ASCII cwd
Numbers:
- pilot_cmd_observation_expected_supported =1 for TYPE or strict ASCII cwd;0 for non-ASCII cwd
- pilot_cmd_observation_expected_bytes =9 for TYPE, exact ASCII cwd byte count+2 for cwd, or-1 when unsupported
- pilot_cmd_observation_raw_complete =0 initially,1 only after all4 raw reads/close outcomes and two source/evidence comparisons succeed
- pilot_cmd_observation_stdout_matches =1 only for exact expected bytes with supported expectation, else0
- pilot_cmd_observation_stderr_empty =1 only for zero bytes, else0

For each fixed label `pilot_cmd_stdout_source`, `pilot_cmd_stdout_evidence`, `pilot_cmd_stderr_source`, `pilot_cmd_stderr_evidence`, reuse the existing strict raw-reader-generated shape:
- Identities[label] = nonempty volume:indexHigh:indexLow; source labels must equal original stdout/stderr identity; evidence IDs measured then revalidated
- Identities[label+_path] = exact respective workspace/evidence file path
- Identities[label+_sha256] = actual read SHA256
- Numbers[label+_open_error]=0, _desired_access=2147483648, _handle_flags=0 (from unchanged native open)
- Numbers[label+_advertised_bytes] and _bytes equal actual count in0..1048576
- Numbers[label+_read_confirmed]=1, _close_confirmed=1, _close_error=0; any close_exception or missing result makes raw_complete unavailable
- Equal source/evidence count/hash plus actual in-memory byte comparison is mandatory. Empty stderr SHA256 is e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

### New classification statuses and invariants
Exactly `cmd_cwd_raw_observed`, `cmd_cwd_raw_not_observed`, `cmd_cwd_expected_encoding_unsupported`, `cmd_read_direct_raw_observed`, `cmd_read_direct_raw_not_observed`; existing deadline_exceeded/fatal error statuses stay applicable. CanaryClassification is `cwd_observation_did_not_attempt_runtime_canary` or `read_observation_did_not_attempt_runtime_canary`.

Raw positive requires exact case/runtime/protocol/command/cwd/executable/original hash, required raw facts, TYPE minimal capture proof, AuthorityObserved/PreResumeReady, successful creation/assignment/resume, existing PilotStdioClosed, unchanged method-diagnostic failures and TokenVerified=false, WAIT_OBJECT_0 plus explicit pilot_exit_query_success=1 and Exit=0; mandatory outside unchanged/no-write checks remain. Never re-run VerifyPilotSignature on terminal Assigned/Resumed receipts; its pre-resume condition correctly rejects them. Raw case classifier resets all unrelated positive/entry/mutation/offline/native/network/cmd-sentinel/batch flags. Test missing observed-policy evidence separately from intentionally false TokenVerified.

## API 设计：finite new symbols

New PilotCmdObservations.cs functions (12):
1. PilotCmdObservationKind(string kind)
2. FixedPilotCmdCwdCommand(string privateCmdExe): Quote(exe)+literal ` /d /q /c cd`
3. FixedPilotCmdReadCommand(string privateCmdExe): Quote(exe)+literal ` /d /q /c type direct.cmd`
4. CapturePilotCmdReadBatchUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops): exact cmd-read-direct/fresh unallocated subject guard, then unchanged CapturePilotCmdBatchCore(...,true)
5. CapturePilotCmdReadBatch(QualificationSubject s,string evidence): unchanged operations-factory wrapper
6. PilotCmdObservationExpectedBytes(string kind,string exactWorkspace): TYPE fixed9bytes; cwd validates path and returns exact ASCII+CRLF or null for non-ASCII, never transliteration
7. ReadPilotCmdObservationUsing(QualificationSubject s,string evidence,PilotCmdCaptureOperations ops): fixed4 raw reads and exact complete receipt
8. ReadPilotCmdObservation(QualificationSubject s,string evidence): native factory wrapper after stop/capture gate only
9. PilotCmdObservationEvidenceVerified(PilotCaseReceipt row): pure raw/provenance/observed-execution predicate
10. ClassifyPilotCmdObservation(PilotCaseReceipt row): pure classification with exact status/raw-only fields
11. PilotCmdCwdRawMatched(IList<PilotCaseReceipt> rows): exact slot8/case/identity/raw contract
12. PilotCmdReadRawMatched(IList<PilotCaseReceipt> rows): exact slot9/case/identity/raw contract

New managed entry RunPilotCmdObservationContractTests plus private pure fixture/assert/mutation methods and at most one nested PilotCmdObservationTrace. No real native/file/network operations in test bodies. Existing injected capture helpers omit some new required desired_access/close_error facts, so raw-positive fixtures must use the permitted new trace adapter with the complete native-shaped receipt; do not edit old helpers or weaken new facts to make an old trace pass. Reuse old pure helpers only where shapes genuinely match.

## External acceptance schema and algorithm (FR-4, FR-6)

The unified cmd-observations-audit.py imports a pure `evaluate_cmd_observation_artifact(trusted_context, members)` plus synthetic tests. It does not download/unzip, call GitHub, read OS/process/token state or write producer acceptance files. Outer existing read-only tooling owns the verified download/CRC/manifest/source/run identity. This boundary is explicit and cannot be satisfied by self-asserted artifact JSON.

Trusted-context fields, supplied out of band by the reviewer/tooling:
- repository=`Eswink/coding-tools-mcp`; workflow_path=`.github/workflows/windows-lpac-runtime-diagnostic.yml`; artifact_name=`windows-lpac-runtime-diagnostic`; commit/tree=the exact future reviewed source identities; run_head_sha=commit; run_id/job_id/artifact_id positive integers, run_attempt positive integer
- artifact_sha256 lowercase64hex; artifact_size positive integer; member_sha256 is the exact canonical member-name-to-SHA256 map externally verified from this same downloaded archive/manifest
- artifact_crc_verified=true, manifest_verified=true, member_set_complete=true; values come from outer verification, never a member file
- job_terminal_state=`success` or `failure`; cancelled/timed_out/unknown cannot establish full acceptance
- required_setup_and_capture_verified=true means exact-source audit/compile/build/preparation plus manifest/capture/upload verification succeeded; expected failed old diagnostic gates are not relabeled setup success

Members is a bounded mapping of canonical artifact-relative paths to raw bytes already verified against the external artifact hash/manifest. Outer tooling must reject duplicate/casefold-colliding paths, absolute/parent traversal paths and incomplete ZIP entries before construction. The workflow manifest intentionally excludes its own evidence-sha256.txt: hash that one member directly from the trusted provenance/CRC-verified archive, include it in the trusted full member map, and require every other archive member exactly once in the manifest (no other unlisted/missing member permitted). Parse each manifest line as64hex plus one separating space and the complete path; map only the exact workflow prefix evidence\ or evidence/ to ZIP-root-relative names, converting Windows backslash separators to / before collision checks. Reject unsupported mixed/ambiguous prefixes and aliases; never strip an arbitrary leading directory. ZIP entry names themselves must already be unambiguous canonical relative paths. Bounds: at most4096 members and128MiB total, producer JSON/journal at most4MiB each, new raw members at most1MiB, JSON nesting at most32 and any array at most4096. Reject unsupported limits as incomplete; never truncate. Rehash every supplied member against trusted_context.member_sha256, require exact key-set equality, then parse C# receipts/journals as strict UTF-8 without BOM. Only these wrapper members may have one leading UTF-8 BOM removed for text parsing after raw hashing: source.txt, fixture-binaries-sha256.txt, evidence-sha256.txt, pilot/preparation-premise.json, runtime/runtime-inventory.json, runtime/runtime-copy-sha256.txt. Their remaining bytes must decode strictly as UTF-8; ASCII-compatible PowerShell5.1 default-codepage bytes are thereby supported, but unsupported/non-UTF8 wrapper bytes are incomplete with no ANSI/UTF16/codepage guess or producer change. selected-parent-preflight.json is explicitly written with UTF8.GetBytes and permits no BOM. Other legacy members remain hash-verified opaque unless their fixed format is explicitly validated; their JSON content cannot supply a prerequisite or accepted-result truth. An injected accepted-result field in opaque legacy bytes must not influence either verdict, and missing required parsed proof still rejects. No semantic verification of opaque legacy JSON is claimed; stdout/stderr/bin are always raw bytes. Reject NaN/Infinity, duplicate JSON keys, wrong JSON types (including bool-as-int), unknown protocol values and new ObservationPassed keys anywhere in parsed contributing producer receipts/wrappers. Require exact journal fields and the source-defined single terminal LF, with no duplicate fields or additional trailing lines. Trust context is provenance, not substitute for raw validation.

Result schema: protocol=`cmd-cwd-read-acceptance-v1`; source_commit/tree/run_id/job_id/run_attempt/artifact_id echo trusted context; CmdCwdObservationPassed and CmdReadObservationPassed booleans; CwdStatus/ReadStatus each `accepted|not_matched|incomplete|inconsistent`; RunCompletionValidated boolean; CmdCwdRawObservationMatched/CmdReadRawObservationMatched independently recomputed raw results; Reasons a bounded list of objects {code,case,member}, each code drawn from the fixed tested categories identity,provenance,missing,parse,stage,commit,cleanup,raw_mismatch,unsupported_encoding,producer_acceptance_leak. Default both false; accepted never means Windows/runtime/network/production support. Return this to the reviewer only, not into Windows pilot receipts.

Common acceptance gate:
1. Trusted context valid; member source.txt exactly matches expected commit/tree; required old evidence/controls/counts retained and current-run completion protocol valid
2. Final run preconditions and pilot-result show policy accesscheck_signature_v1_ci, phase completion_preconditions_persisted, null Failure, initial selected-parent preflight success, OrdinaryControlPassed and ReferenceRoutePassed true, exact10row order, AllCaseCleanupConfirmed/RunRootRemoved true and actual selected-parent acquired/finalscan/close evidence with no failure/uncertain pin. Old AllFourOfflineCasesPassed/native/sentinel/batch positive aggregates may be false
3. CompletionJournal must match completed-<Broker.Identities[pilot_journal_run_nonce]>.txt; validate exact protocol/nonce/label=run/planned-root/preconditions_record, corresponding immutable bytes and no pending/conflicting/failure evidence. Bodies legitimately retain state=pending; nonce is linkage, not cryptographic authentication
4. Every allocated row has its own identity/nonce-bound completed journal, preconditions and case.json, mandatory raw/provenance files and consistent final-row lifecycle. No-allocation preparation_failed is allowed only for finite optional-prepared runtime rows with exact existing non-created/non-assigned/non-resumed/no-marker/default Launcher shape and matching preparation inventory. It is never a substitute for missing allocated evidence or allowed for ordinary/reference/accepted new controls
5. Apply stage-specific consistency: case preconditions precede marker resolution; case.json precedes its write bookkeeping, proved in finalrun; pilot-result precedes final-result write/close, proved in run preconditions; final preconditions precede their own validation/rename, committed by journal. Compare exact stable case/command/hash/cwd/raw/authority facts and only source-explained mutable bookkeeping differences. Matrix-N must contain exactly the firstN cases and collecting phase; original ordinary/reference booleans update after matrix01/02 respectively, so those matrices must not be forced to equal final prerequisite flags. No whole-JSON equality
6. Each accepted new case must be allocated, not fatal, exact identity/kind/profile/copy/hash/command/cwd, scoped cleanup confirmed, own case.json evidence-close confirmed in finalrun, source/evidence raw metadata complete and independent bytes matched. Cwd output expectation requires ASCII; TYPE requires captured exact minimal9bytes and not cwd match
7. Explicit authority truth must agree with original source predicate: actual source/duplicate AppContainer1/zero caps/profileSID/LowIL, query-only SecurityIdentification duplicate and4 descriptor results mixed2/AAP0/ARAP2/World0; same-run ordinary control signature/rejection; direct class46 failures and TokenVerified=false. Do not port or weaken the Windows verifier or attempt a new token query in Python
8. Recompute new raw matches; require their agreement with case/run raw flags. Never treat missing raw fields as defaults. Contradictory/stale serialized claims are inconsistent, not selected for favorable interpretation

Numeric PID is correlation only; original successful process handles establish ownership, and sequential PID recycling is not itself proof of reuse. Fresh root/profile identity is distinct; every target independently passes the predicate. Listener teardown/outer upload remain separate and must be disclosed if uncertain.

## 文件结构：exact proposed scope

New implementation/test files8, all in tests/windows-broker-direct:
- PilotCmdObservations.cs <=350lines:12 fixed functions, no new type/import
- PilotCmdObservationsTests.cs <=480lines: injected managed matrix
- cmd-observations-audit.py <=300lines: source-union/immutable/mutations and unified unittest entry
- cmd_observation_artifact.py <=480lines: pure bounded trusted-input/member/parser orchestration and result contract
- cmd_observation_contracts.py <=480lines: pure raw/authority/provenance and stage-specific journal/matrix validation
- cmd_observation_fixtures.py <=480lines: complete synthetic producer-shaped artifacts, never real-run evidence
- cmd_observation_artifact_tests.py <=480lines: parameterized acceptance/late-failure tests, all classes loaded by unified entry
- cmd_observation_failure_fixtures.py <=140lines: pure failure-stage transformations and their mutation helpers, exercised by the unified entry

Existing files10:
- PilotSubjects.cs <=250: ValidatePilotPreparation; PreparePilotSubject prelude
- PilotRunner.cs <=300: PilotCaseReceipt; PilotRunReceipt; RunPilotCase adjacent raw-call only plus finite mapping/hash; RunPilot raw reducers/count/list
- PilotClassification.cs <=110: ClassifyPilotFacts reset/route
- run-pilot.ps1 <=112:2 raw outcome checks after old checks
- pilot-audit.py <=350: inspect finite sequence assertion and reviewed mutable file pins
- parent-candidate-audit.py <=250: fixture_coverage and ParentCandidateAudit.test_unknown_missing_and_case_collision expected union
- selected-parent-audit.py <=225: coverage and SelectedParentAudit.test_union_rejects_unknown_missing_collision union
- cmd-sentinel-audit.py <=365: coverage, inspect finite mappings/counts and CmdSentinelAudit.test_union_rejects_unknown_missing_collision; old helper pins and all original semantic mutations preserved
- .github/workflows/windows-lpac-runtime-diagnostic.yml <=125: new audit/test entry and step label
- README.md <=430: exact protocol/raw/accepted limits and no historical result rewriting

Exactly7 existing C# symbols and8 existing Python functions/methods have pre-edit impact requests; static pin and finite MUTATIONS text updates are separately reviewed. Existing managed tests, native/nested controls and production/snapshot sources remain unchanged. If a single file cannot stay <=500lines without poor tests, stop for a precise split review rather than silently adding files or compressing code.

## 设计决策
### 决策1: Keep old commands/controls byte-identical (FR-1, FR-2)
Separate12-function helper and exact new capture adapter avoid editing FixedCommand/PilotCmdSentinel/authority/cleanup. No generic command argument or arbitrary file tail exists.
### 决策2: Raw bytes with conservative cwd support (FR-3, FR-5)
Reject BOM/newline/casing/extra-byte differences rather than normalize or add shell flags. Non-ASCII cwd inconclusive; TYPE remains independent. Equal new read bytes are not batch execution evidence or a previous-directory-object claim.
### 决策3: No producer acceptance before commit (FR-4)
Existing matrices and pilot-result are precommit snapshots; catch cannot retract them. New producer fields say RawObservationMatched. Artifact evaluator establishes acceptance only after complete trusted evidence, leaving finalfallible sequence untouched.
### 决策4: Scoped counts, preserved failures (FR-1, FR-5)
Full allocated path10+1journals; current path predicts42 main-lease recovery guards (baseline34+4pernewnonordinary), never assert measured count before CI. Pins derive from current selected path. All old reducers independent and NetworkDenialProven/CleanupConfirmed remain false where existing source says so.

## 测试策略
Managed tests cover exact builders and every raw schema predicate; real raw primitive reuse is tested with injected complete operations and per-operation failpoints. Source mutations run independent of hash pins, and pure artifact tests mutate raw bytes/stage evidence from a synthetic completed fixture. Existing managed commit-order and source-boundary checks remain; synthetic artifacts are not actual Windows fault-injection coverage.

Required negatives:
- Wrong/missing case/runtime/executable/command/hash/cwd; unsafe/relative/root alias path; wrong minimal source ID/count/hash or preallocation stage; sourcehash differs from same-run original
- Cwd ASCII exact, non-ASCII unsupported, wrong casing/path/BOM/LF/CR/extra line/NUL/truncated/empty; TYPE9bytes each byte mutated plus extra/truncated/BOM; stderr nonempty
- Missing read object; wrong original stdio identity; changed identity/metadata; reparse/directory/multilink/zero identity/oversize; size-vs-stream mismatch/earlyEOF/trailing byte; source/evidence mismatch; each open/read/validate/close false/throw/ambiguous result; single close attempt/no double close
- Missing observed authority/ordinary witness/pre-resume; direct TokenVerified incorrectly true; wrong pinned method diagnostics; altered handle count/identity/rights/closure; failed create/not assigned/not resumed; timeout/nonterminal wait/missing exit query/stale exit0/exit1or23
- Reclassification clears stale raw booleans; no new entry/positive/mutation/offline/native/network/sentinel/batch credit; no unknown fields/case identities; missing/duplicate/wrong-position new rows; clean failedcwd/successTYPE independence
- Raw success then case cleanup/profiledelete/rootremove, case journal bind/verify/rename, case.json serialization/create/write/flush/close failure; complete-looking case.json with failed close; any matrix persistence failure
- Late runroot false/throw; final guard/identity scan failure; selected pin close false/throw/uncertain; finalresult serialization/create/write/flush/close failure; run BindPreconditions/VerifyPending/binding content/identity/read/close/Resolve rename failure
- Precommit favorable matrix/pilot-result with pending/no journal; preconditions only; wrongnonce/label/root/reference; duplicate/conflicting/run-case-swapped journals; pending and completed together; failure evidence contradictory to completion
- Missing/truncated/altered raw/case/matrix/preconditions; wrong source/tree/run/job/attempt; CRC/hash/unlisted/duplicate path/member incompleteness; injected producer ObservationPassed or computed property; synthetic trusted-context false/unknown booleans fail
- Valid stage-aware positive fixture accepts unchanged pending bodies/earlierfalse marker flags/laterwrite bookkeeping. Failure-shaped fixtures retain actual pending journals/remove successful commits at the corresponding stage; a contradictory completed journal after an impossible injected failure tests inconsistent input, not real cleanup execution. All old positive reducer values unchanged through each late-failure case; bothrawtrue/bothacceptedfalse possible. Noalloc default rows validated separately; allocated missingfile never rewritten noalloc

Artifact verification after later authorized exact CI: bind run/attempt/job/artifact to reviewed commit/tree; check ZIP size/hash/CRC and every manifest entry; all10 fixed rows and actual journals, same-run cmd bytes/environment template, exact commands/cwd/fixtures/stdout/stderr, actual-token and failed-direct-query facts, original failures, inheritedstdio3, queriedexit/wait, new4rawread close evidence, allocated profile/root cleanup and current selected pin/guard evidence. Derive narrow control acceptance only then; expected overall native/runtime failure stays failed.

## 风险评估
- HIGH manual source-union PilotCaseReceipt footprint24methods plus PowerShell serialization, even if graph reports LOW. Root must receive warning before edit
- Fresh exact graph omits cross-file partial-class/dynamic PS/YAML and execution heuristics; zero detected processes is not zero behavior impact. Do not repeat a blanket claim that the whole test directory is excluded
- Nonce linkage and manifest hashes are not external authentication; provenance must be supplied by trusted current-run tooling, never artifact claims
- Compact artifact evaluator is additional test logic, not a security-policy reimplementation. Missing/inconsistent evidence defaults false/inconclusive; no repair or fallback
- Lost old artifacts do not authorize rebuilding unknown code or bypassing any concrete refusal

## 检查清单
- [x] All6 FRs mapped to fixed source changes and acceptance
- [x] Exact producer/evaluator schema and stage-aware late-failure cases
- [x] No post-Resolve action or immutable helper change
- [x] Fresh graph/immutable packet and final hashes reviewed by root before implementation; root delivered HIGH warning02:54:12 and approved local edits02:54:28
- [x] Root approved the four-module pure Python split02:59, then replaced a temporary test-cap499 approval with the exact failure-fixture module split03:25. Artifact tests stay480, new failure fixtures140; scope8new/10modified/3specs, all modules exercised by the unified entry
