import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import os
import shutil
import stat
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('groups', nargs='+')
args = parser.parse_args()
root, output = Path(args.root), Path(args.output)
sys.path.insert(0, str(root / 'scripts'))
output.mkdir(parents=True, exist_ok=False)

def source():
    paths = subprocess.check_output(['/usr/bin/git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
    paths += ['scripts/rc_publication_artifact_admission.py', 'scripts/rc_publication_artifact_admission_cases.py']
    paths += [str(p.relative_to(root)) for p in (root / 'docs/specs/issue88-artifact-admission').glob('*.md')]
    return {p: dict(size=(root/p).stat().st_size, mode=stat.S_IMODE((root/p).stat().st_mode), sha256=hashlib.sha256((root/p).read_bytes()).hexdigest())
            for p in sorted(set(paths)) if p}

def flatten(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from flatten(case)
        else:
            yield case.id()

class NamedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.executed, self.passed = [], []
    def startTest(self, test):
        self.executed.append(test.id())
        super().startTest(test)
    def addSuccess(self, test):
        self.passed.append(test.id())
        super().addSuccess(test)

def runtime():
    names = ('/usr/bin/git', '/usr/local/bin/git', '/usr/bin/python3', '/usr/bin/openssl', sys.executable)
    return {name: dict(realpath=str(Path(name).resolve()), size=Path(name).stat().st_size,
            mode=stat.S_IMODE(Path(name).stat().st_mode), uid=Path(name).stat().st_uid,
            gid=Path(name).stat().st_gid, nlink=Path(name).stat().st_nlink,
            sha256=hashlib.sha256(Path(name).read_bytes()).hexdigest()) for name in sorted(set(names))}

def fixture():
    name = os.environ.get('RC_CONSUMER_TEST_GLIB_ARCHIVE')
    if not name:
        raise RuntimeError('required retained GLib fixture environment missing')
    path = Path(name)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != '233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5':
        raise RuntimeError('retained official GLib fixture hash mismatch')
    return dict(environment=name, realpath=str(path.resolve()), size=path.stat().st_size,
                mode=stat.S_IMODE(path.stat().st_mode), sha256=digest)

runner_before = dict(sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), mode=stat.S_IMODE(Path(__file__).stat().st_mode))
invocation = dict(argv=sys.argv, PATH=os.environ.get('PATH'), resolved_path_git=shutil.which('git'), cwd=os.getcwd())
fixture_before = fixture()
started_utc = datetime.now(timezone.utc).isoformat()
index_before = hashlib.sha256(subprocess.check_output(['/usr/bin/git', '-C', str(root), 'ls-files', '--stage', '-z'])).hexdigest()
before = source()
runtime_before = runtime()
suite = unittest.TestLoader().loadTestsFromNames(args.groups)
loaded = list(flatten(suite))
start = time.monotonic()
with (output / 'cases.log').open('w') as stream, (output / 'session-stdout.log').open('w') as stdout, (output / 'session-stderr.log').open('w') as stderr:
    with redirect_stdout(stdout), redirect_stderr(stderr):
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=NamedResult).run(suite)
elapsed = time.monotonic()-start
after = source()
index_after = hashlib.sha256(subprocess.check_output(['/usr/bin/git', '-C', str(root), 'ls-files', '--stage', '-z'])).hexdigest()
runtime_after = runtime()
runner_after = dict(sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), mode=stat.S_IMODE(Path(__file__).stat().st_mode))
fixture_after = fixture()
receipt = dict(scope='unsealed-native-stage-admission-composition-draft',
    source_parent=subprocess.check_output(['/usr/bin/git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip(),
    loaded=loaded, executed=result.executed, named_passed=result.passed,
    test_ids_sha256=hashlib.sha256(('\n'.join(sorted(loaded))+'\n').encode()).hexdigest(),
    failures=len(result.failures), errors=len(result.errors), skips=len(result.skipped),
    expected_failures=len(result.expectedFailures), unexpected_successes=len(result.unexpectedSuccesses),
    elapsed_seconds=elapsed, started_utc=started_utc, ended_utc=datetime.now(timezone.utc).isoformat(), source_before=before, source_after=after,
    fixture_before=fixture_before, fixture_after=fixture_after, fixture_unchanged=fixture_before == fixture_after,
    stdout_sha256=hashlib.sha256((output/'session-stdout.log').read_bytes()).hexdigest(), stderr_sha256=hashlib.sha256((output/'session-stderr.log').read_bytes()).hexdigest(),
    runtime_before=runtime_before, runtime_after=runtime_after, runtime_unchanged=runtime_before == runtime_after,
    source_unchanged=before == after, runner_before=runner_before, runner_after=runner_after, runner_unchanged=runner_before == runner_after, invocation=invocation, index_before=index_before, index_after=index_after, index_unchanged=index_before == index_after, log_sha256=hashlib.sha256((output/'cases.log').read_bytes()).hexdigest(),
    python_version=sys.version, git_version=subprocess.check_output(['/usr/bin/git', '--version']).decode().strip())
receipt['passed'] = (result.wasSuccessful() and fixture_before == fixture_after and runner_before == runner_after and index_before == index_after and before == after and runtime_before == runtime_after and len(loaded) == len(set(loaded))
    and loaded == result.executed and set(loaded) == set(result.passed) and not result.skipped
    and not result.expectedFailures and not result.unexpectedSuccesses)
(output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps({key:receipt[key] for key in ('scope','passed','elapsed_seconds','failures','errors','skips','test_ids_sha256')}))
sys.exit(0 if receipt['passed'] else 1)
