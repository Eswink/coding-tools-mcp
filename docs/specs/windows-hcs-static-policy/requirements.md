# 需求文档：windows-hcs-static-policy
## 功能概述
One bounded comparison of immutable HCS creation policies; base3d59798040f015f8421849518c32d28842046bad.
The prior dynamic seal failed; its source, assertions and artifact remain unchanged on the prior branch.
## 范围边界
User approved two sequential disposable standardWindowsActions VMs and two private GuestCommunicationServices registrations on2026-10-08.
No existing key/service, registryACL, WFP/firewall/Defender/HyperVsetting, DNS, externalhost, credential or user workspace change.
Same pinned image, runtimes, tiny default-deny dependency patch and process-only import privileges.
## 历史经验与坑
Creation default bind denied a fresh exactVM service, but successful dynamic descriptor updates did not remove existing permission.
DefaultBind excludes wildcard binds. DefaultConnect applies to host-to-guest connections; it is not an outbound guest filter.
## 术语定义
Control: initial explicit allowances for five owned canaries. Restricted: same canaries omitted from the initial service table.
Owned registration: exact fresh random GUID key with created-new disposition, one unchanged ElementName marker and no children.
## 需求列表
### FR-1: Exact temporary registrations
Priority: Must. As a reviewer, I need no existing registration to be adopted or modified.
WHEN registering THEN exactly two generated GUID keys under the existing GuestCommunicationServices parent SHALL pass prior absence and created-new disposition checks.
WHEN initialized THEN only ElementName SHALL be written; retain the key handles and exact marker values.
WHEN cleaning THEN unchanged marker/type, exactly one value and zero subkeys SHALL be required before exact nonrecursive deletion, handle close and absence verification.
IF identity/content is unexpected or any VM lifetime is uncertain THEN retain-and-fail; never broaden cleanup.
### FR-2: Two immutable profiles with sequential ownership
Priority: Must. As a reviewer, I need a matched control without dynamic policy changes.
WHEN running THEN the same five GUIDs SHALL be used by two sequential UVMs, with new IDs/nonces and private scratch per profile.
WHEN starting the second THEN the first SHALL have passed all control cases and independent VM/endpoint/I/O completion checks.
WHEN creating THEN defaults SHALL deny bind/connect; seven broker entries SHALL allow only brokerSID bind, deny connect and deny wildcard.
Control SHALL additionally allow four host canary routes plus host connect to the fifth guest canary; restricted SHALL omit all five.
No UpdateHvSocketService or other runtime policy modification is used.
### FR-3: Actual effective-boundary matrix
Priority: Must. As a reviewer, I need explicit success controls and effective refusal results.
Control SHALL prove four registered/unregistered wildcard/children nonce exchanges and host-to-own-guest listener exchange.
Restricted SHALL reject those same service IDs with explicit access/refusal errors; timeout, absent route or missing ready receipt SHALL fail.
Each profile SHALL close/join canaries before exactVM bind checks, preserving the distinction between access denial and address collision.
### FR-4: Broker lifetime and completion
Priority: Must. As a maintainer, I need useful stock execution only after the restricted matrix passes.
WHEN releasing THEN seven single-accept broker listeners SHALL have actual checked retirement receipts; no new host listener or HCS process SHALL open afterward.
Only restricted success SHALL invoke fixed stock runtimes and live-descendant checks through established supervisor streams.
Both profiles SHALL retain independent Terminate/Wait/ExitError/Close and endpoint/I/O checks; any error remains sticky.
## 非功能需求
At most two owned VMs, never concurrent; five private serviceGUIDs; two registrations;32-byte nonces and2-second dial deadlines.
Up to12 paths. PolicyGo caps495/195/180/230/210(total1310); prototype440 fixture100 prepare160 workflow110; three specs210total.
No dependency lock changes. Native pure tests before imports; exact artifact/source/hash binding.
## 依赖关系
Passing this matrix supports its measured host/build/scopes only; registered precedence and alias/general safety need further assessment.
network_denial_proven/workspace_integration/production_admission remain false. OriginalLinuxpolicy, rootidentity, snapshot and copyback remain separate.
