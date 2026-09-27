# Ubuntu mandatory sandbox dispatch — Issue #73

Status: **IMPLEMENTATION BLOCKED BY HIGH/CRITICAL IMPACT REVIEW**.
Baseline: `416af97bb483371f725798efb0cc4a967feef032`.
The previous library is integrated, but no application dispatch enforcement is claimed.

## 原则

This increment supplies a persisted integration plan, review boundaries and executable
red-first tests. It changes no production symbol, dependency, credential or feature/main
reference. A red witness is evidence of a gap, not a passing security acceptance test.

## 子规格索引

| ID | FR | Depends on |
|---|---|---|
| authority | FR-1, FR-2, FR-3 | none |
| enforcement | FR-4, FR-5 | authority |
| verification | FR-6, FR-7 | enforcement |

## 依赖关系

Native authority -> mandatory enforcement -> actual-dispatch acceptance. See spec-manifest.json.

## 里程碑

M1: exact-source graph review and baseline probes; M2: separately reviewed production
binding; M3: green end-to-end automated acceptance and compatibility. Real workstations,
VPS and ChatGPT acceptance are independently deferred, never substituted for M2/M3.
