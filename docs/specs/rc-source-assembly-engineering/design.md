# 设计文档：rc-source-assembly-engineering

## 概述
The full reviewed design and exact commands are in the parent requirements.md and subspecs/source-evidence/spec.md. The required unadapted source tree is 4e55549810e74236e14eb28a48785c3268ae107d. Only a source assembly created with the required staged review gates may become the immutable anchor.

## 对应需求
FR-1 immutable source chain; FR-2 exact producer; FR-3 real focused matrix; FR-4 artifact integrity; FR-5 release-boundary reporting.

## 技术方案
Recreate exact PR96+PR93+PR94 merges in a fresh branch using --no-commit, staged graph detection, actual-diff gencommit, HIGH/CRITICAL warning/review then commit. Freeze the compliant anchor. The exact published implementation 46f88c60f3a5f8726e4c28cee73e941a7f15a36d (tree 1412f9e1408b1dbb7beefa2db37f70b5965fea65) is the sole fifteen-path predecessor. Every subsequent commit must be a linear append-only descendant with cumulative exact sixteen-path scope, including the dispatch regression module, and unchanged protected blobs; no new merges or foreign/forced push ancestry. Each CI result binds actual HEAD/tree/workflow SHA/ref/run/attempt.
A single read-only workflow runs3 portable matrix jobs (Ubuntu24 additionally browser),2 Linux native jobs, capture and independent verify. Preserve existing producer logic except exact second trusted identity and explicit root plumbing. No env spoofing. All existing collectors/verifiers/raw report semantics remain otherwise unchanged.

## 数据模型与接口
Source receipt: component SHAs/trees/parents, compliant anchor, ordered descendant chain and each tree/delta blobs, full input hashes, actual GitHub source/workflow/run, runner/tool identity, command/status evidence. producer(sha,root=None) checks the exact assembly tuple and source gate before returning the existing identity shape. Capture receipt remains schema1 and engineering-only; independent verifier trusts capture job output digest, never self-attested downloaded digest.

## 文件结构
- .github/workflows/rc-source-assembly.yml
- scripts/rc_source_assembly.py
- scripts/rc_source_assembly_frontend.py
- scripts/rc_source_assembly_tests.py
- scripts/rc_source_assembly_evidence_tests.py
- scripts/rc_source_assembly_dispatch_tests.py
- scripts/engineering_dependency_capture.py
- docs/specs/rc-source-assembly-engineering/README.md
- docs/specs/rc-source-assembly-engineering/design.md
- docs/specs/rc-source-assembly-engineering/requirements.md
- docs/specs/rc-source-assembly-engineering/spec-manifest.json
- docs/specs/rc-source-assembly-engineering/subspecs/focused-validation/spec.md
- docs/specs/rc-source-assembly-engineering/subspecs/focused-validation/tasks.md
- docs/specs/rc-source-assembly-engineering/subspecs/source-evidence/spec.md
- docs/specs/rc-source-assembly-engineering/subspecs/source-evidence/tasks.md
- docs/specs/rc-source-assembly-engineering/tasks.md

## 设计决策
Use one exact additional producer tuple rather than duplicate PR93 validation or weaken the final dependency verifier. Source and frontend helpers are concrete gate logic, not a general workflow framework. Original workflows/tests remain byte-identical. Source preflight passed is not release eligibility.

## 测试策略
Original16 capture,88 delivery and147 JS tests remain; All three assembly test modules execute: source-history/producer contracts and separate evidence-binding/mutation contracts, and dispatch/quiet-UI/history-migration regressions. Each module has its own current-source discovered count and actual execution count; synthetic receipts never count as hosted proof. Hosted proof must show frontend233, native11/7/14/6, four metadata manifests, four compiled outputs, four browser suites and all four raw lock audits. Windows reports4 explicit Linux-only skips honestly.

## 风险评估
Producer upstream impactHIGH21; direct callers collect/verify/test noncloud. collect graphLOW17 and verify graphLOW19 do not reduce shared trust-boundary HIGH. FTS is unavailable; exact UID/Cypher/source validation is fresh. The additional evidence-test allowlist path affects the source-history gate at CRITICAL26 (5 direct callers, 6 process groups); its review and warning precede changes. The exact legacy-to-sixteen-path correction has fresh history impact CRITICAL27 (5 direct callers, 6 process groups); its synthetic dispatcher fixture has HIGH13 (2 direct callers, 4 process groups). No CRITICAL tool result has been downgraded. No PR89/schema/PR97 stack, Windows security driver, Issue86 opened-root binding, consumer malformed-redirect cleanup, runtime production edits, secrets, security weakening, main/canonical advancement, tag or Release. Preserve every original workflow/guard/test/lock/payload. No held-action retry.
