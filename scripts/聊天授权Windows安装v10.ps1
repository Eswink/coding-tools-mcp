param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$Driver)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:GITHUB_REPOSITORY -ne 'Eswink/coding-tools-mcp') { throw '仅允许一次性托管Runner安装验收' }
$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding utf8 | ConvertFrom-Json).version
$source = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $source -ne $env:GITHUB_SHA) { throw '源码身份不符' }
$tree = (& git rev-parse 'HEAD^{tree}').Trim()
$parts = $version.Split('.') | ForEach-Object { [int]$_ }
$built = Get-Item -LiteralPath 'src-tauri/target/release/coding-tools-mcp-desktop.exe'
$setups = @(Get-ChildItem -LiteralPath 'src-tauri/target/release/bundle/nsis' -Filter '*.exe')
if ($setups.Count -ne 1 -or !$setups[0].Name.Contains("_$version`_")) { throw '当前版本必须且只能有一个NSIS安装包' }
$configRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'coding-tools-mcp-desktop'
if (Test-Path -LiteralPath $configRoot) { throw '拒绝覆盖已有应用配置' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$installRoot = Join-Path $env:RUNNER_TEMP ('聊天授权安装v10-' + [Guid]::NewGuid().ToString('N'))
$setup = Start-Process -FilePath $setups[0].FullName -ArgumentList @('/S', "/D=$installRoot") -PassThru
if (!$setup.WaitForExit(180000)) { Stop-Process -Id $setup.Id -Force; throw 'NSIS静默安装超时' }
$setup.Refresh()
if ($setup.ExitCode -ne 0) { throw "NSIS静默安装失败: $($setup.ExitCode)" }
$payloadReport = Join-Path $OutputDirectory '安装载荷核验v7.json'
& python scripts/安装载荷校验v7.py --built $built.FullName --installed-dir $installRoot --output $payloadReport
if ($LASTEXITCODE -ne 0) { throw '安装载荷字节验证失败' }
$payload = Get-Content -LiteralPath $payloadReport -Raw -Encoding utf8 | ConvertFrom-Json
if (!$payload.passed) { throw '安装载荷报告没有通过' }
$installed = Get-Item -LiteralPath $payload.installed_path
$info = $installed.VersionInfo
if ($info.FileMajorPart -ne $parts[0] -or $info.FileMinorPart -ne $parts[1] -or $info.FileBuildPart -ne $parts[2]) { throw '已安装PE版本不一致' }
$fixture = Join-Path $env:RUNNER_TEMP ('聊天授权配置v10-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
New-Item -ItemType File -Path (Join-Path $fixture '.chat-native-fixture-v8') | Out-Null
& python scripts/聊天授权原生验收v6.py --executable $installed.FullName --driver $Driver --kind nsis --source $source --output $OutputDirectory --fixture-root $fixture 2>&1 | Tee-Object -FilePath (Join-Path $OutputDirectory 'Windows已安装原生v10.log')
if ($LASTEXITCODE -ne 0) { throw 'NSIS安装后完整授权验收失败' }
$proof = Get-Content -LiteralPath (Join-Path $OutputDirectory '聊天授权原生结果v6.json') -Raw -Encoding utf8 | ConvertFrom-Json
$binaryHash = (Get-FileHash -LiteralPath $installed.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if (!$proof.passed -or $proof.tests.Count -ne 8 -or $proof.source_sha -ne $source -or $proof.version -ne $version -or $proof.binary_sha256 -ne $binaryHash -or $proof.package_kind -ne 'nsis' -or $proof.build_kind -ne 'release-installed') { throw 'NSIS原生证据身份不一致' }
$target = Join-Path $OutputDirectory "科研工具MCP_聊天授权候选_v$version`_Windows_x64安装包.exe"
Copy-Item -LiteralPath $setups[0].FullName -Destination $target
$package = Get-Item -LiteralPath $target
$record = [ordered]@{
    passed=$true; source_sha=$source; source_tree=$tree; version=$version; run_id=$env:GITHUB_RUN_ID;
    kind='nsis'; package=@{name=$package.Name; size=$package.Length; sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()};
    payload_sha256=$binaryHash; native_executable_sha256=$binaryHash;
    silent_install=$true; exact_nsis_payload_verified=$true; real_native_approval=$true;
    signed=((Get-AuthenticodeSignature -LiteralPath $installed.FullName).Status -eq 'Valid');
    synthetic_conversation_metadata=$true; real_chatgpt_verified=$false;
}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory '聊天授权安装来源v10.json') -Encoding utf8
