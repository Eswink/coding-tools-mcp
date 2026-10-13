"""Generate or check the committed native-probe source manifest (all tracked files except itself)."""
import argparse
import json
from pathlib import Path
import sys
from rc_native_probe_restore import MANIFEST, manifest_rows, set_diff, checkout_files, git


def render(root):
    rows = manifest_rows(root)
    return (json.dumps(dict(schema='rc-native-probe-source-manifest/v1', excludes_self=MANIFEST,
                            entries=len(rows), rows=rows), indent=1, sort_keys=True)+'\n').encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='.')
    parser.add_argument('mode', choices=('write', 'check'))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    raw = render(root)
    target = root/MANIFEST
    if args.mode == 'write':
        target.write_bytes(raw)
        return 0
    committed = target.read_bytes() if target.is_file() else b''
    tracked = git(root, 'ls-files', '-z').decode().split('\0')[:-1]
    diff = set_diff([r['path'] for r in json.loads(raw)['rows']], tracked, checkout_files(root))
    if committed != raw or diff:
        print(json.dumps(dict(manifest_matches=committed == raw, set_diff=diff), sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(dict(manifest_matches=True, entries=json.loads(raw)['entries'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
