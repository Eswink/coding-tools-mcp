import test from 'node:test';
import assert from 'node:assert/strict';
import { parse, stringify } from 'devalue';
import { readFileSync } from 'node:fs';

test('both lockfiles select the same verified devalue package and integrity', () => {
  const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
  const pkg = lock.packages['node_modules/devalue'];
  const pnpm = readFileSync(new URL('../pnpm-lock.yaml', import.meta.url), 'utf8');
  assert.equal(pkg.version, '5.9.4');
  assert.ok(pnpm.includes(`devalue@${pkg.version}:\n    resolution: {integrity: ${pkg.integrity}}`));
  assert.equal((pnpm.match(/devalue: 5\.9\.4/g) || []).length, 2);
  assert.doesNotMatch(pnpm, /devalue[@:]\s*5\.8\.1/);
});

// Bounded regression for GHSA-9rgm-9g3h-6x36, upstream fix8b2a456.
// Deliberately tiny input: never run a resource-exhaustion payload in CI.
test('serialized Set rejects an out-of-bounds reference', () => {
  assert.throws(() => parse('[["Set",7]]'), /Invalid input/);
});

test('supported serialization still round-trips shared values', () => {
  const shared = { value: 'safe fixture' };
  const value = { first: shared, second: shared, set: new Set([shared]), date: new Date('2026-01-01T00:00:00Z') };
  const decoded = parse(stringify(value));
  assert.deepEqual(decoded, value);
  assert.equal(decoded.first, decoded.second);
  assert.equal([...decoded.set][0], decoded.first);
});
