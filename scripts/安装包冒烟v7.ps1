param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$version = (Get-Content -LiteralPath 'package.json' -Raw | ConvertFrom-Json).version
$parts = $version.Split('.') | ForEach-Object { [int]$_ }
$binary = Get-Item -LiteralPath 'src-tauri/target/release/coding-tools-mcp-desktop.exe'
$info = $binary.VersionInfo
if ($info.FileMajorPart -ne $parts[0] -or $info.FileMinorPart -ne $parts[1] -or $info.FileBuildPart -ne $parts[2]) { throw '内嵌PE版本与源码版本不符' }
$installers = @(Get-ChildItem -LiteralPath 'src-tauri/target/release/bundle/nsis' -Filter '*.exe')
if ($installers.Count -ne 1 -or !$installers[0].Name.Contains("_$version`_")) { throw '必须恰好生成一个当前版本安装包' }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$installRoot = Join-Path $env:RUNNER_TEMP ('安装冒烟v7-' + [Guid]::NewGuid().ToString('N'))
$setup = Start-Process -FilePath $installers[0].FullName -ArgumentList @('/S', "/D=$installRoot") -PassThru
if (!$setup.WaitForExit(180000)) { Stop-Process -Id $setup.Id -Force; throw '静默安装超时' }
$setup.Refresh()
if ($setup.ExitCode -ne 0) { throw "静默安装失败: $($setup.ExitCode)" }
$hash = (Get-FileHash -LiteralPath $binary.FullName -Algorithm SHA256).Hash
$installed = @(Get-ChildItem -LiteralPath $installRoot -Recurse -File -Filter '*.exe' | Where-Object { (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash -eq $hash })
if ($installed.Count -ne 1) { throw '已安装程序摘要与构建程序不一致' }
$app = $null
try {
    $app = Start-Process -FilePath $installed[0].FullName -PassThru
    $window = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        $app.Refresh()
        if ($app.HasExited) { throw "桌面应用启动退出: $($app.ExitCode)" }
        if ($app.MainWindowHandle -ne 0) { $window = $true; break }
    }
    if (!$window) { throw '桌面应用未创建可见主窗口' }
    Start-Sleep -Seconds 5
    $app.Refresh()
    if ($app.HasExited) { throw '桌面应用在窗口创建后异常退出' }
    $report = [ordered]@{
        source_sha = $env:SOURCE_SHA; version = $version; platform = 'windows-x64';
        installed_binary_sha256 = $hash.ToLowerInvariant();
        product_version = $installed[0].VersionInfo.ProductVersion;
        file_version = $installed[0].VersionInfo.FileVersion;
        silent_install = $true; native_window_created = $true;
        sustained_process = $true; public_network_tested = $false;
        signed = ((Get-AuthenticodeSignature -LiteralPath $binary.FullName).Status -eq 'Valid')
    }
    $report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDirectory '安装冒烟结果v7.json') -Encoding utf8
} finally {
    if ($null -ne $app) {
        $app.Refresh()
        if (!$app.HasExited) {
            $null = $app.CloseMainWindow()
            if (!$app.WaitForExit(5000)) { Stop-Process -Id $app.Id -Force }
        }
    }
}
Copy-Item -LiteralPath $installers[0].FullName -Destination (Join-Path $OutputDirectory "科研工具MCP_$version`_x64-setup.exe")
