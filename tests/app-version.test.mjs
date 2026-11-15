// A1 C19 NARROW-B: app-version named JSON import (C13 hangover).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const root = join(fileURLToPath(new URL('.', import.meta.url)), '..');
const sourcePath = join(root, 'src/lib/app-version.ts');
const packagePath = join(root, 'package.json');
const source = readFileSync(sourcePath, 'utf8');
const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));

test('source uses named version import from package.json', () => {
  assert.match(
    source,
    /import\s*\{\s*version(?:\s+as\s+APP_VERSION)?\s*\}\s*from\s*["']\.\.\/\.\.\/package\.json["']/,
  );
  assert.doesNotMatch(source, /import\s+packageJson\s+from\s*["']\.\.\/\.\.\/package\.json["']/);
  assert.doesNotMatch(source, /import\s*\*\s*as\s+\w+\s+from\s*["']\.\.\/\.\.\/package\.json["']/);
  assert.doesNotMatch(source, /import\s+\w+\s+from\s*["']\.\.\/\.\.\/package\.json["']/);
});

test('APP_VERSION equals package.json version at runtime', async () => {
  // Node needs import attributes for JSON; rewrite only the import line so the
  // export binding still comes from the real module body.
  const rewritten = source.replace(
    /import\s*\{\s*version\s*\}\s*from\s*["']\.\.\/\.\.\/package\.json["']\s*;?/,
    `import __pkg from ${JSON.stringify(pathToFileURL(packagePath).href)} with { type: 'json' };\nconst version = __pkg.version;`,
  );
  assert.notEqual(rewritten, source, 'named import line must be present to rewrite');
  const code = ts.transpileModule(rewritten, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
  }).outputText;
  const { APP_VERSION } = await import(
    `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
  );
  assert.equal(typeof APP_VERSION, 'string');
  assert.equal(APP_VERSION, packageJson.version);
  assert.equal(APP_VERSION, '0.8.0');
});
