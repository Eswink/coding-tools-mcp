# 需求文档：dependency-capture-live-engineering

## 功能概述
Exercise the unchanged noncloud dependency collector and separate fourth gateway lock audit on exact committed engineering source before a final candidate exists. Preserve genuine GLib source provenance and every raw advisory without granting security acceptance or release authority.

## 历史经验与坑
The collector is currently used only behind the final-source workflow gate. Its six command-boundary tests do not exercise a successful live GLib verifier. The existing exact-build engineering workflow covers only the gateway. Cargo is unavailable in the current local environment, so hosted evidence remains necessary.

## 术语定义
Pipeline integrity means complete, source-bound, untampered capture with validated command outcomes. It does not mean no security findings. Noncloud means desktop, local-agent and cloud-agent locks. Gateway is the fourth independent product lock.

## 范围边界
In scope: one new engineering wrapper/consumer, its deterministic tests, one exact-branch read-only workflow and these three specifications.
Out of scope: changes to existing collectors/verifiers/policies, dependency upgrades, builds or packages, final manifests, tags, publication, security-held runtime work and production credentials. Final-source recapture remains required.

## 需求列表
### FR-1: Genuine complete capture with failure retention
**优先级:** Must
When the engineering job runs, it SHALL execute the unchanged collector, including fresh official advisory acquisition and live pinned GLib verification, and audit the gateway lock against that same unchanged database. It SHALL preserve stdout, stderr, exact exits, commands and timestamps. Audit exit 1 SHALL be accepted only for well-formed nonempty findings; exit 0 with findings, exit 1 without findings, invalid counts, execution failures or source/database drift SHALL fail integrity verification while retaining diagnostics.

### FR-2: Independent exact-source artifact verification
**优先级:** Must
When the consumer downloads the same-run artifact, it SHALL obtain the trusted receipt digest from producer job outputs and expected source, repository, run, attempt and workflow from GitHub context. It SHALL verify source/tree/version, four locks, pinned tool identities, advisory snapshot, complete capture-artifact file hashes, raw report schemas/exits and the existing GLib source/metadata/paired-audit proof. Same-artifact tampering SHALL fail even when the attacker recomputes an inner hash.

### FR-3: Engineering-only authority and bounded execution
**优先级:** Must
The workflow SHALL use only the exact branch ci/issue85-dependency-capture-20261001 in Eswink/coding-tools-mcp, contents:read, pinned actions, no secrets and no package build or publish steps. Both receipts and verification results SHALL retain engineering_only=true, release_approved=false, publish_approved=false and raw_zero_claim=false. Adverse findings SHALL remain visible separately from integrity status.

## 非功能需求
New helper and test files remain below 300 lines each; workflow target is 130 lines. Keep capture and consumer bounded to 35 and 10 minutes, respectively. Never dump environment variables or credentials. Always upload available diagnostics; cancellation or timeout with missing evidence remains incomplete.

## 依赖关系
Reuse release_dependency_capture, exact_build_audit source/database identity and the existing GLib verifier without changing their behavior. This lane cannot satisfy final release or installed-desktop-byte acceptance.

## 验收清单
Local positive/negative contracts, workflow lint and independent code review precede commit/push. Actual hosted capture and downloaded artifact verification remain pending until explicitly approved execution completes on the new head.

The capture artifact is fully inventoried and digest-bound. Installation/test/source logs and the producer convenience summary are uploaded separately as diagnostic-only evidence; the consumer recomputes its own integrity result.
