# Native approved immutable hook registry

## Acceptance
### FR-1
WHEN Hooks are configured THEN the system SHALL accept only explicit native owner approval of an exact preview digest bound to the current live listener, registry identity and workspace; model/project text cannot install or approve hooks.

### FR-2
WHEN a hook is registered or invoked THEN the system SHALL validate bounded unique IDs, fixed event/tool, host executable, immutable argv/cwd and captured script hash; missing or modified artifacts are rejected, never silently refreshed.

### FR-3
WHEN a project contains Git hooks, instructions or scripts THEN the system SHALL not discover or execute them implicitly; only explicitly selected native-approved scripts may execute, and Git hooks stay disabled.

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
