# 设计文档：windows-hcs-surface-observation
## 概述
FR-1..FR-4: fixed synthetic observations built onto the qualified prototype; manual risk remains HIGH.
No network-equivalence, filesystem-backend, #86, snapshot or copyback acceptance is claimed.
## 技术方案
Guest fixture receives one size-limited JSON envelope over existing HCS stdin; no paths/commands/URLs are accepted.
FR-1: explicit Winsock startup, six fixed family/type/protocol allocations and close receipts.
Three listeners bind only127.0.0.1:0, [::1]:0 or a fresh socket pathname within the guest synthetic workspace.
Each client connects only to its own just-created listener, exchanges its nonce and closes both endpoints within fixed deadlines.
No internet, DNS, host address or AF_HYPERV destination appears in executable commands.
AF_HYPERV allocation success is not host reachability evidence; no allocation failure becomes universal denial.
FR-2: host creates fresh source and quarantine sibling directories inside its owned CI root, opens os.Root handles, and writes one fixed input filename.
Capture directory and input identities from held file handles; reread through the same Root and compare identity/hash before quarantine.
Go documents that Windows os.Root holds a directory handle that prevents its rename/deletion; the native preboot test must verify this on the actual runner.
The fixture does not claim os.Root replaces the repository's stricter production reparse/ancestor/authority policy.
Guest writes/reads only fixed synthetic filenames and returns nonce, input hash, output bytes/hash and separate socket observations.
Return data remains in host memory while the retained UVM is alive. Only existing complete(report) plus unchanged fixture checks may create the quarantine file.
Quarantine and imported disks remain owned fixture data; no result is copied to any input/user workspace.
FR-3: test exact bytes, size, nonce/hash mismatches, source mutation, incomplete lifetime and root rename/traversal before import.
FR-4: retain previous stock-runtime/descendant cases, false admission flags and fixed artifact source/hash binding.
## 数据模型
Input: fixed nonce, <=1KiB bytes, SHA256. No caller-supplied filesystem path.
Output: fixed marker/nonce/input hash, <=1KiB bytes/output hash; six allocation and three local-peer observations with errors/close results.
Host report adds synthetic root/file identity and quarantine outcome; no whole-host inventory or secret data.
## API 设计
surface_guest.go contains only the fixture's fixed guest behavior; existing fixture main adds one surface mode.
surface_host.go manages only fresh fixtures and their single envelope; no generic validator or production API is introduced.
Existing driver integrates one case and performs quarantine admission only after its existing owned-UVM completion fence.
## 文件结构
New scripts/windows_hcs_boot/surface_guest.go<=202, surface_host.go<=192, surface_test.go<=166.
Existing fixture.go<=80, prototype.go<=420, prepare.ps1<=110, windows-hcs-boot-prototype.yml<=100.
Three new docs/specs/windows-hcs-surface-observation documents<=80 each; exactly ten paths.
## 设计决策
Guest local peers answer the semantic question without contacting unrelated services or changing security settings.
AF_HYPERV host reachability needs a separately reviewed synthetic host endpoint; it is excluded here.
Transfer into quarantine measures byte/identity/lifetime binding while leaving live-workspace and revocation/copyback policy unresolved.
## 测试策略
Existing19 preboot tests remain. Add targeted socket-inventory/packet/Root/negative-quarantine tests before import.
Actual guest observations are data; unsupported families remain visible. No expected denial assertion is removed.
Independently review exact source/hash and download/verify the final finite artifact before drawing conclusions.
## 风险评估
Loopback or Unix success disproves equivalence to the literal Linux socket-denial policy, not the VM boundary itself.
No NIC and empty HCS service table do not establish AF_HYPERV denial; intrinsic GCS/stdio channels remain.
Parent/ancestor races, reparse/hardlink handling, real copyback conflicts and local authority integration remain outside fixture acceptance.
## 来源
https://go.dev/blog/osroot
https://devblogs.microsoft.com/commandline/af_unix-comes-to-windows/
https://learn.microsoft.com/en-us/virtualization/api/hcs/schemareference#hvsocketsystemconfig
https://github.com/Eswink/coding-tools-mcp/issues/81#issuecomment-6051236444
