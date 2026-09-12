import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../.github/workflows/oauth-version-prepare.yml', import.meta.url), 'utf8');
test('version preparation is confined to the OAuth repair branch and workflow path', () => {
  assert.match(source, /branches: \['fix\/oauth-discovery-runtime'\]/);
  assert.match(source, /paths: \['\.github\/workflows\/oauth-version-prepare\.yml'\]/);
  assert.match(source, /github\.repository == 'Eswink\/coding-tools-mcp' && github\.ref == 'refs\/heads\/fix\/oauth-discovery-runtime'/);
});
test('version preparation checks immutable checkout and rejects a moved branch before push', () => {
  assert.match(source, /ref: \$\{\{ github\.sha \}\}/);
  assert.match(source, /git merge-base --is-ancestor aadfbb05842214880dee25d7234538178c731fc7 HEAD/);
  assert.match(source, /git ls-remote origin refs\/heads\/fix\/oauth-discovery-runtime/);
  assert.ok(source.indexOf('git ls-remote') < source.indexOf('git push'));
});
test('the tested version helper is fixed to one patch increment', () => {
  assert.match(source, /python scripts\/版本递增回归v7\.py/);
  assert.match(source, /--from-version 0\.3\.1 --version 0\.3\.2 --apply/);
  assert.match(source, /assert changed <= allowed/);
  assert.match(source, /git add -- package\.json package-lock\.json src-tauri\/Cargo\.toml src-tauri\/Cargo\.lock src-tauri\/tauri\.conf\.json/);
});
test('preparation cannot publish, tag, force push, or overwrite another branch', () => {
  assert.doesNotMatch(source, /git push[^\n]*(?:--force|--tags)|gh release|action-gh-release|git tag/);
  assert.match(source, /git push origin HEAD:refs\/heads\/fix\/oauth-discovery-runtime/);
  assert.match(source, /cancel-in-progress: false/);
});
test('preparation emits a verified commit, tree, source archive and digest', () => {
  for (const file of ['receipt.json', 'source.txt', 'tree.txt', 'source.zip', 'source.sha256']) assert.ok(source.includes(file));
  assert.match(source, /python scripts\/发布版本校验v4\.py --expect-sha/);
  assert.match(source, /sha256sum version-evidence\/source\.zip/);
});
