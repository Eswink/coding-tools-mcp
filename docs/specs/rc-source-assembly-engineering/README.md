# RC source assembly engineering

## 原则
Obtain fresh focused engineering evidence for the exact reviewed PR96, PR93 and PR94 sources. Existing isolated workflows and their strict tests remain intact. Only a correctly gated immutable assembly anchor and reviewed append-only corrections may produce assembly evidence. This is not full RC release eligibility.

## 子规格索引
| ID | 标题 | FR | 依赖 |
|---|---|---|---|
| source-evidence | Immutable source and exact engineering producer evidence | FR-1, FR-2 | None |
| focused-validation | Focused execution and honest artifact verification | FR-3, FR-4, FR-5 | source-evidence |

## 依赖关系
Source identity precedes every CI assertion. spec-manifest.json owns FR assignments and dependency order. Child task lists are authoritative; parent tasks.md contains references only.

## 里程碑
M1: specifications, check_spec, impact and independent review. M2: correctly gated source assembly and initial fifteen-path integration followed by the exact reviewed sixteen-path correction. M3: local checks, exact-source focused hosted CI and independent artifact-byte verification. Final release gates remain separately required.
