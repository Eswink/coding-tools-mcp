import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
const read = (path) => readFileSync(new URL(path, new URL("../", import.meta.url)), "utf8");

const page = read("src/routes/workspace/[id]/+page.svelte");
const panel = read("src/lib/components/workspace/ExecutionAvailabilityPanel.svelte");
const api = read("src/lib/api/workspaces.ts");
const types = read("src/lib/types.ts");

test("workspace UI keeps pause resume separate from hard stop", () => {
  assert.match(page, /pauseMcpExecution\(id, generation\)/);
  assert.match(page, /resumeMcpExecution\(id, generation\)/);
  assert.match(page, /stopRuntime\(id\)/);
  assert.match(page, /mcpRuntimeGeneration = runtime\.runtimeGeneration \?\? ""/);
  assert.match(page, /mcpExecutionState = runtime\.executionState/);
});

test("pause and resume IPC require the observed runtime generation", () => {
  assert.match(api, /pause_mcp_execution", \{ id, expectedGeneration \}/);
  assert.match(api, /resume_mcp_execution", \{ id, expectedGeneration \}/);
  assert.match(types, /runtimeGeneration\?: string/);
  assert.match(types, /executionState\?: "online" \| "offline"/);
});

test("availability panel explicitly distinguishes pause from connector stop", () => {
  assert.match(panel, /暂停只阻止新的远程业务调用/);
  assert.match(panel, /MCP Connector、OAuth 控制面和已运行的隧道保持在线/);
  assert.match(panel, /“停止”仍是硬停止，会关闭 Connector 与隧道/);
  assert.match(panel, /WORKSPACE_OFFLINE/);
  assert.match(panel, /暂停远程执行/);
  assert.match(panel, /恢复远程执行/);
});
