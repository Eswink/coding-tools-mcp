# Policy-governed Hooks

Retained ISSUE-031 and cloud-execution-bridge FR8 engineering. Native approval and immutable registry feed the actual tool dispatcher; Hooks are never a permission source.

## 原则
Hooks never grant authority.
## 子规格索引
- hook-registry: native approval and immutable manifest
- hook-execution: policy sandbox lifecycle and actual dispatch
## 依赖关系
hook-execution depends on hook-registry and existing platform sandboxes.
## 里程碑
Registry → execution → native integration → real regression and platform gates.
