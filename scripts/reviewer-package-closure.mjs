/** Export only the installed dependency closure required by the offline frontend reviewer. */
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export function reviewerPackages(packages, roots = ['typescript', 'svelte', 'cookie']) {
  const selected = new Set();
  function resolve(name, owner = '') {
    for (let directory = owner; ; directory = path.posix.dirname(directory)) {
      const candidate = path.posix.join(directory, 'node_modules', name);
      if (packages[candidate]) return candidate;
      if (!directory || directory === '.') break;
    }
    throw new Error(`Missing locked reviewer dependency: ${owner || '<root>'} -> ${name}`);
  }
  function visit(location) {
    if (selected.has(location)) return;
    if (!location.startsWith('node_modules/') || location.split('/').includes('..')) {
      throw new Error(`Invalid reviewer package path: ${location}`);
    }
    selected.add(location);
    const item = packages[location];
    for (const name of Object.keys(item.dependencies ?? {})) visit(resolve(name, location));
    for (const name of Object.keys(item.optionalDependencies ?? {})) {
      let optional;
      try { optional = resolve(name, location); } catch { continue; }
      visit(optional);
    }
  }
  for (const name of roots) visit(resolve(name));
  return [...selected].sort();
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const output = process.argv[2];
  if (!output) throw new Error('Usage: node scripts/reviewer-package-closure.mjs OUTPUT');
  const { packages } = JSON.parse(readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
  const selected = reviewerPackages(packages);
  for (const location of selected) {
    const installed = JSON.parse(readFileSync(path.join(root, location, 'package.json'), 'utf8'));
    if (installed.version !== packages[location].version) throw new Error(`Reviewer package version mismatch: ${location}`);
  }
  writeFileSync(output, selected.join('\n') + '\n');
}
