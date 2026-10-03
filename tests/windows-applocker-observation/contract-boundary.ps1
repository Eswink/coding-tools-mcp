# Test-only boundary for fixed repository callbacks; loading defines functions only.
function Invoke-AppLockerSyntheticBoundary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][scriptblock]$Body,
        [Parameter(Mandatory = $true)][scriptblock]$Cleanup
    )

    $appLockerBoundaryExitState = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    $appLockerBoundaryExitPresent = $null -ne $appLockerBoundaryExitState
    $appLockerBoundaryExitValue = $null
    if ($appLockerBoundaryExitPresent) {
        $appLockerBoundaryExitValue = $appLockerBoundaryExitState.Value
    }
    $appLockerBoundaryBodyFailed = $false
    $appLockerBoundaryCleanupError = $null
    $appLockerBoundaryRestoreError = $null
    try {
        & $Body
    } catch {
        $appLockerBoundaryBodyFailed = $true
        throw
    } finally {
        try {
            & $Cleanup
        } catch {
            $appLockerBoundaryCleanupError = $_
        }
        try {
            if ($appLockerBoundaryExitPresent) {
                Set-Variable -Name LASTEXITCODE -Scope Global -Value $appLockerBoundaryExitValue -ErrorAction Stop
            } elseif ($null -ne (Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue)) {
                Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction Stop
            }
        } catch {
            $appLockerBoundaryRestoreError = $_
        }
        # A pending Body failure must survive both secondary failures.
        if (-not $appLockerBoundaryBodyFailed) {
            if ($null -ne $appLockerBoundaryCleanupError) {
                $PSCmdlet.ThrowTerminatingError($appLockerBoundaryCleanupError)
            }
            if ($null -ne $appLockerBoundaryRestoreError) {
                $PSCmdlet.ThrowTerminatingError($appLockerBoundaryRestoreError)
            }
        }
    }
}
