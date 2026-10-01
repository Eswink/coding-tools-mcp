# 需求文档：rc070-product-metadata

## 功能概述
Align non-final engineering product metadata to the selected 0.7.0-rc.1 candidate without changing runtime behavior, dependency resolution or release authority.

## 历史经验与坑
The current desktop six fields are 0.6.0-rc.4 while the externally visible gateway product is 0.1.0. Existing cloud-release-artifacts FR-1 requires coherent product versions but preserves independently versioned libraries. A metadata or input-only pass is not final acceptance.

## 术语定义
Product version means the desktop six fields and gateway package/self-lock. Independent components mean cloud-agent and local-agent libraries. Engineering evidence is bound to its exact source and is not release approval.

## 范围边界
In scope: eight product fields in seven files, two engineering workflow constants, focused tests, an engineering guide and exact-branch read-only validation.
Out of scope: runtime/security changes, held snapshot authority, native Windows security or consumer transport work, dependency upgrades, historical receipts/workflows, source freeze, tags, releases and publication.

## 需求列表
### FR-1: Coherent metadata with byte-preserved dependencies
**优先级:** Must
When preparing the candidate, the implementation SHALL set all eight product fields to 0.7.0-rc.1 and preserve every other byte of the seven metadata files. Independent component manifests/locks and pnpm-lock.yaml SHALL remain byte-identical to e61aaf2da99baccdb99db4922b39f7d8d5997096. Each independent field drift and unauthorized byte change SHALL be rejected by focused regressions.

### FR-2: Exact-source three-platform engineering proof
**优先级:** Must
When the exact engineering branch is pushed, read-only CI SHALL verify immutable source and the explicitly fetched baseline, run the existing provenance/stable/manifest/tag/preflight/cloud/package contracts, install/check/build/test the actual frontend, resolve all four manifests with full locked Cargo metadata and build/probe all four gateway binaries on Ubuntu 22.04/24.04 and Windows 2025. Failures SHALL remain failures, evidence SHALL identify source/tree/run/OS/tools, and final tracked source SHALL be clean.

### FR-3: Non-final guide and freeze boundaries
**优先级:** Must
The version-matched guide SHALL describe engineering inputs only, retain unresolved security and full-release gates and forbid inherited source acceptance. The final guide SHALL be included in the reviewed manifest; later changes SHALL require a new reviewed freeze. No manifest, tag, release or installation acceptance SHALL be generated here.

## 非功能需求
New helper/test/workflow files remain below 500 lines. CI is limited to three 35-minute jobs with pinned actions, exact repository/branch gating, no privileged settings, no package publication and independent step failure retention. Local Node 24 verification and hosted Node 22/Rust 1.98.1 verification are reported separately.

## 依赖关系
Existing cloud-release-artifacts, final-rc-packaging-gate and legacy-source-gates contracts; owner-selected minor series; applicable repository review gates. Windows/security/final packaging remain independent blockers.

## 验收清单
Every FR has deterministic positive/negative verification or explicitly pending exact-head hosted evidence. No final acceptance is inferred from engineering success.
