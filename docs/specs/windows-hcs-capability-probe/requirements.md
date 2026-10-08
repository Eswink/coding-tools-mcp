# 需求文档：windows-hcs-capability-probe
## 功能概述
Observe existing Windows 2025 Actions virtualization prerequisites without changing them.
The result selects the next research step; it does not admit Windows production execution.
## 范围边界
In scope: one fixed read-only probe, eight synthetic self-tests, one dedicated workflow and these three specs.
Out of scope: VM/container/partition creation, service/feature/network/security changes, image pulls, installs, credentials, physical/saved environments, production admission and snapshots.
## 历史经验与坑
Issue81/PR99 runtime initialization failures and Issue101 completion mismatch remain unresolved.
Feature presence, API success and Job accounting are not execution or confinement proof.
## 术语定义
HCS: Host Compute System APIs; WHP: Windows Hypervisor Platform APIs.
Observed: a read returned evidence; it does not mean an execution environment works.
## 需求列表
### FR-1: Fixed read-only acquisition
Priority: Must. As a maintainer, I need existing capabilities without changing the runner.
WHEN invoked on the dedicated Actions runner THEN the probe SHALL record image/OS, fixed feature/service names and CPU virtualization indicators.
WHEN vmcompute is already Running THEN the probe SHALL query only HcsGetServiceProperties Basic; otherwise it SHALL skip that query without starting the service.
WHEN native reads occur THEN only fixed WHvGetCapability codes and HCS Basic SHALL be used.
### FR-2: Honest negative evidence
Priority: Must. As a maintainer, I need missing/error results rather than invented readiness.
IF a required feature/query/service prerequisite is absent or unknown THEN the job SHALL fail after retaining the observation.
WHEN every read succeeds THEN execution/network/filesystem/lifecycle acceptance SHALL still remain untested.
### FR-3: Exact finite validation and provenance
Priority: Must. As a reviewer, I need a bounded source-specific observation.
WHEN the workflow runs THEN eight named synthetic tests SHALL run before native acquisition and exact source/tree/image/run binding SHALL be retained.
IF tests fail THEN native acquisition SHALL not run.
## 非功能需求
Each functional file <=280/160/100 lines respectively, total <=540; each spec <=80 lines.
Job timeout five minutes; bounded native result copy 65536 UTF-16 characters; no automatic retry or remediation.
No user data or credential reads; only fixed diagnostic fields enter the artifact.
## 依赖关系
Base39a9ae7e2761f419db5cace712368e5671042b5e; stock windows-2025/pwsh and installed native DLLs.
GitHub does not guarantee nested virtualization. Positive reads do not change that support boundary.
