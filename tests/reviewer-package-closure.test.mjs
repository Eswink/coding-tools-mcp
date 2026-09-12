import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { reviewerPackages } from '../scripts/reviewer-package-closure.mjs';

test('reviewer archive includes transitive and nested dependencies without unrelated packages', () => {
  const selected = reviewerPackages({
    'node_modules/svelte': { dependencies: { parser: '*', nested: '*' } },
    'node_modules/parser': { dependencies: { codec: '*' } },
    'node_modules/codec': {},
    'node_modules/svelte/node_modules/nested': { dependencies: { parser: '*' } },
    'node_modules/unrelated': {},
  }, ['svelte']);
  assert.deepEqual(selected, ['node_modules/codec', 'node_modules/parser', 'node_modules/svelte', 'node_modules/svelte/node_modules/nested']);
});
test('cycles terminate and missing required dependencies fail instead of exporting a broken archive', () => {
  const packages = {
    'node_modules/a': { dependencies: { b: '*' } },
    'node_modules/b': { dependencies: { a: '*' } },
  };
  assert.equal(reviewerPackages(packages, ['a']).length, 2);
  delete packages['node_modules/b'];
  assert.throws(() => reviewerPackages(packages, ['a']), /Missing locked reviewer dependency/);
});
test('absent optional packages are skipped but broken optional closures are rejected', () => {
  const packages = { 'node_modules/a': { optionalDependencies: { b: '*' } } };
  assert.deepEqual(reviewerPackages(packages, ['a']), ['node_modules/a']);
  packages['node_modules/b'] = { dependencies: { missing: '*' } };
  assert.throws(() => reviewerPackages(packages, ['a']), /missing/);
});
test('actual lock closure includes ESM compiler dependencies and the cookie regression dependency', () => {
  const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
  const selected = reviewerPackages(lock.packages);
  for (const name of ['typescript', 'svelte', 'cookie', 'zimmerframe', 'esm-env', '@jridgewell/sourcemap-codec']) {
    assert.ok(selected.includes(`node_modules/${name}`), name);
  }
  assert.ok(!selected.includes('node_modules/@tauri-apps/cli'));
});
test('CI exports the verified lock closure rather than only two top-level compilers', () => {
  const workflow = readFileSync(new URL('../.github/workflows/oauth-discovery-fix.yml', import.meta.url), 'utf8');
  assert.match(workflow, /node scripts\/reviewer-package-closure\.mjs reviewer-tools\/packages\.txt/);
  assert.match(workflow, /tar czf reviewer-tools\/compilers\.tar\.gz -T reviewer-tools\/packages\.txt/);
});
