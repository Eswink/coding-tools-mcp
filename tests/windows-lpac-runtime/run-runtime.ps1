param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Payload,[Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'metadata.ps1')
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub-hosted Windows diagnostic only'}
$fixturePath=(Resolve-Path $Fixture).Path
$payloadPath=(Resolve-Path $Payload).Path
$evidencePath=[IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$root=Join-Path $env:RUNNER_TEMP ('ctm runtime-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$outcomes=@()
$cases=[ordered]@{'python-budget'='python';'python-workspace'='python';'node-workspace'='node';'npm-cmd'='node';'git-local'='git';'cmd-workspace'='cmd';'powershell-workspace'='powershell';'pwsh-workspace'='pwsh'}
$eofCases=[ordered]@{'node-workspace-private-eof'='node';'npm-cmd-private-eof'='node';'git-local-private-eof'='git';'cmd-workspace-private-eof'='cmd';'powershell-workspace-private-eof'='powershell';'pwsh-workspace-private-eof'='pwsh'}
foreach($name in $eofCases.Keys) {$cases.Add($name,$eofCases[$name])}
$noWindowCases=[ordered]@{'node-workspace-private-eof-no-window'='node';'npm-cmd-private-eof-no-window'='node';'git-local-private-eof-no-window'='git';'cmd-workspace-private-eof-no-window'='cmd';'powershell-workspace-private-eof-no-window'='powershell';'pwsh-workspace-private-eof-no-window'='pwsh'}
foreach($name in $noWindowCases.Keys) {$cases.Add($name,$noWindowCases[$name])}
if($cases.Count -ne 20) {throw 'exact twenty required diagnostic rows expected'}
$inventory=@(Read-RuntimeInventory (Get-Content -Raw (Join-Path $evidencePath 'runtime-inventory.json')))
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
try {
    Add-Type -Path (Join-Path $PSScriptRoot 'RuntimeLauncher.cs')
    foreach($case in $cases.Keys) {
        $caseRoot=Join-Path $root $case
        $outside=Join-Path $caseRoot 'outside'
        $bundle=Join-Path $caseRoot 'bundle'
        $run=Join-Path $caseRoot 'run'
        $caseEvidence=Join-Path $evidencePath $case
        New-Item -ItemType Directory -Path $outside,$bundle,$run,$caseEvidence | Out-Null
        $required=@($cases[$case],'cmd') | Select-Object -Unique
        if($case -eq 'npm-cmd' -or $case -eq 'npm-cmd-private-eof' -or $case -eq 'npm-cmd-private-eof-no-window') {$required+=@('npm')}
        $preparationFailures=@()
        foreach($requiredName in $required) {
            $records=@($inventory | Where-Object {$_.runtime -eq $requiredName})
            if($records.Count -ne 1 -or $records[0].ready -ne $true) {$preparationFailures+=@{runtime=$requiredName;records=$records}}
        }
        if($preparationFailures.Count) {
            $row=@{case=$case;offline_passed=$false;preparation_failed=$true;preparation_failures=$preparationFailures;runtime=$null;native_classification='not_started_preparation_failed';network_denial_proven=$false}
            $row | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $caseEvidence 'preparation-failure.json')
            $outcomes+=@($row)
            $outcomes | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $evidencePath 'runtime-matrix.json')
            continue
        }
        [IO.File]::WriteAllText((Join-Path $outside 'canary.txt'),'synthetic-outside-canary')
        [IO.File]::WriteAllText((Join-Path $bundle 'case.txt'),$case)
        Copy-Item -LiteralPath (Join-Path $payloadPath 'cmd.exe') -Destination (Join-Path $bundle 'cmd.exe')
        if($cases[$case] -ne 'cmd') {
            New-Item -ItemType Directory -Path (Join-Path $bundle 'runtime') | Out-Null
            Copy-Item -Path (Join-Path $payloadPath ($cases[$case]+'\*')) -Destination (Join-Path $bundle 'runtime') -Recurse -Force
        }
        $nativeExit=$null;$nativeFailure=$null;$numbers=@();$runtime=$null;$filesystem=$false;$lifecycle=$null;$nativeViolation=$false
        try {
            # mode 1 is the retained fixed OS-path environment. LPAC=true is
            # mandatory in the adapter; no ordinary/unsandboxed runtime warm-up.
            $nativeExit=[LpacRuntimeLauncher]::Run($fixturePath,$run,$outside,$port,$true,1,$bundle)
        } catch {
            $failure=$_.Exception.GetBaseException()
            $nativeFailure=$failure.GetType().Name
            $numbers=@([regex]::Matches($failure.Message,'win32=\d+|exit=\d+|hex=[0-9A-F]+') | ForEach-Object {$_.Value})
        } finally {
            Get-ChildItem $run -File | Where-Object Name -match '^(sandbox-(receipt|pre-network|runtime-checks)\.txt|runtime-(result\.json|stdout\.txt|stderr\.txt)|launcher-lifecycle\.json|cleanup-uncertain\.txt)$' |
                ForEach-Object {Copy-Item $_.FullName (Join-Path $caseEvidence $_.Name)}
        }
        if(Test-Path (Join-Path $run 'sandbox-pre-network.txt')) {
            $lines=@(Get-Content (Join-Path $run 'sandbox-pre-network.txt'))
            $filesystem=$lines.Count -eq 4 -and @($lines | Where-Object {$_ -notmatch '^(token|inside|outside_read|outside_write)=true$'}).Count -eq 0
        }
        if(Test-Path (Join-Path $run 'runtime-result.json')) {$runtime=Get-Content -Raw (Join-Path $run 'runtime-result.json') | ConvertFrom-Json}
        if(Test-Path (Join-Path $run 'launcher-lifecycle.json')) {$lifecycle=Get-Content -Raw (Join-Path $run 'launcher-lifecycle.json') | ConvertFrom-Json}
        if(Test-Path (Join-Path $run 'sandbox-receipt.txt')) {
            $receipt=@(Get-Content (Join-Path $run 'sandbox-receipt.txt'))
            $nativeViolation=$receipt.Count -ne 5 -or @($receipt | Where-Object {$_ -notmatch '^(token|inside|outside_read|outside_write|network)=true$'}).Count -gt 0
        }
        $nativeClass=if($numbers -contains 'exit=15107') {'winsock_initialization_failed_10107'} elseif($null -ne $lifecycle -and $lifecycle.fixture_wait -eq 258) {'native_fixture_deadline_exceeded'} elseif($nativeExit -eq 0 -and $null -eq $nativeFailure) {'native_five_assertions_passed'} else {'native_setup_or_assertion_failed'}
        $passed=$filesystem -and $null -ne $runtime -and $runtime.passed -eq $true -and $null -ne $lifecycle -and $lifecycle.job_drained -eq $true
        $outcomes+=@{case=$case;offline_passed=$passed;parent_fixture_canaries_passed=$filesystem;runtime=$runtime;lifecycle=$lifecycle;native_exit=$nativeExit;native_failure=$nativeFailure;numeric_diagnosis=$numbers;native_classification=$nativeClass;native_assertion_violation=$nativeViolation;network_denial_proven=($nativeClass -eq 'native_five_assertions_passed' -and -not $nativeViolation)}
        $outcomes | ConvertTo-Json -Depth 12 | Set-Content (Join-Path $evidencePath 'runtime-matrix.json')
        if(Test-Path (Join-Path $run 'cleanup-uncertain.txt')) {throw 'owned process-tree cleanup unconfirmed; resources retained'}
        if($nativeViolation) {throw 'native containment assertion failed after runtime; stop this matrix'}
        if(Test-Path (Join-Path $outside 'probe-write.txt')) {throw 'outside canary was written'}
        if([IO.File]::ReadAllText((Join-Path $outside 'canary.txt')) -ne 'synthetic-outside-canary') {throw 'outside canary mutated'}
    }
    if($outcomes.Count -ne $cases.Count -or @($outcomes | Where-Object {-not $_.offline_passed}).Count) {throw 'one or more required preparation or offline runtime contracts failed; see per-case raw evidence'}
    'Offline runtime observations passed. This is not production integration or network-isolation acceptance.' | Set-Content (Join-Path $evidencePath 'offline-result.txt')
} finally {
    $listener.Stop()
    if(@(Get-ChildItem $root -Filter cleanup-uncertain.txt -Recurse -File).Count -eq 0) {Remove-Item -LiteralPath $root -Recurse -Force}
}
