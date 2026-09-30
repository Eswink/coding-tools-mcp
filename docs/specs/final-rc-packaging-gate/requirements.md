# 需求文档：final-rc-packaging-gate

## 功能概述
Prepare reusable full-scope RC packaging with honest incomplete security status.

## 历史经验与坑
Prior desktop-only version and24-only workflow cannot validate requested full scope.

## 术语定义
Candidate means exact immutable Git commit. Structural packaging does not authorize publication.

## 范围边界
In Scope: workflow, evidence validator, tests and audit. Out of Scope: selecting version or publishing release; original full release scope remains required.

## 需求列表

### FR-1: Version input
**优先级:** Must
**用户故事:** As release owner I need Require explicit RC version matching all six committed fields; never choose or rewrite a version.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Require explicit RC version matching all six committed fields; never choose or rewrite a version.

### FR-2: Exact integration source
**优先级:** Must
**用户故事:** As release owner I need Require completed successful complete-integration run at the same commit, repository and workflow path; reject wrong source, failed or missing jobs.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Require completed successful complete-integration run at the same commit, repository and workflow path; reject wrong source, failed or missing jobs.

### FR-3: Linux compatibility
**优先级:** Must
**用户故事:** As release owner I need Build DEB/AppImage on Ubuntu22.04 and verify same package bytes installed on22.04 and24.04, including raw startup and native acceptance.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Build DEB/AppImage on Ubuntu22.04 and verify same package bytes installed on22.04 and24.04, including raw startup and native acceptance.

### FR-4: Windows package evidence
**优先级:** Must
**用户故事:** As release owner I need Build exact NSIS and preserve standard-user installed acceptance; label this packaging evidence, never Windows sandbox completion.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Build exact NSIS and preserve standard-user installed acceptance; label this packaging evidence, never Windows sandbox completion.

### FR-5: Evidence and no publication
**优先级:** Must
**用户故事:** As release owner I need Verify identities and digests before collecting packages, generate checksums, preserve mandatory Windows security blocker, no release/tag write or publication job.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Verify identities and digests before collecting packages, generate checksums, preserve mandatory Windows security blocker, no release/tag write or publication job.

### FR-6: Legacy gate audit
**优先级:** Must
**用户故事:** As release owner I need Document stale lab scope and stable version failures with precise semantics-preserving repair; never simply widen allowlists or weaken stable tests.
**验收标准:**
When validating the candidate, the gate SHALL enforce the following:
- [ ] Document stale lab scope and stable version failures with precise semantics-preserving repair; never simply widen allowlists or weaken stable tests.

## 非功能需求
Fail closed on missing evidence; no large local Tauri builds; helpers below500lines.

## 验收清单
Every FR has deterministic positive and negative checks or explicit native pending status.

## 依赖关系
Native integration run at exactsource; owner version decision; native Windows security remains blocked; npm audit JSON and RustSec for allfourlockfiles required.

## Push orchestration extension
FR-1/FR-2 SHALL permit only release/full-rc-candidate-* push in the expected repository to derive the already committed RC version and resolve the latest completed successful exact-SHA integration run. Explicit dispatch inputs remain mandatory. Missing/ambiguous runs fail once without polling. Only the parent creates this branch after owner version decision and engineering gates.
