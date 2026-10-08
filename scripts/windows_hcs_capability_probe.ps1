param([string]$OutputPath = '')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Initialize-HcsProbeNative {
    if ('HcsCapabilityReadOnly' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public sealed class HcsProbeNativeResult {
    public string Status = "unobserved";
    public int HResult;
    public uint Written;
    public string Value;
    public string Text;
    public string Error;
    public bool Freed;
}
public static class HcsCapabilityReadOnly {
    [DllImport("WinHvPlatform.dll", ExactSpelling=true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int WHvGetCapability(uint code, IntPtr buffer, uint size, out uint written);
    [DllImport("ComputeCore.dll", ExactSpelling=true, CharSet=CharSet.Unicode)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern int HcsGetServiceProperties(string query, out IntPtr result);
    [DllImport("kernel32.dll", ExactSpelling=true)]
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    private static extern IntPtr LocalFree(IntPtr value);
    public static HcsProbeNativeResult Capability(uint code) {
        if (code != 0 && code != 0x1000 && code != 0x2000) throw new ArgumentException("fixed code");
        uint size = code == 0x2000 ? 8u : 4u;
        var r = new HcsProbeNativeResult();
        IntPtr p = Marshal.AllocHGlobal((int)size);
        try {
            for (int i = 0; i < size; i++) Marshal.WriteByte(p, i, 0);
            r.HResult = WHvGetCapability(code, p, size, out r.Written);
            r.Status = r.HResult == 0 && r.Written == size ? "observed" : "query_failed";
            if (r.Status == "observed") r.Value = size == 4
                ? unchecked((uint)Marshal.ReadInt32(p)).ToString()
                : unchecked((ulong)Marshal.ReadInt64(p)).ToString();
        } catch (Exception ex) { r.Status = "exception"; r.Error = ex.GetType().Name; }
        finally { Marshal.FreeHGlobal(p); r.Freed = true; }
        return r;
    }
    public static HcsProbeNativeResult Basic() {
        var r = new HcsProbeNativeResult();
        IntPtr p = IntPtr.Zero;
        try {
            r.HResult = HcsGetServiceProperties("{\"PropertyTypes\":[\"Basic\"]}", out p);
            r.Status = r.HResult == 0 ? "observed" : "query_failed";
            if (r.HResult == 0 && p != IntPtr.Zero) {
                int n = 0;
                while (n < 65536 && Marshal.ReadInt16(p, n * 2) != 0) n++;
                if (n == 65536) r.Status = "oversize";
                else if (n == 0) r.Status = "missing_result";
                else { r.Text = Marshal.PtrToStringUni(p, n); r.Written = (uint)n; }
            } else if (r.HResult == 0) r.Status = "missing_result";
        } catch (Exception ex) { r.Status = "exception"; r.Error = ex.GetType().Name; }
        finally {
            r.Freed = p == IntPtr.Zero || LocalFree(p) == IntPtr.Zero;
            if (!r.Freed) r.Status = "cleanup_failed";
        }
        return r;
    }
}
'@
}

function Get-HcsProbeBlockers {
    param([hashtable]$Report)
    $blocked = [System.Collections.Generic.List[string]]::new()
    if ([string]::IsNullOrWhiteSpace($Report.image_version)) { $blocked.Add('image_version_unobserved') }
    foreach ($name in @('Hyper-V', 'Containers')) {
        if (!$Report.features.Contains($name) -or $Report.features[$name].status -cne 'observed' -or
            $Report.features[$name].installed -isnot [bool] -or !$Report.features[$name].installed) {
            $blocked.Add("feature_unavailable:$name")
        }
    }
    if (!$Report.services.Contains('vmcompute') -or $Report.services.vmcompute.status -cne 'observed' -or
        $Report.services.vmcompute.state -cne 'Running') { $blocked.Add('vmcompute_not_observed_running') }
    if ($Report.whp.status -cne 'observed' -or $Report.whp.Value -cne '1' -or
        !$Report.whp.Freed) { $blocked.Add('whp_hypervisor_not_observed') }
    if ($Report.hcs.status -cne 'observed' -or !$Report.hcs.Freed) { $blocked.Add('hcs_basic_not_observed') }
    return $blocked.ToArray()
}

function Invoke-HcsCapabilityProbe {
    if ($env:GITHUB_ACTIONS -cne 'true' -or $env:RUNNER_OS -cne 'Windows' -or
        $env:RUNNER_ENVIRONMENT -cne 'github-hosted') { throw 'Dedicated hosted Windows observation only' }
    Initialize-HcsProbeNative
    $report = @{
        schema = 1; image_os = $env:ImageOS; image_version = $env:ImageVersion
        observed_at_utc = [DateTime]::UtcNow.ToString('o')
        os_version = [Environment]::OSVersion.VersionString
        powershell = $PSVersionTable.PSVersion.ToString()
        features = [ordered]@{}; services = [ordered]@{}
        conclusion = 'execution_not_tested'; vm_launch_attempted = $false
        runtime_compatibility_tested = $false; network_denial_tested = $false
        workspace_confinement_tested = $false; lifecycle_completion_tested = $false
        production_admission = 'unchanged_rejected'
    }
    foreach ($name in @('Hyper-V', 'Containers')) {
        try {
            $rows = @(Get-WindowsFeature -Name $name -ErrorAction Stop)
            if ($rows.Count -ne 1 -or $rows[0].Name -cne $name) { throw 'feature identity mismatch' }
            $report.features[$name] = @{status='observed'; installed=$rows[0].Installed; state=[string]$rows[0].InstallState}
        } catch { $report.features[$name] = @{status='exception'; error=$_.Exception.GetType().Name} }
    }
    foreach ($name in @('VirtualMachinePlatform', 'HypervisorPlatform')) {
        try {
            $row = Get-WindowsOptionalFeature -Online -FeatureName $name -ErrorAction Stop
            $report.features[$name] = @{status='observed'; state=[string]$row.State}
        } catch { $report.features[$name] = @{status='exception'; error=$_.Exception.GetType().Name} }
    }
    foreach ($name in @('vmcompute', 'vmms', 'BFE')) {
        try {
            $row = Get-Service -Name $name -ErrorAction Stop
            $report.services[$name] = @{status='observed'; state=[string]$row.Status}
        } catch { $report.services[$name] = @{status='exception'; error=$_.Exception.GetType().Name} }
    }
    try {
        $rows = @(Get-CimInstance -ClassName Win32_Processor -OperationTimeoutSec 15 -ErrorAction Stop |
            Select-Object Manufacturer, VMMonitorModeExtensions, SecondLevelAddressTranslationExtensions, VirtualizationFirmwareEnabled)
        if ($rows.Count -eq 0 -or $rows.Count -gt 32) { throw 'processor count outside probe bound' }
        $report.cpu = @{status='observed'; processors=$rows}
    } catch { $report.cpu = @{status='exception'; error=$_.Exception.GetType().Name} }
    $report.whp = [HcsCapabilityReadOnly]::Capability(0)
    $report.whp_processor_vendor = [HcsCapabilityReadOnly]::Capability(0x1000)
    $report.whp_vmx_basic = [HcsCapabilityReadOnly]::Capability(0x2000)
    $report.hcs = @{status='not_attempted'; Freed=$true; reason='vmcompute_not_observed_running'}
    try {
        $current = Get-Service -Name vmcompute -ErrorAction Stop
        $report.vmcompute_before_hcs = [string]$current.Status
        if ($current.Status.ToString() -ceq 'Running') {
            $report.hcs = [HcsCapabilityReadOnly]::Basic()
        }
    } catch { $report.hcs = @{status='exception'; Freed=$true; error=$_.Exception.GetType().Name} }
    $report.blockers = @(Get-HcsProbeBlockers $report)
    return $report
}

if ($MyInvocation.InvocationName -ne '.') {
    if ([string]::IsNullOrWhiteSpace($OutputPath)) { throw 'OutputPath required' }
    $report = Invoke-HcsCapabilityProbe
    $json = $report | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($OutputPath, $json + "`n", [Text.UTF8Encoding]::new($false))
    if ($report.blockers.Count -ne 0) { throw ('Prerequisites absent or unobserved: ' + ($report.blockers -join ',')) }
}
