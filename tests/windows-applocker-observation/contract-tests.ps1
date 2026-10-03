# Synthetic Windows PowerShell 5.1 contracts: no pilot and no real event reader.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/observe.ps1"
$script:RealStartClock = ${function:New-AppLockerInvocationClock}
$script:RealEndClock = ${function:Complete-AppLockerInvocationClock}
$script:RealWriter = ${function:Write-AppLockerBoundedJson}
$script:Assertions = 0
$script:Variants = 0
function Assert-Contract {
    param([bool]$Condition, [string]$Label)
    $script:Assertions++
    if (-not $Condition) { throw "synthetic assertion failed: $Label" }
}

$script:Bracket = [ordered]@{ Protocol = 'applocker-invocation-bracket-v1'
    StartedUtc = '2026-10-03T07:00:00.0000000Z'; EndedUtc = '2026-10-03T07:00:01.0000000Z'; ElapsedMilliseconds = 1000 }
$script:Request = [ordered]@{ Protocol = 'applocker-prepared-request-v1'; TargetPid = 4311
    TargetPath = 'C:\ctm-direct-pilot-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\owned-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\workspace\direct.cmd'
    StartedUtc = $script:Bracket.StartedUtc; EndedUtc = $script:Bracket.EndedUtc
    OwnershipSha256 = ('1' * 64); CaseSha256 = ('2' * 64); RunSha256 = ('3' * 64)
    InvocationSha256 = ('4' * 64); QuerySha256 = $null
    Query = @'
<QueryList><Query Id="0" Path="Microsoft-Windows-AppLocker/MSI and Script"><Select Path="Microsoft-Windows-AppLocker/MSI and Script">*[System[Provider[@Name='Microsoft-Windows-AppLocker'] and (EventID=8005 or EventID=8006 or EventID=8007) and TimeCreated[@SystemTime&gt;='2026-10-03T07:00:00.0000000Z' and @SystemTime&lt;='2026-10-03T07:00:01.0000000Z']] and UserData[RuleAndFileData[PolicyName='SCRIPT' and TargetProcessId=4311 and FilePath='C:\ctm-direct-pilot-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\owned-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\workspace\direct.cmd']]]</Select></Query></QueryList>
'@
}
$sha = [Security.Cryptography.SHA256]::Create()
try { $script:Request.QuerySha256 = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($script:Request.Query)))).Replace('-', '').ToLowerInvariant() }
finally { $sha.Dispose() }
$script:RequestLine = ($script:Request | ConvertTo-Json -Depth 4 -Compress) + "`n"

function New-SyntheticResource {
    param([string]$Kind)
    $resource = [pscustomobject]@{ Kind = $Kind }
    $resource | Add-Member ScriptMethod Dispose {
        $script:Closes[$this.Kind]++
        if ($null -ne $this.PSObject.Properties['Inner']) { $this.Inner.Dispose() }
        if ($script:Fault -ceq ($this.Kind + ' close failure') -or
            ($script:DriverMode -ceq 'streamclose' -and $this.Kind -ceq 'stdout') -or
            ($script:DriverMode -ceq 'stderrclose' -and $this.Kind -ceq 'stderr') -or
            ($script:DriverMode -ceq 'captureclose' -and $this.Kind -ceq 'capture') -or
            ($script:DriverMode -ceq 'processdispose' -and $this.Kind -ceq 'process')) { throw 'synthetic close' }
    }
    return $resource
}

function New-SyntheticRecord {
    $script:RecordsCreated++
    $record = New-SyntheticResource 'record'
    $record | Add-Member NoteProperty ProviderName 'Microsoft-Windows-AppLocker'
    $record | Add-Member NoteProperty LogName 'Microsoft-Windows-AppLocker/MSI and Script'
    $record | Add-Member NoteProperty Id ([int]8007)
    $record | Add-Member NoteProperty TimeCreated ([DateTime]::Parse('2026-10-03T07:00:00.5000000Z', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime())
    $record | Add-Member NoteProperty Values @('SCRIPT', [uint32]4311, $script:Request.TargetPath)
    $record | Add-Member ScriptMethod GetPropertyValues { param($selector) return ,$this.Values }
    return $record
}

function New-SyntheticStream {
    param([string]$Kind, [byte[]]$Data)
    $stream = New-SyntheticResource $Kind
    $stream | Add-Member NoteProperty Bytes $Data
    $stream | Add-Member NoteProperty Position 0
    $stream | Add-Member ScriptMethod ReadAsync {
        param($buffer, $offset, $length)
        $count = [Math]::Min($length, $this.Bytes.Length - $this.Position)
        [Array]::Copy($this.Bytes, $this.Position, $buffer, $offset, $count)
        $this.Position += $count
        $task = [pscustomobject]@{ Checks = 0; Count = $count; Kind = $this.Kind }
        $task | Add-Member ScriptProperty IsCompleted {
            $this.Checks++
            if ($script:DriverMode -ceq 'pending' -and $this.Checks -eq 1) {
                $script:PendingDeferrals++; return $false
            }
            return $true
        }
        $task | Add-Member ScriptMethod GetAwaiter { return $this }
        $task | Add-Member ScriptMethod GetResult {
            if ($script:DriverMode -ceq ($this.Kind + 'fault')) {
                $script:AsyncFaults++; throw 'synthetic asynchronous read fault'
            }
            return $this.Count
        }
        return $task
    }
    return $stream
}

# Replace constructors, not production code. Unknown event constructors fail closed.
function New-Object {
    [CmdletBinding()]
    param([Parameter(Position=0)][string]$TypeName, [Parameter(Position=1)][object[]]$ArgumentList)
    switch -Exact ($TypeName) {
        'IO.FileStream' {
            if (-not $script:WriterRoot -or -not $ArgumentList[0].StartsWith($script:WriterRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::Ordinal)) { throw 'uncontrolled file write' }
            $file = [pscustomobject]@{ Inner = (Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList) }
            $file | Add-Member ScriptMethod Write { param($bytes, $offset, $count) $this.Inner.Write($bytes, $offset, $count) }
            $file | Add-Member ScriptMethod Flush {
                param($durable)
                Assert-Contract $durable 'durable writer flush requested'
                $this.Inner.Flush($durable)
                if ($script:WriterMode -ceq 'flush') { throw 'synthetic flush confirmation failure' }
            }
            $file | Add-Member ScriptMethod Dispose {
                $script:WriterCloses++; $this.Inner.Dispose()
                if ($script:WriterMode -ceq 'close') { throw 'synthetic close confirmation failure' }
            }
            return $file
        }
        'IO.MemoryStream' {
            $capture = New-SyntheticResource 'capture'
            $capture | Add-Member NoteProperty Inner (Microsoft.PowerShell.Utility\New-Object IO.MemoryStream)
            $capture | Add-Member ScriptProperty Length { return $this.Inner.Length }
            $capture | Add-Member ScriptMethod Write { param($buffer, $offset, $count) $this.Inner.Write($buffer, $offset, $count) }
            $capture | Add-Member ScriptMethod ToArray { return ,$this.Inner.ToArray() }
            return $capture
        }
        'Collections.Generic.HashSet[string]' {
            $set = Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
            return ,$set
        }
        'Diagnostics.Process' {
            $process = New-SyntheticResource 'process'
            $process | Add-Member NoteProperty StartInfo $null
            $process | Add-Member NoteProperty HasExited ($script:DriverMode -cnotin @('timeout', 'killfailure'))
            $process | Add-Member NoteProperty ExitCode $(if ($script:DriverMode -ceq 'nonzero') { 1 } else { 0 })
            $stdout = $script:RequestLine
            if ($script:DriverMode -ceq 'badjson') { $stdout = "{}\n" }
            if ($script:DriverMode -ceq 'extra') { $stdout += "{}\n" }
            if ($script:DriverMode -ceq 'duplicatefirst') { $stdout = $stdout.Replace('{', '{"Protocol":"bad",') }
            if ($script:DriverMode -ceq 'duplicatelast') { $stdout = $stdout.Insert($stdout.LastIndexOf('}'), ',"Protocol":"bad"') }
            if ($script:DriverMode -ceq 'escapedkey') { $stdout = $stdout.Replace('"Protocol":', '"\u0050rotocol":') }
            if ($script:DriverMode -ceq 'casecollision') { $stdout = $stdout.Replace('{', '{"protocol":"bad",') }
            if ($script:DriverMode -ceq 'unknownkey') { $stdout = $stdout.Replace('{', '{"Accepted":"yes",') }
            if ($script:DriverMode -ceq 'pidbool') { $stdout = $stdout.Replace('"TargetPid":4311', '"TargetPid":true') }
            if ($script:DriverMode -ceq 'wronghash') { $stdout = $stdout.Replace($script:Request.QuerySha256, ('0' * 64)) }
            if ($script:DriverMode -cin @('protocolignorable', 'protocolnul', 'querycomposed', 'queryignorable', 'querynul')) {
                $variant = $script:RequestLine | ConvertFrom-Json
                switch ($script:DriverMode) {
                    'protocolignorable' { $variant.Protocol += [char]0x00ad }
                    'protocolnul' { $variant.Protocol += [char]0 }
                    'querycomposed' {
                        $composed = 'C:\caf' + [char]0x00e9 + '\' + $script:Request.TargetPath.Substring(3)
                        $variant.TargetPath = 'C:\cafe' + [char]0x0301 + '\' + $script:Request.TargetPath.Substring(3)
                        $variant.Query = $variant.Query.Replace($script:Request.TargetPath, $composed)
                    }
                    'queryignorable' { $variant.Query = $variant.Query.Replace("PolicyName='SCRIPT'", ("PolicyName='SCRIPT" + [char]0x00ad + "'")) }
                    'querynul' { $variant.Query = $variant.Query.Replace("PolicyName='SCRIPT'", ("PolicyName='SCRIPT" + [char]0 + "'")) }
                }
                $hash = [Security.Cryptography.SHA256]::Create()
                try { $variant.QuerySha256 = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($variant.Query)))).Replace('-', '').ToLowerInvariant() }
                finally { $hash.Dispose() }
                $stdout = ($variant | ConvertTo-Json -Depth 4 -Compress) + "`n"
                $stdout = [regex]::Replace($stdout, '[^\x00-\x7f]', [Text.RegularExpressions.MatchEvaluator]{
                    param($match) return '\u' + ([int][char]$match.Value).ToString('x4')
                })
            }
            if ($script:DriverMode -ceq 'stdoutoverflow') { $stdout = 'x' * 131073 }
            $stderr = if ($script:DriverMode -ceq 'stderroverflow') { 'e' * 4097 }
                elseif ($script:DriverMode -ceq 'stderr') { 'e' } else { '' }
            $process | Add-Member NoteProperty StandardOutput ([pscustomobject]@{ BaseStream = (New-SyntheticStream 'stdout' ([Text.Encoding]::UTF8.GetBytes($stdout))) })
            $process | Add-Member NoteProperty StandardError ([pscustomobject]@{ BaseStream = (New-SyntheticStream 'stderr' ([Text.Encoding]::UTF8.GetBytes($stderr))) })
            $process | Add-Member ScriptMethod Start {
                $script:HelperStarts++
                Assert-Contract (-not $this.StartInfo.UseShellExecute) 'managed helper does not use a shell'
                Assert-Contract ($this.StartInfo.Arguments.StartsWith('-I "') -and $this.StartInfo.Arguments.EndsWith('prepare_query.py"')) 'fixed isolated helper'
                return $true
            }
            $process | Add-Member ScriptMethod WaitForExit {
                param($timeout)
                if ($timeout -eq 10) { $script:HelperPolls++ }
                return $this.HasExited
            }
            $process | Add-Member ScriptMethod Kill {
                $script:HelperKills++
                if ($script:DriverMode -ceq 'killfailure') { throw 'synthetic stop failure' }
                $this.HasExited = $true
            }
            return $process
        }
        'Diagnostics.Stopwatch' {
            $timer = [pscustomobject]@{ ElapsedMilliseconds = $(if ($script:DriverMode -cin @('timeout', 'killfailure')) { 10000 } else { 0 }) }
            $timer | Add-Member ScriptMethod Start { }
            return $timer
        }
        'Diagnostics.Eventing.Reader.EventLogQuery' {
            $script:QueryAttempts++
            if ($script:Fault -ceq 'query creation failure') { throw 'synthetic query failure' }
            Assert-Contract ($ArgumentList[0] -ceq 'Microsoft-Windows-AppLocker/MSI and Script') 'single fixed local channel'
            Assert-Contract ($ArgumentList[2] -ceq $script:Request.Query) 'complete validated query passed intact'
            return [pscustomobject]@{ TolerateQueryErrors = $true }
        }
        'Diagnostics.Eventing.Reader.EventLogReader' {
            $script:ReaderCreated++
            Assert-Contract (-not $ArgumentList[0].TolerateQueryErrors) 'query error tolerance disabled'
            $reader = New-SyntheticResource 'reader'
            $reader | Add-Member NoteProperty BatchSize 64
            $reader | Add-Member ScriptMethod ReadEvent {
                param($timeout)
                Assert-Contract ($this.BatchSize -eq 1) 'batch size set before read'
                Assert-Contract ($timeout.TotalMilliseconds -eq 2000) 'read timeout fixed'
                $script:Reads++
                if (($script:Fault -ceq 'first read failure' -and $script:Reads -eq 1) -or
                    ($script:Fault -ceq 'second read failure' -and $script:Reads -eq 2)) { throw 'synthetic read failure' }
                if ($script:RecordMode -ceq 'access') { throw (Microsoft.PowerShell.Utility\New-Object UnauthorizedAccessException) }
                if ($script:RecordMode -ceq 'timeout') { throw (Microsoft.PowerShell.Utility\New-Object TimeoutException) }
                if ($script:RecordMode -ceq 'missing') { throw (Microsoft.PowerShell.Utility\New-Object Diagnostics.Eventing.Reader.EventLogNotFoundException) }
                if ($script:RecordMode -ceq 'zero') { return $null }
                if ($script:Reads -eq 1 -or $script:RecordMode -ceq 'multiple') { return New-SyntheticRecord }
                return $null
            }
            return $reader
        }
        'Diagnostics.Eventing.Reader.EventLogPropertySelector' {
            $paths = @($ArgumentList[0])
            Assert-Contract ($paths.Count -eq 3) 'three fixed selected properties'
            Assert-Contract (($paths -join '|') -ceq 'Event/UserData/RuleAndFileData/PolicyName|Event/UserData/RuleAndFileData/TargetProcessId|Event/UserData/RuleAndFileData/FilePath') 'no message or unrelated fields'
            return New-SyntheticResource 'selector'
        }
        default {
            if ($TypeName -cnotin @('System.Text.UTF8Encoding', 'Text.UTF8Encoding', 'Diagnostics.ProcessStartInfo',
                'IO.MemoryStream', 'byte[]', 'Xml.XmlDocument')) { throw 'unmocked constructor forbidden' }
            if ($null -eq $ArgumentList -or $ArgumentList.Count -eq 0) {
                return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName
            }
            return Microsoft.PowerShell.Utility\New-Object -TypeName $TypeName -ArgumentList $ArgumentList
        }
    }
}

function New-AppLockerInvocationClock {
    if ($script:Fault -ceq 'start clock failure') { throw 'synthetic start failure' }
    return [pscustomobject]@{ StartedUtc = $script:Bracket.StartedUtc; Stamp = 1 }
}
function Complete-AppLockerInvocationClock {
    param($Clock)
    $script:EndSamples++
    Set-Variable -Name LASTEXITCODE -Scope Global -Value 902
    if ($script:Fault -ceq 'end clock failure') { throw 'synthetic end failure' }
    return $script:Bracket
}
function Write-AppLockerBoundedJson {
    param($RepositoryRoot, $Name, $Value)
    Assert-Contract ($script:EndSamples -eq 1) 'end sampled before observation work'
    Set-Variable -Name LASTEXITCODE -Scope Global -Value 901
    if ($Name -ceq 'invocation.json' -and $script:DriverMode -cin @('reasonignorable', 'reasonnul')) {
        $suffix = if ($script:DriverMode -ceq 'reasonnul') { [char]0 } else { [char]0x00ad }
        throw ('access_denied' + $suffix)
    }
    if ($Name -ceq 'observation.json') {
        $script:Summary = $Value
        if ($script:Fault -ceq 'summary write failure') { throw 'synthetic write failure' }
    } else { Assert-Contract ($Name -ceq 'invocation.json') 'only fixed sibling names' }
}
function Invoke-SyntheticLoad {
    if ($script:Fault -ceq 'observer setup failure') { throw 'synthetic setup failure' }
}
function Invoke-SyntheticPilot {
    [CmdletBinding()]
    param()
    $script:PilotCalls++
    if ($script:PilotMode -ceq 'nonzero') { Set-Variable -Name LASTEXITCODE -Scope Global -Value 23 }
    if ($script:PilotMode -ceq 'throw') { $PSCmdlet.ThrowTerminatingError($script:PilotError) }
}

$workflowPath = Join-Path $PSScriptRoot '../../.github/workflows/windows-lpac-runtime-diagnostic.yml'
$workflow = [IO.File]::ReadAllText($workflowPath)
$block = [regex]::Match($workflow, '(?s)# APPLOCKER_OUTER_BEGIN\r?\n(.*?)\r?\n\s*# APPLOCKER_OUTER_END')
Assert-Contract $block.Success 'actual workflow wrapper is present'
$wrapper = [regex]::Replace($block.Groups[1].Value, '(?m)^          ', '')
$literalPilot = '& tests/windows-broker-direct/run-pilot.ps1 -Fixture tests/windows-lpac-runtime/target/debug/windows_sandbox_fixture.exe -Payload "$env:RUNNER_TEMP/lpac-runtime-payload" -Evidence evidence/pilot -Foundation evidence/foundation'
Assert-Contract (($wrapper.Split(@($literalPilot), [StringSplitOptions]::None)).Count -eq 2) 'unchanged pilot literal occurs once'
$wrapper = $wrapper.Replace($literalPilot, 'Invoke-SyntheticPilot')
$literalLoad = '. tests/windows-applocker-observation/observe.ps1'
Assert-Contract (($wrapper.Split(@($literalLoad), [StringSplitOptions]::None)).Count -eq 2) 'one fixed helper load'
$wrapper = $wrapper.Replace($literalLoad, 'Invoke-SyntheticLoad')
Assert-Contract ($wrapper -notmatch 'run-pilot\.ps1|tests/windows-applocker-observation/observe\.ps1') 'only synthetic pilot and load remain'
$script:WrapperBlock = [scriptblock]::Create($wrapper)
Assert-Contract ($wrapper -is [string]) 'workflow wrapper text stays a string'
Assert-Contract ($script:WrapperBlock -is [scriptblock]) 'compiled wrapper stays a ScriptBlock'
$script:SavedPython = $env:APPLOCKER_PYTHON
$env:APPLOCKER_PYTHON = 'C:\fixed-setup-python\python.exe'

function Invoke-SyntheticCase {
    param([string]$Fault, [string]$PilotMode, [string]$DriverMode = 'normal', [string]$RecordMode = 'normal', [switch]$RestorationFailure)
    $script:Variants++
    $script:Fault = $Fault; $script:PilotMode = $PilotMode
    $script:DriverMode = $DriverMode; $script:RecordMode = $RecordMode
    $script:Closes = @{}; $script:Summary = $null; $script:PilotCalls = 0
    $script:QueryAttempts = 0; $script:ReaderCreated = 0; $script:Reads = 0
    $script:RecordsCreated = 0
    $script:HelperPolls = 0; $script:PendingDeferrals = 0; $script:AsyncFaults = 0
    $script:HelperStarts = 0; $script:HelperKills = 0; $script:EndSamples = 0
    $exception = Microsoft.PowerShell.Utility\New-Object -TypeName InvalidOperationException -ArgumentList 'synthetic pilot identity'
    $script:PilotError = Microsoft.PowerShell.Utility\New-Object -TypeName Management.Automation.ErrorRecord -ArgumentList @(
        $exception, 'original-pilot', [Management.Automation.ErrorCategory]::InvalidOperation, 'synthetic-target')
    Remove-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if ($PilotMode -cne 'absent') { Set-Variable -Name LASTEXITCODE -Scope Global -Value $(if ($PilotMode -ceq 'zero') { 0 } else { 17 }) }
    $caught = $null
    try { & $script:WrapperBlock } catch { $caught = $_ }
    Assert-Contract ($script:PilotCalls -eq 1) 'pilot called exactly once despite observer failure'
    if ($PilotMode -ceq 'throw') {
        Assert-Contract ($null -ne $caught) 'original throw survives'
        Assert-Contract ([object]::ReferenceEquals($caught.Exception, $script:PilotError.Exception)) 'exception object identity'
        Assert-Contract ($caught.CategoryInfo.Category -eq [Management.Automation.ErrorCategory]::InvalidOperation) 'original error category'
        Assert-Contract ($caught.Exception.Message -ceq 'synthetic pilot identity') 'original error message'
        Assert-Contract ($caught.FullyQualifiedErrorId -like 'original-pilot,*') 'original error identifier'
    } else { Assert-Contract ($null -eq $caught) 'observer error cannot replace normal/native result' }
    $exitState = Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue
    if (-not $RestorationFailure) {
        Assert-Contract (($null -ne $exitState) -eq ($PilotMode -cne 'absent')) 'exit variable presence preserved'
    }
    if ($PilotMode -cne 'absent' -and -not $RestorationFailure) {
        $expected = if ($PilotMode -ceq 'nonzero') { 23 } elseif ($PilotMode -ceq 'zero') { 0 } else { 17 }
        Assert-Contract ($exitState.Value -eq $expected) 'exit variable value preserved'
    }
    if ($Fault -cin @('observer setup failure', 'start clock failure', 'end clock failure', 'capture failure')) {
        Assert-Contract ($script:ReaderCreated -eq 0 -and $null -eq $script:Summary) 'failed setup/sampling forbids query'
        if ($Fault -ceq 'capture failure') {
            Assert-Contract ($script:EndSamples -eq 0 -and $script:HelperStarts -eq 0 -and $script:QueryAttempts -eq 0) 'failed exit capture skips all observation work'
        }
    } elseif ($DriverMode -cnotin @('normal', 'pending')) {
        Assert-Contract ($script:QueryAttempts -eq 0) 'invalid/unclosed helper never reaches query construction'
        Assert-Contract ($script:Summary.Status -ceq 'inconclusive' -and $null -eq $script:Summary.Decision) 'helper failure emits no decision'
        if ($DriverMode -cin @('killfailure', 'streamclose', 'stderrclose', 'captureclose', 'processdispose')) { Assert-Contract ($script:Summary.Reason -ceq 'close_uncertain') 'uncertain helper close is explicit' }
        if ($DriverMode -cin @('timeout', 'killfailure')) { Assert-Contract ($script:HelperKills -eq 1) 'only newly owned helper kill attempted once' }
    } elseif ($Fault -cne 'normal' -and $Fault -cne 'summary write failure') {
        Assert-Contract ($script:Summary.Status -ceq 'inconclusive' -and $null -eq $script:Summary.Decision) 'observer failure clears decision'
    } elseif ($RecordMode -ceq 'normal') {
        Assert-Contract ($script:Summary.Status -ceq 'raw_matched') 'one synthetic match plus EOF'
        Assert-Contract ($script:Summary.Decision.EventId -eq 8007) 'minimal synthetic decision'
    } else { Assert-Contract ($script:Summary.Status -ceq 'inconclusive') 'nonmatching or failed read remains inconclusive' }
    if ($DriverMode -ceq 'pending') {
        Assert-Contract ($script:PendingDeferrals -ge 2 -and $script:HelperPolls -ge 1) 'both pipes remain pending for a poll then complete'
    }
    if ($DriverMode -cin @('stdoutfault', 'stderrfault')) { Assert-Contract ($script:AsyncFaults -eq 1) 'faulted read observed from GetResult' }
    if ($DriverMode -cin @('reasonignorable', 'reasonnul')) {
        Assert-Contract ([string]::Equals($script:Summary.Reason, 'evidence_write_failed', [StringComparison]::Ordinal)) 'noncanonical reason text is discarded'
    }
    if ($script:HelperStarts -eq 1) {
        foreach ($kind in @('stdout', 'stderr', 'capture', 'process')) {
            Assert-Contract ($script:Closes[$kind] -eq 1) "owned helper $kind disposed exactly once"
        }
    }
    Assert-Contract ($script:Reads -le 2) 'maximum two read calls'
    Assert-Contract ([int]$script:Closes['record'] -eq $script:RecordsCreated) 'each returned record disposed exactly once'
    foreach ($kind in @('selector', 'reader')) {
        if ($script:ReaderCreated -eq 1) { Assert-Contract ($script:Closes[$kind] -eq 1) 'reader resources disposed exactly once' }
    }
}

$scenarios = @('normal return', 'pilot throw', 'native nonzero', 'absent exit variable', 'present zero exit variable',
    'observer setup failure', 'start clock failure', 'end clock failure', 'driver failure', 'query creation failure',
    'first read failure', 'second read failure', 'record close failure', 'selector close failure', 'reader close failure', 'summary write failure')
try {
    foreach ($scenario in $scenarios) {
        switch -Exact ($scenario) {
            'normal return' {
                Invoke-SyntheticCase 'normal' 'normal'
                Invoke-SyntheticCase 'normal' 'normal' 'pending'
            }
            'pilot throw' {
                Invoke-SyntheticCase 'normal' 'throw'
                # A failed restoration cannot replace the pending pilot exception.
                # Deliberately failed restoration makes no value-preservation claim.
                $savedWrapper = $script:WrapperBlock
                $restore = 'Set-Variable -Name LASTEXITCODE -Scope Global -Value $appLockerExitValue'
                $script:WrapperBlock = [scriptblock]::Create($wrapper.Replace($restore, "throw 'synthetic restore failure'"))
                try { Invoke-SyntheticCase 'normal' 'throw' 'normal' 'normal' -RestorationFailure }
                finally { $script:WrapperBlock = $savedWrapper }
                $capture = '$appLockerExitState=Get-Variable -Name LASTEXITCODE -Scope Global -ErrorAction SilentlyContinue'
                Assert-Contract ($wrapper.Contains($capture)) 'actual exit-state capture is present'
                $script:WrapperBlock = [scriptblock]::Create($wrapper.Replace($capture, "throw 'synthetic capture failure'"))
                try { Invoke-SyntheticCase 'capture failure' 'throw' }
                finally { $script:WrapperBlock = $savedWrapper }
            }
            'native nonzero' { Invoke-SyntheticCase 'normal' 'nonzero' }
            'absent exit variable' { Invoke-SyntheticCase 'normal' 'absent' }
            'present zero exit variable' { Invoke-SyntheticCase 'normal' 'zero' }
            'driver failure' {
                foreach ($mode in @('badjson', 'extra', 'duplicatefirst', 'duplicatelast', 'escapedkey', 'casecollision',
                    'unknownkey', 'pidbool', 'wronghash', 'nonzero', 'stderr', 'stdoutoverflow', 'stderroverflow',
                    'timeout', 'killfailure', 'streamclose', 'stderrclose', 'captureclose', 'processdispose',
                    'stdoutfault', 'stderrfault', 'reasonignorable', 'reasonnul', 'protocolignorable', 'protocolnul',
                    'querycomposed', 'queryignorable', 'querynul')) {
                    foreach ($pilot in @('throw', 'nonzero')) { Invoke-SyntheticCase $scenario $pilot $mode }
                }
            }
            default { foreach ($pilot in @('throw', 'nonzero')) { Invoke-SyntheticCase $scenario $pilot } }
        }
        Write-Output "PASS synthetic scenario: $scenario"
    }
    foreach ($mode in @('zero', 'multiple', 'access', 'missing', 'timeout')) {
        foreach ($pilot in @('throw', 'nonzero')) { Invoke-SyntheticCase 'normal' $pilot 'normal' $mode }
    }
    # Direct selected-field negatives use only fake records; no native query exists here.
    foreach ($field in @('policy', 'pid', 'pidbool', 'pidstring', 'pidzero', 'pidover', 'pidfraction', 'path', 'provider', 'channel', 'id', 'idstring', 'time', 'extra', 'normalization', 'pathignorable', 'pathnul', 'policyignorable', 'providerignorable', 'channelignorable')) {
        $record = New-SyntheticRecord
        $recordRequest = [pscustomobject]@{ TargetPid = 4311; TargetPath = $script:Request.TargetPath; StartedUtc = $script:Request.StartedUtc; EndedUtc = $script:Request.EndedUtc }
        switch ($field) {
            'policy' { $record.Values[0] = 'script' }
            'pid' { $record.Values[1] = [uint32]4312 }
            'pidbool' { $record.Values[1] = $true }
            'pidstring' { $record.Values[1] = '4311' }
            'pidzero' { $record.Values[1] = 0 }
            'pidover' { $record.Values[1] = [uint32]2147483648 }
            'pidfraction' { $record.Values[1] = 4311.5 }
            'path' { $record.Values[2] = $script:Request.TargetPath.ToLowerInvariant() }
            'provider' { $record.ProviderName = 'wrong' }
            'channel' { $record.LogName = 'wrong' }
            'id' { $record.Id = 8004 }
            'idstring' { $record.Id = '8007' }
            'time' { $record.TimeCreated = [DateTime]::Parse('2026-10-03T07:00:01.0000001Z', [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime() }
            'extra' { $record.Values += 'unrequested' }
            'normalization' { $recordRequest.TargetPath = 'C:\caf' + [char]0x00e9 + '\direct.cmd'; $record.Values[2] = 'C:\cafe' + [char]0x0301 + '\direct.cmd' }
            'pathignorable' { $record.Values[2] += [char]0x00ad }
            'pathnul' { $record.Values[2] += [char]0 }
            'policyignorable' { $record.Values[0] += [char]0x00ad }
            'providerignorable' { $record.ProviderName += [char]0x00ad }
            'channelignorable' { $record.LogName += [char]0x00ad }
        }
        $failed = $false
        try { $null = Test-AppLockerMatchedFields $record $null $recordRequest } catch { $failed = $true }
        Assert-Contract $failed "reject selected record $field"
    }
    $record = New-SyntheticRecord
    $unicodePath = 'C:\caf' + [char]0x00e9 + '\direct.cmd'
    $record.Values[2] = $unicodePath
    $recordRequest = [pscustomobject]@{ TargetPid = 4311; TargetPath = $unicodePath; StartedUtc = $script:Request.StartedUtc; EndedUtc = $script:Request.EndedUtc }
    $decision = Test-AppLockerMatchedFields $record $null $recordRequest
    Assert-Contract ($decision.EventId -eq 8007) 'identical Unicode code points remain valid'
    foreach ($endpoint in @($script:Request.StartedUtc, $script:Request.EndedUtc)) {
        $record = New-SyntheticRecord
        $record.TimeCreated = [DateTime]::Parse($endpoint, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
        $decision = Test-AppLockerMatchedFields $record $null ([pscustomobject]$script:Request)
        Assert-Contract ($decision.Utc -ceq $endpoint) 'inclusive exact 100ns endpoint'
    }
    $culture = [Threading.Thread]::CurrentThread.CurrentCulture
    try {
        [Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::GetCultureInfo('th-TH')
        $clock = & $script:RealStartClock
        $bracket = & $script:RealEndClock -Clock $clock
        Assert-Contract ($bracket.StartedUtc.StartsWith([DateTime]::UtcNow.Year.ToString([Globalization.CultureInfo]::InvariantCulture))) 'Gregorian invariant clock year'
        $record = New-SyntheticRecord
        $decision = Test-AppLockerMatchedFields $record $null ([pscustomobject]$script:Request)
        Assert-Contract ($decision.Utc -ceq '2026-10-03T07:00:00.5000000Z') 'invariant selected record time'
    } finally { [Threading.Thread]::CurrentThread.CurrentCulture = $culture }
    # Exercise the actual writer with complete favorable synthetic bytes in fresh local directories.
    Invoke-SyntheticCase 'normal' 'normal'
    $value = $script:Summary
    Assert-Contract ($value.Status -ceq 'raw_matched') 'persistence fixture has a favorable complete summary'
    $expectedBytes = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(($value | ConvertTo-Json -Depth 8 -Compress)))
    foreach ($writerMode in @('success', 'flush', 'close', 'rename')) {
        $script:WriterMode = $writerMode; $script:WriterCloses = 0
        $script:WriterRoot = [IO.Path]::Combine([IO.Path]::GetTempPath(), ('applocker-contract-' + [Guid]::NewGuid().ToString('N')))
        $directory = [IO.Path]::Combine($script:WriterRoot, 'evidence/applocker-observation')
        [void][IO.Directory]::CreateDirectory($directory)
        $pending = [IO.Path]::Combine($directory, 'observation-pending.json')
        $final = [IO.Path]::Combine($directory, 'observation.json')
        if ($writerMode -ceq 'rename') { [IO.File]::WriteAllText($final, 'unchanged sentinel') }
        $failed = $false
        try { & $script:RealWriter -RepositoryRoot $script:WriterRoot -Name 'observation.json' -Value $value } catch { $failed = $true }
        Assert-Contract ($failed -eq ($writerMode -cne 'success')) 'writer failure is not reported as success'
        Assert-Contract ($script:WriterCloses -eq 1) 'actual writer closes its one stream once'
        $persisted = if ($writerMode -ceq 'success') { $final } else { $pending }
        Assert-Contract ([string]::Equals([Convert]::ToBase64String([IO.File]::ReadAllBytes($persisted)), $expectedBytes, [StringComparison]::Ordinal)) 'complete exact UTF8 bytes survive at the expected name'
        Assert-Contract ([IO.File]::Exists($pending) -eq ($writerMode -cne 'success')) 'only successful publication removes the pending name'
        if ($writerMode -ceq 'rename') {
            Assert-Contract ([string]::Equals([IO.File]::ReadAllText($final), 'unchanged sentinel', [StringComparison]::Ordinal)) 'rename conflict never replaces existing final'
        } else { Assert-Contract ([IO.File]::Exists($final) -eq ($writerMode -ceq 'success')) 'flush and close failures never publish final' }
    }
    # Preserve temporary pending states without cleanup, repair, or retry.
    Assert-Contract ($scenarios.Count -eq 16) 'exact named scenario count'
    Write-Output "AppLocker synthetic contracts: $($scenarios.Count) named scenarios; $script:Variants wrapper variants; $script:Assertions assertions. No real event query or pilot."
} finally {
    $script:WriterRoot = $null
    $env:APPLOCKER_PYTHON = $script:SavedPython
}
