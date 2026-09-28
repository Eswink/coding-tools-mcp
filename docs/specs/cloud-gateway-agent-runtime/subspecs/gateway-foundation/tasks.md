# 子任务：Cloud protocol and offline foundation

- [x] 1.1 Write architecture, threat model and versioned wire contracts
  - 证据块: src-tauri/src/mcp/server.rs:13-78; src-tauri/src/tools/聊天运行域v1.rs:82-134
  - 涉及文件: design.md, threat-model.md, protocol.md
  - _需求: FR-1, FR-2, FR-3_

- [x] 1.2 Implement and test isolated loopback-only protocol lab
  - 证据块: round1-validation.md; CI run 35564597505; candidate 82c20d3
  - 涉及文件: prototypes/cloud-gateway/*.mjs, tests/cloud-gateway/*.test.mjs
  - _需求: FR-1, FR-2, FR-3_

- [ ] 1.3 Replace fixture with production Gateway only after channel and OAuth gates
  - 证据块: subspecs/agent-channel/spec.md
  - 涉及文件: future cloud Gateway crate and integration tests
  - _需求: FR-1, FR-2, FR-3_
