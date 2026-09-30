param([Parameter(Mandatory=$true)][string]$Payload,[Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub-hosted Windows diagnostic only'}
if(Test-Path -LiteralPath $Payload) {throw 'payload must be new'}
New-Item -ItemType Directory -Path $Payload,$Evidence -Force | Out-Null
$inventory=@()
$roots=@{
    python=(Split-Path (Get-Command python.exe -CommandType Application).Source)
    node=(Split-Path (Get-Command node.exe -CommandType Application).Source)
    git=(Split-Path (Split-Path (Get-Command git.exe -CommandType Application).Source))
    powershell=(Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0')
    pwsh=(Split-Path (Get-Command pwsh.exe -CommandType Application).Source)
}
$executables=@{python='python.exe';node='node.exe';git='cmd\git.exe';powershell='powershell.exe';pwsh='pwsh.exe'}
# Copy without running any runtime, installer, package manager or version command.
# Existing host installations and ACLs are read-only; only new fixture copies
# later receive the retained launcher's private package ACLs.
foreach($name in @('python','node','git','powershell','pwsh')) {
    $source=$roots[$name]
    if(-not (Test-Path (Join-Path $source $executables[$name]))) {throw "fixed runtime unavailable: $name"}
    $links=@(Get-ChildItem -LiteralPath $source -Recurse -Force | Where-Object {($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0})
    if($links.Count) {throw "runtime copy contains reparse points: $name"}
    $dest=Join-Path $Payload $name
    New-Item -ItemType Directory -Path $dest | Out-Null
    Copy-Item -Path (Join-Path $source '*') -Destination $dest -Recurse -Force
    $binary=Get-Item (Join-Path $dest $executables[$name])
    $inventory+=@{runtime=$name;source_executable=(Join-Path $source $executables[$name]);relative_executable=$executables[$name];file_version=$binary.VersionInfo.FileVersion;product_version=$binary.VersionInfo.ProductVersion;sha256=(Get-FileHash $binary.FullName -Algorithm SHA256).Hash}
}
if(-not (Test-Path (Join-Path $Payload 'node\npm.cmd'))) {throw 'actual npm.cmd missing from copied Node distribution'}
$npm=Get-Content -Raw (Join-Path $Payload 'node\node_modules\npm\package.json') | ConvertFrom-Json
$inventory+=@{runtime='npm';version=$npm.version;relative_executable='node\npm.cmd';sha256=(Get-FileHash (Join-Path $Payload 'node\npm.cmd') -Algorithm SHA256).Hash}
Copy-Item -LiteralPath (Join-Path $env:SystemRoot 'System32\cmd.exe') -Destination (Join-Path $Payload 'cmd.exe')
$cmd=Get-Item (Join-Path $Payload 'cmd.exe')
$inventory+=@{runtime='cmd';file_version=$cmd.VersionInfo.FileVersion;product_version=$cmd.VersionInfo.ProductVersion;sha256=(Get-FileHash $cmd.FullName -Algorithm SHA256).Hash}
$inventory | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Evidence 'runtime-inventory.json')
# Preserve complete copied-runtime identity, including standard libraries/shims.
$base=[IO.Path]::GetFullPath($Payload).TrimEnd('\')+'\'
Get-ChildItem -LiteralPath $Payload -File -Recurse | Sort-Object FullName | ForEach-Object {
    (Get-FileHash $_.FullName -Algorithm SHA256).Hash+' '+$_.FullName.Substring($base.Length)
} | Set-Content (Join-Path $Evidence 'runtime-copy-sha256.txt')
