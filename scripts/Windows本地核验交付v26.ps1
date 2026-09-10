param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:GITHUB_REPOSITORY -ne 'Eswink/coding-tools-mcp' -or $env:GITHUB_REF -ne 'refs/heads/release/聊天授权本地验收v26') { throw '仅显式本地验收预发布允许延期原生审批' }
$source = (& git rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $source -ne $env:GITHUB_SHA) { throw '源码身份不符' }
$configRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'coding-tools-mcp-desktop'
if (Test-Path -LiteralPath $configRoot) { throw '拒绝覆盖已有应用配置' }
$env:SOURCE_SHA = $source
./scripts/安装包冒烟v7.ps1 -OutputDirectory $OutputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Windows实际安装冒烟失败；不可豁免' }
$smoke = Get-Content -LiteralPath (Join-Path $OutputDirectory '安装冒烟结果v7.json') -Raw -Encoding utf8 | ConvertFrom-Json
if ($smoke.source_sha -ne $source -or !$smoke.silent_install -or !$smoke.exact_nsis_payload_verified -or !$smoke.native_window_created -or !$smoke.sustained_process) { throw '安装/载荷/窗口基本门禁未通过' }
$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding utf8 | ConvertFrom-Json).version
$package = Get-Item -LiteralPath (Join-Path $OutputDirectory "科研工具MCP_$version`_x64-setup.exe")
$record = [ordered]@{
    passed=$true; source_sha=$source; source_tree=(& git rev-parse 'HEAD^{tree}').Trim();
    version=$version; run_id=$env:GITHUB_RUN_ID; kind='nsis';
    package=@{name=$package.Name; size=$package.Length; sha256=(Get-FileHash -LiteralPath $package.FullName -Algorithm SHA256).Hash.ToLowerInvariant()};
    payload_sha256=$smoke.installed_binary_sha256; native_executable_sha256=$smoke.installed_binary_sha256;
    silent_install=$true; exact_nsis_payload_verified=$true; native_window_created=$true; sustained_process=$true;
    real_native_approval=$false; native_status='pending_local_verification';
    waiver='user-authorized Windows hosted-runner native approval deferral; NOT PASS';
    synthetic_conversation_metadata=$false; real_chatgpt_verified=$false; signed=$smoke.signed;
}
$record | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $OutputDirectory '聊天授权安装来源v10.json') -Encoding utf8
Write-Warning 'Windows安装/载荷/窗口冒烟通过；八阶段原生审批明确留待用户本地核验，不计为PASS。'
