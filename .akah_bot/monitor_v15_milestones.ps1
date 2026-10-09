param([switch]$Once)
$ErrorActionPreference = 'Stop'
$taskRepo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$taskSeen = New-Object 'System.Collections.Generic.HashSet[string]'
$taskPause = @{}

function Show-Once([string]$Key, [string]$Message) {
    if ($taskSeen.Add($Key)) { Write-Host ('[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message) }
}

function Read-Shared([string]$Path, [int]$TailBytes = 0) {
    if (-not [IO.File]::Exists($Path)) { return '' }
    $share = [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    $stream = $null; $reader = $null
    try {
        $stream = [IO.FileStream]::new($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, $share)
        if ($TailBytes -gt 0) { [void]$stream.Seek([Math]::Max(0, $stream.Length - $TailBytes), [IO.SeekOrigin]::Begin) }
        elseif ($stream.Length -gt 1048576) { throw 'MONITOR_METADATA_SIZE_EXCEEDED' }
        $reader = [IO.StreamReader]::new($stream)
        return $reader.ReadToEnd()
    } catch [IO.FileNotFoundException] { return '' }
    finally {
        if ($reader) { $reader.Dispose() }
        elseif ($stream) { $stream.Dispose() }
    }
}

function Read-Json([string]$Path) {
    $raw = Read-Shared $Path
    if ($raw) { return ($raw | ConvertFrom-Json) }
    return $null
}

function Scope-Path([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { $Path = Join-Path $taskRepo $Path }
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith(($taskRepo + '\.akah_bot\'), [StringComparison]::OrdinalIgnoreCase)) {
        throw 'MONITOR_PATH_OUT_OF_SCOPE'
    }
    return $resolved
}

Write-Host 'Read-only milestone monitor. Ctrl+C stops this monitor ONLY; replay is untouched.'
do {
    try {
        $handoff = Read-Json (Join-Path $taskRepo '.akah_bot\v15_live_recovery_handoff.json')
        if (-not $handoff) { Show-Once 'waiting-handoff' 'WAITING: no live handoff published yet.' }
        else {
            $run = Scope-Path $handoff.live_status_directory
            $hostDirectory = Scope-Path $handoff.independent_launcher_directory
            Show-Once ('run:{0}' -f $run) ('RUN: {0}' -f $run)
            $hostState = Read-Json (Join-Path $hostDirectory 'launcher_status.json')
            $state = Read-Json (Join-Path $run 'status.json')
            if ($state -and $state.arm) {
                Show-Once ('arm:{0}:{1}' -f $run, $state.index) (
                    'ARM START {0}/18: {1}' -f $state.index, $state.arm)
            }
            if ($state) {
                foreach ($doneArm in @($state.completed)) {
                    if ($doneArm) { Show-Once ('done:{0}:{1}' -f $run, $doneArm) ('ARM COMPLETE: {0}' -f $doneArm) }
                }
                if ($state.failures) {
                    foreach ($failure in $state.failures.PSObject.Properties) {
                        Show-Once ('failure:{0}:{1}' -f $run, $failure.Name) (
                            'INCOMPLETE / FAILURE: {0} -- {1}' -f $failure.Name, ($failure.Value | ConvertTo-Json -Depth 8 -Compress))
                    }
                }
            }
            $index = if ($state -and $state.index) { [int]$state.index } else { 1 }
            $armDirectory = Join-Path $run ('arm-{0:00}' -f $index)
            $guard = Read-Json (Join-Path $armDirectory 'status.json')
            # Alternate observations exist only if a Windows reader temporarily
            # denied replacement. Prefer them only when canonical is not fresh.
            if (-not $guard -or ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($guard.utc)).TotalSeconds -gt 10) {
                $alternate = Get-ChildItem -LiteralPath $armDirectory -Filter 'status-observation-*.json' -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
                if ($alternate) {
                    $candidate = Read-Json $alternate.FullName
                    if ($candidate -and (-not $guard -or [DateTimeOffset]::Parse($candidate.utc) -gt [DateTimeOffset]::Parse($guard.utc))) {
                        $guard = $candidate
                    }
                }
            }
            if ($guard -and ([DateTimeOffset]::UtcNow - [DateTimeOffset]::Parse($guard.utc)).TotalSeconds -lt 30) {
                if ($guard.status -eq 'PAUSED_PRESSURE_NO_PROGRESS_LOST') {
                    if (-not $taskPause.ContainsKey($armDirectory)) { $taskPause[$armDirectory] = @{at=Get-Date;shown=$false} }
                    $episode = $taskPause[$armDirectory]
                    if (-not $episode.shown -and ((Get-Date) - $episode.at).TotalSeconds -ge 60) {
                        Write-Host ('[{0}] MEMORY WAIT: replay paused for over 60s; saved progress retained.' -f (Get-Date -Format 'HH:mm:ss'))
                        $episode.shown = $true
                    }
                } elseif ($taskPause.ContainsKey($armDirectory)) {
                    if ($taskPause[$armDirectory].shown) {
                        Write-Host ('[{0}] RESUMED: memory-pressure pause cleared.' -f (Get-Date -Format 'HH:mm:ss'))
                    }
                    $taskPause.Remove($armDirectory)
                }
            }
            foreach ($line in ((Read-Shared (Join-Path $armDirectory 'stdout.log') 65536) -split '\r?\n')) {
                if ($line -match '^REPLAY_PROGRESS=(.+)$') {
                    try {
                        $progress = $Matches[1] | ConvertFrom-Json
                        $day = ([string]$progress.completed_close).Substring(0,10)
                        Show-Once ('day:{0}:{1}:{2}' -f $run, $progress.arm, $day) (
                            'DAY REACHED: {0} @ {1}' -f $progress.arm, $progress.completed_close)
                    } catch { } # A partial first/last tail line is not a replay failure.
                } elseif ($line -match '^(EXACT_ARM_RESUMED|EXACT_SHARED_UNTRADED_PREFIX_REUSED|DURABLE_COMPLETED_HOUR_CHECKPOINT|CHECKPOINT_WALL_SECONDS|ARM_STATUS|EXACT_EIGHTEEN_SAVED_ARM_COLLECTION|GUARDIAN_SAFETY_FAILURE|GUARDIAN_HEARTBEAT_FORENSIC)=') {
                    Show-Once ('log:{0}:{1}' -f $armDirectory, $line) $line
                }
            }
            foreach ($line in ((Read-Shared (Join-Path $armDirectory 'stderr.log') 8192) -split '\r?\n')) {
                if ($line.Trim() -and $line -notmatch '^Failed to find real location of ') {
                    Show-Once ('stderr:{0}:{1}' -f $armDirectory, $line) ('STDERR: {0}' -f $line)
                }
            }
            if ($hostState -and $hostState.status -eq 'INCOMPLETE_REPAIR_REQUIRED_NOT_ECONOMIC_CONCLUSION') {
                Show-Once ('host-failure:{0}' -f $hostDirectory) (
                    'REPAIR REQUIRED: {0}. Waiting for a new resumed run.' -f $hostState.error)
            }
            if ($state -and $state.status -match 'REPAIR_REQUIRED|NO_QUALIFICATION') {
                Show-Once ('repair:{0}:{1}' -f $run, $state.status) (
                    'REPAIR REQUIRED: {0}. This is not an economic conclusion.' -f $state.status)
            }
            if (($state -and $state.status -eq 'ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED') -or
                ($hostState -and $hostState.status -eq 'ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED')) {
                Write-Host ('[{0}] COMPLETE: all 18 arms finished and outputs collected. {1}' -f (Get-Date -Format 'HH:mm:ss'), $run)
                break
            }
        }
    } catch {
        Show-Once ('monitor-error:{0}' -f $_.Exception.Message) (
            'MONITOR READ WARNING (replay untouched): {0}' -f $_.Exception.Message)
    }
    if (-not $Once) { Start-Sleep -Seconds 10 }
} while (-not $Once)
