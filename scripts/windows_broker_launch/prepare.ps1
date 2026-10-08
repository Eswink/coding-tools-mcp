param([Parameter(Mandatory)][string]$RunRoot)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$evidence = Join-Path $RunRoot 'evidence'
$state = @{ schema = 1; built = $false; ran = $false; exit_code = $null; error = $null }
try {
    $root = [IO.Path]::GetFullPath($RunRoot)
    if ($root -ne $RunRoot -or $root -match '["%!\r\n&|<>^]') { throw 'Unsafe run-root syntax' }
    if (!(Test-Path -LiteralPath $evidence -PathType Container)) { throw 'Missing owned evidence directory' }
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (!(Test-Path -LiteralPath $vswhere)) { throw 'Installed vswhere unavailable; no setup permitted' }
    $vs = @(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)
    if ($LASTEXITCODE -ne 0 -or $vs.Count -ne 1) { throw 'Installed MSVC unavailable' }
    $vsdev = Join-Path $vs[0] 'Common7\Tools\VsDevCmd.bat'
    $cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $trusted = Join-Path $root 'trusted'
    $build = Join-Path $root 'build'
    foreach ($path in @($vsdev, $PSScriptRoot, $trusted, $build)) {
        if ($path -match '["%!\r\n&|<>^]') { throw 'Unsafe fixed-build path' }
    }
    New-Item -ItemType Directory -Path $trusted, $build, (Join-Path $root 'cases') | Out-Null
    $flags = '/nologo /W4 /WX /std:c++17 /EHsc /MT /DUNICODE /D_UNICODE /DWIN32_LEAN_AND_MEAN /DNOMINMAX /D_WIN32_WINNT=0x0A00'
    $harness = 'cl.exe {0} /Bv "{1}\launch.cpp" "{1}\cases.cpp" /Fe"{2}\probe.exe" /link bcrypt.lib /INCREMENTAL:NO' -f $flags, $PSScriptRoot, $trusted
    $stub = 'cl.exe {0} /GS- /GR- /DMARKER_BYTE={1} "{2}\fixture.cpp" /Fe"{3}\{4}.exe" /link /NODEFAULTLIB /ENTRY:marker_entry /SUBSYSTEM:CONSOLE /INCREMENTAL:NO kernel32.lib'
    $good = $stub -f $flags, 65, $PSScriptRoot, $trusted, 'good'
    $bad = $stub -f $flags, 66, $PSScriptRoot, $trusted, 'bad'
    # Only compiler/build output is captured. Never dump the CI environment.
    $command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && {1} && {2} && {3}' -f $vsdev, $harness, $good, $bad
    Push-Location $build
    try {
        & $cmd /d /s /c $command *> (Join-Path $evidence 'build.log')
        if ($LASTEXITCODE -ne 0) { throw 'MSVC compilation failed' }
        foreach ($name in @('good', 'bad', 'probe')) {
            $command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && dumpbin.exe /dependents "{1}\{2}.exe"' -f $vsdev, $trusted, $name
            $importsFile = Join-Path $evidence "imports-$name.txt"
            & $cmd /d /s /c $command *> $importsFile
            if ($LASTEXITCODE -ne 0) { throw 'Import inventory failed' }
            $imports = @(Get-Content -LiteralPath $importsFile | ForEach-Object {
                if ($_ -match '^\s+([A-Za-z0-9_.-]+\.dll)\s*$') { $Matches[1].ToUpperInvariant() }
            } | Sort-Object -Unique)
            if (!$imports.Count) { throw 'Empty import inventory' }
            if ($name -ne 'probe' -and ($imports.Count -ne 1 -or $imports[0] -ne 'KERNEL32.DLL')) {
                throw 'Marker stub contains an unexpected import'
            }
        }
    } finally { Pop-Location }
    $manifest = @{}
    foreach ($name in @('good', 'bad', 'probe')) {
        $file = Get-Item -LiteralPath (Join-Path $trusted "$name.exe")
        if ($file.Length -le 0 -or $file.Length -gt 16MB) { throw 'Binary size outside hashing bound' }
        $manifest[$name] = @{ sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(); bytes = $file.Length }
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $evidence 'build-manifest.json')
    $state.built = $true
    $junction = Join-Path $root 'cases\native_junction_redirect'
    New-Item -ItemType Directory -Path $junction, "$junction\image-a", "$junction\image-b", "$junction\cwd" | Out-Null
    New-Item -ItemType Junction -Path "$junction\active" -Value "$junction\image-a" | Out-Null
    New-Item -ItemType Junction -Path "$junction\spare" -Value "$junction\image-b" | Out-Null
    $state.ran = $true
    & "$trusted\probe.exe" $root $manifest.good.sha256 $manifest.bad.sha256 *> (Join-Path $evidence 'harness.log')
    $state.exit_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Native case harness failed; inspect bounded evidence' }
} catch {
    # Messages here are our bounded diagnostics, never serialized process environments.
    $state.error = $_.Exception.Message.Substring(0, [Math]::Min(512, $_.Exception.Message.Length))
} finally {
    $state | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $evidence 'preparation.json')
}
if ($state.error) { throw $state.error }
