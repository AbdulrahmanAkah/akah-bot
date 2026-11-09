# AKAH R54-P0R2 Result Reconciliation. Offline, read-only repository.
$ErrorActionPreference = 'Stop'
$Downloads = Join-Path $HOME 'Downloads'
$Repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$Package = Join-Path $Downloads 'AKAH_R54_P0R2_RESULT_RECONCILIATION_V1.zip'
$ExpectedSha256 = '59685E206B3D74E1115F9C766F8DF1322AA3F33E279E25CD63698C2B06E9F95B'
if (-not (Test-Path -LiteralPath $Repo -PathType Container)) { Write-Host 'R54_P0R2_ERROR=REPO_NOT_FOUND'; exit 2 }
if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) { Write-Host 'R54_P0R2_ERROR=PACKAGE_NOT_FOUND_IN_DOWNLOADS'; exit 3 }
$GotSha256 = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToUpperInvariant()
if ($GotSha256 -ne $ExpectedSha256) { Write-Host 'R54_P0R2_ERROR=PACKAGE_SHA256_MISMATCH'; exit 4 }
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Work = Join-Path $Downloads ('AKAH_R54_P0R2_WORK_' + $Stamp)
New-Item -ItemType Directory -Path $Work -Force | Out-Null
Expand-Archive -LiteralPath $Package -DestinationPath $Work -Force
$Worker = Join-Path $Work 'r54_p0r2_authority.py'
$Snapshot = Join-Path $Work 'PINNED_R54_P0R1_EVIDENCE.zip'
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
$Prefix = @()
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $cmd) { $Python = $cmd.Source; $Prefix = @('-3') }
    else {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $cmd) { Write-Host 'R54_P0R2_ERROR=PYTHON_NOT_FOUND'; exit 5 }
        $Python = $cmd.Source
    }
}
$Log = Join-Path $Work 'R54_P0R2_FULL_LOG.txt'
& $Python @Prefix $Worker --snapshot $Snapshot --repo $Repo --downloads $Downloads 2>&1 | Tee-Object -FilePath $Log
$ReturnCode = $LASTEXITCODE
if ($null -eq $ReturnCode) { $ReturnCode = 1 }
Write-Host "R54_P0R2_EXIT_CODE=$ReturnCode"
exit $ReturnCode
