"""Source-backed native publisher probe. No release, installation or host setup."""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from rc_native_probe_restore import restore, sha, write, RUNNER_SHA, FIXTURE_SHA, ENV, git, read_regular
from rc_native_probe_kernel import identity, realm
from rc_native_probe_owner import run_owned, RUNTIME, OPTIONAL_RUNTIME

BRANCH='test/rc070-native-recovery-probe-20261009'
FILES=('docs/specs/issue88-native-runtime-recovery-probe/requirements.md',
       'docs/specs/issue88-native-runtime-recovery-probe/design.md',
       'docs/specs/issue88-native-runtime-recovery-probe/tasks.md',
       '.github/workflows/rc-native-recovery-probe.yml',
       'scripts/rc_native_probe.py','scripts/rc_native_probe_restore.py','scripts/rc_native_probe_kernel.py',
       'scripts/rc_native_probe_owner.py','scripts/rc_native_probe_original_runner.py',
       'scripts/rc_native_probe_inventory.json','scripts/rc_native_probe_checks.py')


def precondition(context,output):
    path=Path(context['root'])/'scripts/rc_consumer_fixed_git.py'
    assignments={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(path.read_text()).body
                 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('PREFIX','OVERRIDES')}
    assert assignments['PREFIX']==('--no-pager','--no-replace-objects','--no-optional-locks','--no-lazy-fetch')
    assert assignments['OVERRIDES']==('-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
                                    '-c','core.untrackedCache=false','-c','credential.helper=','-c','protocol.allow=never')
    command=['/usr/bin/git',*assignments['PREFIX'],*assignments['OVERRIDES'],'--version']
    observed=subprocess.run(command,env=ENV,capture_output=True,timeout=30)
    missing=[p for p in RUNTIME if not Path(p).is_file()]
    runtime={p:identity(p) for p in RUNTIME if Path(p).is_file()}
    # Decision 2 rev 2026-10-10: the verified /usr/bin/git is the accepted native Git; an image-provided
    # /usr/local/bin/git is recorded when present but its absence is no longer a precondition failure.
    optional_absent=[p for p in OPTIONAL_RUNTIME if not Path(p).is_file()]
    git_ok='/usr/bin/git' in runtime and runtime['/usr/bin/git']['realpath']=='/usr/bin/git'
    passed=observed.returncode==0 and observed.stdout.startswith(b'git version ') and not missing and git_ok
    report=dict(passed=passed,SUT_runs=0,command=command,exit_code=observed.returncode,
                stdout=observed.stdout.decode('ascii',errors='strict'),stderr_sha256=sha(observed.stderr),
                unsupported_no_lazy_fetch=b'unknown option: --no-lazy-fetch' in observed.stderr,
                missing_required_original_runtime_paths=missing,optional_runtime_paths_absent=optional_absent,
                accepted_native_git='/usr/bin/git' if git_ok else None,runtime=runtime,realm=realm(),
                native_PATH='/usr/bin:/bin:'+str(Path(sys.executable).parent),
                actual_native_git_resolved=shutil.which('git',path='/usr/bin:/bin'),
                no_flags_removed=True,no_install_or_binary_replacement=True)
    write(output/'NATIVE-PRECONDITION.json',report)
    assert report['actual_native_git_resolved']=='/usr/bin/git'
    return passed


def safe_artifacts(output):
    # Only exact original evidence filenames, never certificate/temp/source trees.
    names=['SOURCE-RESTORATION.json','NATIVE-PRECONDITION.json','CARRIER-IDENTITY.json','PROBE-RESULT.json']
    for profile in ('necessary85','original300'):
        names += [profile+'/'+n for n in ('LAUNCH.json','NATIVE-CLOSURE.json','RAW-EVIDENCE-SEAL.json','controller-stdout.log','controller-stderr.log',
                  'cases/receipt.json','cases/cases.log','cases/session-stdout.log','cases/session-stderr.log')]
    blobs={name:read_regular(output/name) for name in names if (output/name).is_file()}
    assert sum(map(len,blobs.values()))<=32*1024*1024
    assert all(not (output/name).is_symlink() and (output/name).stat().st_nlink==1 for name in blobs)
    # Values remain solely in this process for comparison; no value/hash exported.
    secret_values=[v.encode() for k,v in os.environ.items() if len(v)>=8 and any(word in k.upper() for word in ('TOKEN','SECRET','PASSWORD','COOKIE','AUTHORIZATION'))]
    for raw in blobs.values():
        assert b'-----BEGIN ' not in raw and b'PRIVATE KEY' not in raw
        assert not any(value in raw for value in secret_values)
        assert b'Authorization: Bearer ' not in raw and b'Authorization: Basic ' not in raw
        assert b'ghp_' not in raw and b'github_pat_' not in raw
    destination=output/'safe-artifacts'
    assert not destination.exists()
    destination.mkdir()
    rows=[]
    for name,raw in blobs.items():
        path=destination/name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        assert path.read_bytes()==raw
        rows.append(dict(path=name,bytes=len(raw),sha256=sha(raw)))
    write(destination/'SAFE-ARTIFACT-MANIFEST.json',dict(original_bytes_preserved=True,scanned=True,files=rows))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--management',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--fixture',required=True)
    args=parser.parse_args()
    management,output,fixture=Path(args.management).resolve(),Path(args.output).resolve(),Path(args.fixture).resolve()
    assert not output.exists() and management not in output.parents
    assert os.environ.get('GITHUB_EVENT_NAME')=='push'
    assert os.environ.get('GITHUB_REPOSITORY')=='Eswink/coding-tools-mcp'
    assert os.environ.get('GITHUB_REF')=='refs/heads/'+BRANCH
    head=git(management,'rev-parse','HEAD').decode().strip()
    assert head==os.environ.get('GITHUB_SHA')
    assert git(management,'status','--porcelain','--untracked-files=all')==b''
    assert len(fixture.read_bytes())==267679 and sha(fixture.read_bytes())==FIXTURE_SHA
    paths=[management/p for p in FILES]
    carrier={str(p):identity(p) for p in paths}
    runner=management/'scripts/rc_native_probe_original_runner.py'
    assert sha(runner.read_bytes())==RUNNER_SHA and len(runner.read_bytes())==6327
    context=restore(management,output)
    write(output/'CARRIER-IDENTITY.json',dict(commit=head,branch=BRANCH,files=carrier,
          source_tree=context['tree'],pure_source_count=1878,immutable_runner_sha256=RUNNER_SHA,
          no_release_grant=True,no_compiler_install_or_privilege=True))
    success=False
    counts=dict(necessary85='NOT_RUN',original300='NOT_RUN')
    error=None
    try:
        if not precondition(context,output):
            pre=json.loads((output/'NATIVE-PRECONDITION.json').read_text())
            error=dict(stage='native-precondition',reason='native runtime precondition not met',
                       missing_required_runtime_paths=pre['missing_required_original_runtime_paths'],
                       git_exit_code=pre['exit_code'],SUT_runs=0)
        else:
            inventories=json.loads((management/'scripts/rc_native_probe_inventory.json').read_text())
            first=run_owned(context,'necessary85',inventories['necessary85'],output/'necessary85',fixture,runner,paths)
            counts['necessary85']='QUALIFIED' if first['native']['qualified'] else 'FAIL_UNKNOWN'
            if first['native']['qualified']:
                second=run_owned(context,'original300',inventories['original300'],output/'original300',fixture,runner,paths,prior=first)
                counts['original300']='QUALIFIED' if second['native']['qualified'] else 'FAIL_UNKNOWN'
                success=second['native']['qualified']
            if not success:
                error=dict(stage='native-profiles',reason='profile not qualified',profiles=dict(counts))
    except BaseException as failure:
        error=dict(stage='exception',reason=type(failure).__name__,detail=str(failure)[:500])
        raise
    finally:
        if not success and error is None:
            error=dict(stage='unknown',reason='probe ended without qualification')
        write(output/'PROBE-RESULT.json',dict(passed=success,profiles=counts,current_CI_result_only=True,
              retained_local85='FAILED_50_named_PASS_35_non_success',release_authorized=False,error=error))
        if error is not None:
            # One structured line so a failed CI step is never silent.
            print(json.dumps(dict(rc_native_probe_error=error),sort_keys=True,separators=(',',':')),file=sys.stderr,flush=True)
        safe_artifacts(output)
    return 0 if success else 1


if __name__=='__main__':
    raise SystemExit(main())
