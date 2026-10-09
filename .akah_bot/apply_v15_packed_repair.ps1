param([Parameter(Mandatory=$true)][string]$ValidationDirectory)
$ErrorActionPreference = 'Stop'
$taskRepo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$taskPython = Join-Path $taskRepo '.venv\Scripts\python.exe'
$taskStatus = Join-Path $taskRepo '.akah_bot\v15_packed_apply_status.json'
Set-Location -LiteralPath $taskRepo
function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Milestone([string]$Stage, $Detail) {
    $doc=@{stage=$Stage;utc=[DateTime]::UtcNow.ToString('o');detail=$Detail;restart_from_zero=$false;other_apps_controlled=$false}
    [IO.File]::WriteAllText("$taskStatus.pending",($doc | ConvertTo-Json -Depth 12))
    [IO.File]::Move("$taskStatus.pending",$taskStatus,$true)
    Write-Output "PACKED_REPAIR=$Stage"
}
try {
    $validation=[IO.Path]::GetFullPath($ValidationDirectory)
    if (-not $validation.StartsWith("$taskRepo\.akah_bot\",[StringComparison]::OrdinalIgnoreCase)) { throw 'VALIDATION_PATH_ESCAPE' }
    $receipt=Get-Content (Join-Path $validation 'receipt.json') -Raw | ConvertFrom-Json
    if ($receipt.os_exit_code -ne 0) { throw 'SYNTHETIC_VALIDATION_NOT_PASSED' }
    & $taskPython -B .akah_bot\certify_v15_packed_repair.py $validation
    if ($LASTEXITCODE -ne 0) { throw 'CERTIFICATION_FAILED_OLD_REPLAY_PRESERVED' }
    $pending=Join-Path $taskRepo '.akah_bot\v15_packed_runtime_certificate.pending.json'
    $cert=Get-Content $pending -Raw | ConvertFrom-Json
    foreach($binding in $cert.runtime_bindings.PSObject.Properties) {
        if ((Hash-File (Join-Path $taskRepo $binding.Name)) -ne $binding.Value) { throw 'RUNTIME_SHA_DRIFT' }
    }
    if ($cert.packed_checkpoint_all_eighteen_exact_resume -ne $true -or $cert.packed_checkpoint_sync_barriers_constant_proven -ne $true) { throw 'PACKED_PARITY_NOT_PROVEN' }
    for($attempt=0;$attempt -lt 3;$attempt++) {
        & $taskPython -B .akah_bot\verify_v15_packed_transfer.py
        if ($LASTEXITCODE -ne 0) { throw 'CHECKPOINT_NOT_VERIFIED_OLD_REPLAY_PRESERVED' }
        $verified=Get-Content .akah_bot\v15_packed_transfer_verified.json -Raw | ConvertFrom-Json
        $latest=Get-Content .akah_bot\v15_recoverable_session\FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json -Raw | ConvertFrom-Json
        if ($latest.sha256 -eq $verified.receipt_sha256) { break }
    }
    if ($latest.sha256 -ne $verified.receipt_sha256) { throw 'NEW_CHECKPOINT_REVERIFICATION_REQUIRED' }
    $live=Join-Path $taskRepo '.akah_bot\v15_bounded_runtime_certificate.json'
    $oldSha=Hash-File $live
    if ((Hash-File (Join-Path $taskRepo ".akah_bot\v15_runtime_certificate_$oldSha.json")) -ne $oldSha) { throw 'OLD_CERTIFICATE_NOT_PRESERVED' }
    $env:GIT_OPTIONAL_LOCKS='0'
    if ((& git rev-parse HEAD).Trim() -ne $cert.head) { throw 'HEAD_DRIFT' }
    $handoffPath=Join-Path $taskRepo '.akah_bot\v15_live_recovery_handoff.json'
    $handoff=Get-Content $handoffPath -Raw | ConvertFrom-Json
    $oldRun=[IO.Path]::GetFullPath((Join-Path $taskRepo ($handoff.live_status_directory + '\arm-01')))
    $oldHost=[IO.Path]::GetFullPath($handoff.independent_launcher_directory)
    if (-not $oldRun.StartsWith("$taskRepo\.akah_bot\") -or -not $oldHost.StartsWith("$taskRepo\.akah_bot\")) { throw 'OWNED_RUN_PATH_ESCAPE' }
    $manifest=Get-Content (Join-Path $oldRun 'guardian_manifest.json') -Raw | ConvertFrom-Json
    $handshake=Get-Content (Join-Path $oldRun 'worker_handshake.json') -Raw | ConvertFrom-Json
    if ($manifest.nonce -ne $handshake.nonce -or $manifest.guardian_pid -ne $handshake.guardian_pid) { throw 'OWNED_HANDSHAKE_DRIFT' }
    $guardian=Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.guardian_pid)"
    $worker=Get-CimInstance Win32_Process -Filter "ProcessId=$($handshake.worker_pid)"
    if ($guardian -and $worker) {
        $wrapper=Get-CimInstance Win32_Process -Filter "ProcessId=$($worker.ParentProcessId)"
        if ($guardian.Name -ne 'python.exe' -or $worker.Name -ne 'python.exe' -or
            -not $guardian.CommandLine.Contains('v15_incremental_launcher.py') -or
            -not $guardian.CommandLine.Contains($oldHost) -or
            -not $worker.CommandLine.Contains((Join-Path $taskRepo '.akah_bot\v15_incremental_recoverable_worker.py')) -or
            -not $wrapper -or $wrapper.ParentProcessId -ne $guardian.ProcessId) { throw 'EXACT_PROCESS_ANCESTRY_NOT_PROVEN' }
        Milestone 'VERIFIED_CHECKPOINT_PROCESS_HANDOFF' @{cursor=$verified.cursor;receipt_sha256=$verified.receipt_sha256}
        Stop-Process -Id $guardian.ProcessId
        for($i=0;$i -lt 30;$i++) {
            $still=Get-CimInstance Win32_Process -Filter "ProcessId=$($handshake.worker_pid)"
            if (-not $still) { break }; Start-Sleep -Seconds 1
        }
        if ($still) { throw 'OLD_CHILD_STILL_EXISTS_DUPLICATE_REFUSED' }
    } elseif ($guardian -or $worker) { throw 'PARTIAL_PROCESS_LIFETIME_REQUIRES_EXACT_RECOVERY' }
    $newSha=Hash-File $pending; Copy-Item -LiteralPath $pending -Destination $live
    if ((Hash-File $live) -ne $newSha) { throw 'CERTIFICATE_PUBLICATION_DRIFT' }
    $directory=Join-Path $taskRepo ('.akah_bot\independent-packed-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
    New-Item -ItemType Directory -Path $directory | Out-Null
    $handoff.independent_launcher_directory=$directory
    $handoff.certificate_sha256=$newSha
    $handoff.last_verified_durable_cursor=$verified.cursor
    $handoff.last_verified_durable_receipt_sha256=$verified.receipt_sha256
    $handoff.status='PACKED_STORAGE_EXACT_RESUME_DISPATCHED_NOT_COMPLETED'
    $handoff | Add-Member -NotePropertyName packed_storage_enabled -NotePropertyValue $true -Force
    $handoff | Add-Member -NotePropertyName packed_validation_directory -NotePropertyValue $validation -Force
    [IO.File]::WriteAllText("$handoffPath.pending",($handoff | ConvertTo-Json -Depth 12))
    [IO.File]::Move("$handoffPath.pending",$handoffPath,$true)
    $arguments='-B .akah_bot/v15_packed_launcher.py --run --directory "' + $directory + '"'
    $started=Start-Process -FilePath $taskPython -ArgumentList $arguments -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
    Milestone 'CERTIFIED_PACKED_RESUME_DISPATCHED_NOT_COMPLETED' @{directory=$directory;cursor=$verified.cursor;certificate_sha256=$newSha;wrapper_pid=$started.Id;tests=$cert.new_packed_storage_tests_passed}
} catch {
    Milestone 'REPAIR_NOT_APPLIED_KEEP_ALL_CHECKPOINTS' $_.Exception.Message
    throw
}
