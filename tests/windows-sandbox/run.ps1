param([Parameter(Mandatory=$true)][string]$Fixture,[Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# This script must run in Windows PowerShell5.1 for the framework ACL APIs.
if ($env:OS -ne 'Windows_NT') { throw 'Windows native test required' }
$fixturePath=(Resolve-Path $Fixture).Path
$evidencePath=[IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $evidencePath -Force | Out-Null
$root=Join-Path ([IO.Path]::GetTempPath()) ('ctm-native-'+[guid]::NewGuid().ToString('N'))
$control=Join-Path $root 'control';$outside=Join-Path $root 'outside';$run=Join-Path $root 'run'
New-Item -ItemType Directory -Path $control,$outside,$run -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $outside 'canary.txt'),'synthetic-outside-canary')
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$listener.Start()
$port=([Net.IPEndPoint]$listener.LocalEndpoint).Port
try {
    Add-Type -Path (Join-Path $PSScriptRoot 'NativeLauncher.cs')
    # Failure-first control proves real canary/network availability without isolation.
    & $fixturePath control $control $outside ('127.0.0.1:'+ $port)
    if ($LASTEXITCODE -ne 0) { throw 'unsandboxed control failed; no valid red witness' }
    Copy-Item (Join-Path $control 'receipt.txt') (Join-Path $evidencePath 'control-receipt.txt')
    Remove-Item (Join-Path $outside 'probe-write.txt')
    # Controlled weakening: omit only the documented LPAC attribute. The exact
    # outside-read assertion must fail on the AAP-readable synthetic canary.
    $ordinary=[LpacFixtureLauncher]::Run($fixturePath,$run,$outside,$port,$false)
    Copy-Item (Join-Path $run 'ordinary-appcontainer-receipt.txt') (Join-Path $evidencePath 'ordinary-appcontainer-receipt.txt')
    $ordinaryLines=Get-Content (Join-Path $evidencePath 'ordinary-appcontainer-receipt.txt')
    if($ordinary -ne 20 -or $ordinaryLines.Count -ne 5 -or
        @($ordinaryLines | Where-Object {$_ -eq 'outside_read=false'}).Count -ne 1 -or
        @($ordinaryLines | Where-Object {$_ -notmatch '^(token|inside|outside_write|network)=true$|^outside_read=false$'}).Count) {
        throw 'ordinary AppContainer mutation did not reproduce the exact LPAC read boundary'
    }
    $exit=[LpacFixtureLauncher]::Run($fixturePath,$run,$outside,$port,$true)
    if (Test-Path (Join-Path $run 'sandbox-receipt.txt')) {
        Copy-Item (Join-Path $run 'sandbox-receipt.txt') (Join-Path $evidencePath 'sandbox-receipt.txt')
    }
    if ($exit -ne 0) { throw "native containment assertions failed: $exit" }
    if (Test-Path (Join-Path $outside 'probe-write.txt')) { throw 'outside canary was written' }
    if ([IO.File]::ReadAllText((Join-Path $outside 'canary.txt')) -ne 'synthetic-outside-canary') { throw 'outside canary mutated' }
    foreach($name in @('control-receipt.txt','sandbox-receipt.txt')) {
        $lines=Get-Content (Join-Path $evidencePath $name)
        if($lines.Count -ne 5 -or @($lines | Where-Object {$_ -notmatch '^(token|inside|outside_read|outside_write|network)=true$'}).Count) {
            throw 'incomplete/failed fixed-case receipt'
        }
    }
    'NATIVE_LPAC_FOUNDATION_PASS:5 fixed assertions; production integration incomplete' | Set-Content (Join-Path $evidencePath 'result.txt')
} finally {
    $listener.Stop()
    # root is exclusively generated above; no user data or runtime journals.
    if (-not (Test-Path (Join-Path $run 'cleanup-uncertain.txt'))) {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}
