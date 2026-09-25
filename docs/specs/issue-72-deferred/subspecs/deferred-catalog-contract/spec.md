# Subspec: Deferred catalog contract

## Scope
Define the immutable, deterministic and bounded metadata view for Deferred tools only.

## Requirements
- FR-1
- FR-2

## Acceptance criteria
1. WHEN the registry contains Direct, Deferred and Hidden tools THEN discovery SHALL return only Deferred entries ordered by ToolName.
2. WHEN Deferred entries exceed the repository entry bound THEN discovery SHALL return at most the bound and SHALL indicate omission deterministically.
3. WHEN metadata would exceed the repository discovery byte bound THEN discovery SHALL stop before exceeding that bound and SHALL indicate omission.
4. WHEN a discovered item is inspected THEN it SHALL contain only cloned validated ToolSpec metadata and SHALL NOT contain an executor, admission token, filesystem path or host-global state.

## Files
- `services/local-agent/src/registry.rs`
- `services/local-agent/src/model.rs`
- focused tests under the existing local-agent test layout

## Not included
No wire protocol, cloud publishing or automatic execution.
