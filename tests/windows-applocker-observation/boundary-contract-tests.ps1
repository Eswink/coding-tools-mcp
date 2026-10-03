# Windows PowerShell 5.1 boundary contracts: no native process or event reader.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/contract-boundary.ps1"
$script:BoundarySavedPython = $env:APPLOCKER_PYTHON
$script:BoundaryAssertions = 0
$script:BoundaryCases = 0
$script:BoundaryInterceptRestore = $false
$script:BoundaryBodyError = [System.Management.Automation.ErrorRecord]::new(
    [System.InvalidOperationException]::new('synthetic boundary body failure'),
    'AppLockerBoundaryBodyFailure', [System.Management.Automation.ErrorCategory]::InvalidOperation, $null)
$script:BoundaryCleanupError = [System.Management.Automation.ErrorRecord]::new(
    [System.IO.IOException]::new('synthetic boundary cleanup failure'),
    'AppLockerBoundaryCleanupFailure', [System.Management.Automation.ErrorCategory]::CloseError, $null)
$script:BoundaryRestoreError = [System.Management.Automation.ErrorRecord]::new(
    [System.UnauthorizedAccessException]::new('synthetic boundary restoration failure'),
    'AppLockerBoundaryRestoreFailure', [System.Management.Automation.ErrorCategory]::WriteError, $null)

function Assert-BoundaryContract {
    param([bool]$Condition, [string]$Label)
    $script:BoundaryAssertions++
    if (-not $Condition) { throw "boundary assertion failed: $Label" }
}

# Only the boundary's Global LASTEXITCODE restoration is counted or faulted.
function script:Set-Variable {
    [CmdletBinding()]
    param([string]$Name, [AllowNull()][object]$Value, [string]$Scope)
    if ($script:BoundaryInterceptRestore -and $Name -ceq 'LASTEXITCODE' -and $Scope -ceq 'Global') {
        $script:BoundarySetCalls++
        if ($script:BoundaryRestorationFails) {
            $PSCmdlet.ThrowTerminatingError($script:BoundaryRestoreError)
        }
    }
    Microsoft.PowerShell.Utility\Set-Variable @PSBoundParameters
}

function script:Remove-Variable {
    [CmdletBinding()]
    param([string]$Name, [string]$Scope)
    if ($script:BoundaryInterceptRestore -and $Name -ceq 'LASTEXITCODE' -and $Scope -ceq 'Global') {
        $script:BoundaryRemoveCalls++
        if ($script:BoundaryRestorationFails) {
            $PSCmdlet.ThrowTerminatingError($script:BoundaryRestoreError)
        }
    }
    Microsoft.PowerShell.Utility\Remove-Variable @PSBoundParameters
}

function Invoke-BoundaryContractCase {
    [CmdletBinding()]
    param(
        [bool]$InitialPresent,
        [AllowNull()][object]$InitialValue,
        [bool]$BodyFails,
        [bool]$CleanupFails,
        [bool]$RestorationFails,
        [switch]$BeforeMutation
    )
    if ($InitialPresent) {
        Microsoft.PowerShell.Utility\Set-Variable -Name LASTEXITCODE -Scope Global -Value $InitialValue -ErrorAction Stop
    } elseif ($null -ne (Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue)) {
        Microsoft.PowerShell.Utility\Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction Stop
    }
    $script:BoundaryBodyCalls = 0
    $script:BoundaryCleanupCalls = 0
    $script:BoundarySetCalls = 0
    $script:BoundaryRemoveCalls = 0
    $script:BoundaryBodyFails = $BodyFails
    $script:BoundaryCleanupFails = $CleanupFails
    $script:BoundaryRestorationFails = $RestorationFails
    $script:BoundaryBeforeMutation = [bool]$BeforeMutation
    $script:BoundaryOutput = [System.Collections.Generic.List[object]]::new()
    $script:BoundaryInterceptRestore = $true
    $caseError = $null
    try {
        Invoke-AppLockerSyntheticBoundary -Body {
            [CmdletBinding()]
            param()
            $script:BoundaryBodyCalls++
            Write-Output 'boundary body output'
            if (-not $script:BoundaryBeforeMutation) {
                Microsoft.PowerShell.Utility\Set-Variable -Name LASTEXITCODE -Scope Global -Value 911 -ErrorAction Stop
            }
            if ($script:BoundaryBodyFails) {
                $PSCmdlet.ThrowTerminatingError($script:BoundaryBodyError)
            }
        } -Cleanup {
            [CmdletBinding()]
            param()
            $script:BoundaryCleanupCalls++
            if ($script:BoundaryCleanupFails) {
                $PSCmdlet.ThrowTerminatingError($script:BoundaryCleanupError)
            }
        } | ForEach-Object { $script:BoundaryOutput.Add($_) }
    } catch {
        $caseError = $_
    }
    $expectedError = if ($BodyFails) { $script:BoundaryBodyError }
        elseif ($CleanupFails) { $script:BoundaryCleanupError }
        elseif ($RestorationFails) { $script:BoundaryRestoreError }
        else { $null }
    $expectedSetCalls = if ($InitialPresent) { 1 } else { 0 }
    $expectedRemoveCalls = if (-not $InitialPresent -and -not $BeforeMutation) { 1 } else { 0 }
    Assert-BoundaryContract ($script:BoundaryBodyCalls -eq 1) 'Body runs once'
    Assert-BoundaryContract ($script:BoundaryCleanupCalls -eq 1) 'Cleanup runs once'
    Assert-BoundaryContract ($script:BoundarySetCalls -eq $expectedSetCalls) 'exact selected Set restoration attempts'
    Assert-BoundaryContract ($script:BoundaryRemoveCalls -eq $expectedRemoveCalls) 'exact selected Remove restoration attempts'
    Assert-BoundaryContract ($script:BoundaryOutput.Count -eq 1) 'Body output survives every failure combination'
    Assert-BoundaryContract ($script:BoundaryOutput[0] -ceq 'boundary body output') 'exact Body output survives'
    Assert-BoundaryContract (($null -ne $caseError) -eq ($null -ne $expectedError)) 'failure is never converted to success'
    if ($null -ne $expectedError) {
        Assert-BoundaryContract ([object]::ReferenceEquals($caseError.Exception, $expectedError.Exception)) 'selected exception object'
        Assert-BoundaryContract ($caseError.CategoryInfo.Category -eq $expectedError.CategoryInfo.Category) 'selected error category'
        Assert-BoundaryContract ($caseError.Exception.Message -ceq $expectedError.Exception.Message) 'selected error message'
        Assert-BoundaryContract ($caseError.FullyQualifiedErrorId.Split(',')[0] -ceq $expectedError.FullyQualifiedErrorId) 'selected identifier prefix'
    }
    if ($RestorationFails) {
        # A deliberate restoration fault establishes failure, not state preservation.
        Assert-BoundaryContract ($null -ne $caseError) 'failed restoration cannot return success'
    } else {
        $caseExitState = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
        Assert-BoundaryContract (($null -ne $caseExitState) -eq $InitialPresent) 'exact original presence restored'
        if ($InitialPresent) {
            Assert-BoundaryContract ([object]::Equals($caseExitState.Value, $InitialValue)) 'exact original value including null restored'
        }
    }
    $script:BoundaryCases++
}

# This outer use also protects the caller if an unexpected assertion terminates.
Invoke-AppLockerSyntheticBoundary -Body {
    $env:APPLOCKER_PYTHON = 'synthetic-boundary-python'
    $initialStates = @(
        @{ Present = $false; Value = $null },
        @{ Present = $true; Value = 0 },
        @{ Present = $true; Value = 73 },
        @{ Present = $true; Value = $null }
    )
    foreach ($initialState in $initialStates) {
        foreach ($bodyFails in @($false, $true)) {
            foreach ($cleanupFails in @($false, $true)) {
                foreach ($restorationFails in @($false, $true)) {
                    Invoke-BoundaryContractCase -InitialPresent $initialState.Present -InitialValue $initialState.Value `
                        -BodyFails $bodyFails -CleanupFails $cleanupFails -RestorationFails $restorationFails
                }
            }
        }
    }
    Assert-BoundaryContract ($script:BoundaryCases -eq 32) 'complete four-state by three-fault matrix'
    Invoke-BoundaryContractCase -InitialPresent $false -InitialValue $null `
        -BodyFails $true -CleanupFails $false -RestorationFails $false -BeforeMutation
    Assert-BoundaryContract ($script:BoundaryCases -eq 33) 'matrix plus initially absent pre-mutation failure'
} -Cleanup {
    $script:BoundaryInterceptRestore = $false
    $script:BoundaryBodyFails = $false
    $script:BoundaryCleanupFails = $false
    $script:BoundaryRestorationFails = $false
    $script:BoundaryBeforeMutation = $false
    $env:APPLOCKER_PYTHON = $script:BoundarySavedPython
}
Write-Output "AppLocker boundary contracts: $script:BoundaryCases cases; $script:BoundaryAssertions assertions. No real event query or pilot."
