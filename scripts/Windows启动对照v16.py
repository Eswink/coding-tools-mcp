"""Same-machine launcher controls. Diagnostic outcomes are not product acceptance."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(label: str, output: Path) -> int:
    if sys.platform != 'win32' or os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted' or os.environ.get('GITHUB_REPOSITORY') != 'Eswink/coding-tools-mcp':
        raise RuntimeError('disposable Windows CI required')
    if label not in ('bash', 'pwsh'):
        raise ValueError('unexpected shell label')
    output.mkdir(parents=True, exist_ok=True)
    medium = load('medium_control_v16', 'Windows非提升进程v12.py')
    smoke = [str(Path(__file__).with_name('Windows桌面冒烟v15.py').resolve())]
    rows = []
    def check(name: str, env: dict, args: list[str]):
        process = None
        row = {'name': name, 'passed': False}
        try:
            process = medium.launch(Path(sys.executable), env, args)
            row['security'] = process.security
            code = process.wait(15)
            row.update(exit_code=code, exit_code_hex=f'0x{code & 0xffffffff:08x}', passed=code == 0)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            row['error_type'] = type(error).__name__
        finally:
            if process:
                try:
                    process.terminate_tree()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    row.update(passed=False, cleanup_error=type(error).__name__)
            rows.append(row)
    try:
        check('plain-user32', dict(os.environ), smoke)
        adapter = load('adapter_control_v16', '跨平台原生驱动v8.py')
        check('after-adapter-import-user32', dict(os.environ), smoke)
        with tempfile.TemporaryDirectory(prefix='native-control-v16-', dir=os.environ['RUNNER_TEMP']) as temporary:
            env = adapter.webview_environment(adapter.gui.port(), Path(temporary).resolve())
            check('webview-environment-user32', env, smoke)
            check('webview-environment-host-help', env, [str(Path(__file__).with_name('Windows原生宿主v13.py').resolve()), '--help'])
    finally:
        report = {'kind': 'launcher-diagnostic-not-product-acceptance', 'source_sha': os.environ['GITHUB_SHA'],
                  'shell': label, 'cases': rows, 'passed': len(rows) == 4 and all(row['passed'] for row in rows)}
        (output / f'Windows启动对照-{label}-v16.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True, choices=['bash', 'pwsh'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.label, args.output))
