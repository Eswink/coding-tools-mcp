"""Necessary carrier checks; never execute the project SUT in this local runtime."""
import argparse
import ast
import copy
import json
from pathlib import Path
import tempfile
from rc_native_probe_restore import sha,restore,whole_source,TREE,RUNNER_SHA,read_regular
from rc_native_probe import FILES,precondition,safe_artifacts


def check(condition,label,rows):
    assert condition,label
    rows.append(dict(check=label,passed=True))


def assert_reject(action,label,rows):
    try:
        action()
    except (AssertionError,KeyError,ValueError,OSError):
        rows.append(dict(check=label,passed=True,expected_reject=True))
    else:
        raise AssertionError(label)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--management',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--golden-v5',required=True)
    parser.add_argument('--golden-inventory',required=True)
    args=parser.parse_args()
    management,output=Path(args.management).resolve(),Path(args.output).resolve()
    assert not output.exists()
    rows=[]
    scripts=management/'scripts'
    inventory=json.loads((scripts/'rc_native_probe_inventory.json').read_text())
    original=json.loads(Path(args.golden_inventory).read_text())
    check(inventory=={k:original[k] for k in ('necessary85','original300')},'original85/300 exact ordered names',rows)
    check(sha((scripts/'rc_native_probe_inventory.json').read_bytes())=='99496a8f599ce50f31a97a692fd3ee101a1a7059f751e670d3c9de298e654bfb','literal inventory SHA',rows)
    check(all(len(inventory[k])==len(set(inventory[k]))==n for k,n in [('necessary85',85),('original300',300)]),'85/300 retained unique sizes',rows)
    runner=(scripts/'rc_native_probe_original_runner.py').read_bytes()
    check(len(runner)==6259 and len(runner.splitlines())==103 and sha(runner)==RUNNER_SHA,'immutable103line runner rawSHA',rows)
    golden=Path(args.golden_v5).read_bytes()
    check(sha(golden)=='99f402108d5db499fe0cde4a38f2810e7f11a0083d00aaf961dafaa19e08e87f','actualV5 golden launcher identity',rows)
    old={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(golden).body if isinstance(n,ast.FunctionDef)}
    current={n.name:ast.dump(n,include_attributes=False) for n in ast.parse((scripts/'rc_native_probe_kernel.py').read_text()).body if isinstance(n,ast.FunctionDef)}
    check(all(current[n]==old[n] for n in ('identity','realm','proc_fields','kernel','owned_family_close')),'all5 currentkernel exactV5 AST',rows)
    for rel in FILES:
        path=management/rel
        check(path.is_file() and not path.is_symlink(),rel+' physical regular source',rows)
    for path in scripts.glob('rc_native_probe*.py'):
        ast.parse(path.read_text())
        check(len(path.read_text().splitlines())<=400,path.name+' bounded parsed source',rows)
    workflow=(management/'.github/workflows/rc-native-recovery-probe.yml').read_text()
    check("branches: ['test/rc070-native-recovery-probe-20261009']" in workflow and 'contents: read' in workflow and 'persist-credentials: false' in workflow and 'fetch-depth: 0' in workflow,'fixedread-only workflow',rows)
    check(all(s not in workflow for s in ('setup-python','sudo ','apt-get','cargo ','secrets.','workflow_dispatch','pull_request_target','contents: write','GITHUB_TOKEN:')),'no install/compiler/token/release privileges',rows)
    context=restore(management,output)
    check(context['tree']==TREE and context['count']==1878 and whole_source(context['root'],context['rows'])==context['source'],'actualfull source restoration1878/b9cf',rows)
    changed=copy.deepcopy(context['rows'])
    changed[0]['sha256']='0'*64
    assert_reject(lambda:whole_source(context['root'],changed),'one corrupt source SHA blocks',rows)
    changed=copy.deepcopy(context['rows'])
    changed[0]['path']='../escape'
    assert_reject(lambda:whole_source(context['root'],changed),'source path escape blocks',rows)
    changed=copy.deepcopy(context['rows'])
    changed[0]['mode']='120000'
    assert_reject(lambda:whole_source(context['root'],changed),'source symlink mode blocks',rows)
    prefix_ok=precondition(context,output)
    pre=json.loads((output/'NATIVE-PRECONDITION.json').read_text())
    check(pre['SUT_runs']==0 and pre['command'][4]=='--no-lazy-fetch' and pre['no_flags_removed'],'actual original nativeprefix precondition SUT0',rows)
    with tempfile.TemporaryDirectory(prefix='owned-native-artifact-negative-') as directory:
        dest=Path(directory)
        (dest/'PROBE-RESULT.json').write_bytes(b'-----BEGIN PRIVATE KEY-----\nowned fake negative only\n')
        assert_reject(lambda:safe_artifacts(dest),'privatekey rawartifact blocks beforecopy',rows)
        check(not (dest/'safe-artifacts').exists(),'scan failure creates no upload directory',rows)
    with tempfile.TemporaryDirectory(prefix='owned-native-artifact-positive-') as directory:
        dest=Path(directory)
        raw=b'{"passed":false,"SUT_runs":0}\n'
        (dest/'PROBE-RESULT.json').write_bytes(raw)
        (dest/'not-whitelisted.key').write_bytes(b'not eligible for upload')
        safe_artifacts(dest)
        check((dest/'safe-artifacts/PROBE-RESULT.json').read_bytes()==raw and not (dest/'safe-artifacts/not-whitelisted.key').exists(),'safe whitelist original bytes exact',rows)
    with tempfile.TemporaryDirectory(prefix='owned-native-nofollow-negative-') as directory:
        dest=Path(directory)
        (dest/'owned').write_bytes(b'owned negative fixture only')
        (dest/'filelink').symlink_to(dest/'owned')
        assert_reject(lambda:read_regular(dest/'filelink'),'symlink leaf rejected nofollow',rows)
        (dest/'dir').mkdir()
        (dest/'dir/data').write_bytes(b'owned directory negative only')
        (dest/'dirlink').symlink_to(dest/'dir',target_is_directory=True)
        assert_reject(lambda:read_regular(dest/'dirlink/data'),'symlink parent rejected nofollow',rows)
        import os
        os.link(dest/'owned',dest/'hardlink')
        assert_reject(lambda:read_regular(dest/'owned'),'hardlink rejected beforebytes',rows)
    report=dict(checks_passed=True,checks=rows,total=len(rows),SUT_runs=0,source_tree=TREE,
                native_prefix_passed=prefix_ok,native_prefix_result=pre['exit_code'],
                current_local85='FAIL_RETAINED',current300='NOT_RUN',CI='NOT_RUN')
    (output/'NECESSARY-CARRIER-CHECKS.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('checks_passed','total','SUT_runs','source_tree','native_prefix_passed','native_prefix_result')}))


if __name__=='__main__':
    main()
