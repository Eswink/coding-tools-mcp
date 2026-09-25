# issue-72-deferred

## Principle

Evaluate and implement only a bounded local Deferred-tool discovery view on the existing `services/local-agent` registry. This increment never invokes a tool, never creates authority, never changes admission/capabilities, and never publishes Hidden tools.

## Subspec index

| ID | Title | FR | Depends on |
|---|---|---|---|
| deferred-catalog-contract | Deferred catalog contract | FR-1, FR-2 | none |
| discovery-safety-evaluation | Discovery safety and evaluation | FR-3 | deferred-catalog-contract |

## Milestone

1. Freeze deterministic bounded catalog semantics.
2. Prove visibility and no-execution safety on both supported CI runners.
