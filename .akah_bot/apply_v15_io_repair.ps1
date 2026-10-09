param([Parameter(Mandatory=$true)][string]$ValidationDirectory)
$ErrorActionPreference='Stop'
$taskRepo='C:\SIRAJ\Repositories\spot-speculation-bot'
$taskPython=Join-Path $taskRepo '.venv\Scripts\python.exe'
Set-Location -LiteralPath $taskRepo
function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
# Do not swap a running process here. The observed old run has already exited
# with OS76. Native lifetime and exact command-line checks precede publication.
$handoffPath=Join-Path $taskRepo '.akah_bot\v15_live_recovery_handoff.json'
$handoff=Get-Content -LiteralPath $handoffPath -Raw | ConvertFrom-Json
$oldRun=[IO.Path]::GetFullPath((Join-Path $taskRepo ($handoff.live_status_directory + '\arm-01')))
if (-not $oldRun.StartsWith("$taskRepo\.akah_bot\",[StringComparison]::OrdinalIgnoreCase)) { throw 'RUN_PATH_ESCAPE' }
$manifest=Get-Content -LiteralPath (Join-Path $oldRun 'guardian_manifest.json') -Raw | ConvertFrom-Json
$handshake=Get-Content -LiteralPath (Join-Path $oldRun 'worker_handshake.json') -Raw | ConvertFrom-Json
$exitPath=Join-Path $oldRun 'exit_receipt.json'
$exitReceipt=$null
if (Test-Path -LiteralPath $exitPath) {
    $exitReceipt=Get-Content -LiteralPath $exitPath -Raw | ConvertFrom-Json
    if ($exitReceipt.os_exit_code -ne 76 -or $exitReceipt.worker_pid -ne $handshake.worker_pid) { throw 'OLD_FAILURE_NOT_BOUND' }
} else {
    $oldHost=[IO.Path]::GetFullPath($handoff.independent_launcher_directory)
    if (-not $oldHost.StartsWith("$taskRepo\.akah_bot\",[StringComparison]::OrdinalIgnoreCase)) { throw 'OLD_HOST_ESCAPE' }
    $failed=Get-Content -LiteralPath (Join-Path $oldHost 'launcher_status.json') -Raw | ConvertFrom-Json
    if ($failed.status -ne 'INCOMPLETE_REPAIR_REQUIRED_NOT_ECONOMIC_CONCLUSION' -or
        $failed.error -ne "RuntimeError('GUARD_TELEMETRY_FAILED')") { throw 'OLD_TELEMETRY_FAILURE_NOT_BOUND' }
}
if ($manifest.nonce -ne $handshake.nonce -or $manifest.guardian_pid -ne $handshake.guardian_pid) { throw 'OLD_HANDSHAKE_DRIFT' }
foreach($pidToCheck in @($manifest.guardian_pid,$handshake.worker_pid)) {
    $process=Get-CimInstance Win32_Process -Filter "ProcessId=$pidToCheck"
    if ($process -and ($process.CommandLine.Contains('v15_packed_') -or $process.CommandLine.Contains('v15_io_'))) {
        throw 'OLD_REPLAY_STILL_ALIVE_DUPLICATE_REFUSED'
    }
}
& $taskPython -B .akah_bot\certify_v15_io_repair.py $ValidationDirectory
if ($LASTEXITCODE -ne 0) { throw 'IO_CERTIFICATION_FAILED' }
$pending=Join-Path $taskRepo '.akah_bot\v15_io_runtime_certificate.pending.json'
$cert=Get-Content -LiteralPath $pending -Raw | ConvertFrom-Json
foreach($binding in $cert.runtime_bindings.PSObject.Properties) {
    if ((Hash-File (Join-Path $taskRepo $binding.Name)) -ne $binding.Value) { throw 'RUNTIME_BINDING_DRIFT' }
}
$env:GIT_OPTIONAL_LOCKS='0'
if ((& git rev-parse HEAD).Trim() -ne $cert.head) { throw 'HEAD_DRIFT' }
$latest=Get-Content .akah_bot\v15_recoverable_session\FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json -Raw | ConvertFrom-Json
if ((Hash-File $latest.receipt) -ne $latest.sha256) { throw 'CHECKPOINT_POINTER_DRIFT' }
# Full archive verification occurs in ONE private recovery pass before unpickle.
# Never duplicate that 2.2GB verification here just to launch the verifier.
$live=Join-Path $taskRepo '.akah_bot\v15_bounded_runtime_certificate.json'
$oldSha=Hash-File $live
if ((Hash-File (Join-Path $taskRepo ".akah_bot\v15_runtime_certificate_$oldSha.json")) -ne $oldSha) { throw 'PRIOR_CERTIFICATE_NOT_PRESERVED' }
$newSha=Hash-File $pending
Copy-Item -LiteralPath $pending -Destination $live
if ((Hash-File $live) -ne $newSha) { throw 'PUBLISHED_CERTIFICATE_DRIFT' }
$directory=Join-Path $taskRepo ('.akah_bot\independent-io-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $directory | Out-Null
$handoff.independent_launcher_directory=$directory
$handoff.certificate_sha256=$newSha
$handoff.status='SINGLE_PASS_VERIFY_AND_EXACT_RESUME_DISPATCHED_NOT_COMPLETED'
$handoff | Add-Member -NotePropertyName io_validation_directory -NotePropertyValue $ValidationDirectory -Force
[IO.File]::WriteAllText("$handoffPath.pending",($handoff | ConvertTo-Json -Depth 12))
[IO.File]::Move("$handoffPath.pending",$handoffPath,$true)
$arguments='-B .akah_bot/v15_io_launcher.py --run --directory "' + $directory + '"'
$started=Start-Process -FilePath $taskPython -ArgumentList $arguments -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
$detail=@{directory=$directory;wrapper_pid=$started.Id;tests=$cert.io_repair_tests_passed;certificate_sha256=$newSha;
    preserved_cursor=$latest.cursor;restart_from_zero=$false;other_apps_controlled=$false;utc=[DateTime]::UtcNow.ToString('o')}
[IO.File]::WriteAllText((Join-Path $taskRepo '.akah_bot\v15_io_apply_status.json'),($detail | ConvertTo-Json -Depth 8))
$detail | ConvertTo-Json -Depth 8
