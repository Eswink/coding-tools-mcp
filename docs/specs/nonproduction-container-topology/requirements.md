# 需求文档：nonproduction-container-topology
## 功能概述
Complete runnable nonproduction deployment engineering for Issue40.
## 范围边界
New renderer, disposableDocker fixture/tests/workflow/docs. Existing binary bind policy and historical blueprint unchanged.
## 依赖关系
Shipped enrollmentbootstrap increment fromIssue39; DockerEngine28+, Compose2.27.0; official pinned images.
## 非功能需求
No secrets in logs/artifacts; all operations bounded; no hostnetwork/securityconfiguration changes.
## 需求列表
### FR-1: Runnable protected topology
The gate SHALL Render actual protected JSON CLI mounts, non-root gateway/ingress/database, immutable canonical origin, private DB network and bounded restart/shutdown settings.
**验收标准:** explicit positive/negative unit andnativefixture cases.
### FR-2: Loopback boundary preserved
The gate SHALL Keep GatewayConfig loopback-only; use namespace-sharing Nginx on internal8080, publish only explicit host127.0.0.1, never host networking or competing443.
**验收标准:** explicit positive/negative unit andnativefixture cases.
### FR-3: Shipped from-empty bootstrap
The gate SHALL Use real shipped migration/owner/client/invite/proof/redeem/select commands with ephemeral fixture secrets; no ad-hoc device SQL or example executable. Application DB role is non-superuser.
**验收标准:** explicit positive/negative unit andnativefixture cases.
### FR-4: Actual protocol and lifecycle proof
The gate SHALL Run DockerCompose2.27 plus actual nginx syntax, originalHost/forwardedHost behavior, OAuth/PKCE, MCP protocol-header behavior, WebSocketupgrade, occupiedport refusal, graceful shutdown/restart and revoked-device non-resurrection.
**验收标准:** explicit positive/negative unit andnativefixture cases.
### FR-5: Safe ownership and cleanup
The gate SHALL Operate only fresh project-labelled containers/volumes and owned temporary protected files; no production registry push/credentials/VPS/security settings; never include secret payloads in evidence.
**验收标准:** explicit positive/negative unit andnativefixture cases.
### FR-6: Truthful readiness
The gate SHALL Require nativeGHA evidence before completion. Unsupported CentOS8 and real TLS/WAF remain external production blockers; shipped local topology is engineering scope and cannot be deferred as a host issue.
**验收标准:** explicit positive/negative unit andnativefixture cases.
