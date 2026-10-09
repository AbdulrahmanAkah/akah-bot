param([Parameter(Mandatory=$true)][string]$ValidationDirectory)
$ErrorActionPreference = 'Stop'
$taskRepo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$taskPython = Join-Path $taskRepo '.venv\Scripts\python.exe'
$taskOutput = Join-Path $taskRepo '.akah_bot\v15_incremental_apply_status.json'
$taskOldRun = Join-Path $taskRepo '.akah_bot\economic-guarded-20261008T131003\arm-01'
$taskOldHost = Join-Path $taskRepo '.akah_bot\independent-replay-20261008T1310'
Set-Location -LiteralPath $taskRepo

function Write-Milestone([string]$Stage, $Detail) {
    $value = @{stage=$Stage; utc=[DateTime]::UtcNow.ToString('o'); detail=$Detail;
        restart_from_zero=$false; other_apps_controlled=$false; economic_replay_complete=$false}
    $pending = "$taskOutput.pending"
    [IO.File]::WriteAllText($pending, ($value | ConvertTo-Json -Depth 12))
    [IO.File]::Move($pending, $taskOutput, $true)
    Write-Output "REPAIR_MILESTONE=$Stage"
}

function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }

try {
    $validation = [IO.Path]::GetFullPath($ValidationDirectory)
    if (-not $validation.StartsWith("$taskRepo\.akah_bot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'VALIDATION_PATH_ESCAPE'
    }
    Write-Milestone 'WAITING_EXISTING_SYNTHETIC_VALIDATION_KEEPING_REPLAY_UNCHANGED' $validation
    $receiptPath = Join-Path $validation 'receipt.json'
    while (-not (Test-Path -LiteralPath $receiptPath)) { Start-Sleep -Seconds 5 }
    $validationReceipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
    if ($validationReceipt.os_exit_code -ne 0) { throw 'VALIDATION_FAILED_OLD_REPLAY_PRESERVED' }
    Write-Milestone 'SYNTHETIC_VALIDATION_COMPLETE_VERIFYING_PENDING_CERTIFICATE' $validation
    & $taskPython -B .akah_bot\certify_v15_incremental_repair.py $validation
    if ($LASTEXITCODE -ne 0) { throw 'CERTIFICATION_FAILED_OLD_REPLAY_PRESERVED' }
    $pendingCert = Join-Path $taskRepo '.akah_bot\v15_incremental_runtime_certificate.pending.json'
    $cert = Get-Content -LiteralPath $pendingCert -Raw | ConvertFrom-Json
    foreach ($binding in $cert.runtime_bindings.PSObject.Properties) {
        if ((Hash-File (Join-Path $taskRepo $binding.Name)) -ne $binding.Value) { throw 'PENDING_RUNTIME_SHA_DRIFT' }
    }
    if ($cert.incremental_checkpoint_parity_proven -ne $true -or
        $cert.shared_untraded_warmup_all_eighteen_proven -ne $true) { throw 'PENDING_REPAIR_NOT_PROVEN' }
    for ($attempt=0; $attempt -lt 3; $attempt++) {
        & $taskPython -B .akah_bot\verify_v15_transfer_checkpoint.py
        if ($LASTEXITCODE -ne 0) { throw 'CHECKPOINT_VERIFICATION_FAILED_OLD_REPLAY_PRESERVED' }
        $verified = Get-Content (Join-Path $taskRepo '.akah_bot\v15_incremental_transfer_checkpoint_verified.json') -Raw | ConvertFrom-Json
        $latest = Get-Content (Join-Path $taskRepo '.akah_bot\v15_recoverable_session\FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json') -Raw | ConvertFrom-Json
        if ($verified.receipt_sha256 -eq $latest.sha256) { break }
    }
    if ($verified.receipt_sha256 -ne $latest.sha256) { throw 'NEW_CHECKPOINT_REQUIRES_REVERIFICATION_OLD_REPLAY_PRESERVED' }
    $liveCert = Join-Path $taskRepo '.akah_bot\v15_bounded_runtime_certificate.json'
    $oldSha = Hash-File $liveCert
    $oldCopy = Join-Path $taskRepo ".akah_bot\v15_runtime_certificate_$oldSha.json"
    if ((Hash-File $oldCopy) -ne $oldSha) { throw 'LIVE_CERTIFICATE_NOT_PRESERVED' }
    $env:GIT_OPTIONAL_LOCKS = '0'
    $head = (& git rev-parse HEAD).Trim()
    if ($head -ne $cert.head) { throw 'HEAD_DRIFT_OLD_REPLAY_PRESERVED' }
    # Resolve exact native process ancestry AND owned handshake nonce. Do not
    # use remembered PIDs or touch Chrome, VS Code, or any unrelated process.
    $manifest = Get-Content (Join-Path $taskOldRun 'guardian_manifest.json') -Raw | ConvertFrom-Json
    $handshake = Get-Content (Join-Path $taskOldRun 'worker_handshake.json') -Raw | ConvertFrom-Json
    if ($manifest.nonce -ne $handshake.nonce -or $manifest.guardian_pid -ne $handshake.guardian_pid) {
        throw 'OWNED_GUARDIAN_HANDSHAKE_DRIFT'
    }
    $guardian = Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.guardian_pid)"
    $worker = Get-CimInstance Win32_Process -Filter "ProcessId=$($handshake.worker_pid)"
    if ($guardian -and $worker) {
        $wrapper = Get-CimInstance Win32_Process -Filter "ProcessId=$($worker.ParentProcessId)"
        if ($guardian.Name -ne 'python.exe' -or $worker.Name -ne 'python.exe' -or
            -not $guardian.CommandLine.Contains('v15_independent_replay_launcher.py') -or
            -not $guardian.CommandLine.Contains($taskOldHost) -or
            -not $worker.CommandLine.Contains((Join-Path $taskRepo '.akah_bot\v15_recoverable_worker.py')) -or
            -not $wrapper -or $wrapper.ParentProcessId -ne $guardian.ProcessId) {
            throw 'OWNED_PROCESS_ANCESTRY_NOT_PROVEN'
        }
        Write-Milestone 'VERIFIED_CHECKPOINT_HANDOFF_NOT_RESTART_FROM_ZERO' @{
            cursor=$verified.cursor; receipt_sha256=$verified.receipt_sha256;
            guardian_pid=$guardian.ProcessId; worker_pid=$worker.ProcessId}
        # Closing only the authenticated guardian closes ONLY its owned Job.
        Stop-Process -Id $guardian.ProcessId
        for ($i=0; $i -lt 30; $i++) {
            $still = Get-CimInstance Win32_Process -Filter "ProcessId=$($handshake.worker_pid)"
            if (-not $still) { break }
            Start-Sleep -Seconds 1
        }
        if ($still) { throw 'OWNED_CHILD_NOT_CLOSED_DUPLICATE_REPLAY_REFUSED' }
    } elseif ($guardian -or $worker) {
        throw 'PARTIAL_OLD_PROCESS_LIFETIME_REQUIRES_EXACT_RECOVERY'
    }
    $newSha = Hash-File $pendingCert
    Copy-Item -LiteralPath $pendingCert -Destination $liveCert
    if ((Hash-File $liveCert) -ne $newSha) { throw 'LIVE_CERTIFICATE_PUBLICATION_DRIFT' }
    $directory = Join-Path $taskRepo ('.akah_bot\independent-incremental-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
    New-Item -ItemType Directory -Path $directory | Out-Null
    $arguments = '-B .akah_bot/v15_incremental_launcher.py --run --directory "' + $directory + '"'
    $handoffPath = Join-Path $taskRepo '.akah_bot\v15_live_recovery_handoff.json'
    $handoff = Get-Content $handoffPath -Raw | ConvertFrom-Json
    $handoff.independent_launcher_directory = $directory
    $handoff.certificate_sha256 = $newSha
    $handoff.last_verified_durable_cursor = $verified.cursor
    $handoff.last_verified_durable_receipt_sha256 = $verified.receipt_sha256
    $handoff.status = 'INCREMENTAL_REPAIR_CERTIFIED_EXACT_CHECKPOINT_RESUME_DISPATCHED_NOT_COMPLETED'
    $handoff | Add-Member -NotePropertyName incremental_storage_enabled -NotePropertyValue $true -Force
    $handoff | Add-Member -NotePropertyName shared_untraded_warmup_enabled -NotePropertyValue $true -Force
    $handoff | Add-Member -NotePropertyName repair_validation_directory -NotePropertyValue $validation -Force
    [IO.File]::WriteAllText("$handoffPath.pending", ($handoff | ConvertTo-Json -Depth 12))
    [IO.File]::Move("$handoffPath.pending", $handoffPath, $true)
    # Publish the handoff BEFORE dispatch: the live supervisor may update this
    # same document. Never overwrite its new run pointer with an old snapshot.
    $started = Start-Process -FilePath $taskPython -ArgumentList $arguments -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
    Write-Milestone 'CERTIFIED_EXACT_CHECKPOINT_RESUME_DISPATCHED_NOT_COMPLETED' @{
        cursor=$verified.cursor; receipt_sha256=$verified.receipt_sha256; certificate_sha256=$newSha;
        launcher_directory=$directory; launcher_wrapper_pid=$started.Id; tests=$cert.new_storage_warmup_tests_passed}
} catch {
    Write-Milestone 'REPAIR_NOT_COMPLETED_FAIL_CLOSED_RETAIN_ALL_CHECKPOINTS' $_.Exception.Message
    throw
}
