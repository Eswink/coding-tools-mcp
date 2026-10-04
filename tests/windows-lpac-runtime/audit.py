"""Portable fail-closed source audit; no Windows command is executed here."""
from hashlib import sha256
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
HASHES = {
    "NativeLauncher.cs": "e83075d8302a4fc27c91ece3a65cd8122ac6298fb2d9449bd9cb5e41147ef223",
    "run.ps1": "8bae4d860fac03959ba11ab9669c649d4063c61eab8c56410716558a4ff8200e",
    "windows_sandbox_fixture.rs": "1d9cee541420fa62d880953ebf481fad32350113871fdc6086dc5fd6e4971ec2",
}
COPY_METHOD = '''    // The payload is a disposable CI copy; reject links rather than traverse to an existing ACL scope.
    static void CopyOwnedBundle(string source,string target) {
        if((File.GetAttributes(source)&FileAttributes.ReparsePoint)!=0) throw new ArgumentException("bundle link rejected");
        foreach(string file in Directory.GetFiles(source)) {
            if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0) throw new ArgumentException("bundle file link rejected");
            File.Copy(file,Path.Combine(target,Path.GetFileName(file)),false);
        }
        foreach(string dir in Directory.GetDirectories(source)) {
            string child=Path.Combine(target,Path.GetFileName(dir));Directory.CreateDirectory(child);
            CopyOwnedBundle(dir,child);
        }
    }
'''
COLLECT = '            // Capture fixed files only after the job is drained, including fixture timeouts.\n            foreach(string resultName in new string[]{"pre-network.txt","runtime-checks.txt","receipt.txt","runtime-result.json","runtime-stdout.txt","runtime-stderr.txt"}) {\n                string resultPath=Path.Combine(workspace,resultName);\n                string destination=Path.Combine(parent,resultName.StartsWith("runtime-") && resultName!="runtime-checks.txt"?resultName:"sandbox-"+resultName);\n                if(File.Exists(resultPath) && !File.Exists(destination)) File.Copy(resultPath,destination,false);\n            }\n            File.WriteAllText(Path.Combine(parent,"launcher-lifecycle.json"),"{\\"job_drained\\":"+verifiedDrained.ToString().ToLowerInvariant()+",\\"fixture_wait\\":"+observedWait+",\\"fixture_exit\\":"+observedExit+"}");\n'


def expected_launcher(baseline):
    """All remaining launch, capability, ACL, job and cleanup code must match."""
    return (baseline
        .replace("public static class LpacFixtureLauncher {", "public static class LpacRuntimeLauncher {")
        .replace("public static int Run(string fixture,string parent,string outside,int port,bool lpac,int mode) {",
                 'public static int Run(string fixture,string parent,string outside,int port,bool lpac,int mode,string bundle) {\n        if(!lpac) throw new ArgumentException("runtime observations require unchanged LPAC");')
        .replace('string name="ctm.fixture."', 'CopyOwnedBundle(bundle,code);\n        string name="ctm.fixture."')
        .replace('bool initialized=false,profile=false;', 'bool initialized=false,profile=false;\n        uint observedWait=UInt32.MaxValue,observedExit=UInt32.MaxValue;bool verifiedDrained=false;')
        .replace('uint wait=WaitForSingleObject(pi.process,15000);', 'uint wait=WaitForSingleObject(pi.process,45000);observedWait=wait;')
        .replace('uint exit;Check(GetExitCodeProcess(pi.process,out exit),"fixture exit code");', 'uint exit;Check(GetExitCodeProcess(pi.process,out exit),"fixture exit code");observedExit=exit;')
        .replace('stopped=stopped && drained;', 'stopped=stopped && drained;verifiedDrained=drained;')
        .replace('            if(profile) { int hr=DeleteAppContainerProfile', COLLECT+'            if(profile) { int hr=DeleteAppContainerProfile')
        .replace('    // root must be a NEW EMPTY directory', COPY_METHOD+'    // root must be a NEW EMPTY directory'))


def expected_fixture(baseline):
    return (baseline
        .replace('//! Fixed synthetic kernel probes. Not a public tool or arbitrary-command runner.',
                 '//! Recovered native fixture plus one bounded offline observation before the unchanged network gate.\n#[cfg(windows)]\nmod runtime_contract;')
        .replace('    // Read-only fixed OS-runtime probes:',
                 '    // Failure here never substitutes for native network-denial evidence.\n    runtime_contract::observe(root, outside);\n    // Read-only fixed OS-runtime probes:'))


def audit(files):
    errors = []
    for name, digest in HASHES.items():
        if sha256(files['baseline/'+name].encode()).hexdigest() != digest:
            errors.append('retained source changed: '+name)
    if files['RuntimeLauncher.cs'] != expected_launcher(files['baseline/NativeLauncher.cs']):
        errors.append('launcher has an unreviewed delta')
    if files['runtime_fixture.rs'] != expected_fixture(files['baseline/windows_sandbox_fixture.rs']):
        errors.append('native fixture has an unreviewed delta')
    workflow = files['workflow']
    if 'continue-on-error' in workflow:
        errors.append('failure laundering is forbidden')
    for expected in ['baseline/run.ps1', "steps.build.outcome == 'success'", "steps.payload.outcome == 'success'", 'if: always()']:
        if expected not in workflow:
            errors.append('missing workflow control: '+expected)
    runner = files['run-runtime.ps1']
    for expected in ["'exit=15107'", "'winsock_initialization_failed_10107'", '$true,1,$bundle', 'outside canary was written', 'owned process-tree cleanup unconfirmed']:
        if expected not in runner:
            errors.append('missing runtime control: '+expected)
    for expected in ['offline_passed=$false;preparation_failed=$true', '$outcomes.Count -ne $cases.Count', 'one or more required preparation or offline runtime contracts failed']:
        if expected not in runner:
            errors.append('missing required preparation failure control: '+expected)
    if 'Read-RuntimeInventory (Get-Content' not in runner:
        errors.append('runtime inventory must use scalar-record parser')
    if 'metadata-contract-tests.ps1' not in workflow:
        errors.append('PowerShell data-shape tests missing')
    if any('Get-FileHash ' in line and 'Get-FileHash -LiteralPath ' not in line for line in files['prepare.ps1'].splitlines()):
        errors.append('payload hash paths must be literal')
    runtime = files['runtime_contract.rs']
    if '.stdin(Stdio::null())' not in runtime:
        errors.append('original null stdin must remain unchanged')
    if 'if !preflight_cleanup_ok {' not in runtime or runtime.index('if !preflight_cleanup_ok {') > runtime.index('cmd.spawn()'):
        errors.append('diagnostic cleanup must gate original spawn')
    original_cases = "$cases=[ordered]@{'python-budget'='python';'python-workspace'='python';'node-workspace'='node';'npm-cmd'='node';'git-local'='git';'cmd-workspace'='cmd';'powershell-workspace'='powershell';'pwsh-workspace'='pwsh'}"
    original_eof = "$eofCases=[ordered]@{'node-workspace-private-eof'='node';'npm-cmd-private-eof'='node';'git-local-private-eof'='git';'cmd-workspace-private-eof'='cmd';'powershell-workspace-private-eof'='powershell';'pwsh-workspace-private-eof'='pwsh'}"
    if original_cases not in runner or original_eof not in runner or 'if($cases.Count -ne 20)' not in runner:
        errors.append('original fourteen and all twenty rows must remain required')
    eof_names = {name+'-private-eof' for name in ['node-workspace', 'npm-cmd', 'git-local', 'cmd-workspace', 'powershell-workspace', 'pwsh-workspace']}
    mode_source = runtime.split('let private_eof =', 1)[-1].split('let base_case =', 1)[0]
    if set(re.findall(r'"([^\"]+-private-eof)"', mode_source)) != eof_names or not mode_source.lstrip().startswith('matches!('):
        errors.append('only six explicit additive cases may select EOF')
    headless_source = runtime.split('let no_window =', 1)[-1].split('let private_eof =', 1)[0]
    if set(re.findall(r'"([^\"]+-private-eof-no-window)"', headless_source)) != {name+'-no-window' for name in eof_names} or not headless_source.lstrip().startswith('matches!('):
        errors.append('only six explicit no-window cases may select headless mode')
    if 'let caller_creation_flags = if no_window { 0x08000000 } else { 0 };' not in runtime or runtime.count('.creation_flags(') != 1:
        errors.append('caller flags may only select CREATE_NO_WINDOW')
    if 'if !input_duplicate_closed {' not in runtime or runtime.index('if !input_duplicate_closed {') > runtime.index('cmd.spawn()'):
        errors.append('input duplicate cleanup must gate spawn')
    if 'const FILE_EXECUTE_ACCESS: u32 = 0x20;' not in files['spawn_observations.rs']:
        errors.append('execute probe must request FILE_EXECUTE only')
    start = runtime.find('        "python-budget" =>')
    end = runtime.find('        _ =>', start)
    if start < 0 or end < 0 or sha256(runtime[start:end].encode()).hexdigest() != '54d3ef93d7e79ba2b0097a0d03f13570f1ebeda9fe31fa42c5e7e0b3e1195194':
        errors.append('original binary and argv cases must remain identical')
    if '.create_new(true)' not in files['private_stdin.rs'] or 'fs::File::open(&path)' not in files['private_stdin.rs']:
        errors.append('private stdin must be new and reopened read-only')
    return errors


def load_files():
    names = ['baseline/'+name for name in HASHES]
    names += ['RuntimeLauncher.cs', 'runtime_fixture.rs', 'run-runtime.ps1', 'prepare.ps1', 'runtime_contract.rs', 'private_stdin.rs', 'spawn_observations.rs']
    files = {name: (ROOT/name).read_bytes().decode('utf-8') for name in names}
    files['workflow'] = (ROOT.parent.parent/'.github/workflows/windows-lpac-runtime-diagnostic.yml').read_bytes().decode('utf-8')
    return files


class AuditMutations(unittest.TestCase):
    def test_exact_recovery(self):
        self.assertEqual([], audit(load_files()))

    def test_byte_changed_newlines_rejected(self):
        files = load_files()
        files['baseline/NativeLauncher.cs'] = files['baseline/NativeLauncher.cs'].replace('\n', '\r\n')
        self.assertIn('retained source changed: NativeLauncher.cs', audit(files))

    def test_capability_count_rejected(self):
        files = load_files()
        files['RuntimeLauncher.cs'] = files['RuntimeLauncher.cs'].replace('capabilities.Sid=sid;', 'capabilities.Sid=sid;capabilities.Count=1;')
        self.assertIn('launcher has an unreviewed delta', audit(files))

    def test_lpac_opt_out_removal_rejected(self):
        files = load_files()
        files['RuntimeLauncher.cs'] = files['RuntimeLauncher.cs'].replace('new IntPtr(0x2000f)', 'new IntPtr(0x20000)')
        self.assertIn('launcher has an unreviewed delta', audit(files))

    def test_winsock_failure_laundering_rejected(self):
        files = load_files()
        files['runtime_fixture.rs'] = files['runtime_fixture.rs'].replace('std::process::exit(5000 + result);', 'std::process::exit(0);')
        self.assertIn('native fixture has an unreviewed delta', audit(files))

    def test_acl_expansion_rejected(self):
        files = load_files()
        files['RuntimeLauncher.cs'] = files['RuntimeLauncher.cs'].replace('OwnedAcl(code,package,FileSystemRights.ReadAndExecute)', 'OwnedAcl(code,package,FileSystemRights.FullControl)')
        self.assertIn('launcher has an unreviewed delta', audit(files))

    def test_ignored_gate_rejected(self):
        files = load_files()
        files['workflow'] += '\ncontinue-on-error: true\n'
        self.assertIn('failure laundering is forbidden', audit(files))

    def test_preparation_failure_cannot_pass(self):
        files = load_files()
        files['run-runtime.ps1'] = files['run-runtime.ps1'].replace('offline_passed=$false;preparation_failed=$true', 'offline_passed=$true;preparation_failed=$true')
        self.assertTrue(any('required preparation failure control' in error for error in audit(files)))

    def test_nested_inventory_parser_rejected(self):
        files = load_files()
        files['run-runtime.ps1'] = files['run-runtime.ps1'].replace('Read-RuntimeInventory (Get-Content', 'ConvertFrom-Json (Get-Content')
        self.assertIn('runtime inventory must use scalar-record parser', audit(files))

    def test_wildcard_hash_paths_rejected(self):
        files = load_files()
        files['prepare.ps1'] = files['prepare.ps1'].replace('Get-FileHash -LiteralPath ', 'Get-FileHash ')
        self.assertIn('payload hash paths must be literal', audit(files))

    def test_stdin_substitution_rejected(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('.stdin(Stdio::null())', '.stdin(Stdio::inherit())')
        self.assertIn('original null stdin must remain unchanged', audit(files))

    def test_uncertain_probe_cleanup_rejected(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('if !preflight_cleanup_ok {', 'if false {')
        self.assertIn('diagnostic cleanup must gate original spawn', audit(files))

    def test_original_rows_cannot_be_replaced(self):
        files = load_files()
        files['run-runtime.ps1'] = files['run-runtime.ps1'].replace("'node-workspace'='node'", "'removed-node'='node'")
        self.assertIn('original fourteen and all twenty rows must remain required', audit(files))

    def test_eof_cannot_be_default(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('let private_eof = matches!', 'let private_eof = true; let ignored = matches!')
        self.assertIn('only six explicit additive cases may select EOF', audit(files))

    def test_existing_input_file_rejected(self):
        files = load_files()
        files['private_stdin.rs'] = files['private_stdin.rs'].replace('.create_new(true)', '.create(true)')
        self.assertIn('private stdin must be new and reopened read-only', audit(files))

    def test_original_argv_change_rejected(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace("print('budget')", "print('changed')")
        self.assertIn('original binary and argv cases must remain identical', audit(files))

    def test_no_window_cannot_be_default(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('let no_window = matches!', 'let no_window = true; let ignored = matches!')
        self.assertIn('only six explicit no-window cases may select headless mode', audit(files))

    def test_extra_creation_flags_rejected(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('0x08000000', '0x09000000')
        self.assertIn('caller flags may only select CREATE_NO_WINDOW', audit(files))

    def test_execute_probe_broadening_rejected(self):
        files = load_files()
        files['spawn_observations.rs'] = files['spawn_observations.rs'].replace('FILE_EXECUTE_ACCESS: u32 = 0x20', 'FILE_EXECUTE_ACCESS: u32 = 0x10000000')
        self.assertIn('execute probe must request FILE_EXECUTE only', audit(files))

    def test_input_duplicate_cleanup_cannot_be_ignored(self):
        files = load_files()
        files['runtime_contract.rs'] = files['runtime_contract.rs'].replace('if !input_duplicate_closed {', 'if false {')
        self.assertIn('input duplicate cleanup must gate spawn', audit(files))


if __name__ == '__main__':
    unittest.main()
