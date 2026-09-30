param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'Windows native test required' }
$fixturePath=(Resolve-Path $Fixture).Path
$evidencePath=[IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$root=Join-Path ([IO.Path]::GetTempPath()) ('ctm-native-'+[guid]::NewGuid().ToString('N'))
$control=Join-Path $root 'control';$outside=Join-Path $root 'outside'
New-Item -ItemType Directory -Path $control,$outside -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $outside 'canary.txt'),'synthetic-outside-canary')
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
$outcomes=@()
try {
    Add-Type -Path (Join-Path $PSScriptRoot 'NativeLauncher.cs')
    & $fixturePath control $control $outside ('127.0.0.1:'+ $port)
    if ($LASTEXITCODE -ne 0) { throw 'unsandboxed control failed; no valid red witness' }
    Copy-Item (Join-Path $control 'receipt.txt') (Join-Path $evidencePath 'control-receipt.txt')
    Remove-Item (Join-Path $outside 'probe-write.txt')
    # Finite diagnostic factors only:0minimalOSenv,1fixedOSpaths,2same+headless.
    # No capabilities, profiles, ACLs, assertions or trusted-root rules differ.
    foreach($mode in @(0,1,2)) {
        $run=Join-Path $root ('mode-'+$mode)
        New-Item -ItemType Directory -Path $run | Out-Null
        $passed=$false;$reason='unknown_setup';$errorNumbers=@()
        try {
            $ordinary=[LpacFixtureLauncher]::Run($fixturePath,$run,$outside,$port,$false,$mode)
            $ordinaryLines=Get-Content (Join-Path $run 'ordinary-appcontainer-receipt.txt')
            if($ordinary -ne 20 -or $ordinaryLines.Count -ne 5 -or
                @($ordinaryLines | Where-Object {$_ -eq 'outside_read=false'}).Count -ne 1 -or
                @($ordinaryLines | Where-Object {$_ -notmatch '^(token|inside|outside_write|network)=true$|^outside_read=false$'}).Count) {
                throw 'ordinary AppContainer mutation did not reproduce the exact LPAC read boundary'
            }
            $exit=[LpacFixtureLauncher]::Run($fixturePath,$run,$outside,$port,$true,$mode)
            if ($exit -ne 0) { throw 'native containment assertions failed' }
            foreach($name in @('control-receipt.txt','sandbox-receipt.txt')) {
                $path=if($name -eq 'control-receipt.txt'){Join-Path $evidencePath $name}else{Join-Path $run $name}
                $lines=Get-Content $path
                if($lines.Count -ne 5 -or @($lines | Where-Object {$_ -notmatch '^(token|inside|outside_read|outside_write|network)=true$'}).Count) {
                    throw 'incomplete/failed fixed-case receipt'
                }
            }
            $passed=$true;$reason='exact_mutation_and_five_assertions_passed'
        } catch {
            $failure=$_.Exception.GetBaseException()
            $reason=$failure.GetType().Name
            $errorNumbers=@([regex]::Matches($failure.Message,'win32=\d+|exit=\d+|hex=[0-9A-F]+') | ForEach-Object {$_.Value})
        } finally {
            Get-ChildItem $run -File | Where-Object Name -match '^(sandbox|ordinary-appcontainer)-(receipt|pre-network|runtime-checks)\.txt$' |
                ForEach-Object {Copy-Item $_.FullName (Join-Path $evidencePath ('mode-'+$mode+'-'+$_.Name))}
        }
        $outcomes+=@{mode=$mode;passed=$passed;reason=$reason;numeric_diagnosis=$errorNumbers}
        $outcomes | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $evidencePath 'diagnostic-matrix.json')
        # Any containment escape or uncertain cleanup fails the entire matrix.
        if(Test-Path (Join-Path $run 'cleanup-uncertain.txt')) {throw 'owned cleanup unconfirmed'}
        if(Test-Path (Join-Path $outside 'probe-write.txt')) {throw 'outside canary was written'}
        if([IO.File]::ReadAllText((Join-Path $outside 'canary.txt')) -ne 'synthetic-outside-canary') {throw 'outside canary mutated'}
    }
    if(@($outcomes | Where-Object {$_.passed}).Count -eq 0) {throw 'all bounded native profiles failed; no isolation evidence'}
    'NATIVE_LPAC_FOUNDATION_PASS: see exact mode receipts; production integration incomplete' | Set-Content (Join-Path $evidencePath 'result.txt')
} finally {
    $listener.Stop()
    if(@(Get-ChildItem $root -Filter cleanup-uncertain.txt -Recurse -File).Count -eq 0) {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}
