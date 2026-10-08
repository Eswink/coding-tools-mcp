# 需求文档：windows-hcs-surface-observation
## 功能概述
Observe guest-only socket surfaces and one fixed synthetic transfer in the already qualified owned-UVM experiment.
Base45ac13ec85c854e25f512f309d362f6be29ddb61; this adds observations, not production admission.
## 范围边界
Standard windows-2025 Actions; unchanged pinned Microsoft image, approved import process privileges and owned UVM lifecycle.
No host socket listener, AF_HYPERV bind/connect, DNS, external address, NIC/HNS/WFP/firewall/service/security change.
No real workspace, user data, copyback, snapshot operation or core RootIdentity/admission implementation change.
## 历史经验与坑
Run37719559925 proves stock cmd/WindowsPowerShell/Node/pwsh entry and owned UVM exit on the measured image only.
Linux currently denies socket/socketpair allocation; no-NIC cannot silently replace that contract.
HCS HvSocket descriptors control host bind/connect access; they are not guest-user outbound deny rules.
## 术语定义
Surface observation: one actual API result, including unavailable/error; never a global denial conclusion.
Quarantine: a fresh synthetic host output directory, never the approved user workspace.
## 需求列表
### FR-1: Fixed guest-only socket observations
Priority: Must. As a reviewer, I need actual allocations and local communication outcomes.
WHEN the fixture runs THEN it SHALL record IPv4/IPv6 TCP+UDP, AF_UNIX stream and AF_HYPERV raw allocation separately.
WHEN communication is attempted THEN it SHALL target only the fixture's own IPv4/IPv6 loopback or guest-workspace Unix listener, with a <=64-byte nonce.
WHEN AF_HYPERV is observed THEN it SHALL only allocate/close; it SHALL never bind/connect or enumerate services.
### FR-2: Bounded synthetic transfer
Priority: Must. As a reviewer, I need one auditable byte transfer without real copyback.
WHEN preparing THEN the host SHALL create fresh source/quarantine fixtures, pin them with supported os.Root handles, and retain source directory/file identities.
WHEN executing THEN at most1KiB synthetic input SHALL enter through HCS stdin and at most1KiB output SHALL return in a bounded fixed-schema envelope.
WHEN finishing THEN quarantine SHALL receive bytes only after complete owned-UVM exit and unchanged source identities/hashes plus matching nonce/input/output hashes.
### FR-3: Negative tests before privileged work
Priority: Must. As a reviewer, I need failure behavior before image import or boot.
WHEN tests run THEN os.Root rename resistance and ../sentinel escape SHALL be exercised only in fresh owned fixtures.
IF transfer bounds, nonce, source identity/content or completion are wrong THEN quarantine SHALL remain empty.
### FR-4: Preserve scope and interpretation
Priority: Must. As a maintainer, I need explicit evidence without weakening existing gates.
WHEN reporting THEN all prior runtime/lifecycle tests SHALL remain and network_denial_proven/workspace_integration/production_admission SHALL remain false.
WHEN an API is unavailable THEN preserve its error and observation slot rather than excluding it from the result.
## 非功能需求
Ten paths: three new Go files caps202/192/166; existing fixture/driver/preparation/workflow caps80/420/110/100; three specs80 each.
No new Go dependency/module resolution. Require Go1.24+ and use its documented Windows os.Root semantics.
One fresh UVM per candidate; socket peers have bounded deadlines; output64KiB/stream and existing30-minute job bound remain.
## 依赖关系
Existing approved CI boot/import authority; no additional settings or external network test authority.
Original all-socket denial and live-workspace semantics require an explicit product decision before any production change.
