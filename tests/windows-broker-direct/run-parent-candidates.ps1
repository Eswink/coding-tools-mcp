param([Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub Windows diagnostic only'}
# The workflow already created this evidence area. This observer creates no directory.
$evidencePath=[IO.Path]::GetFullPath($Evidence)
$directory=Get-Item -LiteralPath $evidencePath -Force -ErrorAction Stop
if(-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'existing regular evidence directory required'}
Add-Type -Path @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.cs' -File | ForEach-Object {$_.FullName})
$result=[BrokerDirectLauncher]::ObserveParentCandidates($env:RUNNER_TEMP)
$packet=@{source_commit=$env:GITHUB_SHA;observation_only=$true;selected_for_execution=$false;result=$result}
$json=ConvertTo-Json -InputObject $packet -Depth 24 -Compress
$bytes=[Text.UTF8Encoding]::new($false,$true).GetBytes($json+"`n")
if($bytes.Length -gt 1048576) {throw 'parent observation evidence exceeds hard byte limit'}
$output=Join-Path $evidencePath 'parent-candidates.json'
$stream=$null
try {
    $stream=[IO.FileStream]::new($output,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $stream.Write($bytes,0,$bytes.Length)
    $stream.Flush($true)
} finally {
    # Transfer once: a failed Dispose is uncertain and is never retried.
    $owned=$stream;$stream=$null
    if($null -ne $owned) {$owned.Dispose()}
}
Write-Output 'parent-candidate evidence flush and close confirmed'
if(-not $result.ObservationCompleted -or -not $result.CleanupConfirmed) {throw 'parent observation incomplete or resource cleanup uncertain'}
# A candidate trust result never selects a parent or invokes the pilot.
