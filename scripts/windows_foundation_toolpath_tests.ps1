# Ordinary management controls only: no Run-SourceCompile, fake CI identity, SUT restoration, owner or VM.
param([Parameter(Mandatory=$true)][string]$PythonExecutable,
    [Parameter(Mandatory=$true)][string]$ControlDirectory)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$Source = Join-Path $PSScriptRoot 'windows_foundation_source_compile.ps1'
$Tokens=$null; $Errors=$null
$Ast=[System.Management.Automation.Language.Parser]::ParseFile($Source,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count -ne 0) { throw 'Actual production PowerShell has parse errors.' }
$Names=@('Resolve-FoundationApplication','Invoke-CheckedCompiler')
foreach ($Name in $Names) {
    $Functions=@($Ast.FindAll({ param($Node) $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $Node.Name -ceq $Name },$true))
    if ($Functions.Count -ne 1) { throw "Actual production function missing/ambiguous: $Name" }
    . ([scriptblock]::Create($Functions[0].Extent.Text))
}
if (Test-Path -LiteralPath $ControlDirectory) { throw 'Controls need an owned fresh directory.' }
$Output=New-Item -ItemType Directory -Path $ControlDirectory
$Receipt=[ordered]@{runtime=@{}; commands=@()}
$ActualPython=$PythonExecutable
$Rows=[System.Collections.Generic.List[string]]::new()
function Expect-Rejection([string]$Name,[scriptblock]$Action,[string]$Expected) {
    try { & $Action; throw "Control unexpectedly accepted: $Name" }
    catch { if ($_.Exception.Message -notmatch $Expected) { throw }; $Rows.Add("PASS $Name") }
}
$Commands=@(Get-Command -Name git -CommandType Application -ErrorAction Stop)
if ($Commands.Count -lt 2) { throw 'Scalar control needs actual multiple native Git applications.' }
$Selected=Resolve-FoundationApplication 'git'
if ($Selected -isnot [string] -or $Selected -cne $Commands[0].Source) { throw 'First actual Git application scalar mismatch.' }
$Rows.Add('PASS actual-multiple-git-scalar-selection')
Invoke-CheckedCompiler 'git' @('--version') 'git-one.log' | Out-Null
Invoke-CheckedCompiler 'git' @('--version') 'git-two.log' | Out-Null
if ($Receipt.commands.Count -ne 2 -or $Receipt.runtime.git.path -isnot [string] -or
    $Receipt.runtime.git.sha256Before -isnot [string]) { throw 'Native invocation/receipt was not scalar.' }
$Rows.Add('PASS repeated-actual-git-and-scalar-identity')
$ResolvedPython=Resolve-FoundationApplication 'python'
if ($ResolvedPython -cne [System.IO.Path]::GetFullPath($ActualPython)) { throw 'Explicit actual interpreter differs.' }
Invoke-CheckedCompiler 'python' @('-c','print("ordinary-management-python")') 'python-real.log' | Out-Null
$Rows.Add('PASS explicit-real-python-payload')
$PythonExecutable=Join-Path $ControlDirectory 'missing-python'
Expect-Rejection 'missing-interpreter-no-path-fallback' { Resolve-FoundationApplication 'python' } 'not recognized|could not be found|does not exist'
$PythonExecutable='python'
Expect-Rejection 'relative-interpreter-no-path-fallback' { Resolve-FoundationApplication 'python' } 'explicit rooted'
$PythonExecutable=Join-Path $ControlDirectory 'Microsoft/WindowsApps/python.exe'
Expect-Rejection 'windowsapps-alias-denied' { Resolve-FoundationApplication 'python' } 'WindowsApps alias'
$PythonExecutable=$ActualPython
Expect-Rejection 'actual-nonzero-exit-preserved' { Invoke-CheckedCompiler 'python' @('-c','import sys; sys.exit(34)') 'python-exit34.log' } 'actual exit 34'
if ($Receipt.commands[-1].exitCode -ne 34) { throw 'Actual exit was lost.' }
$Rows.Add('PASS nonzero-receipt-preserved')
# Owned copies exercise hash/path checks before invoking altered bytes; never replace PATH/system tools.
$NativeSuffix=if ($IsWindows) { '.exe' } else { '' }
$CopyA=Join-Path $ControlDirectory ('python-copy-a'+$NativeSuffix); $CopyB=Join-Path $ControlDirectory ('python-copy-b'+$NativeSuffix)
Copy-Item -LiteralPath $ActualPython -Destination $CopyA; Copy-Item -LiteralPath $ActualPython -Destination $CopyB
if (-not $IsWindows) { & /bin/chmod 'u+x' $CopyA $CopyB; if ($LASTEXITCODE -ne 0) { throw 'Owned control mode setup failed.' } }
$PythonExecutable=$CopyA
$Receipt.runtime.python=[ordered]@{path=(Resolve-FoundationApplication 'python'); sha256Before=(Get-FileHash -LiteralPath $CopyA -Algorithm SHA256).Hash; sha256After=$null}
$PythonExecutable=$CopyB
Expect-Rejection 'selected-payload-path-drift-denied' { Invoke-CheckedCompiler 'python' @('-c','print("must-not-run")') 'path-drift.log' } 'changed before invocation'
$PythonExecutable=$CopyA
$Stream=[System.IO.File]::Open($CopyA,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write)
try { $Stream.WriteByte(0) } finally { $Stream.Dispose() }
Expect-Rejection 'selected-payload-byte-drift-denied' { Invoke-CheckedCompiler 'python' @('-c','print("must-not-run")') 'byte-drift.log' } 'changed before invocation'
if (Test-Path (Join-Path $ControlDirectory 'path-drift.log')) { throw 'Changed path invoked.' }
if (Test-Path (Join-Path $ControlDirectory 'byte-drift.log')) { throw 'Changed bytes invoked.' }
$Rows.Add('PASS drift-rejected-before-native-invocation')
$PythonExecutable=$ActualPython
$Receipt.runtime.python=[ordered]@{path=(Resolve-FoundationApplication 'python');
    sha256Before=(Get-FileHash -LiteralPath $ActualPython -Algorithm SHA256).Hash; sha256After=$null;
    payloadPath=$CopyB; payloadSha256Before=(Get-FileHash -LiteralPath $CopyB -Algorithm SHA256).Hash; payloadSha256After=$null}
$CommandCountBefore=$Receipt.commands.Count
$Stream=[System.IO.File]::Open($CopyB,[System.IO.FileMode]::Append,[System.IO.FileAccess]::Write)
try { $Stream.WriteByte(0) } finally { $Stream.Dispose() }
Expect-Rejection 'owned-native-payload-byte-drift-denied' { Invoke-CheckedCompiler 'python' @('-c','print("must-not-run")') 'actual-payload-drift.log' } 'Actual compiler payload bytes changed before invocation'
if ($Receipt.commands.Count -ne $CommandCountBefore -or
    (Test-Path (Join-Path $ControlDirectory 'actual-payload-drift.log'))) { throw 'Changed actual payload invoked or gained command/log receipt.' }
$Rows | ForEach-Object { Write-Output $_ }
Write-Output ('ORDINARY-CONTROLS ' + $Rows.Count + ' PASS; GitHub/compiler/native/install qualification NOTRUN')
