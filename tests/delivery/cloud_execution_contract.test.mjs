import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const manifest = JSON.parse(readFileSync(new URL('../../tools/delivery/manifest.json', import.meta.url), 'utf8'));
const tasks = new Map(manifest.tasks.map(task => [task.id, task]));

test('full-cloud release requires the separately tracked production integration gate', () => {
  const bridge = tasks.get('cloud-execution-bridge');
  assert.equal(bridge.issue, 81);
  assert.equal(bridge.release_required, true);
  assert.ok(tasks.get('reproducible-packages').depends_on.includes(bridge.id));
});

test('verified foundations alone cannot stand in for native end-to-end integration', () => {
  assert.deepEqual(new Set(tasks.get('cloud-execution-bridge').depends_on), new Set([
    'mcp-business-gateway', 'outbound-client', 'request-admission',
    'local-authority-provider', 'tool-runtime',
  ]));
  for (const id of tasks.get('cloud-execution-bridge').depends_on) assert.ok(tasks.has(id));
});

test('bridge work does not waive any remaining original full-roadmap package dependency', () => {
  const deps = new Set(tasks.get('reproducible-packages').depends_on);
  for (const id of ['ubuntu-sandbox','windows-sandbox','policy-hooks','worktrees',
    'snapshot-rollback','verification','tool-discovery','origin-migration']) {
    assert.ok(deps.has(id), `missing original gate: ${id}`);
    assert.equal(tasks.get(id).release_required, true);
  }
});

test('unfinished integration cannot be satisfied by a deferred real-host observation', () => {
  const bridge = tasks.get('cloud-execution-bridge');
  assert.notEqual(bridge.state, 'deferred');
  assert.ok(bridge.paths.includes('services/cloud-gateway') && bridge.paths.includes('src-tauri'));
  assert.equal(tasks.get('host-acceptance').release_required, true);
  assert.equal(tasks.get('vps-acceptance').release_required, true);
});
