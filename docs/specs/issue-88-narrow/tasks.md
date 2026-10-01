# Tasks: narrow pre-tag contract

## 概述

Only the reviewed schema/evidence-map increment; publication and independent review remain separate acceptance steps. Full release delivery remains blocked separately.

## 交付物清单（Scope-lock）

Expected11 new files: four runtime contract modules, fixture module, two focused test modules, fixture workflow, plus requirements/design/tasks. No existing runtime or workflow files modified. 114 new class/function/method symbols including fixtures/tests; exact staged inventory is the review authority.

## 任务列表

### 阶段 1: 准备工作

- [x] 1.1 Read source/context/reviewed design and refresh exact symbol context/impact
  - **证据块**: `scripts/rc_consumer_snapshot.py:134` `def resolve_candidate(root: Path, expectations: dict, environment: dict, api) -> dict`; function checks source and existing lightweight tag. Fresh impact records HIGH risk; it remains unchanged
  - Files: spec documents, under200 lines each
  - Requirements: FR-1, FR-5; Design: decisions1 and5
- [x] 1.2 Pass check_spec and record scope estimate before source edits
  - **证据块**: `AGENTS.md:20` requires fresh impact; `.agents/skills/mcp-probe-kit/SKILL.md` requires check_spec before implementation
  - Files: three specification files; no source edit before reviewed impact assessment
  - Requirements: FR-1–FR-5; Design: risk assessment

### 阶段 2: 核心实现

- [x] 2.1 Implement strict source/invocation/candidate/receipt codecs without collection
  - **证据块**: `scripts/rc_artifact_consumer.py:42` defines exactly four payloads; `scripts/rc_consumer_snapshot.py:120` requires FINAL attempt1; existing consumer environment is workflow_dispatch
  - Files: `scripts/rc_pretag_types.py` and `scripts/rc_pretag_evidence.py`, each below500 lines
  - Requirements: FR-1, FR-4; Design: data model and API
- [x] 2.2 Map complete ledger and aggregate all input claims as blocked
  - **证据块**: `docs/releases/next-rc-ledger.md:11` says no row DONE; `scripts/release_tag_gate.py:23` declares exact13 FINAL jobs
  - Files: `scripts/rc_release_policy.py`, `scripts/rc_release_eligibility.py`, each below500 lines
  - Requirements: FR-2, FR-3; Design: policy and decisions2/4

### 阶段 3: 集成测试

- [x] 3.1 Exercise every adversarial acceptance and unchanged consumer regression
  - **证据块**: `scripts/rc_consumer_test_runner.py:25` requires at least159 tests and zero skips; existing fixture workflow pins Ubuntu24/Python3.12
  - Files: fixture and two focused test modules, each below500 lines; `.github/workflows/rc-pretag-contract-checks.yml` below150 lines
  - Requirements: FR-1–FR-5; Design: test strategy
- [ ] 3.2 Stage exact tree and record graph/static/test results for independent review
  - **证据块**: `AGENTS.md` requires detect_changes before commit; this phase does not include committing or publication
  - Files: spec task status only; review report retained outside repository
  - Requirements: FR-5; Design: risk assessment

## 检查点

- [x] Source base/design digests verified; no existing consumer symbols changed
- [x] Spec and reviewed impact assessment precede implementation
- [x] Local53 schema tests,159 consumer and208 original regressions pass with zero skips; actionlint/compile pass. Hosted execution and independent implementation review remain pending

## 需求覆盖矩阵

FR-1:1.1/1.2/2.1/3.1; FR-2:1.2/2.2/3.1; FR-3:2.2/3.1; FR-4:2.1/3.1; FR-5:all tasks.

## 文件变更清单

Four new runtime modules, one new fixture module, two new test modules, one new workflow, three new spec documents. Every Python source below500 lines. No old source, host allowlist, unrelated implementation or security setting changes.

## 检查清单

- [x] Scope and FR links explicit
- [x] Eleven additive files; seven Python modules each below500 lines
- [ ] Independent implementation review complete before convergence
