# 设计文档：windows-hcs-capability-probe
## 概述
One independent read-only observer; FR-1, FR-2 and FR-3 are covered.
Base39a9ae7e2761f419db5cace712368e5671042b5e; tree ecf7792ca9911d969ac223227c819fbb8ef70fe7.
## 技术方案
FR-1: Read selected feature states, vmcompute/vmms/BFE statuses, OS/image and selected Win32_Processor fields.
Compile a fixed C# P/Invoke wrapper with DLL resolution limited to System32.
Read WHvGetCapability HypervisorPresent, ProcessorVendor and VmxBasic with exact fixed buffer widths.
VmxBasic absence is recorded as an optional observation, not a conclusion that every nested mechanism is unavailable.
Immediately before HCS Basic, re-read vmcompute. Skip unless the existing service is Running.
Call HcsGetServiceProperties with fixed Basic query; bound the UTF-16 copy and free its LocalAlloc result in finally.
No compute-system enumeration, identifiers, VM creation, service start, network call, install or remediation.
FR-2: Preserve HRESULT, returned size, nullable values, exceptions and skipped reasons separately.
A pure blocker function checks required raw prerequisites, never synthesizes execution support.
Execution, filesystem/network isolation and lifetime completion remain explicitly not tested for every result.
FR-3: Dot-source exposes functions without acquisition. Eight fixed synthetic tests run before the actual probe.
Dedicated branch-only push workflow uses pinned checkout/upload actions, read-only contents and no persisted credentials.
## 数据模型
JSON schema version1 includes source/run/image binding, ordered observations, blockers and fixed untested conclusions.
No arbitrary arguments, remote commands, URLs, environment dump or existing system inventory is accepted.
## API 设计
Get-HcsProbeBlockers accepts fixture observations and returns fixed blocker labels.
Invoke-HcsCapabilityProbe collects actual fixed observations and returns the report.
The script writes one specified evidence file, then fails if blockers are present.
## 文件结构
scripts/windows_hcs_capability_probe.ps1 <=280 lines.
scripts/windows_hcs_capability_probe_tests.ps1 <=160 lines.
.github/workflows/windows-hcs-capability-probe.yml <=100 lines.
Three docs/specs/windows-hcs-capability-probe documents <=80 lines each.
No existing file changes; no production call sites.
## 设计决策
HCS Basic replaces enumeration: it answers API availability without collecting system identities or creating an asynchronous operation handle.
WHP presence and supported HCS schemas are prerequisites only; no partition is created to prove execution.
## 测试策略
Eight synthetic cases cover all-observed, missing feature, wrong feature type/state, service stopped/unknown, WHP false/error and HCS failure.
Inspect native declarations, fixed names, branch filter, readonly token and artifact bounds independently.
Native compilation and self-tests execute on Windows before actual capability reads.
## 风险评估
No local PowerShell runtime is available: static review is local; native tests precede acquisition in Actions.
Service state may change after observation; record uncertainty, never start or repair it.
Native reads may stall: the finite job timeout preserves an incomplete outcome rather than retrying.
Missing prerequisites are a useful negative result, not a reason to enable features.
## 来源
https://learn.microsoft.com/en-us/virtualization/api/hcs/reference/hcsgetserviceproperties
https://learn.microsoft.com/en-us/virtualization/api/hypervisor-platform/funcs/whvgetcapability
https://github.com/actions/runner-images/blob/main/images/windows/toolsets/toolset-2025.json
