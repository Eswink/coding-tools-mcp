import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const root = new URL("../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

const rustPolicy = read("src-tauri/src/auth/session_policy.rs");
const rustAuthorizer = read("src-tauri/src/auth/聊天授权v1.rs");
const localControl = read("src-tauri/src/commands/聊天授权v1.rs");
const tsPolicy = read("src/lib/remote-session-policy.ts");
const settings = read("src/lib/components/RemoteSessionSettings.svelte");
const panel = read("src/lib/components/聊天授权面板v1.svelte");

test("persistent session policy defines explicit new-chat admission modes", () => {
  assert.match(rustPolicy, /new_chat_admission/);
  assert.match(rustPolicy, /Review/);
  assert.match(rustPolicy, /LocalWindow/);
  assert.match(rustPolicy, /DenyNew/);
  assert.match(tsPolicy, /new_chat_admission/);
  assert.match(tsPolicy, /"review"/);
  assert.match(tsPolicy, /"local_window"/);
  assert.match(tsPolicy, /"deny_new"/);
});

test("local authorization service exposes and controls a single-use admission window", () => {
  assert.match(rustAuthorizer, /arm_new_chat/);
  assert.match(rustAuthorizer, /disarm_new_chat/);
  assert.match(rustAuthorizer, /admission/);
  assert.match(rustAuthorizer, /single_use/);
  assert.match(localControl, /"arm_new_chat"/);
  assert.match(localControl, /"disarm_new_chat"/);
});

test("remote session settings exposes the persistent admission choice", () => {
  assert.match(settings, /新聊天申请/);
  assert.match(settings, /自动进入本机审批/);
  assert.match(settings, /仅在本机临时开放时接受/);
  assert.match(settings, /禁止新聊天申请/);
});

test("local authorization panel can arm one new-chat request without changing OAuth", () => {
  assert.match(panel, /允许下一条新聊天申请/);
  assert.match(panel, /关闭新聊天申请/);
  assert.match(panel, /arm_new_chat/);
  assert.match(panel, /disarm_new_chat/);
  assert.match(panel, /single_use/);
});
