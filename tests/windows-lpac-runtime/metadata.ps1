# Data-shape helpers only. No process launch, filesystem traversal or ACL changes.
function Select-ApplicationPath([object[]]$Candidates) {
    if($Candidates.Count -eq 0) {throw 'application resolver returned no candidates'}
    # Get-Command may return all applications with an exact executable name.
    # Preserve normal first-PATH precedence; do not combine roots or probe aliases.
    $path=$Candidates[0].Source
    if($path -isnot [string] -or [string]::IsNullOrWhiteSpace($path)) {throw 'application source must be one nonempty path'}
    return $path
}

function Read-RuntimeInventory([string]$Json) {
    # PowerShell 5.1 can emit ConvertFrom-Json's complete array as one pipeline
    # object. Explicit foreach emits only scalar records to our caller.
    $decoded=ConvertFrom-Json -InputObject $Json
    $names=[Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach($record in $decoded) {
        if($null -eq $record -or $record -is [Array] -or $null -eq $record.PSObject.Properties['runtime'] -or
            $null -eq $record.PSObject.Properties['ready'] -or
            $record.runtime -isnot [string] -or $record.ready -isnot [bool]) {throw 'invalid scalar runtime inventory record'}
        if(-not $names.Add($record.runtime)) {throw 'duplicate runtime inventory record'}
        Write-Output $record
    }
}
