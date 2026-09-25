// Execute the actual inline CI guard; do not maintain a second allowlist.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

// Normalize only the text extraction boundary, never the checked source bytes.
const workflow = readFileSync(new URL('../../.github/workflows/cloud-gateway-lab.yml', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
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
import contextlib, io, json, sys, tempfile
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
# Restore cwd before TemporaryDirectory cleanup (required by Windows file locking).
with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
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
  const result = spawnSync('python', ['-I', '-X', 'utf8', '-c', harness], {
    input: JSON.stringify({ source, paths, files }), encoding: 'utf8', timeout: 10_000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

const migration = '.github/workflows/origin-migration.yml';
const asyncCommand = 'src-tauri/src/tools/异步命令v1.rs';
const mcpListener = 'src-tauri/src/mcp/listener.rs';
const exclusiveRefreshTests = 'src-tauri/src/auth/exclusive_refresh_http_tests.rs';
const patchSource = 'src-tauri/src/tools/patch.rs';
const patchTransaction = 'src-tauri/src/tools/patch_transaction.rs';
const patchTransactionTests = 'src-tauri/src/tools/patch_transaction_tests.rs';
const issue62RuntimePaths = [
  'src-tauri/src/platform/linux/mod.rs',
  'src-tauri/src/platform/linux/net.rs',
  'src-tauri/src/platform/mod.rs',
  'src-tauri/src/runtime/port.rs',
  'src-tauri/src/tools/任务恢复传输v2.rs',
];
test('reviewed origin-migration workflow passes actual guard with source digest', () => {
  const result = run([migration]);
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.candidate, 'a'.repeat(40));
  assert.equal(result.report.sha256[migration], createHash('sha256').update('# fixture\n').digest('hex'));
  assert.equal(result.git_calls, 2);
});

test('reviewed RC60 async-command source passes actual guard with source digest', () => {
  const contents = '// reviewed RC60 UTF-8 fixture\n';
  const result = run([asyncCommand], { [asyncCommand]: contents });
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.sha256[asyncCommand], createHash('sha256').update(contents).digest('hex'));
  assert.equal(result.git_calls, 2);
});

test('reviewed issue62 MCP listener source passes actual guard with source digest', () => {
  const contents = '// reviewed issue62 listener fixture\n';
  const result = run([mcpListener], { [mcpListener]: contents });
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.sha256[mcpListener], createHash('sha256').update(contents).digest('hex'));
  assert.equal(result.git_calls, 2);
});

test('reviewed issue60 exclusive-refresh regression source passes actual guard with source digest', () => {
  const contents = '// reviewed issue60 auth regression fixture\n';
  const result = run([exclusiveRefreshTests], { [exclusiveRefreshTests]: contents });
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.sha256[exclusiveRefreshTests], createHash('sha256').update(contents).digest('hex'));
  assert.equal(result.git_calls, 2);
});

for (const path of issue62RuntimePaths) {
  test(`reviewed issue62 ownerless-LISTEN path passes actual guard with source digest: ${path}`, () => {
    const contents = `// reviewed issue62 ownerless LISTEN fixture for ${path}\n`;
    const result = run([path], { [path]: contents });
    assert.equal(result.accepted, true, result.error);
    assert.equal(result.report.sha256[path], createHash('sha256').update(contents).digest('hex'));
    assert.equal(result.git_calls, 2);
  });
}

for (const [path, contents] of [
  [patchSource, '// reviewed issue68 patch source fixture\n'],
  [patchTransaction, '// reviewed issue68 patch transaction fixture\n'],
  [patchTransactionTests, '// reviewed issue68 patch transaction tests fixture\n'],
]) {
  test(`reviewed issue68 transactional patch path passes actual guard with source digest: ${path}`, () => {
    const result = run([path], { [path]: contents });
    assert.equal(result.accepted, true, result.error);
    assert.equal(result.report.sha256[path], createHash('sha256').update(contents).digest('hex'));
    assert.equal(result.git_calls, 2);
  });
}

for (const path of [
  '.github/workflows/unrelated.yml',
  '.github/workflows/origin-migration.yml.bak',
  '.github/workflows/origin-migration-extra.yml',
  '.github/workflows/ci.yml',
  'src/App.svelte',
  'src-tauri/src/main.rs',
  'src-tauri/src/tools/异步命令v1.rs.bak',
  'src-tauri/src/tools/patch.rs.bak',
  'src-tauri/src/tools/patch_transaction.rs.bak',
  'src-tauri/src/tools/patch_transaction_tests.rs.bak',
  'src-tauri/src/platform/linux/net.rs.bak',
  'src-tauri/src/platform/linux/unreviewed.rs',
  'src-tauri/src/platform/unreviewed.rs',
  'src-tauri/src/runtime/port.rs.bak',
  'src-tauri/src/runtime/unreviewed.rs',
  'src-tauri/src/tools/任务恢复传输v2.rs.bak',
  'src-tauri/src/tools/unreviewed.rs',
  'src-tauri/src/mcp/listener.rs.bak',
  'src-tauri/src/mcp/unreviewed.rs',
  'src-tauri/src/auth/exclusive_refresh_http_tests.rs.bak',
  'src-tauri/src/auth/unreviewed.rs',
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

test('UTF-8 source and a reviewed Unicode path survive the isolated Python boundary', () => {
  const path = 'src-tauri/src/auth/聊天授权v1.rs';
  const result = run([path], { [path]: '// UTF-8 中文 fixture\n' });
  assert.equal(result.accepted, true, result.error);
  assert.equal(result.report.sha256[path], createHash('sha256').update('// UTF-8 中文 fixture\n').digest('hex'));
});

for (const path of [
  'src-tauri/src/mcp/mod.rs',
  'src-tauri/src/mcp/listener_test_support.rs',
  'src-tauri/src/auth/聊天HTTP回归v1.rs',
]) {
  test(`reviewed issue74 bound-listener path passes actual guard with digest: ${path}`, () => {
    const contents = `// reviewed issue74 retained socket fixture for ${path}\n`;
    const result = run([path], { [path]: contents });
    assert.equal(result.accepted, true, result.error);
    assert.equal(result.report.sha256[path], createHash('sha256').update(contents).digest('hex'));
    assert.equal(result.git_calls, 2);
  });
  test(`issue74 allowlist does not permit a suffixed path: ${path}.bak`, () => {
    const result = run([`${path}.bak`]);
    assert.equal(result.accepted, false);
    assert.match(result.error, /Unexpected non-lab changes/);
    assert.equal(result.report, null);
    assert.equal(result.git_calls, 1);
  });
}
