import { readFileSync } from 'node:fs';
import test from 'node:test';
import assert from 'node:assert/strict';

for (const name of ['dot-rc-integration.yml', 'cloud-execution-bridge.yml']) {
  test(`${name}: ephemeral PostgreSQL endpoint is evaluated in a step`, () => {
    const source = readFileSync(new URL(`../../.github/workflows/${name}`, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /^    env:\r?\n\s+TEST_DATABASE_URL:.*job\.services/m);
    assert.match(source, /^        env:\r?\n          TEST_DATABASE_URL:.*job\.services\.postgres\.ports\['5432'\]/m);
    assert.doesNotMatch(source, /job\.services\.postgres\.ports\[5432\]/);
    assert.match(source, /permissions:\r?\n  contents: read/);
  });
}

test('complete candidate keeps both Ubuntu generations and native Windows', () => {
  const source = readFileSync(new URL('../../.github/workflows/dot-rc-integration.yml', import.meta.url), 'utf8');
  assert.match(source, /os: \[ubuntu-22\.04, ubuntu-24\.04, windows-2025\]/);
  assert.match(source, /os: \[ubuntu-22\.04, ubuntu-24\.04\]/);
  assert.match(source, /cloud_application::wss_tests/);
  assert.match(source, /sandbox-dispatch\/run_probe\.py --evidence/);
  assert.doesNotMatch(source, /--expect-gap|continue-on-error: true/);
});
