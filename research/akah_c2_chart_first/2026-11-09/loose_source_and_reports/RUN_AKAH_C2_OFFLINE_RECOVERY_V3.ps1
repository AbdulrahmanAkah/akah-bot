# AKAH C2 OFFLINE RECOVERY V3 - preserve original V2 cached archives, offline by default.
param(
    [ValidateSet('core','daily','none')][string]$RawMode = 'core',
    [switch]$ResumeAggTrades,
    [ValidateRange(0,200)][int]$MaxNewArchives = 30,
    [ValidateRange(5,90)][int]$PacketMB = 85,
    [double]$ArchiveBudgetGB = 30
)
$ErrorActionPreference = 'Stop'
$Repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$Dl = Join-Path $HOME 'Downloads'
$Work = Join-Path $Dl 'AKAH_C2_MARKET_VAULT_V2'
$Tools = Join-Path $Work 'tools'
if (-not (Test-Path -LiteralPath $Work -PathType Container)) { throw 'V2_MARKET_VAULT_NOT_FOUND; no downloading or reset permitted.' }
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { throw "AKAH_REPO_NOT_FOUND: $Repo" }
New-Item -ItemType Directory -Force -Path $Tools | Out-Null
$PyFile = Join-Path $Tools 'akah_c2_recovery_v3.py'
$Code64 = @'
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
//0hBNTtQqBFCMGb0jIq/wtw8mHWkTUAAA==
'@
$CompressedBytes = [Convert]::FromBase64String(($Code64 -replace '\s',''))
$SourceStream = New-Object System.IO.MemoryStream (,$CompressedBytes)
$Decoder = New-Object System.IO.Compression.GZipStream($SourceStream,[System.IO.Compression.CompressionMode]::Decompress)
$Buffer = New-Object System.IO.MemoryStream
try { $Decoder.CopyTo($Buffer) } finally { $Decoder.Dispose(); $SourceStream.Dispose() }
[System.IO.File]::WriteAllBytes($PyFile,$Buffer.ToArray())
$Buffer.Dispose()
$Actual = (Get-FileHash -LiteralPath $PyFile -Algorithm SHA256).Hash.ToUpperInvariant()
if ($Actual -ne '578BB0F7906300F295F16144F230DC2F9D08FDCA5E4741A8A961654DE605993B') { throw 'INTEGRITY_FAILURE_RECOVERY_SCRIPT' }
$RepoPython = Join-Path $Repo '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $RepoPython) { $Python=$RepoPython; $Prefix=@() }
elseif (Get-Command 'py.exe' -ErrorAction SilentlyContinue) { $Python='py.exe'; $Prefix=@('-3') }
elseif (Get-Command 'python.exe' -ErrorAction SilentlyContinue) { $Python='python.exe'; $Prefix=@() }
else { throw 'PYTHON_NOT_FOUND' }
$RunArgs=@($PyFile,'--repo',$Repo,'--downloads',$Dl,'--archive-budget-gb',[string]$ArchiveBudgetGB,'--packet-mb',[string]$PacketMB,'--raw-mode',$RawMode.ToLowerInvariant(),'--max-new-archives',[string]$MaxNewArchives)
if ($ResumeAggTrades) { $RunArgs+='--resume-aggtrades' }
$TranscriptFile = Join-Path $Work 'C2_OFFLINE_RECOVERY_V3_TRANSCRIPT.txt'
$Started = $false
try {
    Start-Transcript -Path $TranscriptFile -Force | Out-Null
    $Started = $true
    Write-Host 'AKAH_C2_RECOVERY_V3=BEGIN'
    if ($ResumeAggTrades) { Write-Host 'MODE=BOUNDED_NETWORK_RESUME_AGGTRADES' } else { Write-Host 'MODE=OFFLINE_NO_NETWORK' }
    Write-Host ('REUSE_WORKDIR=' + $Work)
    & $Python @Prefix @RunArgs
    $RunExit=$LASTEXITCODE
} finally {
    if ($Started) { Stop-Transcript | Out-Null }
}
$Out=Join-Path $Dl 'AKAH_C2_MARKET_VAULT_UPLOAD_PACKETS_RECOVERY_V3'
Write-Host ('UPLOAD_PACKET_FOLDER=' + $Out)
if ($RunExit -ne 0) { Write-Host ('AKAH_C2_RECOVERY_EXIT_CODE=' + $RunExit); exit $RunExit }
Write-Host 'AKAH_C2_RECOVERY_V3=PASS'
