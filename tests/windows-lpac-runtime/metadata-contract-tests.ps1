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
'METADATA_CONTRACT_PASS: scalar source, flat independent records, retained failure, invalid/duplicate rejection'
