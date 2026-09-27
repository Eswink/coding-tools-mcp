"""Reconstruct only the reviewed candidate in a disposable CI checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

staging = Path(__file__).resolve().parents[2]
source = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
if source == staging or source in output.parents:
    raise SystemExit('Source and evidence must be separate from staging and each other')
manifest = json.loads((staging / 'tools/delivery/desktop-candidate.json').read_text(encoding='utf-8'))

def git(*args):
    return subprocess.check_output(['git', '-c', 'core.quotePath=false', *args], cwd=source, text=True, encoding='utf-8').strip()

if git('rev-parse', 'HEAD') != manifest['base'] or git('status', '--porcelain', '--untracked-files=no'):
    raise SystemExit('Expected a clean exact baseline checkout')
for name, expected in manifest['patches'].items():
    path = staging / 'tools/delivery/desktop-patch' / name
    data = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    if actual != expected:
        raise SystemExit('Patch blob identity mismatch: ' + name)
    subprocess.run(['git', 'apply', '--index', '--check', str(path)], cwd=source, check=True)
    subprocess.run(['git', 'apply', '--index', str(path)], cwd=source, check=True)
if git('write-tree') != manifest['tree']:
    raise SystemExit('Candidate tree mismatch')
if set(git('diff', '--cached', '--name-only').splitlines()) != set(manifest['files']):
    raise SystemExit('Candidate scope mismatch')
for path, expected in manifest['files'].items():
    if git('rev-parse', ':' + path) != expected:
        raise SystemExit('Candidate file mismatch: ' + path)
subprocess.run(['git', '-c', 'user.name=Candidate Validator', '-c', 'user.email=validator@localhost', 'commit', '--no-verify', '-m', 'Disposable exact-tree desktop sandbox candidate; not publication'], cwd=source, check=True)
output.mkdir(parents=True, exist_ok=True)
manifest['ci_local_commit'] = git('rev-parse', 'HEAD')
(output / 'source.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'base': manifest['base'], 'tree': manifest['tree'], 'files': len(manifest['files'])}))
