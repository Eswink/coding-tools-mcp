import assert from 'node:assert/strict';
import test from 'node:test';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { post, probe } from './helpers.mjs';

const cli = fileURLToPath(new URL('../../prototypes/cloud-gateway/cli.mjs', import.meta.url));
const token = 'synthetic_cli_token_0123456789abcdef0123456789abcdef';

test('CLI refuses implicit mode and malformed startup without echoing the credential', () => {
  for (const args of [[], ['--lab', '--port'], ['--lab', '--host', '0.0.0.0']]) {
    const child = spawnSync(process.execPath, [cli, ...args], { encoding: 'utf8', timeout: 5000,
      env: { ...process.env, MCP_LAB_TOKEN: token } });
    assert.equal(child.status, 2);
    assert.ok(!(child.stdout + child.stderr).includes(token));
  }
});

test('separate CLI process serves offline results but never exposes its token', async t => {
  const child = spawn(process.execPath, [cli, '--lab', '--port', '0'], {
    env: { ...process.env, MCP_LAB_TOKEN: token }, stdio: ['ignore', 'pipe', 'pipe'],
  });
  t.after(async () => {
    if (child.exitCode !== null || child.signalCode !== null) return;
    const exited = new Promise(resolve => child.once('exit', resolve));
    child.kill();
    await exited;
  });
  let output = '', stderr = '';
  child.stderr.on('data', data => { stderr += data.toString(); });
  const ready = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Lab did not start')), 5000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', () => { clearTimeout(timer); reject(new Error('Lab exited before ready')); });
    child.stdout.on('data', data => {
      output += data.toString();
      if (output.includes('\n')) {
        clearTimeout(timer);
        try { resolve(JSON.parse(output.split('\n')[0])); } catch (error) { reject(error); }
      }
    });
  });
  assert.equal(ready.mode, 'non-production-protocol-lab');
  const r = await post({ endpoint: ready.endpoint, token }, probe());
  assert.equal(r.status, 200);
  assert.equal(r.body.result.structuredContent.error.code, 'WORKSPACE_OFFLINE');
  assert.ok(!(output + stderr).includes(token));
  assert.equal(stderr, '');
});
