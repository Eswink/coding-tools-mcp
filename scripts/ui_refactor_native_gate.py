"""Require new UI evidence in addition to all twelve real installed security stages."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import json
import re
from exclusive_native_gate import load, require, verify as verify_exclusive
from ui_refactor_native import PAGES, SIZES, THEMES, SCENARIO


def verify(value, *, directory, **identity):
    result = verify_exclusive(value, **identity)
    ui = value.get('ui_refactor', {})
    require(ui.get('scenario') == SCENARIO and ui.get('passed') is True, 'new UI acceptance missing')
    require(ui.get('mock_transport') is False and ui.get('interaction_source') == 'native-webdriver-clicks', 'native UI required')
    require(ui.get('publish_approved') is False, 'visual approval is a separate user gate')
    rows = ui.get('screens')
    require(type(rows) is list and len(rows) == 20, 'twenty installed UI screens required')
    expected = [(page, [w,h], theme) for w,h in SIZES for theme in THEMES for page in PAGES]
    require([(r.get('page'),r.get('requested_window'),r.get('theme')) for r in rows] == expected, 'wrong UI coverage')
    for row in rows:
        require(row.get('passed') is True and row.get('overflow') == [], 'native layout failed')
        viewport = row.get('viewport', [])
        require(len(viewport) == 2 and all(type(n) is int for n in viewport) and viewport[0]>=800 and viewport[1]>=500, 'native dimensions missing')
        name = row.get('file', '')
        require(type(name) is str and re.fullmatch(r'ui-native-[a-z]+-\d+x\d+-(light|dark)\.png',name) is not None, 'invalid image path')
        file = directory / name
        require(file.is_file() and not file.is_symlink(), 'native image missing')
        raw = file.read_bytes()
        require(raw.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(raw).hexdigest() == row.get('sha256'), 'native image digest mismatch')
    return {**result, 'ui_screens': len(rows), 'ui_scenario': SCENARIO, 'publish_approved': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('input', 'binary'): p.add_argument('--' + key, type=Path, required=True)
    for key in ('source', 'run-id', 'version', 'kind'): p.add_argument('--' + key, required=True)
    a = p.parse_args()
    with a.binary.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    print(json.dumps(verify(load(a.input), directory=a.input.parent, source=a.source, run_id=a.run_id,
        version=a.version, kind=a.kind, binary_sha256=digest)))

if __name__ == '__main__': main()
