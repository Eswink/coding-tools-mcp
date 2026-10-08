# 任务清单：windows-hcs-hvsocket-policy
## 任务列表
- [x] T1 / FR-1..FR-4: record explicit bounded approval, exact baseline and primary-source mechanism limits
- [x] T2 / FR-1: freeze exact patch/hash, six stdio derivation and finite paths; mandatory HIGH review
- [ ] T3 / FR-1..FR-3: implement fixed policy, owned canaries and persistent supervisor
- [ ] T4 / FR-4: keep lifecycle/error ownership and false production flags; fixed artifact pins
- [ ] T5 / FR-1..FR-4: meaningful native tests before import, local cross-build/vet and independent review
- [ ] T6 / FR-1..FR-4: staged scope/gencommit; publish dedicated source and monitor one candidate
- [ ] T7 / FR-4: verify finite artifact, classify actual outcome, preserve durable evidence and Issue81 update
## 验收标准
AC-1: exact approved patch and input identities; no dependency lock drift, unowned endpoints or settings change.
AC-2: three nonce-positive controls, explicit negative errors after successful seal, denied new exact binds.
AC-3: same channels usable and all four fixed stock runtimes plus live child observed after seal.
AC-4: whole UVM exit and owned endpoint/I/O cleanup independently observed; error/uncertainty stays sticky.
AC-5: no production safety claim; matrix failure is a useful negative result, not a reason to relax an assertion.
## 估算与风险
One source-specific experiment, high uncertainty in HCS descriptor behavior; no remediation or automatic candidate rerun.
## 回滚
Do not merge the experimental branch. Retain all owned VM data until standard runner retirement; production remains unchanged.

## 交付物清单
Exact policy source, native tests, pinned CI workflow and finite source-specific result artifact.
## 需求覆盖矩阵
FR-1: T1,T2,T3,T5; FR-2: T3,T5,T6; FR-3: T3,T5,T6; FR-4: T4,T5,T6,T7.
## 文件变更清单
Five new Go files: policy_host.go, policy_session.go, policy_shared.go, policy_guest.go, policy_test.go.
Four existing files: prototype.go, fixture.go, prepare.ps1 and windows-hcs-boot-prototype.yml.
Three new specs: requirements.md, design.md and tasks.md in this directory.
