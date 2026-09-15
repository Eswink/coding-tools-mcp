param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [Parameter(Mandatory=$true)][string]$Driver)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:GITHUB_REPOSITORY -ne 'Eswink/coding-tools-mcp') { throw 'Only this repository disposable Windows runner is supported' }
$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding utf8 | ConvertFrom-Json).version
$match = [regex]::Match($version, '^(?<major>0|[1-9][0-9]*)\.(?<minor>0|[1-9][0-9]*)\.(?<patch>0|[1-9][0-9]*)-rc\.(?<rc>0|[1-9][0-9]*)$')
if (!$match.Success) { throw 'Windows RC acceptance requires major.minor.patch-rc.N' }
$coreParts = @([int]$match.Groups['major'].Value, [int]$match.Groups['minor'].Value, [int]$match.Groups['patch'].Value)
$source = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $source -ne $env:GITHUB_SHA) { throw 'Source identity mismatch' }
$tree = (& git rev-parse 'HEAD^{tree}').Trim()
$built = Get-Item -LiteralPath 'src-tauri/target/release/coding-tools-mcp-desktop.exe'
$setups = @(Get-ChildItem -LiteralPath 'src-tauri/target/release/bundle/nsis' -Filter '*.exe')
if ($setups.Count -ne 1 -or !$setups[0].Name.Contains("_$version`_")) { throw 'Exactly one NSIS installer for the current RC version is required' }
$configRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'coding-tools-mcp-desktop'
if (Test-Path -LiteralPath $configRoot) { throw 'Refusing to overwrite existing application configuration' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$installRoot = Join-Path $env:RUNNER_TEMP ('rc-install-' + [Guid]::NewGuid().ToString('N'))
$setup = Start-Process -FilePath $setups[0].FullName -ArgumentList @('/S', "/D=$installRoot") -PassThru
if (!$setup.WaitForExit(180000)) { Stop-Process -Id $setup.Id -Force; throw 'NSIS silent install timed out' }
$setup.Refresh()
if ($setup.ExitCode -ne 0) { throw "NSIS silent install failed: $($setup.ExitCode)" }
$payloadReport = Join-Path $OutputDirectory '安装载荷核验v7.json'
& python scripts/安装载荷校验v7.py --built $built.FullName --installed-dir $installRoot --output $payloadReport
if ($LASTEXITCODE -ne 0) { throw 'Installed payload byte verification failed' }
$payload = Get-Content -LiteralPath $payloadReport -Raw -Encoding utf8 | ConvertFrom-Json
if (!$payload.passed) { throw 'Installed payload report did not pass' }
$installed = Get-Item -LiteralPath $payload.installed_path
$info = $installed.VersionInfo
if ($info.FileMajorPart -ne $coreParts[0] -or $info.FileMinorPart -ne $coreParts[1] -or $info.FileBuildPart -ne $coreParts[2]) { throw 'Installed PE numeric version does not match RC core version' }
$fixture = Join-Path $env:RUNNER_TEMP ('rc-config-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture | Out-Null
New-Item -ItemType File -Path (Join-Path $fixture '.chat-native-fixture-v8') | Out-Null
& python scripts/Windows启动对照v17.py --output (Join-Path $OutputDirectory 'Windows同场景启动v17.json') 2>&1 | Tee-Object -FilePath (Join-Path $OutputDirectory 'Windows同场景启动v17.log')
if ($LASTEXITCODE -ne 0) { throw 'Installed standard-user window smoke failed; business acceptance was not started' }
& python scripts/Windows标准用户验收v22.py --scenario exclusive --executable $installed.FullName --driver $Driver --kind nsis --source $source --output $OutputDirectory --fixture-root $fixture 2>&1 | Tee-Object -FilePath (Join-Path $OutputDirectory 'Windows已安装原生RC.log')
if ($LASTEXITCODE -ne 0) { throw 'NSIS installed RC native acceptance failed' }
$proof = Get-Content -LiteralPath (Join-Path $OutputDirectory 'exclusive-native.json') -Raw -Encoding utf8 | ConvertFrom-Json
$binaryHash = (Get-FileHash -LiteralPath $installed.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
if (!$proof.passed -or $proof.tests.Count -ne 12 -or $proof.source_sha -ne $source -or $proof.version -ne $version -or $proof.binary_sha256 -ne $binaryHash -or $proof.package_kind -ne 'nsis' -or $proof.build_kind -ne 'release-installed') { throw 'NSIS RC native evidence identity mismatch' }
& python scripts/rc_native_gate.py --input (Join-Path $OutputDirectory 'exclusive-native.json') --binary $installed.FullName --source $source --run-id $env:GITHUB_RUN_ID --version $version --kind nsis
if ($LASTEXITCODE -ne 0) { throw 'NSIS RC native evidence gate failed' }
$target = Join-Path $OutputDirectory "MCP_$version`_x64-setup.exe"
Copy-Item -LiteralPath $setups[0].FullName -Destination $target
$package = Get-Item -LiteralPath $target
$record = [ordered]@{
    passed=$true; source_sha=$source; source_tree=$tree; version=$version; run_id=$env:GITHUB_RUN_ID;
    scenario='exclusive-refresh-v1'; kind='nsis'; release_candidate=$true; publish_approved=$false;
    package=@{name=$package.Name; size=$package.Length; sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()};
    payload_sha256=$binaryHash; native_executable_sha256=$binaryHash;
    silent_install=$true; exact_nsis_payload_verified=$true; real_native_approval=$true;
    signed=((Get-AuthenticodeSignature -LiteralPath $installed.FullName).Status -eq 'Valid');
    synthetic_conversation_metadata=$true; real_chatgpt_verified=$false;
}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'rc-windows-package.json') -Encoding utf8
