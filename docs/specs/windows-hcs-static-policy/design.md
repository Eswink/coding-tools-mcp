# 设计文档：windows-hcs-static-policy
## 概述
FR-1..FR-4: static creation policy and owned endpoint lifetime, not the rejected dynamic transition.
Manual risk HIGH; root-reviewed plan ad24276133603a88fa7b95283e5195c11a4798d1eb3d8ac9e9c1baf5c3c3ec48.
## 技术方案
FR-1: open existing HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Virtualization\GuestCommunicationServices parent without creating it.
Generate five v4GUIDs once; keys only for first two. Check exact absence, then CreateKey disposition before setting ElementName.
Keep each created handle and marker. Compare its value type/content and key value/subkey counts before deletion.
Freshly reopen its exact path and compare the same bounded owned-content predicate before DeleteKey(parent,GUID); no recursive delete.
An unexpected existing key is never written/deleted. Partial creation stays tracked; failures retain owned keys if identity is uncertain.
After all started VMs have independently exited, clean only verified own keys, close retained handles and verify exact absence.
No hostile concurrent host actor is assumed; this is not an atomic registry identity primitive.
FR-2: import once, separate scratch-control and scratch-restricted, at most one live UVM. Generate separate VMIDs and nonces.
Creation defaults stay D:P(D;;FA;;;WD); exact same upstream preimage/postimage and source hashes as previous candidate.
Always retain only seven broker entries in restricted: GCS and ports0x40000001..06, brokerSID bind, connectdeny, wildcardfalse.
Control additionally admits four private host serviceIDs with wildcardtrue and the fifth private guest service with brokerSID connect.
No dynamic descriptor updates. The source-specific failure is not reclassified or bypassed.
FR-3: host listener scopes alternate wildcard/children for registered pair and unregistered pair. Only guest Parent routing targets those private IDs.
Inside a WCOW container, the fifth guest listener uses wildcard VMID, as pinned official guestBindReExecFunc does; it is reachable only at its privateGUID.
Guest reports actual listener ready before the host dials the retained container SystemGUID plus the fifth private serviceGUID.
Read only PTSystemGUID from the created container handle after checking its ID matches the owned expected container. Capture valid nonzero GUID distinct from UVMRuntimeID before bootstrap; re-read it before dialing and require equality.
HCSOCI already retains the container-SystemGUID-to-UVM passthrough mapping; create no new mapping and enumerate no other compute systems. Positive requires nonce echo; negative requires explicitWSAEACCES/refusal and zero accepted guest connections.
The first static candidate targeted the UVM primary compartment and timed out; this source-supported identity correction is not yet a proven runtime root cause.
Guest listener closure is acknowledged through the existing supervisor protocol and its task is joined; unexpected output/errors fail.
Close and join all host canaries before fresh exactVM bind comparisons to avoid false address-in-use results.
Control requires exactbind success/close; restricted requiresWSAEACCES. Both record all observations without deleting denominator entries.
FR-4: establish trusted bootstrap and persistent ContainerUser supervisor; verify retiredGCS/stdio listeners by rebind/close after handshakes.
A duplicate active-bind control belongs to the control profile, before canary retirement; restricted cannot assume it can bind denied services.
Supervisor sequence is fixed by control/restricted first message. No arbitrary paths, commands, destinations or external traffic accepted.
Control finishes without stock payload. Restricted invokes unchanged four runtime commands and parent/check only after all denies pass.
Both retainedVM lifetimes and cleanup run on errors; uncertain first lifetime prevents the second VM and registration deletion.
## 数据模型
Suite report: schema/source, fiveGUIDs, ownedregistration creation/validation/deletion results, two ordered VM receipts, stickyerrors and falseproductionflags.
VM receipt: profile/ID/nonce, initial serviceinventory, hostroute and hostconnect observations, exactbind results, retiredbrokerlistener receipts and lifetimestates.
Fixed protocol adds guest-listen/guest-close states and bounded listener receipts; strict phase/nonce/GUID count remains.
## API 设计
Static suite orchestration reuses runPrototype with explicit profile/sharedGUID inputs and returns full lifecycle evidence before starting the next profile.
Registry helpers act only on generated GUIDs and fixed parent; a pure bounded metadata predicate supports preboot ownership tests.
policy_session remains the persistent channel owner; no new post-release HCS exec path.
## 文件结构
Five existing policyGo files; prototype.go, prepare.ps1, existingworkflow; fixture.go only if dispatch changes are necessary.
Three new docs/specs/windows-hcs-static-policy documents. No production sources or previous failedcandidate specs are changed.
## 设计决策
SameGUIDs with separate creation profiles give a matched policy comparison without relying on ineffective dynamic changes.
The registration keys persist only across the sequential comparison; all VM-specific endpoints close between profiles.
## 测试策略
Preserve relevant22prebootGo/8PowerShelltests; add pure ownership rejection, profile inventory, sequenced completion and hostconnect classification tests.
Static/source validation confirms no dynamicUpdate calls, exactly two registrations and fixed workflowbranch/parent.
Cross-build/vet before publication; actual native tests before import; independent review of exactfinalpacket.
## 风险评估
Any registered wildcard reachability under the restricted profile rejects this route; no automatic remediation or weaker pass.
Any unsupported/missing guestlistener positive control is inconclusive and prevents claiming hostconnect denial.
No source-independent/globalhost or productionworkspace safety claim is made.
## 来源
https://learn.microsoft.com/en-us/virtualization/api/hcs/schemareference#hvsocketsystemconfig
https://learn.microsoft.com/en-us/windows-server/virtualization/hyper-v/make-integration-service
https://github.com/microsoft/hcsshim/blob/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd/test/functional/hvsock_test.go#L951
https://github.com/Eswink/coding-tools-mcp/issues/81#issuecomment-6053874942

https://github.com/microsoft/hcsshim/blob/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd/internal/hcsoci/create.go#L292
https://github.com/microsoft/hcsshim/blob/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd/internal/hvsocket/hvsocket.go#L39
