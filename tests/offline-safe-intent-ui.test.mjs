import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

const page = read("src/routes/workspace/[id]/+page.svelte");
const servicePanel = read("src/lib/components/ServicePanel.svelte");
const serviceView = read("src/lib/components/workspace/WorkspaceServiceView.svelte");
const executionPanel = read("src/lib/components/workspace/ExecutionAvailabilityPanel.svelte");

test("running MCP primary intent is pause/resume, not hard stop", () => {
  assert.match(page, /async function startMcpConnector\(\)/);
  assert.match(page, /async function stopMcpConnector\(\)/);
  assert.doesNotMatch(page, /async function toggleMcp\(\)/);
  assert.match(page, /pauseMcpExecution\(id, generation\)/);
  assert.match(page, /resumeMcpExecution\(id, generation\)/);
  assert.match(
    page,
    /onToggle=\{activeService === "mcp" \? startMcpConnector : toggleActions\}/,
  );
});

test("MCP lifecycle panel owns normal and destructive connector actions", () => {
  assert.match(executionPanel, /onStart:/);
  assert.match(executionPanel, /onStop:/);
  assert.match(executionPanel, /启动 Connector/);
  assert.match(executionPanel, /暂停远程执行/);
  assert.match(executionPanel, /恢复远程执行/);
  assert.match(executionPanel, /停止 Connector/);
  assert.match(executionPanel, /MCP\/OAuth 监听器和公网隧道/);
});

test("generic service panel does not expose a second MCP stop button", () => {
  assert.match(servicePanel, /showToggle\?: boolean/);
  assert.match(serviceView, /showToggle=\{!mcp\}/);
});

test("hard stop remains explicit and requires confirmation", () => {
  const stopStart = page.indexOf("async function stopMcpConnector()");
  assert.ok(stopStart >= 0, "explicit stopMcpConnector function missing");
  const stopBlock = page.slice(stopStart, stopStart + 2200);
  assert.match(stopBlock, /confirm\(/);
  assert.match(stopBlock, /停止 Connector 会关闭 MCP\/OAuth 监听器和公网隧道/);
  assert.match(stopBlock, /暂停远程执行/);
  assert.match(stopBlock, /stopRuntime\(id\)/);
});

test("Actions keeps its existing start stop lifecycle", () => {
  assert.match(page, /async function toggleActions\(\)/);
  assert.match(page, /stopActionsRuntime\(id\)/);
});
