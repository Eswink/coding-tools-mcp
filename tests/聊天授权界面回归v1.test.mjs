import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const panel = readFileSync(new URL("../src/lib/components/聊天授权面板v1.svelte", import.meta.url),"utf8");
const prompt = readFileSync(new URL("../src/lib/components/ChatGptSessionPrompt.svelte", import.meta.url),"utf8");
const server = readFileSync(new URL("../src-tauri/src/mcp/server.rs", import.meta.url),"utf8");
test("审批只有本机IPC，组件不收集或展示原始身份凭据",()=>{
  assert.match(panel,/chat_authorization_control/);assert.doesNotMatch(panel,/type="password"|access_token|openai\/session/);
  for(const label of ["撤销全部","独占聊天模式","核对指纹并批准","批准权限"]) assert.ok(panel.includes(label));
});
test("切换工作区和卸载清理轮询，旧响应不能覆盖新状态",()=>{
  assert.match(panel,/clearInterval\(timer\)/);assert.match(panel,/generation === current/);
  assert.match(panel,/version === mutation/);assert.match(panel,/untrack\(\(\) => void refresh\(\)\)/);
});
test("提示词与协议均先审批后归档，不再无条件开始就调用业务工具",()=>{
  assert.ok(prompt.indexOf("request_chat_authorization") < prompt.indexOf("history_session_bootstrap"));
  assert.match(server,/Never use business tools before OAuth and local desktop approval/);
  assert.doesNotMatch(server,/At the start of every new ChatGPT conversation, before answering/);
});
