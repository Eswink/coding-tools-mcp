"""Bind actual built-route evidence to a single source and run; never infer native proof."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
from exclusive_native_gate import load, require, legacy

PAGES = ('workspace-overview', 'general-settings', 'credentials-and-keys', 'frp-configuration', 'software-management')
SIZES = ((1586, 992), (1280, 800), (960, 640), (1920, 1080))
STATES = ('empty-workspace', 'empty-frp', 'empty-software', 'long-workspace', 'partial-secret-failure',
          'task-empty-and-error', 'approval-minimum-dark', 'system-theme-live')

def sha(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), 'evidence file missing or symlink: ' + path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect(folder: Path, checkout: Path) -> dict:
    result = load(folder / 'result.json')
    require(result.get('mode') == 'candidate' and result.get('ok') is True and result.get('browser_errors') == [], 'route regression failed')
    require(result.get('transport') == 'mocked Tauri IPC; actual production build/routes'
            and result.get('native_verified') is False and result.get('real_chatgpt_verified') is False, 'mislabeled route evidence')
    rows = result.get('screens', [])
    expected = [(page, w, h, theme) for theme in ('light', 'dark') for w, h in SIZES for page in PAGES]
    require([(r.get('page'), r.get('width'), r.get('height'), r.get('theme')) for r in rows] == expected, 'forty exact route screens required')
    names = []
    for row in rows:
        require(row.get('overflow') == [], 'route overflow')
        name = f"{row['page']}-{row['width']}x{row['height']}-{row['theme']}.png"
        require(row.get('file') == name, 'route image path mismatch')
        raw = (folder / name).read_bytes()
        require(raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[12:16] == b'IHDR' and len(raw) >= 5000
                and struct.unpack('>II', raw[16:24]) == (row['width'], row['height']), 'route PNG geometry invalid')
        names.append(name)
    scenarios = result.get('scenarios', [])
    require(len(scenarios) == 10 and len({r.get('name') for r in scenarios}) == 10
            and all(r.get('ok') is True for r in scenarios), 'ten actual route interactions required')
    states = result.get('state_scenarios', [])
    state_path = folder / 'state-results.json'
    sha(state_path)
    with state_path.open('rb') as stream: raw = stream.read(legacy.LIMIT + 1)
    require(0 < len(raw) <= legacy.LIMIT, 'state evidence size invalid')
    state_doc = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=legacy.unique_object, parse_constant=legacy.reject_constant)
    require([r.get('name') for r in states] == list(STATES) and state_doc == states, 'eight route states required')
    for row in states:
        name = f"state-{row['name']}.png"
        require(row.get('ok') is True and row.get('native_verified') is False and row.get('file') == name, 'invalid state observation')
        raw = (folder / name).read_bytes()
        require(raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) >= 5000, 'invalid state image')
        names.append(name)
    manifest = load(folder / 'source-manifest.json')
    actual = {str(p.relative_to(checkout)): sha(p) for p in (checkout / 'src').rglob('*') if p.is_file()}
    require(actual and manifest.get('files') == actual, 'route source tree mismatch')
    require(manifest.get('fixture_sha256') == sha(checkout / 'tests/fixtures/ui-refactor-ipc.js'), 'route fixture mismatch')
    names += ['result.json', 'state-results.json', 'source-manifest.json']
    return {'route_screens': 40, 'route_interactions': 10, 'route_states': 8,
            'files': {name: sha(folder / name) for name in names}, 'mock_transport': True, 'native_verified': False}

def verify(folder: Path, checkout: Path, *, source: str, tree: str, run_id: str) -> dict:
    value = load(folder / 'provenance.json')
    require(value.get('source_sha') == source and value.get('source_tree') == tree and value.get('run_id') == run_id,
            'route evidence source/run mismatch')
    observed = inspect(folder, checkout)
    require(value.get('observed') == observed, 'route evidence bytes changed')
    return {key: value for key, value in observed.items() if key != 'files'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['record'])
    parser.add_argument('--root', type=Path, required=True); parser.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.root, text=True).strip()
    tree = subprocess.check_output(['git', 'rev-parse', 'HEAD^{tree}'], cwd=args.root, text=True).strip()
    require(os.environ.get('GITHUB_SHA') == source and re.fullmatch(r'[1-9][0-9]*', os.environ.get('GITHUB_RUN_ID', '')), 'hosted route source mismatch')
    observed = inspect(args.folder, args.root)
    (args.folder / 'provenance.json').write_text(json.dumps({'source_sha': source, 'source_tree': tree,
        'run_id': os.environ['GITHUB_RUN_ID'], 'observed': observed}, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__': main()
