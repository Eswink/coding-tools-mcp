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
  git clone --depth 1 --single-branch --branch v0.14.1 https://github.com/microsoft/hcsshim.git $upstream
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
    $cmd = New-Item -ItemType Directory -Path 'cmd/ctm-boot-prototype'
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/prototype.go" -Destination "$cmd/main.go"
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/prototype_test.go" -Destination "$cmd/main_test.go"
    Copy-Item -LiteralPath "$env:GITHUB_WORKSPACE/scripts/windows_hcs_boot/fixture.go" -Destination "$cmd/fixture.go"
    go version | Set-Content -LiteralPath "$evidence/go-version.txt"; Assert-NativeExit
    go test -mod=vendor -count=1 -v ./cmd/ctm-boot-prototype 2>&1 | Tee-Object -FilePath "$evidence/tests.txt"
    Assert-NativeExit
    go build -mod=vendor -trimpath -o "$root/prototype.exe" ./cmd/ctm-boot-prototype; Assert-NativeExit
    go build -mod=vendor -trimpath -tags fixture -o "$root/fixture.exe" ./cmd/ctm-boot-prototype; Assert-NativeExit
    git diff --exit-code; Assert-NativeExit
    $locks | ConvertTo-Json | Set-Content -LiteralPath "$evidence/dependency-locks.json"
  } finally { Pop-Location }
  $node = (Get-Command node.exe -CommandType Application).Source
  $allowedNode = $node.StartsWith('C:\Program Files\nodejs\',[StringComparison]::OrdinalIgnoreCase) -or $node.StartsWith('C:\hostedtoolcache\windows\node\',[StringComparison]::OrdinalIgnoreCase)
  if (-not $allowedNode -or -not $PSHOME.StartsWith('C:\Program Files\PowerShell\',[StringComparison]::OrdinalIgnoreCase)) { throw 'unexpected stock runtime source' }
  Assert-NoReparse $node; Assert-NoReparse $PSHOME
  $runtime = New-Item -ItemType Directory -Path "$root/runtime"
  Copy-Item -LiteralPath $node -Destination "$runtime/node.exe"
  $license = @(Get-ChildItem -LiteralPath (Split-Path $node) -File | Where-Object Name -in @('LICENSE','LICENSE.txt'))
  if ($license.Count -ne 1) { throw 'Node distribution license unavailable' }
  Copy-Item -LiteralPath $license[0].FullName -Destination "$runtime/NODE-LICENSE.txt"
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
  @{node=(& $node --version); pwsh=$PSVersionTable.PSVersion.ToString(); bundle_sha256=(Get-FileHash -LiteralPath "$root/runtime.zip").Hash.ToLowerInvariant(); hcsshim=$sha} |
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
