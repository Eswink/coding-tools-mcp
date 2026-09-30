param([Parameter(Mandatory=$true)][string]$Payload,[Parameter(Mandatory=$true)][string]$Evidence)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot 'metadata.ps1')
if($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_OS -ne 'Windows') {throw 'GitHub-hosted Windows diagnostic only'}
if(Test-Path -LiteralPath $Payload) {throw 'payload must be new'}
New-Item -ItemType Directory -Path $Payload,$Evidence -Force | Out-Null
$inventory=@()
$executables=@{python='python.exe';node='node.exe';git='cmd\git.exe';powershell='powershell.exe';pwsh='pwsh.exe'}

function Get-ReparseMetadata([string]$Source) {
    $pending=[Collections.Generic.Stack[string]]::new()
    $pending.Push($Source)
    while($pending.Count) {
        $path=$pending.Pop()
        $item=Get-Item -LiteralPath $path -Force
        if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            # Read the link's metadata only; never recurse into or resolve target.
            $targetProperty=$item.PSObject.Properties['Target']
            $typeProperty=$item.PSObject.Properties['LinkType']
            @{path=$item.FullName;attributes=[string]$item.Attributes;link_type=$(if($null -ne $typeProperty){[string]$typeProperty.Value}else{$null});target=$(if($null -ne $targetProperty){@($targetProperty.Value)}else{@()})}
            continue
        }
        if($item.PSIsContainer) {
            # Deliberately no -Recurse: inspect each entry before descending.
            foreach($child in @(Get-ChildItem -LiteralPath $path -Force)) {$pending.Push($child.FullName)}
        }
    }
}

# Keep each required payload's failure as data so independent runtimes can run.
# The final matrix gate fails if ANY required payload or runtime row fails.
foreach($name in @('python','node','git','powershell','pwsh')) {
    $row=@{runtime=$name;ready=$false;source_executable=$null;source_root=$null;relative_executable=$executables[$name];reparse_points=@();reason=$null}
    if($name -eq 'python') {$row.setup_python_location=$env:pythonLocation}
    try {
        if($name -eq 'powershell') {
            $source=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0'
            $resolved=Join-Path $source 'powershell.exe'
        } else {
            $commandName=$executables[$name].Split('\')[-1]
            $candidates=@(Get-Command $commandName -CommandType Application)
            $row.source_candidates=@($candidates | ForEach-Object {$_.Source})
            $resolved=Select-ApplicationPath $candidates
            $source=Split-Path $resolved
            if($name -eq 'git') {$source=Split-Path $source}
        }
        $row.source_executable=$resolved;$row.source_root=$source
        $row.reparse_points=@(Get-ReparseMetadata $source)
        if($row.reparse_points.Count) {throw "runtime copy contains reparse points: $name"}
        if(-not (Test-Path (Join-Path $source $executables[$name]))) {throw "fixed runtime unavailable: $name"}
        $dest=Join-Path $Payload $name
        New-Item -ItemType Directory -Path $dest | Out-Null
        Copy-Item -Path (Join-Path $source '*') -Destination $dest -Recurse -Force
        $binary=Get-Item (Join-Path $dest $executables[$name])
        $row.file_version=$binary.VersionInfo.FileVersion;$row.product_version=$binary.VersionInfo.ProductVersion
        $row.sha256=(Get-FileHash $binary.FullName -Algorithm SHA256).Hash;$row.ready=$true
    } catch {
        $failure=$_.Exception.GetBaseException()
        $row.reason=$failure.Message;$row.error_type=$failure.GetType().Name
    }
    $inventory+=@($row)
    $inventory | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Evidence 'runtime-inventory.json')
}
$npmRow=@{runtime='npm';ready=$false;reason=$null;relative_executable='node\npm.cmd'}
try {
    if(@($inventory | Where-Object {$_.runtime -eq 'node' -and $_.ready}).Count -ne 1) {throw 'Node payload unavailable; npm remains required and failed'}
    if(-not (Test-Path (Join-Path $Payload 'node\npm.cmd'))) {throw 'actual npm.cmd missing from copied Node distribution'}
    $npm=Get-Content -Raw (Join-Path $Payload 'node\node_modules\npm\package.json') | ConvertFrom-Json
    $npmRow.version=$npm.version;$npmRow.sha256=(Get-FileHash (Join-Path $Payload 'node\npm.cmd') -Algorithm SHA256).Hash;$npmRow.ready=$true
} catch {$npmRow.reason=$_.Exception.GetBaseException().Message}
$inventory+=@($npmRow)
$cmdRow=@{runtime='cmd';ready=$false;reason=$null}
try {
    $cmdSource=Join-Path $env:SystemRoot 'System32\cmd.exe'
    $cmdRow.reparse_points=@(Get-ReparseMetadata $cmdSource)
    if($cmdRow.reparse_points.Count) {throw 'cmd source is a reparse point'}
    Copy-Item -LiteralPath $cmdSource -Destination (Join-Path $Payload 'cmd.exe')
    $cmd=Get-Item (Join-Path $Payload 'cmd.exe')
    $cmdRow.file_version=$cmd.VersionInfo.FileVersion;$cmdRow.product_version=$cmd.VersionInfo.ProductVersion
    $cmdRow.sha256=(Get-FileHash $cmd.FullName -Algorithm SHA256).Hash;$cmdRow.ready=$true
} catch {$cmdRow.reason=$_.Exception.GetBaseException().Message}
$inventory+=@($cmdRow)
$inventory | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Evidence 'runtime-inventory.json')
# Hash only the already validated disposable copies, never rejected targets.
$base=[IO.Path]::GetFullPath($Payload).TrimEnd('\')+'\'
Get-ChildItem -LiteralPath $Payload -File -Recurse | Sort-Object FullName | ForEach-Object {
    (Get-FileHash $_.FullName -Algorithm SHA256).Hash+' '+$_.FullName.Substring($base.Length)
} | Set-Content (Join-Path $Evidence 'runtime-copy-sha256.txt')
