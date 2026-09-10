// Build the real TypeScript sources in a fresh directory; never rely on /tmp fixtures.
import { createRequire } from 'node:module';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'package.json'));
const temporary = mkdtempSync(path.join(tmpdir(), '聊天授权前端回归v4-'));
function run(args, env = process.env) {
  const result = spawnSync(process.execPath, args, {
    cwd: root, env, stdio: 'inherit', windowsHide: true, timeout: 120_000,
  });
  if (result.error) throw result.error;
  if (result.signal || result.status !== 0) throw new Error(`回归命令失败：${args[0]}，退出码 ${result.status}，信号 ${result.signal}`);
}
try {
  run([require.resolve('typescript/bin/tsc'), '--target', 'ES2022', '--module', 'commonjs',
    '--skipLibCheck', '--rootDir', 'src/lib', '--outDir', temporary,
    'src/lib/任务日志v2.ts', 'src/lib/固定入口.ts', 'src/lib/types.ts']);
  const tests = readdirSync(path.join(root, 'tests'))
    .filter((name) => /\.test\.(mjs|cjs)$/.test(name)).sort()
    .map((name) => path.join(root, 'tests', name));
  if (!tests.length) throw new Error('没有发现前端回归测试');
  run(['--test', ...tests], {
    ...process.env, TASK_LOG_MODULE: path.join(temporary, '任务日志v2.js'), ENTRY_TEST_BUILD: temporary,
  });
} catch (error) {
  console.error(error);
  process.exitCode = 1;
} finally {
  rmSync(temporary, { recursive: true, force: true });
}
