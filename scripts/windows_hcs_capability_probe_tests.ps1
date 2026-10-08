param([Parameter(Mandatory=$true)][string]$OutputPath)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$testOutputPath = $OutputPath
. "$PSScriptRoot/windows_hcs_capability_probe.ps1"
Initialize-HcsProbeNative

function New-ObservedFixture {
    return @{
        image_version = 'synthetic-image'
        features = @{'Hyper-V'=@{status='observed'; installed=$true}; Containers=@{status='observed'; installed=$true}}
        services = @{vmcompute=@{status='observed'; state='Running'}}
        whp = @{status='observed'; Value='1'; Freed=$true}
        hcs = @{status='observed'; Freed=$true}
        conclusion='execution_not_tested'; vm_launch_attempted=$false
    }
}

function Assert-Blockers {
    param([hashtable]$Fixture, [string[]]$Expected)
    $actual = @(Get-HcsProbeBlockers $Fixture)
    if (($actual -join '|') -cne ($Expected -join '|')) { throw 'Unexpected blocker set' }
    if ($Fixture.conclusion -cne 'execution_not_tested' -or $Fixture.vm_launch_attempted) { throw 'Acceptance leakage' }
}

$cases = [ordered]@{
    all_observed_remains_execution_untested = {
        Assert-Blockers (New-ObservedFixture) @()
    }
    missing_image_blocks = {
        $r=New-ObservedFixture; $r.image_version=$null
        Assert-Blockers $r @('image_version_unobserved')
    }
    missing_required_feature_blocks = {
        $r=New-ObservedFixture; $r.features.Remove('Hyper-V')
        Assert-Blockers $r @('feature_unavailable:Hyper-V')
    }
    false_and_wrong_type_features_block = {
        foreach ($value in @($false, 'true', 1, $null)) {
            $r=New-ObservedFixture; $r.features.Containers.installed=$value
            Assert-Blockers $r @('feature_unavailable:Containers')
        }
    }
    stopped_or_missing_service_blocks = {
        $r=New-ObservedFixture; $r.services.vmcompute.state='Stopped'
        Assert-Blockers $r @('vmcompute_not_observed_running')
        $r.services.Remove('vmcompute')
        Assert-Blockers $r @('vmcompute_not_observed_running')
    }
    whp_false_error_or_unfreed_blocks = {
        $r=New-ObservedFixture; $r.whp.Value='0'
        Assert-Blockers $r @('whp_hypervisor_not_observed')
        $r.whp.Value='1'; $r.whp.status='query_failed'
        Assert-Blockers $r @('whp_hypervisor_not_observed')
        $r.whp.status='observed'; $r.whp.Freed=$false
        Assert-Blockers $r @('whp_hypervisor_not_observed')
    }
    hcs_error_skipped_or_unfreed_blocks = {
        foreach ($status in @('exception','query_failed','not_attempted','oversize','missing_result','cleanup_failed')) {
            $r=New-ObservedFixture; $r.hcs.status=$status
            Assert-Blockers $r @('hcs_basic_not_observed')
        }
        $r=New-ObservedFixture; $r.hcs.Freed=$false
        Assert-Blockers $r @('hcs_basic_not_observed')
    }
    exceptional_observations_do_not_require_missing_values = {
        $r=New-ObservedFixture; $r.features['Hyper-V']=@{status='exception'}
        $r.services.vmcompute=@{status='exception'}; $r.whp=@{status='exception'}; $r.hcs=@{status='exception'}
        Assert-Blockers $r @('feature_unavailable:Hyper-V','vmcompute_not_observed_running','whp_hypervisor_not_observed','hcs_basic_not_observed')
    }
}
$executed = [System.Collections.Generic.List[string]]::new()
foreach ($name in $cases.Keys) {
    & $cases[$name]
    $executed.Add($name)
    Write-Output "PASS $name"
}
if ($executed.Count -ne 8) { throw 'Expected eight self-tests' }
$receipt = @{declared_ids=@($cases.Keys); executed_ids=$executed.ToArray(); tests_run=8; native_queries_run=0}
[IO.File]::WriteAllText($testOutputPath, ($receipt | ConvertTo-Json -Depth 5) + "`n", [Text.UTF8Encoding]::new($false))
