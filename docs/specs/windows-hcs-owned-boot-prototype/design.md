# 设计文档：windows-hcs-owned-boot-prototype
## 概述
FR-1..FR-4: one source-reviewed Actions-only experiment, not an execution backend.
HIGH risk from privileged image parsing and hypervisor lifecycle; independent review precedes publication.
## 技术方案
FR-1: reuse fixed read-only capability tests/probe, require already-running vmcompute and installed prerequisites.
Clone only official hcsshim at the exact SHA and verify go.mod/go.sum/vendor/modules.txt hashes.
Build only our command and pure tests inside that module with vendored dependencies; never run upstream functional TestMain.
Its LazyImageLayers helper adds Defender exclusions; this prototype must not call it.
Download only the two fixed official MCR layers (total2396769443 bytes); verify sizes and SHA256 before importing.
Import into fresh private roots using ImportLayerFromTar in a separate process; no global privilege policy changes.
FR-2: create private UVM scratch and one guest container scratch, readonly OS layer shares, no extra host mappings.
Preserve upstream guest EnableCompartmentNamespace=1 default; do not disable isolation to avoid guest registry writes.
Intrinsic HCS guest-control/HvSocket address plumbing remains exposed; no host HNS namespace, NIC or network policy changes.
Use NoWritableFileShares, NoDirectMap, two vCPUs and 2GiB; no dumps, console pipe, graphics, credentials or additional devices.
Use ContainerUser without administrative fallback. Transfer a trusted runtime ZIP over fixed HCS stdin, expand inside synthetic guest workspace.
Run stock cmd/WindowsPowerShell from ServerCore plus existing Actions Node/pwsh distributions with fixed commands and no profiles.
FR-3: create uses fresh UUID and retained UtilityVM pointer; no enumerate/adopt/prefix cleanup route exists.
Fixture parent spawns a child, exits23, then a second fixture invocation verifies the child handle is still nonsignaled.
Terminate and WaitCtx results are separate, sticky observations. ExitError is recorded too; close success cannot erase them.
Constructor failure remains uncertain because upstream may internally clean up without exposing wait errors.
Keep every imported layer and scratch file until the runner itself is retired, including on success; no recursive cleanup.
FR-4: record fixed source/tree/run/image, dependency locks, runtime hashes, each bounded output and lifecycle result.
No user workspace is mounted or copied. Guest loopback/socket creation, AF_UNIX and AF_HYPERV denial are unproven.
## 数据模型
Fixed JSON schema1 report: source identity, owned IDs, stage, cases, errors, termination/wait/exit/close results and false production flags.
Host inventory is limited to known runner/runtime/prerequisite fields. No environment or secret dump.
## API 设计
Host command modes are exactly import and run; parameters are private root plus fixed runtime bundle, never shell/URL inputs.
runGuest accepts only driver-internal commands and bounded stdin/output; deadlines and I/O joins are mandatory.
buildOptions and completion predicates are pure-testable; a fixed host cmd fixture uses only its fresh test directory, without import/VM/network changes.
## 文件结构
.github/workflows/windows-hcs-boot-prototype.yml (100); scripts/windows_hcs_boot/prepare.ps1 (180).
scripts/windows_hcs_boot/prototype.go (420), prototype_test.go (180), fixture.go (100).
Three docs/specs/windows-hcs-owned-boot-prototype documents (80 each); no existing path changes.
## 设计决策
Use Microsoft's pinned production APIs directly, not Docker defaults or the upstream test harness with hidden remediation.
Offline vendored build avoids a new dependency lock or mutable package download during privileged execution.
Keep lifecycle cleanup errors visible and data retained; shared Job accounting is not a completion authority.
## 测试策略
Native preboot tests precede image download/import/boot; verify fixed options, nil network/mounts, command allowlist, io.Copy output cap, sticky failures and original/corrected cmd bytes.
Local static workflow/source review is separate from Windows compilation/tests; never label unrun native tests passed.
Actual CI checks four stock runtime markers/file roundtrips/exit23, live descendant, and retained whole-UVM termination.
Verify source unchanged after run and exact artifact members/hashes before interpreting results.
## 风险评估
Image import uses approved privileges and trusted digest-bound Microsoft input but exercises complex Windows parsers.
The VM may not boot on standard Actions; fail honestly, with no feature/service/network auto-fix or extra environment.
No-NIC is insufficient to meet the original deny-network contract; even successful runtime entry leaves that gate unresolved.
## 来源
https://github.com/microsoft/hcsshim/tree/fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd
https://learn.microsoft.com/en-us/virtualization/api/hcs/reference/hcsterminatecomputesystem
https://learn.microsoft.com/en-us/virtualization/windowscontainers/images-eula
https://learn.microsoft.com/en-us/virtualization/windowscontainers/manage-containers/container-base-images
