# 需求文档：strict-legacy-release-gates
## 功能概述
Repair classification and scope validation without relaxing source truth.
## 范围边界
In scope: two workflows, two new helpers and tests, documentation. Existing verifiers and production code unchanged.
## 依赖关系
Final source/version review and parent-frozen manifest; no approval can be inferred from repository content.
## 需求列表
### FR-1: Strict provenance routing
**优先级:** Must
When validating a candidate, the gate SHALL Select stable or numbered RC by fullmatch of committed package version; retain both verifier implementations and both negative suites; reject all other syntax, dirty source and wrong SHA.
**验收标准:** positive and mutated negative fixtures verify this exact rule.
### FR-2: Frozen cumulative manifest
**优先级:** Must
When validating a candidate, the gate SHALL Validate exact changed paths, statuses, before/after Git blob identities, modes and SHA256 bytes against pinned main758c60a6e74e624e144f9c19c5f19d04d17f7a13; include deletions; reject missing, extra, stale, malformed or untracked manifest.
**验收标准:** positive and mutated negative fixtures verify this exact rule.
### FR-3: Bounded metadata and trust
**优先级:** Must
When validating a candidate, the gate SHALL Exclude only docs/releases/reviewed-source-manifest.json from content hash to avoid self-reference; bind its actual Git blob to the report; do not equate a PR-authored manifest with external approval. No CI manifest generator.
**验收标准:** positive and mutated negative fixtures verify this exact rule.
### FR-4: Historical tests retained
**优先级:** Must
When validating a candidate, the gate SHALL Preserve old additive feat/cloud-gateway-agent-runtime branch guard; cumulative paths use frozen manifest; protocol, offline and fault-proxy tests run regardless of scope-check outcome.
**验收标准:** positive and mutated negative fixtures verify this exact rule.
### FR-5: No release authority
**优先级:** Must
When validating a candidate, the gate SHALL No version choice, publication, canonical edit or broad source prefix allowance; missing manifest is explicit blocked state until parent manually freezes final reviewed source.
**验收标准:** positive and mutated negative fixtures verify this exact rule.
## 非功能需求
Bounded Git subprocesses and JSON reads, strict duplicate-key handling, deterministic path order, no external writes.
