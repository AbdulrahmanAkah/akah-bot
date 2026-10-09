$ErrorActionPreference='Stop'
$taskRepo='C:\SIRAJ\Repositories\spot-speculation-bot'
$taskPython=Join-Path $taskRepo '.venv\Scripts\python.exe'
Set-Location -LiteralPath $taskRepo
function Hash-File([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash }
function Scoped([string]$Path) {
    $resolved=[IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith("$taskRepo\.akah_bot\",[StringComparison]::OrdinalIgnoreCase)) { throw 'PATH_ESCAPE' }
    $resolved
}
$handoffPath=Join-Path $taskRepo '.akah_bot\v15_live_recovery_handoff.json'
$handoff=Get-Content -LiteralPath $handoffPath -Raw | ConvertFrom-Json
$oldArm=Scoped (Join-Path $taskRepo ($handoff.live_status_directory + '\arm-01'))
$oldHost=Scoped $handoff.independent_launcher_directory
$manifest=Get-Content -LiteralPath (Join-Path $oldArm 'guardian_manifest.json') -Raw | ConvertFrom-Json
$handshake=Get-Content -LiteralPath (Join-Path $oldArm 'worker_handshake.json') -Raw | ConvertFrom-Json
if ($manifest.nonce -ne $handshake.nonce -or $manifest.guardian_pid -ne $handshake.guardian_pid) { throw 'OWNERSHIP_NONCE_DRIFT' }
$pending=Join-Path $taskRepo '.akah_bot\v15_point_index_runtime_certificate.pending.json'
$cert=Get-Content -LiteralPath $pending -Raw | ConvertFrom-Json
if (-not $cert.exact_point_query_and_continuation_index_proven) { throw 'POINT_INDEX_PROOFS_REQUIRED' }
foreach($binding in $cert.runtime_bindings.PSObject.Properties) {
    if ((Hash-File (Join-Path $taskRepo $binding.Name)) -ne $binding.Value) { throw 'RUNTIME_BINDING_DRIFT' }
}
$env:GIT_OPTIONAL_LOCKS='0'
if ((& git rev-parse HEAD).Trim() -ne $cert.head) { throw 'HEAD_DRIFT' }
if (& git diff --name-only) { throw 'TRACKED_WORKTREE_NOT_CLEAN' }
if (& git diff --cached --name-only) { throw 'INDEX_NOT_CLEAN' }
$live=Join-Path $taskRepo '.akah_bot\v15_bounded_runtime_certificate.json'
$oldSha=Hash-File $live
if ($oldSha -ne $handoff.certificate_sha256 -or
    (Hash-File (Join-Path $taskRepo ".akah_bot\v15_runtime_certificate_$oldSha.json")) -ne $oldSha) { throw 'OLD_CERT_NOT_PRESERVED' }
$latestPath=Join-Path $taskRepo '.akah_bot\v15_recoverable_session\FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json'
$latest=Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
if ((Hash-File (Scoped $latest.receipt)) -ne $latest.sha256) { throw 'CHECKPOINT_POINTER_DRIFT' }
$saved=Get-Content -LiteralPath (Scoped $latest.receipt) -Raw | ConvertFrom-Json
if ($saved.authority.supplemental_certificate_sha256 -ne $oldSha -or
    $saved.authority.precommit_sha256 -ne $cert.precommit_sha256 -or
    $saved.authority.source_version_sha256 -ne $cert.source_version_sha256 -or
    $saved.authority.arm -ne 'FS_WYCKOFF_FRESH_CAUSE_V8|1X' -or
    ([DateTimeOffset]::Parse($latest.cursor)).Year -ne 2021) { throw 'EXACT_UNTRADED_WARMUP_AUTHORITY_REQUIRED' }
$guardian=Get-CimInstance Win32_Process -Filter "ProcessId=$($manifest.guardian_pid)"
$worker=Get-CimInstance Win32_Process -Filter "ProcessId=$($handshake.worker_pid)"
if (-not $guardian -or -not $worker -or
    -not $guardian.CommandLine.Contains('v15_paged_io_launcher.py') -or
    -not $guardian.CommandLine.Contains($oldHost) -or
    -not $worker.CommandLine.Contains('v15_paged_io_entry.py') -or
    -not $worker.CommandLine.Contains('v15_paged_recoverable_worker.py') -or
    -not $worker.CommandLine.Contains('FS_WYCKOFF_FRESH_CAUSE_V8|1X')) { throw 'LIVE_OWNED_COMMAND_LINE_REQUIRED' }
$workerWrapper=Get-CimInstance Win32_Process -Filter "ProcessId=$($worker.ParentProcessId)"
if (-not $workerWrapper -or $workerWrapper.ParentProcessId -ne $guardian.ProcessId -or
    -not $workerWrapper.CommandLine.Contains('v15_paged_io_entry.py')) { throw 'LIVE_WORKER_ANCESTRY_REQUIRED' }
$guardianProcess=Get-Process -Id $guardian.ProcessId
Stop-Process -InputObject $guardianProcess
$guardianProcess.WaitForExit(15000) | Out-Null
for($attempt=0;$attempt -lt 100;$attempt++) {
    if (-not (Get-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue)) { break }
    Start-Sleep -Milliseconds 100
}
if (Get-Process -Id $worker.ProcessId -ErrorAction SilentlyContinue) { throw 'OLD_OWNED_WORKER_STILL_ALIVE' }
$latest=Get-Content -LiteralPath $latestPath -Raw | ConvertFrom-Json
if ((Hash-File (Scoped $latest.receipt)) -ne $latest.sha256) { throw 'FINAL_POINTER_DRIFT' }
$newSha=Hash-File $pending
Copy-Item -LiteralPath $pending -Destination "$live.pending"
[IO.File]::Move("$live.pending",$live,$true)
if ((Hash-File $live) -ne $newSha) { throw 'CERT_PUBLICATION_DRIFT' }
$directory=Join-Path $taskRepo ('.akah_bot\independent-point-index-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $directory | Out-Null
$handoff.independent_launcher_directory=$directory
$handoff.certificate_sha256=$newSha
$handoff.status='EXACT_SOURCE_POINT_INDEX_HANDOFF_DISPATCHED_NOT_COMPLETED'
$handoff.last_verified_durable_cursor=$latest.cursor
$handoff.last_verified_durable_receipt_sha256=$latest.sha256
$handoff | Add-Member -NotePropertyName point_query_index_enabled -NotePropertyValue $true -Force
[IO.File]::WriteAllText("$handoffPath.pending",($handoff | ConvertTo-Json -Depth 12))
[IO.File]::Move("$handoffPath.pending",$handoffPath,$true)
$arguments='-B .akah_bot/v15_point_index_launcher.py --run --directory "' + $directory + '"'
$started=Start-Process -FilePath $taskPython -ArgumentList $arguments -WorkingDirectory $taskRepo -WindowStyle Hidden -PassThru
$detail=@{directory=$directory;wrapper_pid=$started.Id;tests=$cert.point_index_tests_passed;certificate_sha256=$newSha;
    preserved_cursor=$latest.cursor;preserved_receipt_sha256=$latest.sha256;restart_from_zero=$false;
    old_guardian_nonce_verified=$true;other_apps_controlled=$false;utc=[DateTime]::UtcNow.ToString('o')}
[IO.File]::WriteAllText((Join-Path $taskRepo '.akah_bot\v15_point_index_apply_status.json'),($detail | ConvertTo-Json -Depth 8))
$detail | ConvertTo-Json -Depth 8
