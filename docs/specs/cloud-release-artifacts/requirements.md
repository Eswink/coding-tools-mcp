# 需求文档：cloud-release-artifacts
## 功能概述
Deliver standalone server executables alongside desktop installers.
## 范围边界
Independent cloudworkflow/helper/tests/docs only; frozen desktop packaging files unchanged.
## 依赖关系
Owner version decision, gateway product version alignment, final exact seven-job integration.
## 需求列表
### FR-1: Product/component authority
**优先级:** Must
The gate SHALL Require desktop six-field selectedRC and cloud-gateway package/self-lock version equal; preserve independent library/protocol versions.
**验收标准:** mutation tests or real nativeCI receipts verify eachrequirement.
### FR-2: Exact release binaries
**优先级:** Must
The gate SHALL Build all four Linuxamd64 binaries onUbuntu22 from locked exactsource; verify ELF64x86_64, actual--help/--version and missingarguments rejection.
**验收标准:** mutation tests or real nativeCI receipts verify eachrequirement.
### FR-3: Safe portable bundle
**优先级:** Must
The gate SHALL Package only fourbinaries plus explicit README and source/version/digest manifest; no configs, fixturekeys, credentials or localstate; verify archive members andchecksums before extracting.
**验收标准:** mutation tests or real nativeCI receipts verify eachrequirement.
### FR-4: Actual process smoke
**优先级:** Must
The gate SHALL Run existing isolated realHTTP andcontrol/AgentWSS process tests against downloaded exactreleasebytes onUbuntu24, retain actual reports andfinaldigest. Explicitly distinguish MCP CLI smoke from full liveMCP process proof.
**验收标准:** mutation tests or real nativeCI receipts verify eachrequirement.
### FR-5: Release boundaries
**优先级:** Must
The gate SHALL Require exactsuccessful integration using existing packaging helper, owner-controlled push/explicitdispatch; no versionchoice, VPS, publication or fullWindowssecurityclaim. Fullrelease requires both desktop andcloud artifactfamilies.
**验收标准:** mutation tests or real nativeCI receipts verify eachrequirement.

## 非功能需求
Bounded JSON and subprocess operations; exact allowlists; no embedded secrets or production service changes.
