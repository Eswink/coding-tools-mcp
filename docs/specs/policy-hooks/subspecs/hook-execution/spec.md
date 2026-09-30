# Policy sandbox lifecycle and production dispatch

## Acceptance
### FR-4
WHEN an enabled hook runs THEN the system SHALL recheck current local execution authority and parent exec.run scope, native command policy and shared ExecPolicy; prompt, forbidden, missing approval or unknown rules block and hook output never grants authority.

### FR-5
WHEN a hook child starts THEN the system SHALL use the existing mandatory platform sandbox and managed process tree; network remains denied and filesystem write is allowed only when locally approved within the parent workspace capability; unsupported platforms fail closed.

### FR-6
WHEN hooks run THEN the system SHALL enforce eight registrations, deterministic ID ordering, one nonqueued invocation per registry, per-hook two-second timeout, bounded output and total budget, request deadline/cancel/revoke checks and actual descendant drain; no recursive trigger or automatic uncertain replay is allowed.

### FR-7
WHEN a mandatory before hook fails THEN the primary operation SHALL not start; WHEN an after hook fails THEN the result SHALL retain the actual primary outcome and state that side effects are not rolled back; raw hook output remains untrusted and is not returned as permission.

### FR-8
WHEN release validation runs THEN the system SHALL exercise the real native dispatcher and native approval path with immutable script execution, denial, changed hashes, malformed bounds, deterministic order, before/after failure, cancellation, revocation and sandbox containment; Windows unavailable remains release-blocking rather than waived.

## Design and tests
Use parent design. Fail-closed negative tests and real production native dispatcher evidence are mandatory.

## 范围
Acceptance requirements above; production integration is mandatory.
## 需求回链
See FR references above and parent requirements.md.
## 涉及文件
See parent design explicit source ownership.
## 不做项
No implicit discovery, model approval, sandbox bypass or waiver of Windows gate.
