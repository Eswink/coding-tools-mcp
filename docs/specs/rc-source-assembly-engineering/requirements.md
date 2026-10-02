# 需求文档：rc-source-assembly-engineering

## 功能概述
Assemble exact reviewed source into a separately gated branch, then obtain fresh focused engineering CI evidence. No old green result applies to the new SHA. Details and immutable component IDs are in the parent requirements.md and subspecs/source-evidence/spec.md.

## 范围边界
In scope: seven implementation paths plus nine durable specification additions, exact source gates, three OS portable/metadata/version proof, two Linux native jobs, four Ubuntu24 browser suites, and four-lock capture plus independent verification. The nine durable spec files are explicit published additions. Caches and local execution evidence remain excluded.
Out of scope: No PR89/schema/PR97 stack, Windows security driver, Issue86 opened-root binding, consumer malformed-redirect cleanup, runtime production edits, secrets, security weakening, main/canonical advancement, tag or Release. Preserve every original workflow/guard/test/lock/payload. No held-action retry.

## 需求列表
| FR ID | 需求摘要 | 主子规格 |
|---|---|---|
| FR-1 | Immutable reviewed assembly anchor and bounded linear append-only exact-scope descendants | source-evidence |
| FR-2 | One additional exact workflow/ref producer tuple with source-gated capture and verify | source-evidence |
| FR-3 | Reuse unchanged real commands and preserve complete focused matrix counts/fixtures | focused-validation |
| FR-4 | Independently verify exact-run artifact bytes and retain all failures/raw findings | focused-validation |
| FR-5 | Preserve full-release blockers, source-preflight scope, and protected lanes | focused-validation |

## 验收标准
WHEN any source identity or scope invariant differs THEN execution SHALL fail closed. WHEN focused evidence passes THEN the report SHALL only claim its actual engineering scope. WHEN a final gate is missing or failed THEN it SHALL remain missing or failed, regardless of local unit test success.

## 非功能需求
Read-only contents permission, immutable action pins, no credentials persistence, bounded command/job timeouts, always-upload failure evidence, strict nonzero test counts. No source file exceeds500 lines. No generic framework or bypass flags. All commit gates execute before each commit, not retrospectively.

## 依赖关系
Pinned Probe4.0.1 and GitNexus1.6.9; Node22/Python3.12/Rust1.98.1/cargo-audit0.22.2 in hosted CI. Cargo absent locally. source-evidence precedes focused-validation.
