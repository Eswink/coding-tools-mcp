# 设计文档：final-rc-packaging-gate
## 概述
Manual dispatch workflow, fixed source checkout, explicit version and prior integration run.
## 架构设计
FR-1/FR-2: contracts validates existing rc_version_gate and GitHub REST run/jobs identity. No production changes.
FR-3: build on22, four installed combinations across22/24 anddeb/appimage. Existing rc_packages/rc_native_gate remain strict.
FR-4: current Windows installer and standard-user helper reused; native execution is not sandbox completion.
FR-5: evidence collection verifies all package and native identities/digests; emits publish_approved=false and explicit Windows security blocker. No publishing credential or job.
FR-6: separate audit explains additive lab guard versus cumulative release and stable versus RC semantics.
## 文件结构
.github/workflows/final-rc-packages.yml; scripts/final_rc_evidence.py; scripts/final_rc_evidence_tests.py; docs/releases/final-rc-gates.md.
## 数据模型与接口
Version is strict major.minor.patch-rc.N. SHA is40lowerhex; digests64lowerhex; run_id positive decimal. Integration run requires expected six job names and successful conclusions, exact workflow path andhead SHA. Packaging receipts bind source tree/version/source/run/package payload. No arbitrary URL accepted.
## 测试策略
Unit tests mutate identity, missing/failedjobs, missing packages, wrongdigest and security approval. actionlint validates workflow. Native build/install pending future authorized dispatch. Existing RC version/package/native contract tests retained.
## 风险与决策
Historical integration success does not validate later candidate. Same commit required. Windows isolation blocker intentionally survives packaging success. No versionselected.
## 检查清单
AllFRs covered; no runtime isolation behavior changed.

## 技术方案
Use existing strict RC helpers; new evidence validator rejects missing/failed/source-drift receipts. npm audit real JSON and cargo audit real JSON for allfourlockfiles, no synthetic success receipts.

## Push orchestration
A source-only trigger branch points to the already green immutable commit. The read-only API selects one unique highest run ID among successful exact-SHA exact-workflow runs, then verifies all seven jobs. Outputs propagate the committed version to every packaging job. No version mutation or release authorization.
