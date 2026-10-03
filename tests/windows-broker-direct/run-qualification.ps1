param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Evidence,[Parameter(Mandatory=$true)][string]$Foundation)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub-hosted Windows qualification only'}
$fixturePath=(Resolve-Path -LiteralPath $Fixture).Path
if([IO.Path]::GetFileName($fixturePath) -ne 'windows_sandbox_fixture.exe') {throw 'unchanged native reference required'}
$evidencePath=[IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
function Test-QualificationReceipt([string]$Path,[string[]]$Expected) {
    if(-not (Test-Path -LiteralPath $Path -PathType Leaf)) {return $false}
    $lines=@(Get-Content -LiteralPath $Path)
    if($lines.Count -ne $Expected.Count) {return $false}
    foreach($line in $Expected) {if(@($lines | Where-Object {$_ -ceq $line}).Count -ne 1) {return $false}}
    return $true
}
$foundationValid=(Test-QualificationReceipt (Join-Path $Foundation 'control-receipt.txt') @('token=true','inside=true','outside_read=true','outside_write=true','network=true')) -and
    (Test-QualificationReceipt (Join-Path $Foundation 'mode-2-ordinary-appcontainer-receipt.txt') @('token=true','inside=true','outside_read=false','outside_write=true','network=true'))
@{valid=$foundationValid;source='retained native live and ordinary-AppContainer witnesses'} | ConvertTo-Json | Set-Content (Join-Path $evidencePath 'foundation-premise.json')
if(-not $foundationValid) {throw 'retained native control premise missing or invalid'}
if(@(Get-ChildItem -LiteralPath (Split-Path $evidencePath) -Filter cleanup-uncertain.txt -Recurse -File).Count) {throw 'prior diagnostic recovery marker prohibits qualification'}
foreach($scanRoot in @($env:RUNNER_TEMP,[IO.Path]::GetTempPath() | Select-Object -Unique)) {
    foreach($candidate in @(Get-ChildItem -LiteralPath $scanRoot -Directory | Where-Object {$_.Name -like 'ctm-native-*' -or $_.Name -like 'ctm runtime-*' -or $_.Name -like 'ctm-direct-*' -or $_.Name -like 'ctm-qualification-*'})) {
        if(@(Get-ChildItem -LiteralPath $candidate.FullName -Filter cleanup-uncertain.txt -Recurse -File).Count) {throw 'prior owned recovery scope prohibits qualification'}
    }
}
$root=Join-Path $env:RUNNER_TEMP ('ctm-qualification-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start();$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
try {
    Add-Type -Path @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' -File | ForEach-Object {$_.FullName})
    $pair=$null;$failure=$null
    try {$pair=[BrokerDirectLauncher]::ObserveQualificationPair($fixturePath,$root,$port)}
    catch {$failure=$_.Exception.GetBaseException().Message}
    finally {
        foreach($kind in @('ordinary','lpac')) {
            $source=Join-Path $root $kind;$destination=Join-Path $evidencePath $kind
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            if(Test-Path -LiteralPath $source) {
                # Broker-owned top-level evidence only, never recurse into the retained child scope.
                Get-ChildItem -LiteralPath $source -File | ForEach-Object {Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $destination $_.Name)}
            }
        }
        if(Test-Path -LiteralPath (Join-Path $root 'cleanup-uncertain.txt')) {
            Copy-Item -LiteralPath (Join-Path $root 'cleanup-uncertain.txt') -Destination (Join-Path $evidencePath 'cleanup-uncertain.txt')
        }
    }
    if($null -eq $pair) {
        @{failure=$failure;qualification_matched=$false;verifier_adopted=$false;runtime_attempts=0} | ConvertTo-Json | Set-Content (Join-Path $evidencePath 'qualification-failure.json')
        throw 'paired collector did not return complete receipts; recovery retained'
    }
    $pair | ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'pair-receipt.json')
    $expected=@{ordinary=@{mixed=@(1,3);aap=@(1,1);arap=@(1,2);world=@(0,0)};lpac=@{mixed=@(1,2);aap=@(0,0);arap=@(1,2);world=@(0,0)}}
    $rows=@();$allMatched=$pair.ObservationsCollected -and $pair.IndividualResourceCleanupConfirmed -and $null -eq $pair.Failure
    foreach($kind in @('ordinary','lpac')) {
        $subjects=@($pair.Subjects | Where-Object {$_.Kind -ceq $kind})
        if($subjects.Count -ne 1) {$allMatched=$false;continue}
        $r=$subjects[0];$r | ConvertTo-Json -Depth 12 | Set-Content (Join-Path (Join-Path $evidencePath $kind) 'subject-receipt.json')
        $n=$r.Numbers
        $subjectReady=$r.Created -and $r.StdioValidated -and $r.HostStdioClosed -and $r.HandleListCount -eq 3 -and
            -not $r.Assigned -and -not $r.Resumed -and $r.Drained -and $n.ContainsKey('source_restricted_properties_verified') -and $n['source_restricted_properties_verified'] -eq 1 -and
            $n.ContainsKey('duplicate_valid') -and $n['duplicate_valid'] -eq 1 -and $n.ContainsKey('accesscheck_observer_completed') -and $n['accesscheck_observer_completed'] -eq 1
        foreach($label in @('mixed','aap','arap','world')) {
            $prefix='accesscheck_'+$label
            $keys=@(($prefix+'_api_success'),($prefix+'_access_status_raw'),($prefix+'_granted_access_raw'),($prefix+'_decision_valid'))
            $complete=@($keys | Where-Object {-not $n.ContainsKey($_)}).Count -eq 0
            $matched=$subjectReady -and $complete -and $n[$prefix+'_api_success'] -eq 1 -and $n[$prefix+'_decision_valid'] -eq 1 -and
                $n[$prefix+'_access_status_raw'] -eq $expected[$kind][$label][0] -and $n[$prefix+'_granted_access_raw'] -eq $expected[$kind][$label][1]
            $rows+=@{subject=$kind;descriptor=$label;observed_signature_matched=$matched;expected_access_status=$expected[$kind][$label][0];expected_mask=$expected[$kind][$label][1];raw=$n}
            $allMatched=$matched -and $allMatched
        }
        $outside=Join-Path (Join-Path $root $kind) 'outside'
        if(-not (Test-Path -LiteralPath (Join-Path $outside 'canary.txt')) -or [IO.File]::ReadAllText((Join-Path $outside 'canary.txt')) -cne 'synthetic-outside-canary' -or (Test-Path -LiteralPath (Join-Path $outside 'probe-write.txt'))) {$allMatched=$false}
    }
    $allMatched=$allMatched -and $rows.Count -eq 8 -and $pair.Subjects.Count -eq 2 -and $pair.ObservationOnly -and -not $pair.VerifierAdopted -and -not $pair.CleanupConfirmed -and $pair.RecoveryRetained
    @{qualification_matched=$allMatched;verifier_adopted=$false;runtime_attempts=0;network_denial_proven=$false;reference_resumes=0;rows=$rows;full_cleanup_confirmed=$false;recovery_retained=$true} |
        ConvertTo-Json -Depth 14 | Set-Content (Join-Path $evidencePath 'qualification-matrix.json')
    # A matching signature is candidate evidence, never a waived gate or full cleanup pass.
    throw 'observation-only qualification complete; verifier remains unadopted and recovery retained'
} finally {
    $listener.Stop()
    # Never clear a marker or delete these intentionally retained owned recovery scopes.
}
