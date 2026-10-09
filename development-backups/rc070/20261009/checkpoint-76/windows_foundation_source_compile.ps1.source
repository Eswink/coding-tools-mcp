param([Parameter(Mandatory=$true)][ValidateSet('rust','go')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Manager = Split-Path $PSScriptRoot -Parent
$Output = Join-Path $env:RUNNER_TEMP 'windows-foundation-probe'
$Destination = Join-Path $env:RUNNER_TEMP 'windows-foundation-sut-19bb2920'
New-Item -ItemType Directory -Force $Output | Out-Null
$Guard = Join-Path $PSScriptRoot 'windows_foundation_source_guard.py'
$Manifest = Join-Path $PSScriptRoot 'windows_foundation_source_manifest.json'
$Observer = Join-Path $PSScriptRoot 'windows_foundation_manager_observation.py'
$InferenceOverlay = Join-Path $PSScriptRoot 'windows_foundation_inference_overlay.py'
$Receipt = [ordered]@{ mode=$Mode; managerCommit=$env:GITHUB_SHA; runId=$env:GITHUB_RUN_ID;
    pureSutTree=$(if ($Mode -ceq 'rust') {'6b7e33c45c5e56340b1cfb81a7d304c6c60cf23f'} else {'19bb292004e0fd4ed02374b35bcd2f22469779f0'}); baselineSutTree='19bb292004e0fd4ed02374b35bcd2f22469779f0'; qualification='SOURCE_ONLY_BLOCKED';
    nativePositive='NOTRUN'; compiler='NOTRUN'; sourceBaseline=$null; sourceBefore=$null; sourceAfter=$null; managerSourceBefore=$null; managerSourceAfter=$null; commands=@(); runtime=@{}; managerObservationFailed=$false; passed=$false }

$ObservationCancellation = $null
$SourceCancellation = $null
$PrimaryFailure = $null
$DelegateHandled = $false

function Resolve-FoundationApplication([string]$Executable) {
    $Requested = $Executable
    if ($Executable -ceq 'python') {
        if ([string]::IsNullOrWhiteSpace($PythonExecutable) -or
            -not [System.IO.Path]::IsPathRooted($PythonExecutable) -or
            $PythonExecutable -match '[\\/]Microsoft[\\/]WindowsApps[\\/]') {
            throw 'Python must be the explicit rooted setup-python payload, never a WindowsApps alias.'
        }
        $Requested = $PythonExecutable
    }
    $Commands = @(Get-Command -Name $Requested -CommandType Application -ErrorAction Stop)
    if ($Commands.Count -eq 0) { throw "No native application resolved: $Executable" }
    if ($Executable -ceq 'python' -and $Commands.Count -ne 1) { throw 'Explicit Python payload resolved ambiguously.' }
    $Path = [string]$Commands[0].Source
    if ([string]::IsNullOrWhiteSpace($Path) -or -not [System.IO.Path]::IsPathRooted($Path) -or
        -not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Native application is not one rooted file: $Executable" }
    if ($Executable -ceq 'python' -and $Path -cne [System.IO.Path]::GetFullPath($PythonExecutable)) {
        throw 'Python resolution differs from setup-python payload.'
    }
    return $Path
}

function Invoke-CheckedCompiler([string]$Executable, [string[]]$Arguments, [string]$LogName) {
    $LogPath = Join-Path $Output $LogName
    $CommandPath = Resolve-FoundationApplication $Executable
    $CommandHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $CommandPath).Hash
    if (-not $Receipt.runtime.ContainsKey($Executable)) {
        $Receipt.runtime[$Executable] = [ordered]@{ path=$CommandPath;
            sha256Before=$CommandHash; sha256After=$null }
    }
    if ($Receipt.runtime[$Executable].path -cne $CommandPath -or
        $Receipt.runtime[$Executable].sha256Before -cne $CommandHash) {
        throw 'Compiler/runtime selection or bytes changed before invocation.'
    }
    $ActualExecutable = $CommandPath
    if ($Receipt.runtime[$Executable].Contains('payloadPath')) {
        $ActualExecutable = $Receipt.runtime[$Executable].payloadPath
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ActualExecutable).Hash -cne
            $Receipt.runtime[$Executable].payloadSha256Before) { throw 'Actual compiler payload bytes changed before invocation.' }
    }
    $global:LASTEXITCODE = $null
    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $ActualExecutable @Arguments 2>&1 | Tee-Object -FilePath $LogPath | Out-Host
        $Code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $OldPreference }
    if ($null -eq $Code) { throw "$Executable returned no native exit code." }
    $Receipt.commands += [ordered]@{ executable=$Executable; resolvedExecutable=$ActualExecutable; arguments=$Arguments; exitCode=$Code; log=$LogName }
    if ($Code -ne 0) { throw "$Executable failed with actual exit $Code; see $LogName" }
    return $LogPath
}

function Invoke-ManagerSourceObservation([ValidateSet('Before','After')][string]$Phase) {
    try {
        $ObservationPath = Join-Path $Output "management-byte-observation-$Phase.json"
        Invoke-CheckedCompiler 'python' @($Observer,'--manager',$Manager,'--receipt',$ObservationPath) "management-byte-observation-$Phase.log" | Out-Null
        $Observed = Get-Content -Raw $ObservationPath | ConvertFrom-Json
        if (-not $Observed.diagnostic_only -or $Observed.admission -or $Observed.native_authority -or
            $Observed.transport -cne 'SUCCESS' -or $Observed.fixed_source_count -ne 7) {
            throw 'Fixed public source observation did not complete its diagnostic-only contract.'
        }
        $Receipt["managerObservation$Phase"] = $Observed
    } catch {
        if ($_.Exception -is [System.Management.Automation.PipelineStoppedException] -or
            $_.Exception -is [System.OperationCanceledException]) {
            $script:ObservationCancellation = $_.Exception
            $Receipt["managerObservation${Phase}Cancellation"] = $_.Exception.GetType().FullName
            $Receipt.managerObservationFailed = $true
            if ($Phase -ceq 'Before') { throw }
            return
        }
        $Receipt["managerObservation${Phase}Error"] = $_.Exception.Message
        $Receipt.managerObservationFailed = $true
    }
}

function Run-SourceCompile {
    if ($env:GITHUB_ACTIONS -cne 'true' -or $env:GITHUB_REPOSITORY -cne 'Eswink/coding-tools-mcp' -or
        $env:GITHUB_REF -cne 'refs/heads/probe/windows-foundation-compile-20261009-19bb2920') {
        throw 'This fixed compiler probe only runs in the named temporary GitHub branch.'
    }
    if (($Mode -eq 'rust' -and $env:RUNNER_OS -cne 'Windows') -or
        ($Mode -eq 'go' -and $env:RUNNER_OS -cne 'Linux')) { throw 'Wrong disposable runner OS.' }
    if (Get-ChildItem Env: | Where-Object { $_.Name.StartsWith('CTM_') }) {
        throw 'Native/source authorization flags are forbidden in this compiler-only probe.'
    }
    Invoke-CheckedCompiler 'git' @('--version') 'git-version.log' | Out-Null
    Invoke-CheckedCompiler 'python' @('-c','import sys; assert sys.version_info[:2] == (3, 12), sys.version; print(sys.version)') 'python-version.log' | Out-Null
    Invoke-ManagerSourceObservation 'Before'
    $ManagerBefore = Join-Path $Output 'management-before.json'
    Invoke-CheckedCompiler 'python' @($Guard,'verify-manager','--manifest',$Manifest,'--manager',$Manager,
        '--receipt',$ManagerBefore) 'management-before.log' | Out-Null
    $Receipt.managerSourceBefore = Get-Content -Raw $ManagerBefore | ConvertFrom-Json
    $Before = Join-Path $Output 'source-before.json'
    Invoke-CheckedCompiler 'python' @($Guard,'restore','--manifest',$Manifest,'--manager',$Manager,
        '--destination',$Destination,'--receipt',$Before) 'source-restore.log' | Out-Null
    $Receipt.sourceBaseline = Get-Content -Raw $Before | ConvertFrom-Json
    if ($Mode -ceq 'rust') {
        $Receipt.sourceOverlayStarted = $true
        $CandidateBefore = Join-Path $Output 'candidate-source-before.json'
        Invoke-CheckedCompiler 'python' @($InferenceOverlay,'apply','--manifest',$Manifest,'--manager',$Manager,
            '--destination',$Destination,'--receipt',$CandidateBefore) 'candidate-source-overlay.log' | Out-Null
        $Receipt.sourceBefore = Get-Content -Raw $CandidateBefore | ConvertFrom-Json
    } else { $Receipt.sourceBefore = $Receipt.sourceBaseline }
    Push-Location $Destination
    try {
        if ($Mode -eq 'go') {
            $Version = Invoke-CheckedCompiler 'go' @('version') 'go-version.log'
            if ((Get-Content -Raw $Version) -notmatch '^go version go1\.24\.13 linux/amd64') { throw 'Unexpected Go runtime.' }
            $Files = @('services/windows-vm-broker/transfer.go','services/windows-vm-broker/transfer_test.go',
                'services/windows-vm-broker/transfer_identity_linux_test.go',
                'services/windows-vm-broker/workspace_stream.go','services/windows-vm-broker/guest_workspace_control.go')
            $Receipt.compiler = 'RUNNING'
            Invoke-CheckedCompiler 'go' (@('test','-v','-count=1') + $Files) 'go5-data-test.log' | Out-Null
            $Receipt.compiler = 'DATA_TEST_PASS'
        } else {
            foreach ($Tool in @('rustc','cargo')) {
                $Which = Invoke-CheckedCompiler 'rustup' @('which','--toolchain','1.98.1',$Tool) "rustup-which-before-$Tool.log"
                $PayloadPath = (Resolve-Path -LiteralPath (Get-Content -Raw $Which).Trim()).Path
                $ProxyPath = Resolve-FoundationApplication $Tool
                $Receipt.runtime[$Tool] = [ordered]@{ path=$ProxyPath;
                    sha256Before=(Get-FileHash -Algorithm SHA256 -LiteralPath $ProxyPath).Hash; sha256After=$null;
                    payloadPath=$PayloadPath; payloadSha256Before=(Get-FileHash -Algorithm SHA256 $PayloadPath).Hash;
                    payloadSha256After=$null }
            }
            if (Get-ChildItem Env: | Where-Object { $_.Name -match '^(RUSTC(_WRAPPER|_WORKSPACE_WRAPPER)?|CARGO_BUILD_RUSTC.*)$' }) {
                throw 'Inherited compiler or wrapper override is forbidden.'
            }
            $env:RUSTC = $Receipt.runtime['rustc'].payloadPath
            $env:CARGO_INCREMENTAL = '0'
            $Version = Invoke-CheckedCompiler 'rustc' @('--version','--verbose') 'rustc-version.log'
            if ((Get-Content -Raw $Version) -notmatch 'rustc 1\.98\.1\b') { throw 'Unexpected Rust runtime.' }
            Invoke-CheckedCompiler 'cargo' @('--version','--verbose') 'cargo-version.log' | Out-Null
            $Cargo = @('test','--locked','--manifest-path','src-tauri/Cargo.toml','--lib',
                '--config','build.rustc-wrapper=""','--config','build.rustc-workspace-wrapper=""')
            $Receipt.compiler = 'RUNNING'
            Invoke-CheckedCompiler 'cargo' ($Cargo + @('--no-run')) 'cargo-whole-test-compile.log' | Out-Null
            $Receipt.compiler = 'WHOLE_TEST_COMPILE_PASS'
            $List = Invoke-CheckedCompiler 'cargo' ($Cargo + @('--','--list')) 'cargo-whole-test-list.log'
            $Allowed = @('sealed_chunks_keep_original_and_detached_owners_independent',
                'chunk_cap_and_cancel_do_not_publish_partial_copy',
                'exact_transfer_binding_rejects_each_field_mismatch',
                'invalid_wire_names_and_nil_binding_never_make_native_authority',
                'checked_close_consumes_data_only_transfer','relative_names_remain_data_not_native_permission',
                'diagnostic_metadata_cannot_authorize_output')
            $Lines = Get-Content $List
            foreach ($Case in $Allowed) {
                $MatchingLines = @($Lines | Where-Object { $_ -match ('::' + [regex]::Escape($Case) + ': test$') })
                if ($MatchingLines.Count -ne 1) { throw "Named data test absent/ambiguous: $Case" }
                $FullName = $MatchingLines[0] -replace ': test$', ''
                if ($FullName -cnotmatch '^tools::windows_vm::(input|output_stage)::') { throw 'Unexpected data test namespace.' }
                $TestLog = Invoke-CheckedCompiler 'cargo' ($Cargo + @($FullName,'--','--exact','--nocapture','--test-threads=1')) "data-$Case.log"
                if ((Get-Content -Raw $TestLog) -notmatch '1 passed; 0 failed; 0 ignored') { throw "Exact test count differs: $Case" }
            }
            $Receipt.compiler = 'WHOLE_TEST_COMPILE_AND_7_DATA_PASS'
        }
    } finally { Pop-Location }
}

try {
    Run-SourceCompile
    $Receipt.passed = $true
    $DelegateHandled = $true
} catch {
    $PrimaryFailure = $_.Exception
    $Receipt.error = $_.Exception.Message
    if ($Receipt.Contains('sourceOverlayStarted') -and
        ($_.Exception -is [System.Management.Automation.PipelineStoppedException] -or
         $_.Exception -is [System.OperationCanceledException])) {
        $SourceCancellation = $_.Exception
        $Receipt.passed = $false
        $Receipt.sourceCancellation = $_.Exception.GetType().FullName
    }
    if ($Receipt.compiler -eq 'RUNNING') { $Receipt.compiler = 'ACTUAL_FAILURE' }
    $DelegateHandled = $true
} finally {
    $DelegateInterrupted = -not $DelegateHandled
    if ($DelegateInterrupted) {
        $Receipt.passed = $false
        $Receipt.delegateInterruptedUnknown = $true
    }
    $SourceAfterHandled = $false
    $SourceGuardInterrupted = $DelegateInterrupted
    try {
        if (Test-Path (Join-Path $Destination '.git/foundation-candidate.index')) {
            try {
                $After = Join-Path $Output 'source-after.json'
                if ($Mode -ceq 'rust') {
                    Invoke-CheckedCompiler 'python' @($InferenceOverlay,'verify','--manifest',$Manifest,'--manager',$Manager,'--destination',$Destination,
                        '--receipt',$After) 'source-after.log' | Out-Null
                } else {
                    Invoke-CheckedCompiler 'python' @($Guard,'verify','--manifest',$Manifest,'--manager',$Manager,'--destination',$Destination,
                        '--receipt',$After) 'source-after.log' | Out-Null
                }
                $Receipt.sourceAfter = Get-Content -Raw $After | ConvertFrom-Json
                if ($null -eq $Receipt.sourceBefore -or
                    $Receipt.sourceAfter.source_digest -cne $Receipt.sourceBefore.source_digest) {
                    throw 'Candidate source before/after digest differs or before was not admitted.'
                }
            } catch {
                $Receipt.passed=$false; $Receipt.sourceAfterError=$_.Exception.Message
                if ($_.Exception -is [System.Management.Automation.PipelineStoppedException] -or
                    $_.Exception -is [System.OperationCanceledException]) {
                    $SourceCancellation = $_.Exception
                    $Receipt.sourceAfterCancellation = $_.Exception.GetType().FullName
                }
            }
        } else { $Receipt.passed=$false; $Receipt.sourceAfterError='No admitted source existed; compiler NOTRUN.' }
        $SourceAfterHandled = $true
    } finally {
        if (-not $SourceAfterHandled) {
            $Receipt.passed = $false
            $SourceGuardInterrupted = $true
            $Receipt.sourceAfterInterruptedUnknown = $true
            $Receipt.sourceAfterError = 'Required source-after did not finish; original native host signal propagates and completion is UNKNOWN.'
        }
    try {
        $ManagerAfter = Join-Path $Output 'management-after.json'
        Invoke-CheckedCompiler 'python' @($Guard,'verify-manager','--manifest',$Manifest,'--manager',$Manager,
            '--receipt',$ManagerAfter) 'management-after.log' | Out-Null
        $Receipt.managerSourceAfter = Get-Content -Raw $ManagerAfter | ConvertFrom-Json
        if ($null -eq $Receipt.managerSourceBefore -or
            $Receipt.managerSourceAfter.management_digest -cne $Receipt.managerSourceBefore.management_digest) {
            throw 'Management seven source bytes/modes changed or before was not admitted.'
        }
    } catch { $Receipt.passed=$false; $Receipt.managementAfterError=$_.Exception.Message }
    if ($null -eq $ObservationCancellation -and $null -eq $SourceCancellation -and -not $SourceGuardInterrupted) {
        Invoke-ManagerSourceObservation 'After'
    } else {
        $Receipt.managerObservationAfterSkipped = 'Before observation or source guard cancelled/interrupted; no new diagnostic child.'
    }
    foreach ($Executable in $Receipt.runtime.Keys) {
        try {
            $CurrentPath = Resolve-FoundationApplication $Executable
            $Runtime = $Receipt.runtime[$Executable]
            $Runtime.sha256After = (Get-FileHash -Algorithm SHA256 -LiteralPath $CurrentPath).Hash
            if ($Runtime.Contains('payloadPath')) {
                $WhichAfter = Invoke-CheckedCompiler 'rustup' @('which','--toolchain','1.98.1',$Executable) "rustup-which-after-$Executable.log"
                $PayloadAfter = (Resolve-Path -LiteralPath (Get-Content -Raw $WhichAfter).Trim()).Path
                $Runtime.payloadSha256After = (Get-FileHash -Algorithm SHA256 $PayloadAfter).Hash
                if ($PayloadAfter -cne $Runtime.payloadPath -or $Runtime.payloadSha256Before -cne $Runtime.payloadSha256After) {
                    throw 'Actual Rust toolchain payload changed during the probe.'
                }
            }
            if ($CurrentPath -cne $Runtime.path -or $Runtime.sha256Before -cne $Runtime.sha256After) {
                throw 'Compiler/runtime source changed during the probe.'
            }
        } catch { $Receipt.passed=$false; $Receipt.runtimeAfterError=$_.Exception.Message }
    }
    if ($Receipt.managerObservationFailed) { $Receipt.passed = $false }
    $Receipt | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 (Join-Path $Output 'compiler-result.json')
    }
}
if ($null -ne $SourceCancellation) {
    $Failures = [System.Collections.Generic.List[System.Exception]]::new()
    foreach ($Failure in @($PrimaryFailure, $SourceCancellation, $ObservationCancellation)) {
        if ($null -ne $Failure) {
            $AlreadyPresent = $false
            foreach ($ExistingFailure in $Failures) {
                if ([Object]::ReferenceEquals($ExistingFailure, $Failure)) { $AlreadyPresent = $true }
            }
            if (-not $AlreadyPresent) { $Failures.Add($Failure) }
        }
    }
    if ($Failures.Count -gt 1) {
        throw [System.AggregateException]::new('Original primary and source/observation cancellations were all preserved.',
            [System.Exception[]]$Failures.ToArray())
    }
    throw $SourceCancellation
}
if ($null -ne $ObservationCancellation) {
    if ($null -ne $PrimaryFailure -and -not [Object]::ReferenceEquals($PrimaryFailure, $ObservationCancellation)) {
        throw [System.AggregateException]::new('Original delegate failure and observation cancellation were both preserved.',
            [System.Exception[]]@($PrimaryFailure, $ObservationCancellation))
    }
    throw $ObservationCancellation
}
if (-not $Receipt.passed) { throw "Actual source/compiler/data probe failed. See compiler-result.json." }
