# Function-only, Windows PowerShell 5.1. This observer does not run the pilot.
function New-AppLockerInvocationClock {
    $utc = [DateTime]::UtcNow
    $stamp = [Diagnostics.Stopwatch]::GetTimestamp()
    [pscustomobject]@{ StartedUtc = $utc.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ', [Globalization.CultureInfo]::InvariantCulture); Stamp = $stamp }
}

function Complete-AppLockerInvocationClock {
    param($Clock)
    # End samples precede validation, serialization, helper launch, and event acquisition.
    $utc = [DateTime]::UtcNow
    $stamp = [Diagnostics.Stopwatch]::GetTimestamp()
    if ($null -eq $Clock -or $stamp -lt $Clock.Stamp) { throw 'bracket_invalid' }
    $elapsed = [Math]::Floor(($stamp - $Clock.Stamp) * 1000.0 / [Diagnostics.Stopwatch]::Frequency)
    if ($elapsed -lt 0 -or $elapsed -gt 900000) { throw 'bracket_invalid' }
    [ordered]@{ Protocol = 'applocker-invocation-bracket-v1'; StartedUtc = $Clock.StartedUtc
        EndedUtc = $utc.ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ', [Globalization.CultureInfo]::InvariantCulture); ElapsedMilliseconds = [long]$elapsed }
}

function Write-AppLockerBoundedJson {
    param([string]$RepositoryRoot, [string]$Name, $Value)
    $ErrorActionPreference = 'Stop'
    $invocation = [string]::Equals($Name, 'invocation.json', [StringComparison]::Ordinal)
    if (-not $invocation -and -not [string]::Equals($Name, 'observation.json', [StringComparison]::Ordinal)) { throw 'evidence_write_failed' }
    $limit = if ($invocation) { 4096 } else { 16384 }
    $encoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList @($false, $true)
    $bytes = $encoding.GetBytes(($Value | ConvertTo-Json -Depth 8 -Compress))
    if ($bytes.Length -gt $limit) { throw 'evidence_write_failed' }
    $evidence = [IO.Path]::Combine($RepositoryRoot, 'evidence')
    $directory = [IO.Path]::Combine($evidence, 'applocker-observation')
    foreach ($path in @($evidence, $directory)) {
        [void][IO.Directory]::CreateDirectory($path)
        if (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'evidence_write_failed'
        }
    }
    $finalPath = [IO.Path]::Combine($directory, $Name)
    $writePath = if ($invocation) { $finalPath } else { [IO.Path]::Combine($directory, 'observation-pending.json') }
    $stream = $null
    try {
        $stream = New-Object -TypeName IO.FileStream -ArgumentList @($writePath,
            [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        if ($null -ne $stream) { $stream.Dispose() }
    }
    # Two-argument File.Move does not overwrite; publish only after confirmed close.
    if (-not $invocation) { [IO.File]::Move($writePath, $finalPath) }
}

function Get-AppLockerPreparedRequest {
    param([string]$PythonPath, [string]$RepositoryRoot)
    $ErrorActionPreference = 'Stop'
    $reason = 'setup_unavailable'
    $process = $null; $started = $false; $stopped = $false; $closed = $true
    $outputStream = $null; $errorStream = $null; $capture = $null
    try {
        if (-not [IO.Path]::IsPathRooted($PythonPath) -or $PythonPath.Contains('"')) { throw 'fixed_helper' }
        $driver = [IO.Path]::Combine($RepositoryRoot, 'tests\windows-applocker-observation\prepare_query.py')
        if (-not [IO.Path]::IsPathRooted($driver) -or $driver.Contains('"')) { throw 'fixed_helper' }
        $info = New-Object Diagnostics.ProcessStartInfo
        $info.FileName = $PythonPath
        $info.Arguments = '-I "' + $driver + '"'
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $info.WorkingDirectory = $RepositoryRoot
        $process = New-Object Diagnostics.Process
        $process.StartInfo = $info
        $timer = New-Object Diagnostics.Stopwatch
        $timer.Start()
        if (-not $process.Start()) { throw 'fixed_helper' }
        $started = $true
        $reason = 'request_invalid'
        $outputStream = $process.StandardOutput.BaseStream
        $errorStream = $process.StandardError.BaseStream
        $capture = New-Object IO.MemoryStream
        $outBuffer = New-Object byte[] 8192
        $errBuffer = New-Object byte[] 4096
        $outTask = $outputStream.ReadAsync($outBuffer, 0, $outBuffer.Length)
        $errTask = $errorStream.ReadAsync($errBuffer, 0, $errBuffer.Length)
        $outDone = $false; $errDone = $false; $stderrCount = 0
        # Only this new owned helper is supervised. Both pipes are drained concurrently.
        while (-not ($outDone -and $errDone -and $process.HasExited)) {
            if ($timer.ElapsedMilliseconds -ge 10000) { throw 'helper_timeout' }
            if (-not $outDone -and $outTask.IsCompleted) {
                $count = $outTask.GetAwaiter().GetResult()
                if ($count -eq 0) { $outDone = $true }
                else {
                    if ($capture.Length + $count -gt 131072) { throw 'stdout_overflow' }
                    $capture.Write($outBuffer, 0, $count)
                    $outTask = $outputStream.ReadAsync($outBuffer, 0, [int][Math]::Min($outBuffer.Length, 131073 - $capture.Length))
                }
            }
            if (-not $errDone -and $errTask.IsCompleted) {
                $count = $errTask.GetAwaiter().GetResult()
                $stderrCount += $count
                if ($stderrCount -gt 4096) { throw 'stderr_overflow' }
                if ($count -eq 0) { $errDone = $true }
                else { $errTask = $errorStream.ReadAsync($errBuffer, 0, [int][Math]::Min($errBuffer.Length, 4097 - $stderrCount)) }
            }
            [void]$process.WaitForExit(10)
        }
        $stopped = $process.HasExited
        if (-not $stopped -or $process.ExitCode -ne 0 -or $stderrCount -ne 0) { throw 'helper_failed' }
        $bytes = $capture.ToArray()
    } catch {
        $bytes = $null
    } finally {
        if ($started -and -not $stopped) {
            try {
                if (-not $process.HasExited) { $process.Kill() }
                $stopped = $process.WaitForExit(1000) -and $process.HasExited
            } catch { $stopped = $false }
        }
        foreach ($resource in @($outputStream, $errorStream, $capture, $process)) {
            if ($null -ne $resource) {
                try { $resource.Dispose() } catch { $closed = $false }
            }
        }
    }
    if (-not $closed -or ($started -and -not $stopped)) { throw 'close_uncertain' }
    if ($null -eq $bytes) { throw $reason }
    try {
        $encoding = New-Object -TypeName Text.UTF8Encoding -ArgumentList @($false, $true)
        $text = $encoding.GetString($bytes)
        if ($text -cmatch '[^\x00-\x7f]' -or $text.Length -lt 3 -or -not $text.StartsWith('{', [StringComparison]::Ordinal) -or -not $text.EndsWith("}`n", [StringComparison]::Ordinal) -or
            $text.Substring(0, $text.Length - 1).Contains("`n") -or $text.Contains("`r")) { throw 'line' }
        $keys = @('Protocol', 'TargetPid', 'TargetPath', 'StartedUtc', 'EndedUtc', 'OwnershipSha256',
            'CaseSha256', 'RunSha256', 'InvocationSha256', 'QuerySha256', 'Query')
        # The private request is one flat object. Reject duplicates before ConvertFrom-Json.
        $quoted = '"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"'
        $pair = '"(?<key>' + ($keys -join '|') + ')":(?:' + $quoted + '|0|[1-9][0-9]*)'
        if ($text -cnotmatch ('\A\{' + $pair + '(?:,' + $pair + ')*\}\n\z')) { throw 'shape' }
        $matches = [regex]::Matches($text, '(?:\{|,)' + $pair)
        $rawNames = @($matches | ForEach-Object { $_.Groups['key'].Value })
        $allowedKeys = New-Object 'Collections.Generic.HashSet[string]' -ArgumentList ([StringComparer]::Ordinal)
        $seenKeys = New-Object 'Collections.Generic.HashSet[string]' -ArgumentList ([StringComparer]::Ordinal)
        foreach ($key in $keys) { [void]$allowedKeys.Add($key) }
        if ($rawNames.Count -ne $keys.Count) { throw 'duplicate' }
        foreach ($name in $rawNames) { if (-not $seenKeys.Add($name)) { throw 'duplicate' } }
        $request = $text | ConvertFrom-Json -ErrorAction Stop
        $names = @($request.PSObject.Properties.Name)
        if ($names.Count -ne $keys.Count -or @($names | Where-Object { -not $allowedKeys.Contains($_) }).Count) { throw 'keys' }
        if (-not [string]::Equals($request.Protocol, 'applocker-prepared-request-v1', [StringComparison]::Ordinal)) { throw 'protocol' }
        if (($request.TargetPid -isnot [int] -and $request.TargetPid -isnot [long]) -or
            $request.TargetPid -lt 1 -or $request.TargetPid -gt [int]::MaxValue) { throw 'pid' }
        foreach ($key in $keys | Where-Object { -not [string]::Equals($_, 'TargetPid', [StringComparison]::Ordinal) }) {
            if ($request.$key -isnot [string]) { throw 'type' }
        }
        foreach ($key in @('OwnershipSha256', 'CaseSha256', 'RunSha256', 'InvocationSha256', 'QuerySha256')) {
            if ($request.$key -cnotmatch '\A[0-9a-f]{64}\z') { throw 'hash' }
        }
        $culture = [Globalization.CultureInfo]::InvariantCulture
        $style = [Globalization.DateTimeStyles]::AssumeUniversal -bor [Globalization.DateTimeStyles]::AdjustToUniversal
        foreach ($key in @('StartedUtc', 'EndedUtc')) {
            if ($request.$key -cnotmatch '\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z\z') { throw 'time' }
            [void][DateTime]::ParseExact($request.$key, 'yyyy-MM-ddTHH:mm:ss.fffffffZ', $culture, $style)
        }
        if ([string]::CompareOrdinal($request.StartedUtc, $request.EndedUtc) -gt 0 -or $request.TargetPath.Contains("'")) { throw 'literal' }
        $hash = [Security.Cryptography.SHA256]::Create()
        try { $actual = ([BitConverter]::ToString($hash.ComputeHash($encoding.GetBytes($request.Query)))).Replace('-', '').ToLowerInvariant() }
        finally { $hash.Dispose() }
        if (-not [string]::Equals($actual, $request.QuerySha256, [StringComparison]::Ordinal) -or $request.Query.Contains('<!') -or $request.Query.Contains('<?')) { throw 'query_hash' }
        $xml = New-Object Xml.XmlDocument
        $xml.XmlResolver = $null
        $xml.LoadXml($request.Query)
        $root = $xml.DocumentElement; $query = $root.FirstChild; $select = $query.FirstChild
        $channel = 'Microsoft-Windows-AppLocker/MSI and Script'
        $expected = "*[System[Provider[@Name='Microsoft-Windows-AppLocker'] and (EventID=8005 or EventID=8006 or EventID=8007) and TimeCreated[@SystemTime>='$($request.StartedUtc)' and @SystemTime<='$($request.EndedUtc)']] and UserData[RuleAndFileData[PolicyName='SCRIPT' and TargetProcessId=$($request.TargetPid) and FilePath='$($request.TargetPath)']]]"
        if ($xml.ChildNodes.Count -ne 1 -or -not [string]::Equals($root.Name, 'QueryList', [StringComparison]::Ordinal) -or $root.Attributes.Count -ne 0 -or
            $root.ChildNodes.Count -ne 1 -or -not [string]::Equals($query.Name, 'Query', [StringComparison]::Ordinal) -or $query.Attributes.Count -ne 2 -or
            -not [string]::Equals($query.GetAttribute('Id'), '0', [StringComparison]::Ordinal) -or -not [string]::Equals($query.GetAttribute('Path'), $channel, [StringComparison]::Ordinal) -or
            $query.ChildNodes.Count -ne 1 -or -not [string]::Equals($select.Name, 'Select', [StringComparison]::Ordinal) -or $select.Attributes.Count -ne 1 -or
            -not [string]::Equals($select.GetAttribute('Path'), $channel, [StringComparison]::Ordinal) -or $select.ChildNodes.Count -ne 1 -or
            $select.FirstChild.NodeType -ne [Xml.XmlNodeType]::Text -or -not [string]::Equals($select.InnerText, $expected, [StringComparison]::Ordinal)) { throw 'query' }
        return $request
    } catch { throw 'request_invalid' }
}

function Test-AppLockerMatchedFields {
    param($Record, $Selector, $Request)
    $values = $Record.GetPropertyValues($Selector)
    if ($values.Count -ne 3 -or $values[0] -isnot [string] -or -not [string]::Equals($values[0], 'SCRIPT', [StringComparison]::Ordinal) -or
        $values[2] -isnot [string] -or -not [string]::Equals($values[2], $Request.TargetPath, [StringComparison]::Ordinal)) { throw 'record_invalid' }
    $pidValue = $values[1]
    if (($pidValue -isnot [uint32] -and $pidValue -isnot [int] -and $pidValue -isnot [long]) -or
        $pidValue -lt 1 -or $pidValue -gt [int]::MaxValue -or $pidValue -ne $Request.TargetPid) { throw 'record_invalid' }
    if ($Record.Id -isnot [int] -or $Record.ProviderName -isnot [string] -or $Record.LogName -isnot [string] -or
        -not [string]::Equals($Record.ProviderName, 'Microsoft-Windows-AppLocker', [StringComparison]::Ordinal) -or
        -not [string]::Equals($Record.LogName, 'Microsoft-Windows-AppLocker/MSI and Script', [StringComparison]::Ordinal) -or
        $Record.Id -notin @(8005, 8006, 8007) -or $Record.TimeCreated -isnot [DateTime]) { throw 'record_invalid' }
    $utc = $Record.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffffffZ', [Globalization.CultureInfo]::InvariantCulture)
    if ([string]::CompareOrdinal($utc, $Request.StartedUtc) -lt 0 -or
        [string]::CompareOrdinal($utc, $Request.EndedUtc) -gt 0) { throw 'record_invalid' }
    [ordered]@{ EventId = [int]$Record.Id; Utc = $utc }
}

function Read-AppLockerScriptDecision {
    param($Request)
    $ErrorActionPreference = 'Stop'
    $reader = $null; $selector = $null; $first = $null; $second = $null
    $decision = $null; $reason = 'query_unsupported'; $closed = $true
    try {
        $query = New-Object -TypeName Diagnostics.Eventing.Reader.EventLogQuery -ArgumentList @(
            'Microsoft-Windows-AppLocker/MSI and Script', [Diagnostics.Eventing.Reader.PathType]::LogName, $Request.Query)
        $query.TolerateQueryErrors = $false
        $reader = New-Object -TypeName Diagnostics.Eventing.Reader.EventLogReader -ArgumentList @($query)
        $reader.BatchSize = 1
        $paths = [string[]]@('Event/UserData/RuleAndFileData/PolicyName',
            'Event/UserData/RuleAndFileData/TargetProcessId', 'Event/UserData/RuleAndFileData/FilePath')
        $selector = New-Object -TypeName Diagnostics.Eventing.Reader.EventLogPropertySelector -ArgumentList (,$paths)
        $reason = 'read_failed'
        $first = $reader.ReadEvent([TimeSpan]::FromMilliseconds(2000))
        if ($null -eq $first) { $reason = 'no_matching_record' }
        else {
            $reason = 'record_invalid'
            $decision = Test-AppLockerMatchedFields -Record $first -Selector $selector -Request $Request
            $reason = 'read_failed'
            $second = $reader.ReadEvent([TimeSpan]::FromMilliseconds(2000))
            if ($null -ne $second) { $reason = 'multiple_records'; $decision = $null }
            else { $reason = $null }
        }
    } catch {
        $decision = $null
        $errorObject = $_.Exception
        if ($errorObject -is [Management.Automation.MethodInvocationException] -and $null -ne $errorObject.InnerException) {
            $errorObject = $errorObject.InnerException
        }
        if ($errorObject -is [UnauthorizedAccessException]) { $reason = 'access_denied' }
        elseif ($errorObject -is [Diagnostics.Eventing.Reader.EventLogNotFoundException] -or
            $errorObject -is [Diagnostics.Eventing.Reader.EventLogProviderDisabledException]) { $reason = 'channel_unavailable' }
        elseif ($errorObject -is [TimeoutException]) { $reason = 'read_timeout' }
        # Framework EventLogException hides its native code; it remains read_failed, never EOF.
    } finally {
        foreach ($resource in @($first, $second, $selector, $reader)) {
            if ($null -ne $resource) {
                try { $resource.Dispose() } catch { $closed = $false }
            }
        }
    }
    if (-not $closed) { $reason = 'close_uncertain'; $decision = $null }
    [pscustomobject]@{ Reason = $reason; Decision = $decision }
}

function Invoke-AppLockerScriptObservation {
    param($Bracket, [string]$PythonPath, [string]$RepositoryRoot)
    $ErrorActionPreference = 'Stop'
    $summary = [ordered]@{ Protocol = 'applocker-script-observation-raw-v1'; Case = 'cmd-relative-batch-exit23'
        Status = 'inconclusive'; Reason = 'setup_unavailable'; OwnershipSha256 = $null; CaseSha256 = $null
        RunSha256 = $null; InvocationSha256 = $null; QuerySha256 = $null; Decision = $null }
    $reasons = @('setup_unavailable', 'bracket_invalid', 'identity_unavailable', 'identity_inconsistent',
        'request_invalid', 'channel_unavailable', 'access_denied', 'query_unsupported', 'read_failed',
        'read_timeout', 'record_invalid', 'no_matching_record', 'multiple_records', 'close_uncertain', 'evidence_write_failed')
    try {
        if ($null -eq $Bracket) { throw 'bracket_invalid' }
        $summary.Reason = 'evidence_write_failed'
        Write-AppLockerBoundedJson -RepositoryRoot $RepositoryRoot -Name 'invocation.json' -Value $Bracket
        $summary.Reason = 'request_invalid'
        $request = Get-AppLockerPreparedRequest -PythonPath $PythonPath -RepositoryRoot $RepositoryRoot
        if (-not [string]::Equals($request.StartedUtc, $Bracket.StartedUtc, [StringComparison]::Ordinal) -or -not [string]::Equals($request.EndedUtc, $Bracket.EndedUtc, [StringComparison]::Ordinal)) { throw 'request_invalid' }
        foreach ($key in @('OwnershipSha256', 'CaseSha256', 'RunSha256', 'InvocationSha256', 'QuerySha256')) { $summary[$key] = $request.$key }
        $result = Read-AppLockerScriptDecision -Request $request
        $summary.Reason = $result.Reason
        if ($null -ne $result.Decision -and $null -eq $result.Reason) {
            $summary.Status = 'raw_matched'; $summary.Decision = $result.Decision
        }
    } catch {
        $summary.Status = 'inconclusive'; $summary.Decision = $null
        foreach ($canonicalReason in $reasons) {
            if ([string]::Equals($_.Exception.Message, $canonicalReason, [StringComparison]::Ordinal)) {
                $summary.Reason = $canonicalReason
                break
            }
        }
    }
    # Never retry, repair, or replace an uncertain evidence write.
    Write-AppLockerBoundedJson -RepositoryRoot $RepositoryRoot -Name 'observation.json' -Value $summary
}
