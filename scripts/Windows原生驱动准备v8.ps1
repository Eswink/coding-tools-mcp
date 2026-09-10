param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw '只允许一次性托管CI环境' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$runtimes = @()
foreach ($base in @("${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application", "$env:ProgramFiles\Microsoft\EdgeWebView\Application")) {
    if (Test-Path -LiteralPath $base) {
        foreach ($folder in Get-ChildItem -LiteralPath $base -Directory) {
            $exe = Join-Path $folder.FullName 'msedgewebview2.exe'
            if ($folder.Name -match '^\d+\.\d+\.\d+\.\d+$' -and (Test-Path -LiteralPath $exe)) {
                $runtimes += Get-Item -LiteralPath $exe
            }
        }
    }
}
if ($runtimes.Count -eq 0) { throw '未发现真实WebView2运行时' }
$runtime = $runtimes | Sort-Object { [version]$_.VersionInfo.FileVersion } -Descending | Select-Object -First 1
$version = $runtime.VersionInfo.FileVersion
if ($version -notmatch '^\d+\.\d+\.\d+\.\d+$') { throw 'WebView2版本格式异常' }
$archive = Join-Path $OutputDirectory 'Edge驱动v8.zip'
$url = "https://msedgedriver.microsoft.com/$version/edgedriver_win64.zip"
Invoke-WebRequest -Uri $url -OutFile $archive -TimeoutSec 90
Expand-Archive -LiteralPath $archive -DestinationPath $OutputDirectory -Force
$driver = Join-Path $OutputDirectory 'msedgedriver.exe'
$driverVersion = (& $driver --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $driverVersion -notmatch [regex]::Escape($version)) { throw '驱动与WebView2版本不匹配' }
$signature = Get-AuthenticodeSignature -LiteralPath $driver
[ordered]@{
    source_sha=$env:GITHUB_SHA; webview_version=$version; webview_path=$runtime.FullName;
    driver_version=$driverVersion; download_url=$url;
    archive_sha256=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant();
    driver_sha256=(Get-FileHash -LiteralPath $driver -Algorithm SHA256).Hash.ToLowerInvariant();
    authenticode_status=[string]$signature.Status
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory '驱动来源v8.json') -Encoding utf8
