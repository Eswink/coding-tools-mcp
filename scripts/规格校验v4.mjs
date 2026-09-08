import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const VERSION = '4.0.1';
const FILES = [['需求v4.md', 'requirements.md'], ['设计v4.md', 'design.md'], ['任务v4.md', 'tasks.md']];
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');

function inside(root, candidate) {
  const relative = path.relative(root, realpathSync(candidate));
  if (relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error('规格路径必须位于项目内');
  }
  return candidate;
}

/** Run the unmodified, pinned checker on byte-identical protocol filenames. */
export function checkChineseSpec({ projectRoot = process.cwd(), probeEntry = process.env.MCP_PROBE_LOCAL_ENTRY } = {}) {
  const root = realpathSync(projectRoot);
  if (!probeEntry) throw new Error('请设置 MCP_PROBE_LOCAL_ENTRY，指向已安装的 mcp-probe-kit 4.0.1 build/index.js');
  const entry = realpathSync(probeEntry);
  const pkg = JSON.parse(readFileSync(path.resolve(path.dirname(entry), '../package.json'), 'utf8'));
  if (pkg.name !== 'mcp-probe-kit' || pkg.version !== VERSION) throw new Error('规格工具版本必须为 mcp-probe-kit 4.0.1');
  const sourceDir = inside(root, path.join(root, 'docs/specs/固定公网入口v1'));
  const sources = FILES.map(([name, protocol]) => {
    const file = inside(root, path.join(sourceDir, name));
    return { name, protocol, file, bytes: readFileSync(file) };
  });
  const generatedRoot = path.join(root, '.mcp-probe-kit');
  if (existsSync(generatedRoot)) inside(root, generatedRoot);
  mkdirSync(generatedRoot, { recursive: true });
  const temporary = mkdtempSync(path.join(generatedRoot, '规格校验v4-'));
  try {
    const target = path.join(temporary, 'specs/fixed-public-entry-v1');
    mkdirSync(target, { recursive: true });
    for (const source of sources) writeFileSync(path.join(target, source.protocol), source.bytes);
    const args = { project_root: root, docs_dir: path.relative(root, temporary).split(path.sep).join('/'), feature_name: 'fixed-public-entry-v1' };
    const result = spawnSync(process.execPath, [entry, 'exec', 'check_spec', '--stdin'], {
      cwd: root, input: JSON.stringify(args), encoding: 'utf8', timeout: 45_000, maxBuffer: 4 * 1024 * 1024, windowsHide: true,
    });
    if (result.error || result.signal || result.status !== 0) throw new Error('原版 check_spec 执行失败或超时');
    let response;
    try { response = JSON.parse(result.stdout); } catch { throw new Error('check_spec 未返回有效JSON'); }
    const report = response.structuredContent;
    if (!response.ok || response.isError || typeof report?.passed !== 'boolean' || !Array.isArray(report.issues)) {
      throw new Error('check_spec 未返回有效结构化校验结果');
    }
    const hashes = sources.map((source) => {
      const mirror = readFileSync(path.join(target, source.protocol));
      const current = readFileSync(inside(root, source.file));
      if (!source.bytes.equals(mirror) || !source.bytes.equals(current)) throw new Error('校验期间规格内容变化，拒绝复用结果');
      return { source: path.relative(root, source.file).split(path.sep).join('/'), protocol: source.protocol, sha256: digest(source.bytes), identical: true };
    });
    return { scope: 'spec-structure-only', toolVersion: VERSION, passed: report.passed, hashes, result: report };
  } finally {
    // Only remove the random directory created by this invocation, never source documents.
    rmSync(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  try {
    const report = checkChineseSpec();
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = report.passed ? 0 : 1;
  } catch (error) {
    console.error(JSON.stringify({ passed: false, scope: 'spec-structure-only', error: error.message }));
    process.exitCode = 1;
  }
}
