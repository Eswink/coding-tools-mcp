param([Parameter(Mandatory)][ValidateSet('build','acquire','boot')][string]$Phase)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_RUN_ATTEMPT -cne '1') { throw 'fresh standard Windows Actions attempt required' }
$root = $env:CTM_BOOT_ROOT
$evidence = $env:CTM_BOOT_EVIDENCE
if ($root -cne (Join-Path $env:RUNNER_TEMP "ctm-hcs-boot-$env:GITHUB_RUN_ID") -or $evidence -cne (Join-Path $env:RUNNER_TEMP 'ctm-hcs-boot-evidence')) { throw 'fixed private paths required' }
$upstream = Join-Path $root 'hcsshim'
$sha = 'fb5aa2e9478c8f5dcaba00601cc7c7d10e1320cd'
function Assert-NativeExit { if ($LASTEXITCODE -ne 0) { throw "native command failed: $LASTEXITCODE" } }
function Assert-NoReparse([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "reparse input: $Path" }
}
if ($Phase -ceq 'build') {
  Assert-NoReparse $env:RUNNER_TEMP
  New-Item -ItemType Directory -Path $root -ErrorAction Stop | Out-Null
  $env:GOTOOLCHAIN = 'local'; $env:GOPROXY = 'off'; $env:GOSUMDB = 'off'; $env:CGO_ENABLED = '0'
  $env:GOCACHE = Join-Path $root 'go-cache'
  git -c core.autocrlf=false clone --depth 1 --single-branch --branch v0.14.1 https://github.com/microsoft/hcsshim.git $upstream
  Assert-NativeExit
  Push-Location $upstream
  try {
    if ((git rev-parse HEAD).Trim() -cne $sha) { throw 'upstream SHA mismatch' }; Assert-NativeExit
    if (@(git status --porcelain).Count -ne 0) { throw 'upstream not clean' }; Assert-NativeExit
    $locks = @{'go.mod'='2abd6398e5b05c2b776fd26895bf8d8fa3a305c7ae2fa97d22ec3be079839adc';
      'go.sum'='18b99012599d98bbc9e1cf1723552271abf0eddf16357963b7b55e2e98caa5d7';
      'vendor/modules.txt'='7f7bce9db52949d840616a4456c32aae0486825096f84d58f636f0e82c006eec'}
    foreach ($path in $locks.Keys) {
      if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $locks[$path]) { throw "dependency lock mismatch: $path" }
    }
    $upstreamFile = 'internal/uvm/create_wcow.go'
    $preHash = '756d21059132c34baf64cfa1ff2c798f6486c6235514960ab1f4ebf28497cfb4'
    $postHash = 'b22b6d758ef183b3d40ad11bab62265126ce5f91ff957fb8ecad04be6fe72927'
    if ((Get-FileHash -LiteralPath $upstreamFile).Hash.ToLowerInvariant() -cne $preHash) { throw 'policy patch preimage mismatch' }
    $patch = @'
--- a/internal/uvm/create_wcow.go
+++ b/internal/uvm/create_wcow.go
@@ -217,7 +217,8 @@
 \t\t\t\t\tHvSocketConfig: &hcsschema.HvSocketSystemConfig{
 \t\t\t\t\t\t// Allow administrators and SYSTEM to bind to hyper-v sockets
 \t\t\t\t\t\t// so that we can communicate to the GCS.
-\t\t\t\t\t\tDefaultBindSecurityDescriptor: "D:P(A;;FA;;;SY)(A;;FA;;;BA)",
+\t\t\t\t\t\tDefaultBindSecurityDescriptor: "D:P(D;;FA;;;WD)",
+\t\t\t\t\t\tDefaultConnectSecurityDescriptor: "D:P(D;;FA;;;WD)",
 \t\t\t\t\t\tServiceTable:                  make(map[string]hcsschema.HvSocketServiceConfig),
 \t\t\t\t\t},
 \t\t\t\t},
'@
    $patchPath = Join-Path $root 'upstream-defaults.patch'
    [IO.File]::WriteAllText($patchPath, $patch.Replace('\t',"`t").Replace("`r`n","`n")+"`n", [Text.UTF8Encoding]::new($false))
    git apply --check $patchPath; Assert-NativeExit
    git apply $patchPath; Assert-NativeExit
    if ((Get-FileHash -LiteralPath $upstreamFile).Hash.ToLowerInvariant() -cne $postHash) { throw 'policy patch postimage mismatch' }
    $pinSources = @{
      'internal/gcs/guestconnection.go'='d605eb5bf62c4b17109d0d7d986017ee831ed805fbb51383c511392c8b39f6f3'
      'internal/gcs/process.go'='e3e6655b04ee999b9573e2964bb55740fbc84de027bf43a6de353a429a76abbf'
      'internal/gcs/iochannel.go'='936ecc4616a39dbc984e507be00fd604d2ea3af4d7048798a4a986e68bb661c9'
      'internal/uvm/start.go'='259ee9063389a1c2a4f714e4e399375f5ff02309365e03c85f84df59209c0833'
    }
    foreach ($path in $pinSources.Keys) { if ((Get-FileHash -LiteralPath $path).Hash.ToLowerInvariant() -cne $pinSources[$path]) { throw 'pinned stdio allocation/close implementation changed' } }
    @{path=$upstreamFile; preimage=$preHash; postimage=$postHash; patch_sha256=(Get-FileHash -LiteralPath $patchPath).Hash.ToLowerInvariant(); source_assumptions=$pinSources} |
      ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$evidence/policy-patch.json"
    $cmd = New-Item -ItemType Directory -Path 'cmd/ctm-boot-prototype'
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/prototype.go" -Destination "$cmd/main.go"
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/prototype_test.go" -Destination "$cmd/main_test.go"
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/fixture.go" -Destination "$cmd/fixture.go"
    foreach ($file in @('surface_guest.go','surface_host.go','surface_test.go','policy_host.go','policy_session.go','policy_shared.go','policy_guest.go','policy_test.go')) {
      Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/$file" -Destination "$cmd/$file"
    }
    go version | Set-Content -LiteralPath "$evidence/go-version.txt"; Assert-NativeExit
    $goVersion = (go env GOVERSION).Trim(); Assert-NativeExit
    $goMatch = [regex]::Match($goVersion, '^go1\.(\d+)\.(\d+)$')
    if (-not $goMatch.Success -or [int]$goMatch.Groups[1].Value -lt 24) { throw 'documented Go1.24+ os.Root required' }
    $testFiles = (go list -mod=vendor -f '{{join .TestGoFiles ","}}' ./cmd/ctm-boot-prototype).Trim(); Assert-NativeExit
    if ($testFiles -cne 'main_test.go,policy_test.go,surface_test.go') { throw 'native test files were omitted or changed' }
    go test -mod=vendor -count=1 -v ./cmd/ctm-boot-prototype 2>&1 | Tee-Object -FilePath "$evidence/tests.txt"
    Assert-NativeExit
    if (@(Get-Content -LiteralPath "$evidence/tests.txt" | Where-Object { $_ -match '^--- PASS: Test' }).Count -ne 25) { throw 'native test count mismatch' }
    go build -mod=vendor -trimpath -o "$root/prototype.exe" ./cmd/ctm-boot-prototype; Assert-NativeExit
    go build -mod=vendor -trimpath -tags fixture -o "$root/fixture.exe" ./cmd/ctm-boot-prototype; Assert-NativeExit
    git diff --check; Assert-NativeExit
    $modified = @(git diff --name-only); Assert-NativeExit
    if ($modified.Count -ne 1 -or $modified[0] -cne $upstreamFile -or (Get-FileHash -LiteralPath $upstreamFile).Hash.ToLowerInvariant() -cne $postHash) { throw 'unexpected patched dependency changes' }
    $locks | ConvertTo-Json | Set-Content -LiteralPath "$evidence/dependency-locks.json"
  } finally { Pop-Location }
  $node = (Get-Command node.exe -CommandType Application).Source
  $allowedNode = $node.StartsWith('C:\Program Files\nodejs\',[StringComparison]::OrdinalIgnoreCase) -or $node.StartsWith('C:\hostedtoolcache\windows\node\',[StringComparison]::OrdinalIgnoreCase)
  if (-not $allowedNode -or -not $PSHOME.StartsWith('C:\Program Files\PowerShell\',[StringComparison]::OrdinalIgnoreCase)) { throw 'unexpected stock runtime source' }
  Assert-NoReparse $node; Assert-NoReparse $PSHOME
  $nodeVersion = (& $node --version).Trim(); Assert-NativeExit
  Write-Output "Observed stock Node: $nodeVersion"
  if ($nodeVersion -cne 'v22.23.3') { throw 'stock Node version differs from pinned license release' }
  $runtime = New-Item -ItemType Directory -Path "$root/runtime"
  Copy-Item -LiteralPath $node -Destination "$runtime/node.exe"
  # The runner MSI does not promise an adjacent license; use the matching immutable official release.
  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/nodejs/node/80dc632040e6bada37aac1220dde9c79581c9c22/LICENSE' -OutFile "$runtime/NODE-LICENSE.txt" -TimeoutSec 30
  if ((Get-Item -LiteralPath "$runtime/NODE-LICENSE.txt").Length -ne 145485 -or
    (Get-FileHash -LiteralPath "$runtime/NODE-LICENSE.txt" -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'c738ae413cf561f174e34f6961f8ca458aae2369a73640dda6234c629b98bcc4') { throw 'pinned Node license mismatch' }
  foreach ($item in Get-ChildItem -LiteralPath $PSHOME -Recurse -Force) { Assert-NoReparse $item.FullName }
  Copy-Item -LiteralPath $PSHOME -Destination "$runtime/pwsh" -Recurse
  Copy-Item -LiteralPath "$root/fixture.exe" -Destination "$runtime/fixture.exe"
  $runtimeFiles = @(Get-ChildItem -LiteralPath $runtime -Recurse -File | Sort-Object FullName | ForEach-Object {
    @{path=[IO.Path]::GetRelativePath($runtime.FullName,$_.FullName); size=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
  })
  if ($runtimeFiles.Count -gt 5000) { throw 'runtime file inventory exceeded' }
  $runtimeFiles | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$evidence/runtime-files.json"
  Compress-Archive -LiteralPath @(Get-ChildItem -LiteralPath $runtime -Force | ForEach-Object FullName) -DestinationPath "$root/runtime.zip"
  if ((Get-Item -LiteralPath "$root/runtime.zip").Length -gt 300MB) { throw 'runtime bundle exceeded bound' }
  @{node=$nodeVersion; pwsh=$PSVersionTable.PSVersion.ToString(); bundle_sha256=(Get-FileHash -LiteralPath "$root/runtime.zip").Hash.ToLowerInvariant(); hcsshim=$sha} |
    ConvertTo-Json | Set-Content -LiteralPath "$evidence/runtime.json"
  Assert-NativeExit
}
if ($Phase -ceq 'acquire') {
  $layers = @(
    @{sha='97e96e9cbeb16024139f78dc6ed542a7cf572ac80d8cea50a3308368094c4574'; size=1482371926},
    @{sha='67f39c55a3f42bc0569099cebb32cef6688837ca694dfacaa00053810cb810d6'; size=914397517})
  for ($i=0; $i -lt $layers.Count; $i++) {
    $file = "$root/layer$i.gz"
    if (Test-Path -LiteralPath $file) { throw 'fresh layer acquisition required' }
    Invoke-WebRequest -Uri "https://mcr.microsoft.com/v2/windows/servercore/blobs/sha256:$($layers[$i].sha)" -OutFile $file -TimeoutSec 600
    if ((Get-Item -LiteralPath $file).Length -ne $layers[$i].size -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $layers[$i].sha) { throw 'MCR layer verification failed' }
  }
  @{image='mcr.microsoft.com/windows/servercore@sha256:22505496dd4229dba63453ba0c6dc31c06fd3e11810e5b8e429aa6b16dab2457'; os_version='10.0.26100.33438'; layers=$layers} |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "$evidence/image.json"
  & "$root/prototype.exe" import; Assert-NativeExit
}
if ($Phase -ceq 'boot') {
  if ((Get-Service -Name vmcompute).Status -ne 'Running') { throw 'vmcompute no longer running; no remediation' }
  & "$root/prototype.exe" run; Assert-NativeExit
}
