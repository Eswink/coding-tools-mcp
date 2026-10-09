# Design: finite manager source-byte observation

## 概述
Add a separate external diagnostic helper beside the existing Python source guard. Retain the complete original guard bytes and verify_manager function AST without rewriting them. The observer independently uses the same seven literal public paths, native Git HEAD/blob bytes and raw worktree file bytes. Record bounded metadata, never bytes. It does not call restore, compile, authorize or update Git/source.

## 技术方案
- observe_manager_sources: fixed-path expected/raw hashes, lengths, framed OIDs and LF/CRLF counts with2MiB input/32KiB receipt bounds.
- External helper CLI: real HEAD checks, diagnostic classification and admission=false; import only original run_git function from unchanged guard.
- PS before/after observer calls: errors recorded separately; original verify-manager calls always remain; final passed=false on any observer failure.
- Ordinary tests: actual full Python source import and native owned repository controls, not fake production owners or replacement harnesses.

## Data Flow
Expected public bytes from native Git HEAD; actual public bytes from regular raw files. Raw equality and comparison-only CRLF transforms become JSON. The original verifier subsequently reads unchanged raw bytes and refuses any blob mismatch.

## Error Handling
Missing/symlink/oversize or identity failure yields bounded diagnostic failure, without changing files or suppressing the original admission error. Before non-cancellation failure is retained after Run-SourceCompile success logic; final error flag prevents carrier PASS. Before typed cancellation stops new work while retaining the original prescribed finally cleanup, skips a new After observer child, and is propagated after receipt. After observation moves after the original manager-after check but before the existing runtime-after loop; typed cancellation is deferred through receipt writing. The final dispatch rethrows its original typed exception or an aggregate of distinct original primary failure and cancellation objects, never overwriting the original error receipt. Original error has its original field and failed native command entry.

## FR Coverage Matrix
| Requirement | Component | Validation |
|---|---|---|
| FR-1 | fixed-path observer | exact/invalid owned files, bound/count/OID controls |
| FR-2 | comparison-only metadata | native LF/CRLF/mutation controls plus strict verifier |
| FR-3 | original AST + PS independent handling | original AST hash, ordinary failure-delegate control |
| FR-4 | independent source review | exact freeze, fresh impact, actual tests, parent push only |

## 文件结构
Existing guarded scripts/windows_foundation_source_compile.ps1; new scripts/windows_foundation_manager_observation.py and scripts/windows_foundation_manager_observation_tests.py and three docs/specs/windows-manager-byte-observation specification files. No other source files change.
