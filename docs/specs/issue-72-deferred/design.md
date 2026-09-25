# Design: issue-72-deferred

## Existing state
`ToolRegistry` stores tools in a `BTreeMap` and already separates `Direct`, `Deferred`, and `Hidden`. `deferred_specs()` clones all Deferred ToolSpec values but does not expose an explicit bounded discovery contract.

## Proposed contract
Add a small immutable discovery value and a registry method dedicated to Deferred discovery.

- The registry remains the sole source of tool metadata.
- Selection is exactly `ToolExposure::Deferred`.
- Ordering reuses the registry BTreeMap order.
- Discovery applies fixed repository limits before returning data. It never serializes executor objects or authority.
- The result contains cloned validated `ToolSpec` values plus bounded summary state (returned count / omitted marker). No host-global path or secret field exists.
- Discovery is read-only and never calls `invoke` or `ToolExecutor::execute`.

## Compatibility
Existing Direct invocation/admission behavior is unchanged. Hidden tools remain registered but undiscoverable. No wire protocol integration is added in this increment.

## Risk control
GitNexus reports `deferred_specs` as UNKNOWN/exact with zero resolved callers, which is not proof of safety; repository text search also finds no production call sites. Implementation therefore stays in the local-agent registry/model boundary and adds focused regression tests.
