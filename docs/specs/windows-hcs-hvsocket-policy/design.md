# 设计文档：windows-hcs-hvsocket-policy
## 概述
FR-1..FR-4 measure descriptor-only transition feasibility while production gates remain closed.
Manual risk HIGH; exact source and the tiny disposable dependency patch require independent review before publication.
## 技术方案
FR-1: prepare.ps1 embeds one literal unified diff against internal/uvm/create_wcow.go at official fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd.
Preimage SHA256 756d21059132c34baf64cfa1ff2c798f6486c6235514960ab1f4ebf28497cfb4.
Postimage SHA256 b22b6d758ef183b3d40ad11bab62265126ce5f91ff957fb8ecad04be6fe72927.
The diff replaces default bind D:P(A;;FA;;;SY)(A;;FA;;;BA) with D:P(D;;FA;;;WD) and adds the same default connect deny.
No general replacement, package updates, lock edits or unreviewed runtime downloads. Clone uses process-local core.autocrlf=false for exact bytes.
Initial explicit bind allows only the broker process user's SID; connect deny and wildcard=false except the two owned wildcard canaries.
GCS service acef5661-84a1-4e44-856b-6245e69f4620 plus winio.VsockServiceID ports 0x40000001..0x40000006.
The pinned GCS code initializes its counter at 0x40000001 and allocates stdin/stdout/stderr sequentially per process.
Exactly two HCS processes are created: trusted bootstrap then persistent ContainerUser fixture. Additional allocation fails under default deny.
The fixture emits initial stdout and stderr handshakes and acknowledges stdin, which waits for each upstream one-accept ioChannel listener to close before release.
After the stdin/stdout/stderr receipts, rebind and immediately close each of the identical seven broker addresses; failure prevents sealing.
This actual receipt verifies one-accept listener release in addition to pinning the upstream allocation and close source hashes.
FR-2: create three distinct GUID service entries; each host listener binds exact runtime ID, wildcard or children, respectively.
No registry writes. Guest targets only these GUIDs through documented Parent alias; no existing service ID is dialed.
Canaries remain listening after the positive handshake to test preexisting-listener bypass explicitly.
Update all ten entries to deny bind/connect, wildcard=false, Disabled=false. Await every call; first unsupported update prevents payload release.
Fresh connections use short deadlines. Only explicit refusal/access-denied qualifies as denial; timeout/unavailable is inconclusive failure.
After the negative connections, close/join only the three owned canaries so address-in-use cannot masquerade as an ACL result.
Fresh exact-VM bind checks require WSAEACCES; a successful socket is closed and recorded as unexpected permission.
FR-3: same persistent process invokes fixed runtime commands internally after seal, so no extra HCS stdio services are opened.
All original runtime command strings are shared unchanged between the host test inventory and guest fixture.
Guest captures bounded outputs and reports exact exit23/markers; starts fixture parent/check cases to observe a live descendant.
A final stdout/stderr exchange proves established broker streams survived; process wait/exit/close and owned UVM termination remain separate.
FR-4: errors accumulate; unexpected permissions cannot be overwritten by successful later cases. No resources or evidence are deleted.
## 数据模型
Fixed JSON-line messages: nonce, phase, exactly three owned service IDs. No command, filesystem path, destination VM or URL fields.
Replies include fixed phase/nonce, canary results and fixed runtime results; strict decoding rejects unknown fields, extra JSON and oversized lines.
Finite result.json adds configured IDs/descriptors, before/after observations, bind errors, stream/lifecycle results and explicit scope limits.
## API 设计
Host policy owns VM configuration, listeners, policy updates and the checked result matrix.
Host session owns one supervisor process and all I/O tasks; failure to join is uncertain and sticky.
Shared file contains fixed protocol plus unchanged runtime/encoding/output helpers; guest file accepts only fixed phases.
## 文件结构
Add policy_host.go, policy_session.go, policy_shared.go, policy_guest.go and policy_test.go under scripts/windows_hcs_boot.
Modify prototype.go, fixture.go, prepare.ps1 and .github/workflows/windows-hcs-boot-prototype.yml.
Three new documents in docs/specs/windows-hcs-hvsocket-policy. No upstream source is committed, only the exact patch in preparation.
## 设计决策
Use the fixed broker SID rather than a broad administrators/system allowlist for each admitted bind.
Preserve errors from preexisting listeners instead of closing them before the negative test, which would hide a policy bypass.
No registered wildcard endpoint claim: unregistered canary results cannot establish registered service behavior.
## 测试策略
Retain the existing17 Go and8 PowerShell preboot tests. Add policy inventory, frame rejection, denied-classification and sticky-failure tests.
Native tests precede imports; local cross-compilation/vet is not claimed as Windows execution.
Verify source/tree/parent, official inputs, patched-source hashes, exact test inventory and final artifact member hashes.
## 风险评估
Default bind/connect does not itself prove guest-origin isolation. A live exact listener may remain reachable after ACL tightening.
Kernel/registered service interactions, alias routing and source-specific host configuration remain outside this first matrix.
Uncertain constructor or cleanup never permits production admission or deletion of owned data.
## 来源
https://learn.microsoft.com/en-us/virtualization/api/hcs/schemareference#hvsocketsystemconfig
https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/make-integration-service#vmid-wildcards
https://github.com/microsoft/hcsshim/blob/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd/internal/uvm/hvsocket.go
https://github.com/microsoft/hcsshim/blob/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd/internal/gcs/guestconnection.go
