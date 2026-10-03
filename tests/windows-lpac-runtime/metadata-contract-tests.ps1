$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'metadata.ps1')
$candidates=@([pscustomobject]@{Source='C:\fixture\python.exe'},[pscustomobject]@{Source='C:\unselected alias\python.exe'})
$selected=Select-ApplicationPath $candidates
if($selected -isnot [string] -or $selected -ne 'C:\fixture\python.exe') {throw 'first-PATH source selection must return one path'}
$json='[{"runtime":"python","ready":false},{"runtime":"cmd","ready":true},{"runtime":"pwsh","ready":true}]'
$records=@(Read-RuntimeInventory $json)
if($records.Count -ne 3) {throw 'inventory array was not explicitly flattened'}
$cmd=@($records | Where-Object {$_.runtime -eq 'cmd'})
if($cmd.Count -ne 1 -or $cmd[0].ready -ne $true) {throw 'ready record selection failed'}
$python=@($records | Where-Object {$_.runtime -eq 'python'})
if($python.Count -ne 1 -or $python[0].ready -ne $false) {throw 'failed record was lost or accepted'}
foreach($invalid in @('[{"runtime":"cmd","ready":true},{"runtime":"cmd","ready":false}]','[{"runtime":"cmd","ready":"true"}]','[[{"runtime":"cmd","ready":true}]]')) {
    $rejected=$false
    try {$null=@(Read-RuntimeInventory $invalid)} catch {$rejected=$true}
    if(-not $rejected) {throw 'malformed inventory was not rejected'}
}
$owned=Join-Path ([IO.Path]::GetTempPath()) ('ctm-hash-contract-'+[guid]::NewGuid().ToString('N'))
if(Test-Path -LiteralPath $owned) {throw 'hash contract directory must be new'}
[IO.Directory]::CreateDirectory($owned) | Out-Null
try {
    # Git's distribution has a real file named [.exe; it is not a glob.
    $literal=Join-Path $owned '[.exe'
    [IO.File]::WriteAllText($literal,'fixture',[Text.UTF8Encoding]::new($false))
    $hash=(Get-FileHash -LiteralPath $literal -Algorithm SHA256).Hash
    if($hash -ne 'f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d') {throw 'literal filename hash differs'}
} finally {[IO.Directory]::Delete($owned,$true)}
'METADATA_CONTRACT_PASS: scalar source, flat records, retained failure, invalid/duplicate rejection, literal filename hash'
