import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, unlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkChineseSpec } from './规格校验v4.mjs';

const original = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../docs/specs/固定公网入口v1');
const names = ['需求v4.md', '设计v4.md', '任务v4.md'];
function fixture(run) {
  const root = mkdtempSync(path.join(tmpdir(), '规格中文路径v4-'));
  const dir = path.join(root, 'docs/specs/固定公网入口v1');
  mkdirSync(dir, { recursive: true });
  for (const name of names) writeFileSync(path.join(dir, name), readFileSync(path.join(original, name)));
  try { run(root, dir); } finally { rmSync(root, { recursive: true, force: true }); }
}
function edit(dir, name, transform) {
  const file = path.join(dir, name);
  writeFileSync(file, transform(readFileSync(file, 'utf8')));
}

test('原版检查器通过中文权威规格，摘要逐字节对应，任务保持未完成', () => fixture((projectRoot, dir) => {
  const before = readFileSync(path.join(dir, '任务v4.md'));
  const report = checkChineseSpec({ projectRoot });
  assert.equal(report.passed, true);
  assert.equal(report.result.warningCount, 0);
  assert.equal(report.result.frIds.length, 12);
  assert.equal(report.scope, 'spec-structure-only');
  for (const item of report.hashes) {
    assert.equal(item.sha256, createHash('sha256').update(readFileSync(path.join(projectRoot, item.source))).digest('hex'));
    assert.equal(item.identical, true);
  }
  assert.deepEqual(readFileSync(path.join(dir, '任务v4.md')), before);
  assert.match(before.toString(), /- \[ \] 1\.7/);
  // The original CLI bootstraps its own bin/runtime files. Only our mirror must be removed.
  assert.equal(readdirSync(path.join(projectRoot, '.mcp-probe-kit')).some((name) => name.startsWith('规格校验v4-')), false);
}));

test('缺少中文来源文件立即失败而不是创建空文件', () => fixture((projectRoot, dir) => {
  unlinkSync(path.join(dir, '设计v4.md'));
  assert.throws(() => checkChineseSpec({ projectRoot }), /ENOENT/);
}));

for (const [name, file, transform, expected] of [
  ['FR稳定ID', '需求v4.md', (s) => s.replace(/FR-\d+/g, '需求'), 'no_fr'],
  ['EARS验收', '需求v4.md', (s) => s.replace(/SHALL/g, '应'), 'no_acceptance'],
  ['需求覆盖', '任务v4.md', (s) => s.replace(/FR-12/g, '范围'), 'uncovered_fr'],
  ['设计章节', '设计v4.md', (s) => s.replace('## 技术方案', '## 方法'), 'missing_section'],
  ['未填占位', '需求v4.md', (s) => s + '\n[填写：验收]\n', 'placeholder'],
]) {
  test(`原版检查器拒绝${name}缺陷`, () => fixture((projectRoot, dir) => {
    edit(dir, file, transform);
    const report = checkChineseSpec({ projectRoot });
    assert.equal(report.passed, false);
    assert.ok(report.result.issues.some((issue) => issue.code === expected));
  }));
}

test('修改来源后不复用上一次PASS', () => fixture((projectRoot, dir) => {
  const first = checkChineseSpec({ projectRoot });
  edit(dir, '需求v4.md', (s) => s.replace(/SHALL/g, '必须'));
  const second = checkChineseSpec({ projectRoot });
  assert.equal(first.passed, true);
  assert.equal(second.passed, false);
  assert.notEqual(first.hashes[0].sha256, second.hashes[0].sha256);
}));

test('拒绝错误工具版本且不执行其入口', () => fixture((projectRoot) => {
  const fake = path.join(projectRoot, '错误工具');
  mkdirSync(path.join(fake, 'build'), { recursive: true });
  writeFileSync(path.join(fake, 'package.json'), JSON.stringify({ name: 'mcp-probe-kit', version: '0.0.0' }));
  writeFileSync(path.join(fake, 'build/index.js'), 'throw new Error("should not execute")');
  assert.throws(() => checkChineseSpec({ projectRoot, probeEntry: path.join(fake, 'build/index.js') }), /4\.0\.1/);
}));
