// Execute the actual inline CI guard; do not maintain a second allowlist.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const workflow = readFileSync(new URL('../../.github/workflows/cloud-gateway-lab.yml', import.meta.url), 'utf8');
const marker = "          python - <<'PY'\n";
const start = workflow.indexOf(marker);
assert.notEqual(start, -1, 'scope guard Python entry must exist');
const end = workflow.indexOf('\n          PY', start + marker.length);
assert.notEqual(end, -1, 'scope guard Python terminator must exist');
const source = workflow.slice(start + marker.length, end).split('\n').map(line => {
  assert.ok(line.startsWith('          '), 'unexpected guard indentation');
  return line.slice(10);
}).join('\n');

const harness = String.raw`
import contextlib, io, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
payload = json.load(sys.stdin)
sha = 'a' * 40
calls = []
def git(args, **kwargs):
    calls.append(args)
    if args == ['git', '-c', 'core.quotePath=false', 'diff', '--name-only',
                '758c60a6e74e624e144f9c19c5f19d04d17f7a13', 'HEAD']:
        return '\n'.join(payload['paths']) + '\n' if payload['paths'] else ''
    if args == ['git', 'rev-parse', 'HEAD']:
        return sha + '\n'
    raise AssertionError('unexpected subprocess call')
with tempfile.TemporaryDirectory() as directory:
    os.chdir(directory)
    Path('evidence').mkdir()
    for name, contents in payload['files'].items():
        path = Path(name)
        assert not path.is_absolute() and '..' not in path.parts
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding='utf-8', newline='\n')
    result = {'accepted': False, 'report': None}
    with patch('subprocess.check_output', side_effect=git):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                exec(compile(payload['source'], '<actual-ci-scope-guard>', 'exec'), {})
            result['accepted'] = True
        except SystemExit as error:
            result['error'] = str(error)
    report = Path('evidence/candidate.json')
    if report.exists():
        result['report'] = json.loads(report.read_text(encoding='utf-8'))
    result['git_calls'] = len(calls)
    print(json.dumps(result))
`;

function run(paths, files = Object.fromEntries(paths.map(path => [path, '# fixture\n']))) {
  const result = spawnSync('python', ['-I', '-c', harness], {
    input: JSON.stringify({ source, paths, files }), encoding: 'utf8', timeout: 10_000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

const migration = '.github/workflows/origin-migration.yml';
test('reviewed origin-migration workflow passes actual guard with source digest', () => {
  const result = run([migration]);
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.candidate, 'a'.repeat(40));
  assert.equal(result.report.sha256[migration], createHash('sha256').update('# fixture\n').digest('hex'));
  assert.equal(result.git_calls, 2);
});

for (const path of [
  '.github/workflows/unrelated.yml',
  '.github/workflows/origin-migration.yml.bak',
  '.github/workflows/origin-migration-extra.yml',
  '.github/workflows/ci.yml',
  'src/App.svelte',
  'src-tauri/src/main.rs',
  'AGENTS.md',
  'CLAUDE.md',
  'package.json',
]) {
  test(`unreviewed path remains denied: ${path}`, () => {
    const result = run([path]);
    assert.equal(result.accepted, false);
    assert.match(result.error, /Unexpected non-lab changes/);
    assert.equal(result.report, null);
    assert.equal(result.git_calls, 1);
  });
}

test('one reviewed path cannot hide another forbidden path', () => {
  const result = run([migration, 'src-tauri/src/main.rs']);
  assert.equal(result.accepted, false);
  assert.equal(result.report, null);
});
test('allowed-prefix source still passes', () => {
  assert.equal(run(['tests/cloud-gateway/fixture.test.mjs']).accepted, true);
});
test('deletion of even an allowed file remains forbidden', () => {
  const result = run([migration], {});
  assert.equal(result.accepted, false);
  assert.match(result.error, /must not delete files/);
  assert.equal(result.report, null);
});
test('500-line module still violates the existing source limit', () => {
  const name = 'tests/cloud-gateway/fixture.test.mjs';
  const result = run([name], { [name]: '// fixture\n'.repeat(500) });
  assert.equal(result.accepted, false);
  assert.match(result.error, /Source file exceeds/);
});
test('499-line module still passes the existing source limit', () => {
  const name = 'tests/cloud-gateway/fixture.test.mjs';
  assert.equal(run([name], { [name]: '// fixture\n'.repeat(499) }).accepted, true);
});
test('empty candidate has an empty digest set', () => {
  const result = run([]);
  assert.equal(result.accepted, true);
  assert.deepEqual(result.report.sha256, {});
});
