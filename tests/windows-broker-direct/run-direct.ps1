param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Payload,[Parameter(Mandatory=$true)][string]$Evidence,[Parameter(Mandatory=$true)][string]$Foundation)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../windows-lpac-runtime/metadata.ps1')
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub-hosted Windows diagnostic only'}
$fixturePath=(Resolve-Path -LiteralPath $Fixture).Path
if([IO.Path]::GetFileName($fixturePath) -ne 'windows_sandbox_fixture.exe') {throw 'unchanged native reference required'}
$payloadPath=(Resolve-Path -LiteralPath $Payload).Path
$evidencePath=[IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
function Test-ExactReceipt([string]$Path,[string[]]$Expected) {
    if(-not (Test-Path -LiteralPath $Path -PathType Leaf)) {return $false}
    $lines=@(Get-Content -LiteralPath $Path)
    if($lines.Count -ne $Expected.Count) {return $false}
    foreach($line in $Expected) {if(@($lines | Where-Object {$_ -ceq $line}).Count -ne 1) {return $false}}
    return $true
}
$allTrue=@('token=true','inside=true','outside_read=true','outside_write=true','network=true')
$foundationValid=(Test-ExactReceipt (Join-Path $Foundation 'control-receipt.txt') $allTrue) -and
    (Test-ExactReceipt (Join-Path $Foundation 'mode-2-ordinary-appcontainer-receipt.txt') @('token=true','inside=true','outside_read=false','outside_write=true','network=true'))
@{valid=$foundationValid;source='unchanged native-only live control and ordinary-AppContainer mode-2';network_denial_proven=$false} |
    ConvertTo-Json | Set-Content (Join-Path $evidencePath 'foundation-premise.json')
if(-not $foundationValid) {throw 'retained live/ordinary native canary premise missing or invalid'}
$inventory=@(Read-RuntimeInventory (Get-Content -Raw -LiteralPath (Join-Path (Split-Path $evidencePath) 'runtime/runtime-inventory.json')))
# A previous uncertain tree must be resolved before another launch method runs.
if(@(Get-ChildItem -LiteralPath (Split-Path $evidencePath) -Filter cleanup-uncertain.txt -Recurse -File).Count) {throw 'earlier diagnostic cleanup remains uncertain'}
foreach($scanRoot in @($env:RUNNER_TEMP,[IO.Path]::GetTempPath() | Select-Object -Unique)) {
    foreach($candidate in @(Get-ChildItem -LiteralPath $scanRoot -Directory | Where-Object {$_.Name -like 'ctm-native-*' -or $_.Name -like 'ctm runtime-*'})) {
        if(@(Get-ChildItem -LiteralPath $candidate.FullName -Filter cleanup-uncertain.txt -Recurse -File).Count) {throw 'earlier owned diagnostic recovery scope remains'}
    }
}
$root=Join-Path $env:RUNNER_TEMP ('ctm-direct-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$outcomes=@();$referenceValid=$false
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start();$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
try {
    Add-Type -Path @('DirectNative.cs','DirectHandles.cs','DirectCases.cs','DirectCapture.cs','DirectLauncher.cs' | ForEach-Object {Join-Path $PSScriptRoot $_})
    foreach($kind in @('reference','node','cmd','powershell','pwsh')) {
        $row=@{case=('broker-direct-'+$kind);method='broker_direct_private_file_stdio';required_observation=$true;positive_passed=$false;network_denial_proven=$false;runtime_canary_classification='not_measured';status='pending';launcher=$null}
        if($kind -ne 'reference' -and -not $referenceValid) {
            $row.status='blocked_matched_reference_failed';$outcomes+=@($row)
            $outcomes | ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'direct-matrix.json');continue
        }
        if($kind -ne 'reference') {
            $records=@($inventory | Where-Object {$_.runtime -eq $kind})
            if($records.Count -ne 1 -or $records[0].ready -ne $true) {
                $row.status='preparation_failed';$row.preparation_records=$records;$outcomes+=@($row)
                $outcomes | ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'direct-matrix.json');continue
            }
        }
        $caseRoot=Join-Path $root $kind;$outside=Join-Path $caseRoot 'outside';$bundle=Join-Path $caseRoot 'bundle';$run=Join-Path $caseRoot 'run'
        $caseEvidence=Join-Path $evidencePath $kind
        New-Item -ItemType Directory -Path $outside,$bundle,$run,$caseEvidence | Out-Null
        [IO.File]::WriteAllText((Join-Path $outside 'canary.txt'),'synthetic-outside-canary')
        if($kind -eq 'cmd') {Copy-Item -LiteralPath (Join-Path $payloadPath 'cmd.exe') -Destination (Join-Path $bundle 'cmd.exe')}
        elseif($kind -ne 'reference') {
            New-Item -ItemType Directory -Path (Join-Path $bundle 'runtime') | Out-Null
            Copy-Item -Path (Join-Path $payloadPath ($kind+'\*')) -Destination (Join-Path $bundle 'runtime') -Recurse -Force
        }
        $r=$null;$callFailure=$null
        try {$r=[BrokerDirectLauncher]::RunDirect($fixturePath,$run,$outside,$port,$kind,$bundle)}
        catch {$callFailure=$_.Exception.GetBaseException().Message}
        finally {Get-ChildItem -LiteralPath $run -File | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $caseEvidence $_.Name)}}
        if($null -eq $r) {
            $row.status='launcher_exception_recovery_retained';$row.failure=$callFailure;$outcomes+=@($row)
            $outcomes | ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'direct-matrix.json')
            throw 'direct launcher did not return a complete lifecycle receipt'
        }
        $row.launcher=$r
        $r | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $caseEvidence 'launcher.json')
        $safeLaunch=$r.Created -and $r.StdioValidated -and $r.HandleListCount -eq 3 -and $r.HostStdioClosed -and $r.TokenVerified -and $r.Assigned -and $r.Resumed -and $r.Drained -and $r.CleanupConfirmed -and $null -eq $r.Failure
        $outsideUnchanged=[IO.File]::ReadAllText((Join-Path $outside 'canary.txt')) -ceq 'synthetic-outside-canary'
        $outsideWriteAbsent=-not (Test-Path -LiteralPath (Join-Path $outside 'probe-write.txt'))
        $row.outside_bytes_unchanged=$outsideUnchanged;$row.outside_write_absent=$outsideWriteAbsent
        if($kind -eq 'reference') {
            $pre=Test-ExactReceipt (Join-Path $run 'pre-network.txt') @('token=true','inside=true','outside_read=true','outside_write=true')
            $full=Test-ExactReceipt (Join-Path $run 'receipt.txt') $allTrue
            $referenceValid=$safeLaunch -and $pre -and $outsideUnchanged -and $outsideWriteAbsent -and ($r.Exit -eq 15107 -or ($r.Exit -eq 0 -and $full))
            $row.reference_route_valid=$referenceValid;$row.parent_fixture_canaries_passed=$pre
            $row.status=if($r.Exit -eq 15107){'winsock_initialization_failed_10107'}elseif($r.Exit -eq 0 -and $full){'native_five_assertions_passed'}else{'matched_reference_setup_or_assertion_failed'}
            $row.network_denial_proven=$safeLaunch -and $r.Exit -eq 0 -and $full
        } else {
            $output=if(Test-Path -LiteralPath (Join-Path $run 'stdout.txt')){[IO.File]::ReadAllText((Join-Path $run 'stdout.txt'))}else{''}
            $mutation=if(Test-Path -LiteralPath (Join-Path $run 'mutation.txt')){[IO.File]::ReadAllText((Join-Path $run 'mutation.txt'))}else{''}
            $entry=if(Test-Path -LiteralPath (Join-Path $run 'script-entry.txt')){[IO.File]::ReadAllText((Join-Path $run 'script-entry.txt'))}else{''}
            $row.script_entry_observed=$entry.Trim() -ceq 'runtime-entered'
            $row.exit_hex=$r.Exit.ToString('X8')
            $startupStatuses=@{'C0000135'='STATUS_DLL_NOT_FOUND';'C0000142'='STATUS_DLL_INIT_FAILED';'C000007B'='STATUS_INVALID_IMAGE_FORMAT'}
            $row.known_startup_status=$startupStatuses[$row.exit_hex]
            $row.output_ok=$output.Trim() -ceq 'runtime-ok';$row.mutation_ok=$mutation.Trim() -ceq 'runtime-ok'
            $row.operation_completed=$safeLaunch -and $row.script_entry_observed -and $row.output_ok -and $row.mutation_ok
            $row.positive_passed=$row.operation_completed -and $r.Exit -eq 0 -and $outsideUnchanged -and $outsideWriteAbsent
            $row.runtime_outside_read_observed=$false
            if($kind -eq 'cmd') {
                $row.runtime_canary_classification='cmd_errorlevel_is_not_raw_denial_evidence'
                if(Test-Path -LiteralPath (Join-Path $run 'outside-read.txt')) {
                    $row.runtime_outside_read_observed=[IO.File]::ReadAllText((Join-Path $run 'outside-read.txt')).Contains('synthetic-outside-canary')
                }
            }
            else {
                $expected=if($kind -eq 'node'){@('read=EACCES','write=EACCES')}else{@('read_type=System.UnauthorizedAccessException','read_hresult=-2147024891','write_type=System.UnauthorizedAccessException','write_hresult=-2147024891')}
                $denied=Test-ExactReceipt (Join-Path $run 'runtime-canary.txt') $expected
                $row.runtime_canary_classification=if($denied){'exact_runtime_access_denied'}else{'missing_or_other_runtime_error'}
                $row.positive_passed=$row.positive_passed -and $denied
                if(Test-Path -LiteralPath (Join-Path $run 'runtime-canary.txt')) {
                    $canaryLines=@(Get-Content -LiteralPath (Join-Path $run 'runtime-canary.txt'))
                    $row.runtime_outside_read_observed=($canaryLines -ccontains 'read=unexpected_success') -or ($canaryLines -ccontains 'read_type=success')
                }
            }
            $row.positive_passed=$row.positive_passed -and -not $row.runtime_outside_read_observed
            $row.status=if(-not $r.Created){'direct_creation_or_preparation_failed'}elseif(-not $r.Resumed){'suspended_target_verification_failed'}elseif($r.Wait -eq 258){'deadline_exceeded'}elseif(-not $row.script_entry_observed){
                if($null -ne $row.known_startup_status){'known_startup_status_without_script_entry'}else{'no_script_entry_evidence_inconclusive'}
            }elseif(-not $row.operation_completed){'user_code_positive_operation_failed'}elseif($row.runtime_canary_classification -eq 'missing_or_other_runtime_error'){'positive_operation_completed_canary_unproven'}elseif($r.Exit -ne 0){'positive_operation_completed_nonzero_exit'}elseif(-not $row.positive_passed){'positive_operation_completed_boundary_failed'}else{'positive_operation_completed'}
        }
        $outcomes+=@($row);$outcomes | ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'direct-matrix.json')
        if(-not $r.CleanupConfirmed -or (Test-Path -LiteralPath (Join-Path $run 'cleanup-uncertain.txt'))) {throw 'direct recovery state uncertain; owned resources retained'}
        if(-not $outsideUnchanged -or -not $outsideWriteAbsent -or ($kind -ne 'reference' -and $row.runtime_outside_read_observed)) {throw 'direct runtime outside canary violated'}
    }
    @{not_covered=@('python','npm.cmd','git','nested_child_support','ConPTY','production_integration');original_nested_required_rows=20;full_release_scope_unchanged=$true} |
        ConvertTo-Json | Set-Content (Join-Path $evidencePath 'coverage-limits.json')
    if($outcomes.Count -ne 5 -or -not $referenceValid -or @($outcomes | Where-Object {$_.case -ne 'broker-direct-reference' -and -not $_.positive_passed}).Count) {
        throw 'one or more required direct observations failed; retained original gates remain independent'
    }
} finally {
    $listener.Stop()
    if(@(Get-ChildItem -LiteralPath $root -Filter cleanup-uncertain.txt -Recurse -File).Count -eq 0) {Remove-Item -LiteralPath $root -Recurse -Force}
}
