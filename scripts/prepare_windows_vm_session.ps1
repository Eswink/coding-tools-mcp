param([Parameter(Mandatory)][ValidateSet('build','acquire')][string]$Phase)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or $env:GITHUB_RUN_ATTEMPT -cne '1') { throw 'fresh Windows Actions attempt required' }
$root = $env:CTM_VM_SESSION_ROOT
$evidence = $env:CTM_VM_SESSION_EVIDENCE
if ($root -cne (Join-Path $env:RUNNER_TEMP "ctm-vm-session-$env:GITHUB_RUN_ID") -or $evidence -cne (Join-Path $env:RUNNER_TEMP 'ctm-vm-session-evidence')) { throw 'fixed CI paths required' }
$source = Join-Path $env:GITHUB_WORKSPACE 'services/windows-vm-broker'
$pins = Get-Content -Raw -LiteralPath "$source/inputs.json" | ConvertFrom-Json
$upstream = Join-Path $root 'hcsshim'
function Assert-NativeExit { if ($LASTEXITCODE -ne 0) { throw "native command failed: $LASTEXITCODE" } }
function Assert-NoReparse([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "reparse input: $Path" }
}
function Assert-Hash([string]$Path, [string]$Hash) {
  if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Hash) { throw "source/input hash mismatch: $Path" }
}
if ($Phase -ceq 'build') {
  $env:CGO_ENABLED='0'; $env:GOTOOLCHAIN='local'; $env:GOPROXY='off'; $env:GOSUMDB='off'
  if ((go env GOVERSION).Trim() -cne $pins.go) { throw 'exact tested Go compiler required' }; Assert-NativeExit
  go version | Set-Content -LiteralPath "$evidence/go-version.txt"; Assert-NativeExit
  git -c core.autocrlf=false clone --quiet --no-checkout https://github.com/microsoft/hcsshim.git $upstream; Assert-NativeExit
  Push-Location $upstream
  try {
    git checkout --quiet --detach $pins.hcsshim; Assert-NativeExit
    if ((git rev-parse HEAD).Trim() -cne $pins.hcsshim) { throw 'upstream SHA mismatch' }; Assert-NativeExit
    if (@(git status --porcelain).Count -ne 0) { throw 'upstream not clean' }; Assert-NativeExit
    foreach ($p in $pins.dependency_hashes.PSObject.Properties) { Assert-Hash $p.Name $p.Value }
    foreach ($p in $pins.source_assumptions.PSObject.Properties) { Assert-Hash $p.Name $p.Value }
    $patchSource = "$source/upstream-defaults.patch"
    Assert-Hash $patchSource $pins.patch_source_sha256
    $patch = "$root/upstream-defaults.patch"
    [IO.File]::WriteAllText($patch, (Get-Content -Raw -LiteralPath $patchSource).Replace('\t',"`t"), [Text.UTF8Encoding]::new($false))
    Assert-Hash $patch $pins.patch_sha256
    Assert-Hash 'internal/uvm/create_wcow.go' $pins.patch_preimage
    git apply --check $patch; Assert-NativeExit
    git apply $patch; Assert-NativeExit
    Assert-Hash 'internal/uvm/create_wcow.go' $pins.patch_postimage
    $cmd = New-Item -ItemType Directory -Path 'cmd/ctm-windows-vm-broker'
    Copy-Item -Path "$source/*.go" -Destination $cmd
    $files = (go list -mod=vendor -f '{{join .TestGoFiles ","}}' ./cmd/ctm-windows-vm-broker).Trim(); Assert-NativeExit
    if ($files -cne 'owner_windows_test.go') { throw 'compiled native Go test inventory changed' }
    go test -mod=vendor -count=1 -v ./cmd/ctm-windows-vm-broker 2>&1 | Tee-Object -FilePath "$evidence/go-tests.txt"; Assert-NativeExit
    if (@(Get-Content -LiteralPath "$evidence/go-tests.txt" | Where-Object { $_ -match '^--- PASS: Test[^/ ]+ ' }).Count -ne 12) { throw 'expected twelve native Go tests' }
    $env:CGO_ENABLED = '0'
    $env:GOTOOLCHAIN = 'local'
    $env:GOPROXY = 'off'
    $env:GOSUMDB = 'off'
    $ldflags = "-X main.buildSource=$env:GITHUB_SHA"
    go build -mod=vendor -trimpath -ldflags $ldflags -o "$root/broker.exe" ./cmd/ctm-windows-vm-broker; Assert-NativeExit
    go build -mod=vendor -trimpath -ldflags $ldflags -tags guest -o "$root/guest.exe" ./cmd/ctm-windows-vm-broker; Assert-NativeExit
    git diff --check; Assert-NativeExit
    $changed = @(git diff --name-only); Assert-NativeExit
    if ($changed.Count -ne 1 -or $changed[0] -cne 'internal/uvm/create_wcow.go') { throw 'unexpected upstream change' }
    foreach ($p in $pins.dependency_hashes.PSObject.Properties) { Assert-Hash $p.Name $p.Value }
    $pins | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath "$evidence/pinned-inputs.json"
  } finally { Pop-Location }
  $node = (Get-Command node.exe -CommandType Application).Source
  $allowedNode = $node.StartsWith('C:\Program Files\nodejs\',[StringComparison]::OrdinalIgnoreCase) -or $node.StartsWith('C:\hostedtoolcache\windows\node\',[StringComparison]::OrdinalIgnoreCase)
  if (-not $allowedNode -or -not $PSHOME.StartsWith('C:\Program Files\PowerShell\',[StringComparison]::OrdinalIgnoreCase)) { throw 'unexpected stock runtime source' }
  Assert-NoReparse $node; Assert-NoReparse $PSHOME
  Assert-Hash $node $pins.node_exe_sha256
  Assert-Hash (Join-Path $PSHOME 'pwsh.exe') $pins.pwsh_exe_sha256
  $nodeVersion = (& $node --version).Trim(); Assert-NativeExit
  if ($nodeVersion -cne $pins.node -or $PSVersionTable.PSVersion.ToString() -cne $pins.pwsh) { throw 'stock runtime differs from tested pin' }
  $runtime = New-Item -ItemType Directory -Path "$root/runtime"
  Copy-Item -LiteralPath $node -Destination "$runtime/node.exe"
  Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/nodejs/node/80dc632040e6bada37aac1220dde9c79581c9c22/LICENSE' -OutFile "$runtime/NODE-LICENSE.txt" -TimeoutSec 30
  if ((Get-Item -LiteralPath "$runtime/NODE-LICENSE.txt").Length -ne 145485) { throw 'Node license size mismatch' }
  Assert-Hash "$runtime/NODE-LICENSE.txt" 'c738ae413cf561f174e34f6961f8ca458aae2369a73640dda6234c629b98bcc4'
  foreach ($item in Get-ChildItem -LiteralPath $PSHOME -Recurse -Force) { Assert-NoReparse $item.FullName }
  Copy-Item -LiteralPath $PSHOME -Destination "$runtime/pwsh" -Recurse
  Copy-Item -LiteralPath "$root/guest.exe" -Destination "$runtime/guest.exe"
  $runtimeFiles = @(Get-ChildItem -LiteralPath $runtime -Recurse -File | Sort-Object FullName | ForEach-Object {
    @{path=[IO.Path]::GetRelativePath($runtime.FullName,$_.FullName); size=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
  })
  if ($runtimeFiles.Count -gt 5000) { throw 'runtime file inventory exceeded' }
  $runtimeFiles | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$evidence/runtime-files.json"
  Compress-Archive -LiteralPath @(Get-ChildItem -LiteralPath $runtime -Force | ForEach-Object FullName) -DestinationPath "$root/runtime.zip"
  if ((Get-Item -LiteralPath "$root/runtime.zip").Length -gt 300MB) { throw 'runtime bundle bound' }
  @{source=$env:GITHUB_SHA; broker_sha256=(Get-FileHash "$root/broker.exe").Hash.ToLowerInvariant(); guest_sha256=(Get-FileHash "$root/guest.exe").Hash.ToLowerInvariant();
    node=$nodeVersion; pwsh=$PSVersionTable.PSVersion.ToString(); image_manifest=$pins.image_manifest; runtime_sha256=(Get-FileHash "$root/runtime.zip").Hash.ToLowerInvariant()} |
    ConvertTo-Json | Set-Content -Encoding utf8NoBOM -LiteralPath "$root/bundle.json"
  Copy-Item -LiteralPath "$root/bundle.json" -Destination "$evidence/bundle.json"
}
if ($Phase -ceq 'acquire') {
  if ((Get-Service -Name vmcompute).Status -ne 'Running') { throw 'vmcompute unavailable; no remediation' }
  for ($i=0; $i -lt $pins.layers.Count; $i++) {
    $l = $pins.layers[$i]; $path = "$root/layer$i.gz"
    if (Test-Path -LiteralPath $path) { throw 'fresh layer acquisition required' }
    Invoke-WebRequest -Uri "https://mcr.microsoft.com/v2/windows/servercore/blobs/sha256:$($l.sha)" -OutFile $path -TimeoutSec 600
    if ((Get-Item -LiteralPath $path).Length -ne $l.size) { throw 'MCR layer size mismatch' }
    Assert-Hash $path $l.sha
  }
  & "$root/broker.exe" --import-root $root 2>&1 | Tee-Object -FilePath "$evidence/import.txt"; Assert-NativeExit
}
