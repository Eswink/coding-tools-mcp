param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Payload,[Parameter(Mandatory=$true)][string]$Evidence,[Parameter(Mandatory=$true)][string]$Foundation)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot '../windows-lpac-runtime/metadata.ps1')
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub Windows diagnostic only'}
$fixturePath=(Resolve-Path -LiteralPath $Fixture).Path
if([IO.Path]::GetFileName($fixturePath) -ne 'windows_sandbox_fixture.exe') {throw 'unchanged native reference required'}
$payloadPath=(Resolve-Path -LiteralPath $Payload).Path
$binaryManifest=Join-Path (Split-Path ([IO.Path]::GetFullPath($Evidence))) 'fixture-binaries-sha256.txt'
$nativeHashes=@(Get-Content -LiteralPath $binaryManifest | Where-Object {$_ -match '^([0-9A-Fa-f]{64}) windows_sandbox_fixture[.]exe$'} | ForEach-Object {$_.Split(' ')[0].ToLowerInvariant()})
$actualNativeHash=(Get-FileHash -LiteralPath $fixturePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($nativeHashes.Count -ne 1 -or $nativeHashes[0] -cne $actualNativeHash) {throw 'same-run native binary manifest mismatch'}
$evidencePath=[IO.Path]::GetFullPath($Evidence)
function Test-ExactPilotPremise([string]$Path,[string[]]$Expected) {
    if(-not (Test-Path -LiteralPath $Path -PathType Leaf)) {return $false}
    $lines=@(Get-Content -LiteralPath $Path)
    if($lines.Count -ne $Expected.Count) {return $false}
    foreach($line in $Expected) {if(@($lines | Where-Object {$_ -ceq $line}).Count -ne 1) {return $false}}
    return $true
}
$foundationValid=(Test-ExactPilotPremise (Join-Path $Foundation 'control-receipt.txt') @('token=true','inside=true','outside_read=true','outside_write=true','network=true')) -and
    (Test-ExactPilotPremise (Join-Path $Foundation 'mode-2-ordinary-appcontainer-receipt.txt') @('token=true','inside=true','outside_read=false','outside_write=true','network=true'))
if(-not $foundationValid) {throw 'retained live/ordinary native foundation missing or invalid'}
$cmdDebugSources=@((Join-Path $PSScriptRoot '../windows-cmd-debugger-observation/CmdDebugNative.cs'),(Join-Path $PSScriptRoot '../windows-cmd-debugger-observation/CmdDebugSession.cs'))
Add-Type -Path (@(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' -File | ForEach-Object {$_.FullName})+$cmdDebugSources)
$selectedParent=[BrokerDirectLauncher]::ResolvePilotSelectedPath()
# Repeated metadata-only guard. Hidden markers, wrong types, links and scan errors fail closed.
function Assert-PilotRecoveryScope([string[]]$Allowed) {
    if($Allowed.Count -gt 2) {throw 'only current run/case journals may be recognized'}
    $allow=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach($path in $Allowed) {
        $full=[IO.Path]::GetFullPath($path)
        if(-not $allow.Add($full)) {throw 'duplicate allowed journal path'}
        $item=Get-Item -LiteralPath $full -Force -ErrorAction Stop
        if($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or $item.Name -ine 'cleanup-uncertain.txt') {throw 'allowed journal must remain an ordinary file'}
    }
    $scopes=@((Split-Path $evidencePath))
    $roots=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $entries=0
    foreach($scanRoot in @($env:RUNNER_TEMP,[IO.Path]::GetTempPath(),$selectedParent)) {
        $exactRoot=[IO.Path]::GetFullPath($scanRoot)
        if(-not $roots.Add($exactRoot)) {continue}
        $rootItem=Get-Item -LiteralPath $exactRoot -Force -ErrorAction Stop
        if(-not $rootItem.PSIsContainer -or ($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'recovery root changed'}
        $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach($candidate in @(Get-ChildItem -LiteralPath $exactRoot -Force -ErrorAction Stop)) {
            $entries++;if($entries -gt 100000) {throw 'recovery scan entry bound exceeded'}
            if(-not $names.Add($candidate.Name)) {throw 'duplicate recovery root entry'}
            if(($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'recovery root refuses reparse entries'}
            if($candidate.Name -ieq 'cleanup-uncertain.txt') {throw 'direct unknown recovery marker prohibits pilot'}
            if($candidate.Name -like 'ctm-native-*' -or $candidate.Name -like 'ctm runtime-*' -or $candidate.Name -like 'ctm-direct-*' -or $candidate.Name -like 'ctm-qualification-*') {
                if(-not $candidate.PSIsContainer) {throw 'owned recovery scope has unexpected type'}
                $scopes+=@($candidate.FullName)
            }
        }
    }
    $stack=[Collections.Generic.Stack[object]]::new();$seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach($scope in $scopes) {$stack.Push(@{path=[IO.Path]::GetFullPath($scope);depth=0})}
    while($stack.Count -gt 0) {
        $next=$stack.Pop();if(-not $seen.Add($next.path)) {continue}
        if($next.depth -gt 32) {throw 'recovery scan depth bound exceeded'}
        $directory=Get-Item -LiteralPath $next.path -Force -ErrorAction Stop
        if(-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'recovery scan directory changed'}
        $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach($item in @(Get-ChildItem -LiteralPath $next.path -Force -ErrorAction Stop)) {
            if(-not $names.Add($item.Name)) {throw 'duplicate recovery scope entry'}
            $entries++;if($entries -gt 100000) {throw 'recovery scan entry bound exceeded'}
            if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'recovery scan refuses reparse entries'}
            if($item.Name -ieq 'cleanup-uncertain.txt' -and ($item.PSIsContainer -or -not $allow.Contains($item.FullName))) {throw 'unknown or prior recovery marker prohibits pilot'}
            if($item.PSIsContainer) {$stack.Push(@{path=$item.FullName;depth=($next.depth+1)})}
        }
    }
}
$markerGuard=[Action[string[]]] {param($allowed) Assert-PilotRecoveryScope -Allowed $allowed}
$preflight=[BrokerDirectLauncher]::CheckSelectedParentRecovery($selectedParent,$markerGuard,[string[]]@())
# Ordinary evidence output in the existing evidence area; no candidate allocation.
$preflightPath=Join-Path (Split-Path $evidencePath) 'selected-parent-preflight.json'
$preflightBytes=[Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $preflight -Depth 24 -Compress))
if($preflightBytes.Length -gt 1048576) {throw 'selected parent preflight evidence bound exceeded'}
$preflightStream=$null
try {
    $preflightStream=[IO.FileStream]::new($preflightPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $preflightStream.Write($preflightBytes,0,$preflightBytes.Length);$preflightStream.Flush($true)
} finally {if($null -ne $preflightStream) {$owned=$preflightStream;$preflightStream=$null;$owned.Dispose()}}
if($null -ne $preflight.Failure -or -not $preflight.FinalScanConfirmed -or -not $preflight.CloseConfirmed) {throw 'selected parent initial recovery preflight failed'}
if(Test-Path -LiteralPath $evidencePath) {throw 'pilot evidence directory must be new'}
New-Item -ItemType Directory -Path $evidencePath | Out-Null
$inventory=@(Read-RuntimeInventory (Get-Content -Raw -LiteralPath (Join-Path (Split-Path $evidencePath) 'runtime/runtime-inventory.json')))
$ready=@()
foreach($kind in @('node','cmd','powershell','pwsh')) {
    $records=@($inventory | Where-Object {$_.runtime -ceq $kind})
    if($records.Count -eq 1 -and $records[0].ready -eq $true) {$ready+=@($kind)}
}
@{selected_parent_policy='localappdata_temp_ci_v1';selected_parent=$selectedParent;runner_temp_control=$env:RUNNER_TEMP;policy='accesscheck_signature_v1_ci';foundation_valid=$foundationValid;network_denial_proven=$false;runtime_inventory=$inventory;ready=$ready;native_fixture_sha256=$actualNativeHash} |
    ConvertTo-Json -Depth 12 | Set-Content (Join-Path $evidencePath 'preparation-premise.json')
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
try {
    $listener.Start();$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
    $serializeCase=[Func[BrokerDirectLauncher+PilotCaseReceipt,string]] {param($row) ConvertTo-Json -InputObject $row -Depth 20 -Compress}
    $serializeRun=[Func[BrokerDirectLauncher+PilotRunReceipt,string]] {param($row) ConvertTo-Json -InputObject $row -Depth 24 -Compress}
    $result=[BrokerDirectLauncher]::RunPilot($fixturePath,$payloadPath,$evidencePath,$selectedParent,$port,[string[]]$ready,$markerGuard,$serializeCase,$serializeRun)
    # RunPilot persisted terminal evidence before its final journal rename. No writes here.
    if(-not $result.AllFourOfflineCasesPassed) {throw 'one or more required offline pilot observations failed; original gates remain independent'}
    if(-not $result.CmdSentinelObservationPassed) {throw 'required additive cmd exit23 observation failed; original verdicts remain independent'}
    if(-not $result.CmdBatchObservationPassed) {throw 'required minimal cmd batch observation failed; prior verdicts remain independent'}
    if(-not $result.CmdCwdRawObservationMatched) {throw 'required cmd cwd raw observation did not match; committed artifact acceptance is separate'}
    if(-not $result.CmdReadRawObservationMatched) {throw 'required cmd read raw observation did not match; committed artifact acceptance is separate'}
    if(-not $result.CmdRelativeBatchRawObservationMatched) {throw 'required relative cmd batch raw observation did not match; committed artifact acceptance is separate'}
} finally {
    $listener.Stop()
    # Never delete profiles, roots or recovery journals in a PowerShell finally block.
}
