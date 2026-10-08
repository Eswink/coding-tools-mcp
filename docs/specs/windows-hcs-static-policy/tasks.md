# 任务清单：windows-hcs-static-policy
## 任务列表
- [x] T1 FR-1/FR-2: explicit twoVM/tworegistration approval and HIGH scoped design
- [x] T2 FR-1/FR-2/FR-3/FR-4: specs, impact and exact baseline
- [ ] T3 FR-1: owned registration creation/validation/nonrecursive cleanup
- [ ] T4 FR-2/FR-3: fixed profiles, matched canaries and guest-listener control
- [ ] T5 FR-4: sequential lifecycle, sticky failures and restricted-only stock payload
- [ ] T6 FR-1/FR-2/FR-3/FR-4: native tests, static/cross-build, independent source review
- [ ] T7 FR-1/FR-2/FR-3/FR-4: gencommit, dedicated branch, single exactcandidate run and verifiedartifact
## 交付物清单
Finite source/spec packet, matched control evidence and explicit security/cleanup result. Prior failedsource remains intact.
## 需求覆盖矩阵
FR-1:T1,T2,T3,T6,T7. FR-2:T1,T2,T4,T6,T7. FR-3:T2,T4,T6,T7. FR-4:T2,T5,T6,T7.
## 文件变更清单
policy_host/session/shared/guest/test.go; prototype.go; prepare.ps1; windows-hcs-boot-prototype.yml; optionalfixture.go; three new specs.
## 验收标准
AC-1: only two created-new keys changed, own markers/nochildren checked, exactcleanup or explicit retained uncertainty.
AC-2: first profile positively controlled and fullyfinished before second; immutablepolicies/sharedGUIDs/newnonces.
AC-3: restricted effective denial for all testedhostroutes/hostconnect, no timeout-as-denial.
AC-4: restricted success permits stockruntime phase; all lifetimes/cleanup checked independently; productionflagsfalse.
## 风险与回滚
A failedmatrix rejects the candidate. No merge, no rerun, no existingservice remediation. Retain uncertainownedstate to runnerretirement.
