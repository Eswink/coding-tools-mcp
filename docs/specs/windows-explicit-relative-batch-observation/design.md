# 设计文档：windows-explicit-relative-batch-observation

## 概述

This design covers FR-1, FR-2, FR-3, FR-4 and FR-5. Baseline is published `071d5590d689d3b30c0dba5fdd7697264ba04f21`, tree `3915136fe50228184e9c92f5764d4762b7475964`. Preparation creates only specifications and evidence; root reviews exact scope/impact before implementation.

## 技术方案

The existing test-only C# coordinator prepares one additional finite case. It reuses the unchanged minimal batch capture core and native capture adapter, the current four bounded raw stream reads, the current process authority predicate, and existing lifecycle/journal machinery. The pure Python evaluator reuses the existing strict provenance/completion contract. Two small pure Python support files replace repeated finite metadata and extract one existing bulky test body; they do not introduce another evaluator, artifact generator or native fixture.

Ordered cases remain `ordinary, reference, node, cmd, powershell, pwsh, cmd-exit23, cmd-batch-exit23, cmd-cwd, cmd-read-direct`, followed only by `cmd-relative-batch-exit23` at slot 10. Total count becomes 11. Every fresh profile/PID/root remains independently verified; common construction does not establish object identity across cases.

The fixed new tail is ` /d /q /c .\direct.cmd`. Payload remains hex `657869742032330d0a`, SHA256 `cab50bf1c23956b80d898c7af8f1c1e853e5bba6b14b8a2fbe4981d382fb7e8a`. Expected stdout/stderr are empty and queried exit is 23. Old cwd output remains ASCII cwd+CRLF or explicitly unsupported; TYPE remains nine bytes. The relative case supports non-ASCII cwd because its expected output is empty. No text decoding/trimming/newline or receipt normalization is permitted.

## 数据模型

| Location | Exact contract |
|---|---|
| Case receipt | New bool `CmdRelativeBatchExit23Observed`, false initially and on all ten old rows and pre-observation ownership snapshots |
| Run receipt | New bool `CmdRelativeBatchRawObservationMatched`, false before slot 10 has a measured match |
| Run counts | `RequiredCaseCount=11`, `AdditiveRelativeBatchRequiredCaseCount=1`; all old additive/original counts unchanged |
| New raw identity protocol | `cmd-relative-batch-raw-v1`; old cwd/TYPE retain `cmd-cwd-read-raw-v1` |
| New matching status | `cmd_relative_batch_exit23_raw_observed` |
| New nonmatch status | `cmd_relative_batch_exit23_raw_not_observed`; existing `deadline_exceeded` on timeout |
| New canary label | `relative_batch_observation_did_not_attempt_runtime_canary`; ScriptEntryObserved stays false |
| Existing numeric namespace | expected_supported=1, expected_bytes=0, raw_complete/stdout_matches/stderr_empty measured as before; no new arbitrary keys or producer expected-exit field |
| Expected output hash | Empty-byte SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| External protocol | `cmd-cwd-read-relative-batch-acceptance-v1` |
| External result fields | External-only `CmdRelativeBatchObservationPassed` and `RelativeBatchStatus`; independently recomputed `CmdRelativeBatchRawObservationMatched` also exists as a producer raw fact |
| External status set | accepted, not_matched, incomplete, inconsistent |

All three raw case flags are mutually exclusive and exact-case bound. The new raw flag is not an accepted producer verdict. Recursive rejection of new ObservationPassed keys remains strict in every parsed contributing receipt/wrapper. Opaque legacy JSON contributes no prerequisite truth.

This is an explicit new eleven-case schema. Old ten-case artifacts remain reviewable with their pinned 071 evaluator; the new evaluator must reject incompatible schema without fabricating a row or injecting default fields. Existing cwd/read semantics are retained within valid eleven-case artifacts.

## API 设计

Existing external API remains `evaluate_cmd_observation_artifact(trusted_context, members)`. Every accepted flag defaults false; malformed-shape fallback returns all three false. The caller supplies independently verified archive/run context, never JSON self-attestation. Pure modules contain no acquisition, filesystem, OS, process, token or network operation.

Six test-only C# helpers are proposed inside the existing partial class:

1. `FixedPilotCmdRelativeBatchCommand`: existing executable/path validation plus the one literal tail
2. `FixedPilotCmdObservationCommand`: exact three-kind dispatch, unknown kind rejected
3. `PilotCmdObservationProtocol`: exact finite raw protocol selection
4. `CapturePilotCmdRelativeBatchUsing`: preallocation/ownership and exact case/command/cwd/protocol guards; delegates `CapturePilotCmdBatchCore(...,true)` unchanged
5. `CapturePilotCmdRelativeBatch`: existing native capture adapter only
6. `PilotCmdRelativeBatchRawMatched`: exact count 11, slot 10, duplicate/cross-flag rejection, genuine raw predicate without late cleanup/Fatal gating

The current raw predicate selects expected exit 23 only for the exact new kind and 0 for the old two. Only the exit equality is adapted; authority/stdio/token/AccessCheck clauses and measured constants retain their bytes. New payload checks extend the existing TYPE minimal-capture arm, not its native capture core.

Existing cwd reducer changes its allowed count from 9..10 to 9..11; TYPE changes 10 to 10..11. Both retain fixed slots 8/9, original predicates, duplicate rejection and ten-row regressions. Their own rows must keep the new raw flag false. Legitimate relative exit 1/output mismatch cannot erase old measured facts or old acceptance after common completion validates. Malformed shared evidence still blocks common completion.

## 文件结构

Exactly 21 prospective paths: 16 existing modifications, two new pure Python support files and three new specifications. All code paths below use `tests/windows-broker-direct/` unless fully qualified.

| Path | Proposed change and ceiling |
|---|---|
| PilotSubjects.cs | Finite observation preparation arm only |
| PilotRunner.cs | Receipt fields, append two coordination arrays, raw reducer wiring, truthful eleven-case accounting |
| PilotClassification.cs | Separate new reset after the frozen old reset; old dispatch stays intact |
| PilotCmdObservations.cs | Seven existing observation helpers adapted plus six thin helpers; cap 400 |
| PilotCmdObservationsTests.cs | Reuse all managed matrices, add CaptureBatch/Eleven test support; cap 500 |
| run-pilot.ps1 | Append raw-match wrapper check after existing checks; retain old gates/order/text |
| cmd_observation_contracts.py | Strict eleven schema and third fixed raw case; cap 490 |
| cmd_observation_artifact.py | Third external result, exact eleven matrices/completion and ownership-snapshot flag check; cap 500 |
| cmd_observation_fixtures.py | Finite eleven-row fixture and source-correct projections; cap 500 |
| cmd_observation_artifact_tests.py | Parameterize existing tests; one existing test delegates its extracted body; cap 500 |
| cmd_observation_failure_fixtures.py | Explicit old/new case and matrix fault targets with blocked future row; cap 200 |
| cmd_observation_cases.py (new) | Fixed three-case metadata, shared unchanged ArtifactError, strict lookup/output helpers; cap 80 |
| cmd_observation_late_failure_tests.py (new) | One ordinary assertion function extracted from the existing late-failure unittest body; cap 140 |
| pilot-audit.py | Exact appended sequence and only legitimately changed producer pins |
| cmd-sentinel-audit.py | Count/sequence and existing mutation anchors; preserve all old mutation names/pins |
| cmd-observations-audit.py | Exact methods/files/protocols/fields, seven-module pure allowlist, independent descriptor literals and caps; existing cap 300 |
| README.md | Current eleven-case scope and interpretation limits |
| .github/workflows/windows-lpac-runtime-diagnostic.yml | One display-label update only; triggers, commands, ordering and seven managed entrypoints unchanged |
| docs/specs/windows-explicit-relative-batch-observation/requirements.md | FR-1 through FR-5 |
| docs/specs/windows-explicit-relative-batch-observation/design.md | This finite design |
| docs/specs/windows-explicit-relative-batch-observation/tasks.md | Reviewed execution/validation sequence |

The new late-failure module exports `assert_late_failures_keep_raw_and_old_results(test)`. Keep the existing unittest method name and class identity as a thin delegation. It defines no TestCase, adds no inheritance/import cycle, and is not separately discovered; its sole function executes through the existing unified entry. Both new modules must appear in exact pure-import/file auditing and be covered through that entry. No additional C# file/entrypoint is proposed. If readable implementation cannot fit these caps, stop for a precise additional scope proposal; do not compress code or omit coverage.

Shared finite metadata is never the sole oracle. Independently written literal assertions bind all three exact case IDs/slots/tails/protocols/field names/output policies/exit constants. Descriptor mutation must be rejected even if evaluator and synthetic fixture share that descriptor. Keep the literal new nine-byte payload, empty-stream and exit23 assertions independent.

The descriptor exports are exactly `OBSERVATIONS`, `ArtifactError`, `observation_case(kind)` and `observation_expected_bytes(kind,cwd)`. Move the existing ArtifactError class unchanged from contracts into this import-free module, and re-export it by import from contracts; all callers retain one exception identity, with no circular import. Each of the three descriptors has fourteen literal cells: kind, slot, tag, row_flag, run_flag, accepted_field, status_key, raw_protocol, command_tail, output_policy, expected_exit, matched_status, unmatched_status, canary. Strict lookup rejects non-string/unknown kinds with the shared ArtifactError('identity'); byte selection rejects invalid types/policies the same way. Only cwd returns ASCII path+CRLF or None for non-ASCII; TYPE returns literal nine bytes, relative returns empty bytes. Unknown input must never select a default descriptor or become an unsupported-encoding success. Independent audit tuples and fixture byte expectations must not derive solely from these helpers. The fixed overall CASES sequence remains in contracts and is independently asserted.

## 设计决策

FR-1/FR-2: Change only pathname qualification. No marker fixture or same-process read-then-run is bundled. Source flags and existing effective authority are unchanged.

FR-3/FR-4: Preserve producer raw versus final-commit separation. Valid late failure receipts may retain measured raw facts. External accepted fields require all eleven case outcomes, matrix-01 through matrix-11, exact case/precondition/result snapshots, writer bookkeeping, run-root removal, selected-parent final scan/close, journal binding and completed filename. No post-Resolve operation is added. A favorable final-result/precondition file alone is insufficient.

FR-3/FR-5: Preserve source chronology in synthetic faults. Old TYPE case failure at slot9 blocks slot10 without allocation or relative evidence; the loop may write the blocked-row matrix11 only if earlier matrix persistence succeeded. Matrix10 persistence failure cannot have matrix11 or any relative allocation; catch padding is blocked_run_failure_no_subject_created. Relative case/matrix11 faults occur after the first ten rows. Shared final run faults may retain all three measured raw facts. Guard counts follow reached stage, not a blanket 42-to46 substitution.

FR-4: Preserve all nine contiguous immutable spans with their existing hashes, plus 24 whole C#/PowerShell files recorded by `immutable-controls.json`. In particular original command/capture helpers, policy/gates/journal/owned-file/selected-parent/AccessCheck/native/handle/cleanup code and all production/snapshot files stay unchanged. `ValidatePilotPreparation` and `RunPilotCase` require no edits because their finite-kind routing already suffices. Retain the final fallible journal sequence verbatim and old classification reset/dispatch spans; insert the new reset separately.

For a nominal fully allocated run, evidence is eleven case outcomes, twelve completed journals, six selected-parent pins and 46 guards. Actual path depth/allocation/failure facts govern reported counts; never pad evidence. These counts do not establish universal CleanupConfirmed.

## 测试策略

Retain all 330 portable unittest method identities and all seven managed entrypoints; add zero portable methods by extending finite parameter rows. The seventh managed assertion count is measured after implementation, not predicted. Preserve all baseline mutation rows.

| Coverage | Required finite expansion |
|---|---|
| Main late failures | 51 to78: old TYPE case21 + relative case21 + matrix10 six + matrix11 six + shared final-run24 |
| Contradictory completion | Four to six; old variants remain plus relative root-removal/receipt-close contradictions |
| Raw read faults | Existing cwd116 plus relative116; 232 total; seed nonempty bytes for early-EOF variants despite normal empty output |
| Payload mutations | Existing TYPE14 plus relative captured-payload14; byte/framing/BOM/LF/truncation/extra cases |
| Authority/stdio/raw/cleanup | Existing27 plus relative27; 54 total |
| Required identity/payload proofs | Retain17 baseline TYPE cases, add one explicit batch-source-path corruption, mirror all18 for relative; 36 total |
| Missing/truncated required members | 22 to32, retaining matrix10 and adding matrix11/new-case evidence |
| Missing matrix suffixes | Ten to eleven positions |
| Clean wrong-exit/timeout | Three to seven; relative exit0/1/legitimate timeout retain old independent acceptance; stale timeout exit23 rejects |
| Source semantic mutation intents | Existing18 plus12 new relative C# variants plus14 independently rejected descriptor-cell mutations; 44 total |

New relative stream mismatch values are NUL, x, BOM, LF, CR, CRLF and the nine-byte payload; nonempty stderr remains an independent mismatch. Missing/uncertain read/close, wrong identities, reparse/multilink/oversize, unverified token/extra handles, stale exit and all persistence stages reject matching/acceptance appropriately. Old false runtime/network/support fields and producer accepted-field exclusion remain tested. Unicode cwd leaves TYPE/relative eligible while cwd remains unsupported. The plain assertion-function extraction preserves discovery/executed counts and reports source/synthetic coverage honestly.

The missing-matrix-suffix test must first construct its failure variant at matrix_position=11, then remove each requested suffix starting at positions1..11. Starting from the old default matrix10 failure would make the new position11 case vacuous. Keep old matrix10 failures separately in the78-variant matrix. Independently assert that every semantic mutation anchor/cell actually changes the targeted implementation with source pins disabled.

CI uses the existing push-triggered Windows workflow after exact candidate review/publication. Verify PS5.1 compilation/all seven managed entries, 330 portable methods, metadata contracts and Rust checks, then inspect all original and additive real outcomes. Independently authenticate exact commit/tree/run/job/attempt/artifact, ZIP SHA256/size/CRC, manifest/member set and raw bytes. Re-run an actual-evidence in-memory missing-final-journal negative without altering the retained artifact. Original aggregate failures may remain; do not demand or synthesize a green run to accept a narrow diagnostic.

## 风险评估

Fresh pre-edit analysis reports HIGH shared-receipt footprint (35 C# method references) and CRITICAL synthetic-fixture/test upstream breadth. Exact IDs, hashes, caller/process membership and graph limitations accompany the packet. Counts reported by GitNexus as processes are entry-point groups; distinct raw Process IDs are enumerated separately. Partial C# and PowerShell/YAML gaps prevent interpreting zero graph edges as zero impact. Root receives warnings before implementation.

## Documentation and interpretation

Microsoft [cmd](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd), [exit](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/exit), [type](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/type), [cd](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cd), and [NeedCurrentDirectoryForExePathW](https://learn.microsoft.com/en-us/windows/win32/api/processenv/nf-processenv-needcurrentdirectoryforexepathw) define the relevant command semantics. The explicit environment omits NoDefaultCurrentDirectoryInExePath; documented resolution predicts both relative forms reach their corresponding workspace file. Different observed exits show path-sensitive behavior across comparable fresh cases, not proof of omitted lookup or a specific failed API. Another exit1 does not locate the failure. The minimal script has no entry marker; empty streams cannot establish failure before entry. Exit1 is not itself a Win32 denial code.

## 检查清单

- [x] All five FRs mapped to finite implementation and negative coverage
- [x] Exact producer/external schema and source-ordered late failures specified
- [x] Reused harness, bounded two-file extraction, independent literal oracle and discovery counts specified
- [x] Security helpers/old failures/actual evidence interpretation remain immutable or explicitly bounded
- [x] Root review of exact fresh impact packet remains required before source implementation
