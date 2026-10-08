$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_RUN_ATTEMPT -cne '1') { throw 'fresh Windows Actions attempt required' }
$root = $env:CTM_VM_SESSION_ROOT
$evidence = $env:CTM_VM_SESSION_EVIDENCE
if ($root -cne (Join-Path $env:RUNNER_TEMP "ctm-vm-session-$env:GITHUB_RUN_ID") -or $evidence -cne (Join-Path $env:RUNNER_TEMP 'ctm-vm-session-evidence')) { throw 'fixed CI paths required' }
$launch = Join-Path $root 'launch'
$code = Join-Path $root 'trusted-code'
$fixture = Join-Path $PSScriptRoot 'windows_vm_launch_fixture.cpp'
if ((Get-FileHash -LiteralPath $fixture).Hash.ToLowerInvariant() -cne '4d08b93bc62b301b975c05ec54ce810db7fa4b70047f089c54a4a50153578d95') { throw 'fixture donor changed' }
$bundle = Get-Content -Raw -LiteralPath "$root/bundle.json" | ConvertFrom-Json
if ($bundle.source -cne $env:GITHUB_SHA) { throw 'broker source mismatch' }
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (!(Test-Path -LiteralPath $vswhere)) { throw 'installed vswhere required; no setup permitted' }
$vs = @(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath)
if ($LASTEXITCODE -ne 0 -or $vs.Count -ne 1) { throw 'installed MSVC required' }
$vsdev = Join-Path $vs[0] 'Common7\Tools\VsDevCmd.bat'
$cmd = Join-Path $env:SystemRoot 'System32\cmd.exe'
foreach ($path in @($root, $evidence, $fixture, $vsdev)) {
  if ($path -match '["%!\r\n&|<>^]') { throw 'unsafe fixed build path' }
}
New-Item -ItemType Directory -Path $launch,$code,"$launch/build","$launch/trusted","$launch/cases" | Out-Null
foreach ($path in @($root, $launch, $code, "$launch/trusted")) {
  if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'reparse code directory' }
}
Copy-Item -LiteralPath "$root/broker.exe" -Destination "$code/broker.exe"
if ((Get-FileHash -LiteralPath "$code/broker.exe").Hash.ToLowerInvariant() -cne $bundle.broker_sha256) { throw 'broker copy mismatch' }
$flags = '/nologo /W4 /WX /std:c++17 /EHsc /MT /DUNICODE /D_UNICODE /DWIN32_LEAN_AND_MEAN /DNOMINMAX /D_WIN32_WINNT=0x0A00 /GS- /GR-'
$stub = 'cl.exe {0} /Bv /DMARKER_BYTE={1} "{2}" /Fe"{3}\{4}.exe" /link /NODEFAULTLIB /ENTRY:marker_entry /SUBSYSTEM:CONSOLE /INCREMENTAL:NO kernel32.lib'
$good = $stub -f $flags,65,$fixture,"$launch\trusted",'good'
$bad = $stub -f $flags,66,$fixture,"$launch\trusted",'bad'
$command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && {1} && {2}' -f $vsdev,$good,$bad
Push-Location "$launch/build"
try {
  & $cmd /d /s /c $command *> "$evidence/launch-build.txt"
  if ($LASTEXITCODE -ne 0) { throw 'marker compilation failed' }
  $command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && echo MSVC=!VCToolsVersion! && echo SDK=!WindowsSDKVersion!' -f $vsdev
  & $cmd /d /v:on /s /c $command *> "$evidence/msvc-sdk.txt"
  if ($LASTEXITCODE -ne 0) { throw 'compiler identity failed' }
  $manifest = @{source=$env:GITHUB_SHA; fixture_sha256=(Get-FileHash -LiteralPath $fixture).Hash.ToLowerInvariant()}
  foreach ($name in @('good','bad','broker')) {
    $binary = if ($name -ceq 'broker') { "$code/broker.exe" } else { "$launch/trusted/$name.exe" }
    $file = Get-Item -LiteralPath $binary
    if ($file.Length -le 0 -or $file.Length -gt 64MB) { throw 'image hashing bound' }
    $command = 'call "{0}" -arch=x64 -host_arch=x64 >nul && dumpbin.exe /dependents "{1}"' -f $vsdev,$binary
    & $cmd /d /s /c $command *> "$evidence/imports-$name.txt"
    if ($LASTEXITCODE -ne 0) { throw 'import inventory failed' }
    $imports = @(Get-Content -LiteralPath "$evidence/imports-$name.txt" | ForEach-Object {
      if ($_ -match '^\s+([A-Za-z0-9_.-]+\.dll)\s*$') { $Matches[1].ToUpperInvariant() }
    } | Sort-Object -Unique)
    if ($imports.Count -ne 1 -or $imports[0] -cne 'KERNEL32.DLL') { throw 'unexpected static import; no loader closure claimed' }
    $manifest[$name] = @{sha256=(Get-FileHash -LiteralPath $binary).Hash.ToLowerInvariant(); bytes=$file.Length; imports=$imports}
  }
} finally { Pop-Location }
Copy-Item -LiteralPath "$launch/trusted/good.exe" -Destination "$launch/trusted/same.exe"
if ((Get-FileHash -LiteralPath "$launch/trusted/same.exe").Hash.ToLowerInvariant() -cne $manifest.good.sha256) { throw 'same-byte fixture copy mismatch' }
$junction = Join-Path $launch 'cases/native_launch_junction_redirect_rejects'
New-Item -ItemType Directory -Path $junction,"$junction/image-a","$junction/image-b","$junction/cwd" | Out-Null
Copy-Item -LiteralPath "$launch/trusted/good.exe" -Destination "$junction/image-a/image.exe"
Copy-Item -LiteralPath "$launch/trusted/bad.exe" -Destination "$junction/image-b/image.exe"
New-Item -ItemType Junction -Path "$junction/active" -Value "$junction/image-a" | Out-Null
New-Item -ItemType Junction -Path "$junction/spare" -Value "$junction/image-b" | Out-Null
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8NoBOM -LiteralPath "$launch/manifest.json"
Copy-Item -LiteralPath "$launch/manifest.json" -Destination "$evidence/launch-manifest.json"
